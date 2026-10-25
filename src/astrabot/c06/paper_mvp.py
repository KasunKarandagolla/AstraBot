"""Small typed OpenBot-facing adapter for the offline C06 paper demonstration.

This module is a domain-tool adapter, not an agent runtime or execution writer.
All research decisions come from the existing C02/C03 contracts. Proposal
values are copied from an immutable research decision; the fake owner and
fake venue remain outside this adapter.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from astrabot.data.models import stable_id
from astrabot.research.models import Evaluation, ResearchDecision, ResearchSetup
from astrabot.universe.eligibility import SymbolData, scan_universe


class StrictToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ScanOpportunitiesInput(StrictToolModel):
    as_of: datetime


class EvaluateSymbolInput(StrictToolModel):
    symbol: str
    as_of: datetime


class EvaluateCandidatesInput(StrictToolModel):
    candidate_ids: tuple[str, ...]


class PreparePlanInput(StrictToolModel):
    candidate_id: str


class GetPlanStatusInput(StrictToolModel):
    plan_id: str
    as_of: datetime


class GetOperationsSummaryInput(StrictToolModel):
    lifecycle_id: str | None = None


class Opportunity(StrictToolModel):
    symbol: str
    state: str
    eligible: bool
    reasons: tuple[str, ...]
    shortlist_status: str


class ScanOpportunitiesOutput(StrictToolModel):
    as_of: datetime
    fixture_label: Literal["SYNTHETIC_FIXTURE"]
    symbols: tuple[str, ...]
    opportunities: tuple[Opportunity, ...]
    executable: Literal[False] = False


class EvaluateSymbolOutput(StrictToolModel):
    symbol: str
    as_of: datetime
    decision_ids: tuple[str, ...]
    research_decisions: tuple[str, ...]
    readiness: str
    source_snapshot_id: str
    executable: Literal[False] = False


class CandidateOutput(StrictToolModel):
    candidate_id: str | None
    decision: Literal["RESEARCH_CANDIDATE", "NO_TRADE"]
    research_status: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    reason_codes: tuple[str, ...] = ()
    executable: Literal[False] = False


class PaperPlan(StrictToolModel):
    """Immutable, non-executable proposal copied from one C03 candidate."""

    schema_version: Literal["c06.paper_plan.v1"] = "c06.paper_plan.v1"
    plan_id: str
    approval_nonce: str
    candidate_id: str
    candidate_hash: str
    setup_id: str
    source_snapshot_id: str
    trigger_event_id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    strategy_version: str
    anchor_ids: tuple[str, ...]
    entry_min: Decimal
    entry_max: Decimal
    proposed_quantity: Decimal
    modeled_loss_usdt: Decimal
    notional_bound_usdt: Decimal
    stop: Decimal
    targets: tuple[tuple[Decimal, Decimal], ...]
    cost_profile_hash: str
    management_policy_hash: str
    event_evidence_ids: tuple[str, ...]
    account_evidence_ids: tuple[str, ...]
    expires_at: datetime
    research_status: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    executable: Literal[False] = False
    immutable_hash: str

    def hash_payload(self) -> dict:
        return self.model_dump(mode="json", exclude={"immutable_hash"})

    def verify_hash(self) -> bool:
        canonical = json.dumps(self.hash_payload(), sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode()).hexdigest() == self.immutable_hash

    @model_validator(mode="after")
    def immutable_proposal(self):
        if self.entry_min > self.entry_max:
            raise ValueError("paper plan entry bounds are inverted")
        if not self.verify_hash():
            raise ValueError("paper plan hash mismatch")
        if not self.event_evidence_ids or not self.account_evidence_ids:
            raise ValueError("paper plan requires event and account evidence")
        return self


PlanState = Literal[
    "PROPOSED_RESEARCH_ONLY",
    "FAKE_OWNER_APPROVED",
    "OWNER_REJECTED",
    "EXPIRED",
    "CONSUMED",
    "SIMULATED_OPEN",
    "CLOSED_RECONCILED",
]


class PlanStatusOutput(StrictToolModel):
    plan_id: str
    plan_hash: str
    approval_nonce: str
    expires_at: datetime
    status: PlanState
    executable: Literal[False] = False


class JournalEvent(StrictToolModel):
    event_id: str
    occurred_at: datetime
    received_at: datetime
    actor: Literal["offline_test_driver", "fake_owner", "fake_supervisor"]
    event_type: str
    plan_id: str
    lifecycle_id: str
    details: tuple[tuple[str, str], ...] = ()


class OperationsSummaryOutput(StrictToolModel):
    lifecycle_id: str | None
    event_count: int = Field(ge=0)
    event_ids: tuple[str, ...]
    last_event_type: str | None
    event_digest: str


class PlanRegistry:
    """Harness-side status mirror. It is not exposed as an OpenBot tool."""

    _transitions = {
        "PROPOSED_RESEARCH_ONLY": {"FAKE_OWNER_APPROVED", "OWNER_REJECTED", "EXPIRED"},
        "FAKE_OWNER_APPROVED": {"CONSUMED", "EXPIRED"},
        "CONSUMED": {"SIMULATED_OPEN", "CLOSED_RECONCILED"},
        "SIMULATED_OPEN": {"SIMULATED_OPEN", "CLOSED_RECONCILED"},
        "OWNER_REJECTED": set(),
        "EXPIRED": set(),
        "CLOSED_RECONCILED": set(),
    }

    def __init__(self) -> None:
        self._plans: dict[str, PaperPlan] = {}
        self._states: dict[str, PlanState] = {}

    def add(self, plan: PaperPlan) -> None:
        existing = self._plans.get(plan.plan_id)
        if existing and existing != plan:
            raise ValueError("plan ID already exists with different immutable content")
        self._plans[plan.plan_id] = plan
        self._states.setdefault(plan.plan_id, "PROPOSED_RESEARCH_ONLY")

    def __len__(self) -> int:
        return len(self._plans)

    def observe_external_state(self, plan_id: str, status: PlanState) -> None:
        """Called by the offline owner/supervisor harness, never by the coordinator."""
        if plan_id not in self._plans:
            raise KeyError("unknown plan")
        prior = self._states[plan_id]
        if status != prior and status not in self._transitions[prior]:
            raise ValueError(f"invalid plan status transition: {prior} -> {status}")
        self._states[plan_id] = status

    def get(self, plan_id: str, as_of: datetime) -> PlanStatusOutput:
        plan = self._plans[plan_id]
        status = self._states[plan_id]
        if as_of >= plan.expires_at and status in {"PROPOSED_RESEARCH_ONLY", "FAKE_OWNER_APPROVED"}:
            status = "EXPIRED"
        return PlanStatusOutput(plan_id=plan.plan_id, plan_hash=plan.immutable_hash,
            approval_nonce=plan.approval_nonce, expires_at=plan.expires_at,
            status=status)


class EventJournal:
    """Append-only deterministic event stream for one offline demonstration."""

    def __init__(self) -> None:
        self._events: list[JournalEvent] = []
        self.available = True

    @property
    def events(self) -> tuple[JournalEvent, ...]:
        return tuple(self._events)

    def append(self, *, occurred_at: datetime, actor: str, event_type: str,
               plan_id: str, lifecycle_id: str, details: dict[str, object] | None = None) -> JournalEvent:
        if not self.available:
            raise RuntimeError("journal role unavailable")
        received_at = occurred_at
        if self._events and (occurred_at < self._events[-1].occurred_at
                             or received_at < self._events[-1].received_at):
            raise ValueError("journal timestamps must be monotonic")
        ordered_details = tuple(sorted((str(k), str(v)) for k, v in (details or {}).items()))
        event_body = {"occurred_at": occurred_at.isoformat(), "received_at": received_at.isoformat(),
            "actor": actor, "event_type": event_type, "plan_id": plan_id,
            "lifecycle_id": lifecycle_id, "details": ordered_details,
            "sequence": len(self._events)}
        event_id = stable_id("c06.machine_event.v1", event_body)
        event = JournalEvent(event_id=event_id, occurred_at=occurred_at, received_at=received_at,
            actor=actor, event_type=event_type, plan_id=plan_id, lifecycle_id=lifecycle_id,
            details=ordered_details)
        self._events.append(event)
        return event

    def summary(self, lifecycle_id: str | None = None) -> OperationsSummaryOutput:
        if not self.available:
            raise RuntimeError("journal role unavailable")
        selected = tuple(e for e in self._events if lifecycle_id is None or e.lifecycle_id == lifecycle_id)
        ids = tuple(e.event_id for e in selected)
        return OperationsSummaryOutput(lifecycle_id=lifecycle_id, event_count=len(selected),
            event_ids=ids, last_event_type=selected[-1].event_type if selected else None,
            event_digest=stable_id("c06.journal_summary.v1", ids))


class C06ToolGateway:
    """Expose exactly six typed, deterministic, read-only/proposal tools."""

    tool_names = (
        "scan_opportunities", "evaluate_symbol", "evaluate_candidates", "prepare_plan",
        "get_plan_status", "get_operations_summary",
    )

    _input_models = {
        "scan_opportunities": ScanOpportunitiesInput,
        "evaluate_symbol": EvaluateSymbolInput,
        "evaluate_candidates": EvaluateCandidatesInput,
        "prepare_plan": PreparePlanInput,
        "get_plan_status": GetPlanStatusInput,
        "get_operations_summary": GetOperationsSummaryInput,
    }

    def __init__(self, *, symbol: str, data: SymbolData, scan_notional_usdt: Decimal,
                 evaluation: Evaluation, candidate: ResearchDecision | None,
                 setup: ResearchSetup | None, plans: PlanRegistry, journal: EventJournal) -> None:
        self._symbol = symbol
        self._data = data
        self._scan_notional_usdt = scan_notional_usdt
        self._evaluation = evaluation
        emitted_at = evaluation.emitted[0].as_of if evaluation.emitted else None
        self._as_of = candidate.as_of if candidate else emitted_at
        self._candidate = candidate
        self._setup = setup
        self._plans = plans
        self._journal = journal

    def call(self, name: str, payload: dict[str, object]):
        if name not in self._input_models:
            raise ValueError("unknown OpenBot tool")
        typed = self._input_models[name].model_validate(payload)
        return getattr(self, name)(typed)

    def scan_opportunities(self, request: ScanOpportunitiesInput) -> ScanOpportunitiesOutput:
        if request.as_of != self._as_of:
            raise ValueError("as_of must match the immutable offline evaluation snapshot")
        result = scan_universe({self._symbol: self._data}, request.as_of, self._scan_notional_usdt)
        return ScanOpportunitiesOutput(as_of=request.as_of, fixture_label="SYNTHETIC_FIXTURE",
            symbols=result.shortlist, opportunities=tuple(Opportunity(symbol=o.symbol, state=o.state,
                eligible=o.eligible, reasons=o.reasons, shortlist_status=o.shortlist_status)
                for o in result.considered))

    def evaluate_symbol(self, request: EvaluateSymbolInput) -> EvaluateSymbolOutput:
        if request.symbol != self._symbol:
            raise ValueError("symbol is outside this offline fixture")
        if request.as_of != self._as_of:
            raise ValueError("as_of must match the immutable offline evaluation snapshot")
        decisions = self._evaluation.emitted
        representative = self._candidate or (decisions[0] if decisions else None)
        return EvaluateSymbolOutput(symbol=request.symbol, as_of=request.as_of,
            decision_ids=tuple(d.decision_id for d in decisions),
            research_decisions=tuple(d.decision for d in decisions),
            readiness=representative.readiness if representative else "UNAVAILABLE",
            source_snapshot_id=representative.source_snapshot_id if representative else "no-evaluation")

    def evaluate_candidates(self, request: EvaluateCandidatesInput) -> CandidateOutput:
        if self._candidate is None or self._candidate.decision_id not in request.candidate_ids:
            decision = next((d for d in self._evaluation.emitted if d.decision_id in request.candidate_ids), None)
            if decision is None or decision.decision != "RESEARCH_CANDIDATE":
                reason_codes = decision.rejection_reason_codes if decision else ("CANDIDATE_NOT_FOUND",)
                return CandidateOutput(candidate_id=decision.decision_id if decision else None,
                    decision="NO_TRADE", reason_codes=reason_codes)
            candidate = decision
        else:
            candidate = self._candidate
        return CandidateOutput(candidate_id=candidate.decision_id, decision=candidate.decision,
            reason_codes=candidate.rejection_reason_codes)

    def prepare_plan(self, request: PreparePlanInput) -> PaperPlan:
        candidate = self._candidate
        setup = self._setup
        if not candidate or not setup or candidate.decision_id != request.candidate_id:
            raise ValueError("candidate cannot produce a paper plan")
        if candidate.decision != "RESEARCH_CANDIDATE" or candidate.research_status != "RESEARCH_ONLY" or candidate.executable:
            raise ValueError("only a C03 research-only candidate can be proposed")
        if not candidate.geometry or not candidate.economics or candidate.entry_min is None or candidate.entry_max is None:
            raise ValueError("candidate is missing bounded geometry or economics")
        event = next((d for d in candidate.dependencies if d.name == "VERIFIED_EVENT_CLEARANCE"), None)
        account = next((d for d in candidate.dependencies if d.name == "RESEARCH_ACCOUNT"), None)
        if not event or event.readiness != "READY" or not event.source_ids:
            raise ValueError("verified event evidence missing")
        if not account or account.readiness != "READY" or not account.source_ids:
            raise ValueError("synthetic research account evidence missing")
        anchors = tuple(a.anchor_id for a in setup.snapshot.anchors)
        if not anchors or tuple(candidate.original_anchor_ids[:len(anchors)]) != anchors:
            raise ValueError("candidate and frozen setup anchors do not match")
        quantity = candidate.economics.proposed_quantity
        payload = {
            "schema_version": "c06.paper_plan.v1",
            "plan_id": stable_id("c06.paper_plan", candidate.decision_id),
            "approval_nonce": stable_id("c06.fake_owner_nonce", candidate.decision_id),
            "candidate_id": candidate.decision_id,
            "candidate_hash": stable_id("c06.candidate_payload", candidate.model_dump(mode="json")),
            "setup_id": candidate.setup_id,
            "source_snapshot_id": candidate.source_snapshot_id,
            "trigger_event_id": candidate.trigger_event_id,
            "symbol": candidate.symbol,
            "side": candidate.side,
            "strategy_version": candidate.strategy_version,
            "anchor_ids": anchors,
            "entry_min": candidate.entry_min,
            "entry_max": candidate.entry_max,
            "proposed_quantity": quantity,
            "modeled_loss_usdt": candidate.economics.proposed_modeled_loss_usdt,
            "notional_bound_usdt": candidate.entry_max * quantity,
            "stop": candidate.geometry.original_stop,
            "targets": tuple((t.price, t.fraction) for t in candidate.geometry.targets),
            "cost_profile_hash": candidate.cost_profile_hash,
            "management_policy_hash": candidate.management_policy_hash,
            "event_evidence_ids": event.source_ids,
            "account_evidence_ids": account.source_ids,
            "expires_at": min(candidate.expires_at, setup.snapshot.expires_at),
            "research_status": "RESEARCH_ONLY",
            "executable": False,
        }
        normalized_payload = PaperPlan.model_construct(**payload, immutable_hash="").hash_payload()
        canonical = json.dumps(normalized_payload, sort_keys=True, separators=(",", ":"))
        plan = PaperPlan(**payload, immutable_hash=sha256(canonical.encode()).hexdigest())
        self._plans.add(plan)
        return plan

    def get_plan_status(self, request: GetPlanStatusInput) -> PlanStatusOutput:
        return self._plans.get(request.plan_id, request.as_of)

    def get_operations_summary(self, request: GetOperationsSummaryInput) -> OperationsSummaryOutput:
        return self._journal.summary(request.lifecycle_id)
