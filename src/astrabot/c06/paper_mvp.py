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
import sqlite3
from contextlib import closing
from pathlib import Path
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

_PLAN_STATES = frozenset({
    "PROPOSED_RESEARCH_ONLY", "FAKE_OWNER_APPROVED", "OWNER_REJECTED",
    "EXPIRED", "CONSUMED", "SIMULATED_OPEN", "CLOSED_RECONCILED",
})
_PLAN_TRANSITIONS = {
    "PROPOSED_RESEARCH_ONLY": {"FAKE_OWNER_APPROVED", "OWNER_REJECTED", "EXPIRED"},
    "FAKE_OWNER_APPROVED": {"CONSUMED", "EXPIRED"},
    "CONSUMED": {"SIMULATED_OPEN", "CLOSED_RECONCILED"},
    "SIMULATED_OPEN": {"SIMULATED_OPEN", "CLOSED_RECONCILED"},
    "OWNER_REJECTED": set(), "EXPIRED": set(), "CLOSED_RECONCILED": set(),
}


class _C06SQLite:
    """Shared, local SQLite schema for optional durable C06 plan/journal state."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS paper_plans (
                    plan_id TEXT PRIMARY KEY,
                    lifecycle_id TEXT NOT NULL UNIQUE,
                    immutable_hash TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_plan_transitions (
                    plan_id TEXT NOT NULL REFERENCES paper_plans(plan_id),
                    sequence INTEGER NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    PRIMARY KEY(plan_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS machine_events (
                    sequence INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    plan_id TEXT NOT NULL REFERENCES paper_plans(plan_id),
                    lifecycle_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS paper_plan_identity_is_immutable
                BEFORE UPDATE OF plan_id, lifecycle_id, immutable_hash, payload, expires_at
                ON paper_plans BEGIN SELECT RAISE(ABORT, 'immutable paper plan'); END;
                CREATE TRIGGER IF NOT EXISTS paper_plan_cannot_be_deleted
                BEFORE DELETE ON paper_plans BEGIN SELECT RAISE(ABORT, 'paper plans are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS plan_transitions_are_append_only_update
                BEFORE UPDATE ON paper_plan_transitions BEGIN SELECT RAISE(ABORT, 'plan transitions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS plan_transitions_are_append_only_delete
                BEFORE DELETE ON paper_plan_transitions BEGIN SELECT RAISE(ABORT, 'plan transitions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS machine_events_are_append_only_update
                BEFORE UPDATE ON machine_events BEGIN SELECT RAISE(ABORT, 'machine events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS machine_events_are_append_only_delete
                BEFORE DELETE ON machine_events BEGIN SELECT RAISE(ABORT, 'machine events are append-only'); END;
            """)
        self.verify_integrity()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def verify_integrity(self) -> None:
        with closing(self.connect()) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("C06 durable state failed SQLite integrity check")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("C06 durable state has broken foreign-key references")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


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
    correlation_id: str
    details: tuple[tuple[str, str], ...] = ()


class OperationsSummaryOutput(StrictToolModel):
    lifecycle_id: str | None
    event_count: int = Field(ge=0)
    event_ids: tuple[str, ...]
    last_event_type: str | None
    event_digest: str


class PlanRegistry:
    """Harness-side status mirror. It is not exposed as an OpenBot tool."""
    _transitions = _PLAN_TRANSITIONS

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._plans: dict[str, PaperPlan] = {}
        self._states: dict[str, PlanState] = {}
        self._store = _C06SQLite(storage_path) if storage_path is not None else None
        if self._store:
            self._restore()

    def _restore(self) -> None:
        assert self._store
        with closing(self._store.connect()) as db:
            rows = db.execute("SELECT plan_id, lifecycle_id, immutable_hash, payload, expires_at, status "
                              "FROM paper_plans ORDER BY plan_id").fetchall()
            for plan_id, lifecycle_id, plan_hash, payload, expires_at, status in rows:
                try:
                    plan = PaperPlan.model_validate_json(payload)
                except Exception as exc:
                    raise ValueError("corrupted persisted paper plan") from exc
                expected_lifecycle = stable_id("c06.fake_lifecycle", plan_id)
                if (plan.plan_id != plan_id or plan.immutable_hash != plan_hash or not plan.verify_hash()
                    or plan.expires_at.isoformat() != expires_at or lifecycle_id != expected_lifecycle
                    or status not in _PLAN_STATES):
                    raise ValueError("inconsistent persisted paper plan identity, hash, expiry or status")
                history = db.execute("SELECT sequence, from_status, to_status FROM paper_plan_transitions "
                                     "WHERE plan_id=? ORDER BY sequence", (plan_id,)).fetchall()
                if not history or history[0] != (0, None, "PROPOSED_RESEARCH_ONLY"):
                    raise ValueError("persisted paper plan is missing its initial status transition")
                prior_status = None
                for expected_sequence, (sequence, from_status, to_status) in enumerate(history):
                    if sequence != expected_sequence or to_status not in _PLAN_STATES:
                        raise ValueError("corrupted persisted plan transition sequence")
                    if expected_sequence == 0:
                        if from_status is not None:
                            raise ValueError("corrupted initial paper plan status")
                    elif from_status != prior_status or to_status not in _PLAN_TRANSITIONS[prior_status]:
                        raise ValueError("invalid persisted paper plan status transition")
                    prior_status = to_status
                if prior_status != status:
                    raise ValueError("persisted paper plan status disagrees with transition history")
                self._plans[plan_id] = plan
                self._states[plan_id] = status

    def add(self, plan: PaperPlan, *, lifecycle_id: str | None = None,
            occurred_at: datetime | None = None) -> None:
        if not plan.verify_hash():
            raise ValueError("paper plan hash mismatch")
        lifecycle_id = lifecycle_id or stable_id("c06.fake_lifecycle", plan.plan_id)
        if lifecycle_id != stable_id("c06.fake_lifecycle", plan.plan_id):
            raise ValueError("paper plan lifecycle ID is not deterministic")
        existing = self._plans.get(plan.plan_id)
        if existing and existing != plan:
            raise ValueError("plan ID already exists with different immutable content")
        if existing and self._states[plan.plan_id] != "PROPOSED_RESEARCH_ONLY":
            raise ValueError("expired, rejected, approved or consumed paper plan cannot be reused")
        if self._store:
            payload = _canonical(plan.model_dump(mode="json"))
            occurred_at = occurred_at or datetime.now().astimezone()
            with closing(self._store.connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT immutable_hash, payload, lifecycle_id, status FROM paper_plans "
                                 "WHERE plan_id=?", (plan.plan_id,)).fetchone()
                if row:
                    plan_hash, stored_payload, stored_lifecycle, status = row
                    if (plan_hash != plan.immutable_hash or stored_payload != payload
                        or stored_lifecycle != lifecycle_id):
                        raise ValueError("plan ID already exists with different immutable content")
                    if status != "PROPOSED_RESEARCH_ONLY":
                        raise ValueError("expired, rejected, approved or consumed paper plan cannot be reused")
                else:
                    now = occurred_at.isoformat()
                    db.execute("INSERT INTO paper_plans VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (plan.plan_id, lifecycle_id, plan.immutable_hash, payload,
                         plan.expires_at.isoformat(), "PROPOSED_RESEARCH_ONLY", now))
                    db.execute("INSERT INTO paper_plan_transitions VALUES(?, 0, NULL, ?, ?)",
                        (plan.plan_id, "PROPOSED_RESEARCH_ONLY", now))
                    event = EventJournal._new_event(occurred_at=occurred_at,
                        actor="offline_test_driver", event_type="PAPER_PLAN_PERSISTED",
                        plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
                        details={"plan_hash": plan.immutable_hash,
                            "status": "PROPOSED_RESEARCH_ONLY"})
                    EventJournal._append_sqlite(db, event)
        self._plans[plan.plan_id] = plan
        self._states.setdefault(plan.plan_id, "PROPOSED_RESEARCH_ONLY")

    def __len__(self) -> int:
        if self._store:
            with closing(self._store.connect()) as db:
                return db.execute("SELECT COUNT(*) FROM paper_plans").fetchone()[0]
        return len(self._plans)

    def observe_external_state(self, plan_id: str, status: PlanState, *,
                               occurred_at: datetime | None = None) -> None:
        """Called by the offline owner/supervisor harness, never by the coordinator."""
        if plan_id not in self._plans:
            raise KeyError("unknown plan")
        if status not in _PLAN_STATES:
            raise ValueError("unknown paper plan status")
        prior = self._states[plan_id]
        if status != prior and status not in self._transitions[prior]:
            raise ValueError(f"invalid plan status transition: {prior} -> {status}")
        if self._store and status != prior:
            with closing(self._store.connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT status, lifecycle_id FROM paper_plans WHERE plan_id=?",
                                  (plan_id,)).fetchone()
                if not row:
                    raise KeyError("unknown persisted paper plan")
                if row[0] != prior:
                    raise ValueError("persisted plan status changed outside this registry; reconcile first")
                if occurred_at is None:
                    last_event = db.execute("SELECT occurred_at FROM machine_events "
                                            "ORDER BY sequence DESC LIMIT 1").fetchone()
                    occurred_at = datetime.fromisoformat(last_event[0]) if last_event else datetime.now().astimezone()
                now = occurred_at.isoformat()
                sequence = db.execute("SELECT COALESCE(MAX(sequence), -1)+1 FROM paper_plan_transitions "
                                      "WHERE plan_id=?", (plan_id,)).fetchone()[0]
                db.execute("INSERT INTO paper_plan_transitions VALUES(?, ?, ?, ?, ?)",
                    (plan_id, sequence, prior, status, now))
                db.execute("UPDATE paper_plans SET status=?, updated_at=? WHERE plan_id=?",
                    (status, now, plan_id))
                event = EventJournal._new_event(occurred_at=occurred_at,
                    actor="fake_supervisor", event_type="PLAN_STATUS_TRANSITION",
                    plan_id=plan_id, lifecycle_id=row[1],
                    details={"from_status": prior, "to_status": status})
                EventJournal._append_sqlite(db, event)
        self._states[plan_id] = status

    def get(self, plan_id: str, as_of: datetime) -> PlanStatusOutput:
        plan = self._plans[plan_id]
        status = self._states[plan_id]
        if as_of >= plan.expires_at and status in {"PROPOSED_RESEARCH_ONLY", "FAKE_OWNER_APPROVED"}:
            status = "EXPIRED"
            self.observe_external_state(plan_id, status, occurred_at=as_of)
        return PlanStatusOutput(plan_id=plan.plan_id, plan_hash=plan.immutable_hash,
            approval_nonce=plan.approval_nonce, expires_at=plan.expires_at,
            status=status)


class EventJournal:
    """Append-only deterministic event stream with optional SQLite persistence."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._events: list[JournalEvent] = []
        self.available = True
        self._store = _C06SQLite(storage_path) if storage_path is not None else None
        if self._store:
            self._restore()

    @classmethod
    def _new_event(cls, *, occurred_at: datetime, actor: str, event_type: str,
                   plan_id: str, lifecycle_id: str, details: dict[str, object] | None = None,
                   received_at: datetime | None = None,
                   correlation_id: str | None = None) -> JournalEvent:
        received_at = received_at or occurred_at
        ordered_details = tuple(sorted((str(k), str(v)) for k, v in (details or {}).items()))
        draft = JournalEvent(event_id="", occurred_at=occurred_at, received_at=received_at,
            actor=actor, event_type=event_type, plan_id=plan_id, lifecycle_id=lifecycle_id,
            correlation_id=correlation_id or lifecycle_id, details=ordered_details)
        body = draft.model_dump(mode="json")
        body.pop("event_id")
        return draft.model_copy(update={"event_id": cls._event_id(body)})

    @staticmethod
    def _event_id(body: dict[str, object]) -> str:
        return stable_id("c06.machine_event.v2", body)

    @staticmethod
    def _record_hash(event: JournalEvent, previous_hash: str) -> str:
        return sha256(_canonical({"event": event.model_dump(mode="json"),
                                  "previous_hash": previous_hash}).encode()).hexdigest()

    @classmethod
    def _append_sqlite(cls, db: sqlite3.Connection, event: JournalEvent) -> bool:
        serialized_details = _canonical(event.details)
        existing = db.execute("SELECT event_id, occurred_at, received_at, actor, event_type, "
            "plan_id, lifecycle_id, correlation_id, details_json FROM machine_events WHERE event_id=?",
            (event.event_id,)).fetchone()
        expected = (event.event_id, event.occurred_at.isoformat(), event.received_at.isoformat(),
            event.actor, event.event_type, event.plan_id, event.lifecycle_id,
            event.correlation_id, serialized_details)
        if existing:
            if existing != expected:
                raise ValueError("event ID already exists with different content")
            return False
        plan = db.execute("SELECT lifecycle_id FROM paper_plans WHERE plan_id=?",
                          (event.plan_id,)).fetchone()
        if not plan or plan[0] != event.lifecycle_id:
            raise ValueError("machine event must correlate to a persisted plan lifecycle")
        last = db.execute("SELECT sequence, occurred_at, received_at, record_hash "
                          "FROM machine_events ORDER BY sequence DESC LIMIT 1").fetchone()
        if last and (event.occurred_at < datetime.fromisoformat(last[1])
                     or event.received_at < datetime.fromisoformat(last[2])):
            raise ValueError("journal timestamps must be monotonic")
        sequence = last[0] + 1 if last else 1
        previous_hash = last[3] if last else "0" * 64
        db.execute("INSERT INTO machine_events VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sequence, event.event_id, event.occurred_at.isoformat(), event.received_at.isoformat(),
             event.actor, event.event_type, event.plan_id, event.lifecycle_id,
             event.correlation_id, serialized_details, previous_hash,
             cls._record_hash(event, previous_hash)))
        return True

    def _restore(self) -> None:
        assert self._store
        with closing(self._store.connect()) as db:
            rows = db.execute("SELECT sequence, event_id, occurred_at, received_at, actor, event_type, "
                "plan_id, lifecycle_id, correlation_id, details_json, previous_hash, record_hash "
                "FROM machine_events ORDER BY sequence").fetchall()
            previous_hash = "0" * 64
            previous_occurred = previous_received = None
            for expected_sequence, row in enumerate(rows, start=1):
                (sequence, event_id, occurred_at, received_at, actor, event_type, plan_id,
                 lifecycle_id, correlation_id, details_json, stored_previous, stored_hash) = row
                if sequence != expected_sequence or stored_previous != previous_hash:
                    raise ValueError("persisted C06 event journal has a sequence or hash-chain gap")
                try:
                    details = tuple(tuple(item) for item in json.loads(details_json))
                    event = JournalEvent(event_id=event_id,
                        occurred_at=datetime.fromisoformat(occurred_at),
                        received_at=datetime.fromisoformat(received_at), actor=actor,
                        event_type=event_type, plan_id=plan_id, lifecycle_id=lifecycle_id,
                        correlation_id=correlation_id, details=details)
                except Exception as exc:
                    raise ValueError("corrupted persisted C06 machine event") from exc
                body = event.model_dump(mode="json")
                body.pop("event_id")
                if event_id != self._event_id(body):
                    raise ValueError("persisted C06 machine event ID mismatch")
                if stored_hash != self._record_hash(event, previous_hash):
                    raise ValueError("persisted C06 event journal hash mismatch")
                if ((previous_occurred and event.occurred_at < previous_occurred)
                    or (previous_received and event.received_at < previous_received)):
                    raise ValueError("persisted C06 event journal timestamps are not monotonic")
                plan = db.execute("SELECT lifecycle_id FROM paper_plans WHERE plan_id=?", (plan_id,)).fetchone()
                if not plan or plan[0] != lifecycle_id or correlation_id not in {plan_id, lifecycle_id}:
                    raise ValueError("persisted C06 event correlation does not match its plan")
                self._events.append(event)
                previous_hash = stored_hash
                previous_occurred, previous_received = event.occurred_at, event.received_at

    @property
    def events(self) -> tuple[JournalEvent, ...]:
        if self._store:
            self._events = []
            self._restore()
        return tuple(self._events)

    def append(self, *, occurred_at: datetime, actor: str, event_type: str,
               plan_id: str, lifecycle_id: str, details: dict[str, object] | None = None,
               received_at: datetime | None = None, correlation_id: str | None = None) -> JournalEvent:
        if not self.available:
            raise RuntimeError("journal role unavailable")
        received_at = received_at or occurred_at
        ordered_details = tuple(sorted((str(k), str(v)) for k, v in (details or {}).items()))
        correlation_id = correlation_id or lifecycle_id
        event = self._new_event(occurred_at=occurred_at, received_at=received_at,
            actor=actor, event_type=event_type, plan_id=plan_id, lifecycle_id=lifecycle_id,
            correlation_id=correlation_id, details=dict(ordered_details))
        if self._store:
            with closing(self._store.connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                inserted = self._append_sqlite(db, event)
                if inserted:
                    self._events.append(event)
            return event
        if self._events and (occurred_at < self._events[-1].occurred_at
                             or received_at < self._events[-1].received_at):
            raise ValueError("journal timestamps must be monotonic")
        self._events.append(event)
        return event

    def summary(self, lifecycle_id: str | None = None) -> OperationsSummaryOutput:
        if not self.available:
            raise RuntimeError("journal role unavailable")
        selected = tuple(e for e in self.events if lifecycle_id is None or e.lifecycle_id == lifecycle_id)
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
        self._plans.add(plan, occurred_at=self._as_of)
        return plan

    def get_plan_status(self, request: GetPlanStatusInput) -> PlanStatusOutput:
        return self._plans.get(request.plan_id, request.as_of)

    def get_operations_summary(self, request: GetOperationsSummaryInput) -> OperationsSummaryOutput:
        return self._journal.summary(request.lifecycle_id)
