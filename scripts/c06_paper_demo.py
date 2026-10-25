#!/usr/bin/env python3
"""Reproducible, fixture-only C06 OpenBot-facing paper MVP demonstration."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal as D
import json
from pathlib import Path
import sys
import tempfile
from contextlib import nullcontext
import argparse
from datetime import timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from pydantic import ValidationError

from astrabot.c06.paper_mvp import C06ToolGateway, EventJournal, PlanRegistry
from astrabot.contracts import OwnerIdentity, SetupSnapshotV15, TradeAuthorizationV15
from astrabot.data.models import stable_id
from astrabot.research.demo import START, account, candle, costs, market, roll_market
from astrabot.research.engine import evaluate
from astrabot.research.replay import synthetic_eligible_panel
from c01_fake import FakeClock, FakeOwner, FakeVenue


FIXTURE_QUANTITY = D("10")  # Existing C03 synthetic pipeline fixture input.
FIXTURE_EQUITY = D("10000")  # Existing C01 fake-owner fixture default.


class DeterministicOfflineCoordinator:
    """Test driver for the six tool calls; it cannot approve or execute."""

    def __init__(self, gateway: C06ToolGateway) -> None:
        self._gateway = gateway
        self.available = True

    def call(self, name: str, payload: dict[str, object]):
        if not self.available:
            raise RuntimeError("offline coordinator unavailable")
        return self._gateway.call(name, payload)


def build_fixture(*, event_evidence: bool = True, market_evidence: bool = True,
                  storage_path: Path | str | None = None):
    """Use the existing C04 synthetic panel and the same causal C03 fixture steps."""
    panel = synthetic_eligible_panel()
    symbol = "ALTUSDT"
    data = panel.symbols[symbol]
    formed_at = START + timedelta(seconds=5)
    confirmed_at = START + timedelta(minutes=5, seconds=5)

    # C04's synthetic_eligible_panel uses these exact C03 steps so this driver
    # can retain the C01 SetupSnapshotV15 anchors alongside the emitted decision.
    formation_data = market(formed_at)
    formation = evaluate(formation_data, symbol=symbol,
        instrument_id=formation_data.metadata.instrument_id, as_of=formed_at,
        account=account(formed_at), profile=costs(), requested_quantity=FIXTURE_QUANTITY,
        strategies=("T1",), sides=("LONG",))
    confirmation_bar = candle(START, open="99.9", high="100.5", low="99.8", close="100.4")
    snapshot = roll_market(formation_data, confirmed_at, extra=(confirmation_bar,))
    if not event_evidence:
        snapshot = snapshot.model_copy(update={"event_clearance": None})
        data = data.model_copy(update={"event_clearance": None})
    if not market_evidence:
        snapshot = snapshot.model_copy(update={"metadata": None, "depth": None})
        data = data.model_copy(update={"metadata": None, "depth": None})
    result = evaluate(snapshot, symbol=symbol,
        instrument_id=formation_data.metadata.instrument_id, as_of=confirmed_at,
        account=account(confirmed_at), profile=costs(), state=formation.state,
        requested_quantity=FIXTURE_QUANTITY, strategies=("T1",), sides=("LONG",))
    candidate = next((d for d in result.emitted if d.decision == "RESEARCH_CANDIDATE"), None)
    setup = next((s for s in result.state.setups
        if candidate and s.snapshot.setup_id == candidate.setup_id), None)
    scan_notional = FIXTURE_QUANTITY * data.depth.asks[0].price if data.depth else D("1")
    plans, journal = PlanRegistry(storage_path), EventJournal(storage_path)
    gateway = C06ToolGateway(symbol=symbol, data=data, scan_notional_usdt=scan_notional,
        evaluation=result, candidate=candidate, setup=setup, plans=plans, journal=journal)
    return {
        "panel": panel,
        "data": data,
        "gateway": gateway,
        "plans": plans,
        "journal": journal,
        "evaluation": result,
        "candidate": candidate,
        "setup": setup,
        "formed_at": formed_at,
        "as_of": confirmed_at,
    }


def make_fake_authorization(plan, candidate, setup, approved_at: datetime):
    if not plan.verify_hash():
        raise ValueError("owner cannot approve a changed immutable paper plan")
    if not candidate or not candidate.economics or not candidate.trigger_submit_deadline:
        raise ValueError("C03 candidate lacks bounded execution terms")
    if not setup:
        raise ValueError("C03 setup evidence missing")
    # C03 marks the research setup CONSUMED after emitting a decision. C01 uses
    # a fresh fake execution lifecycle with those same frozen anchors/terms.
    fake_setup = SetupSnapshotV15.model_validate_json(
        setup.snapshot.model_copy(update={"state": "CONFIRMED"}).model_dump_json())
    trigger_at = candidate.earliest_hypothetical_entry_at
    deadline_ms = int((candidate.trigger_submit_deadline - trigger_at).total_seconds() * 1000)
    if deadline_ms <= 0:
        raise ValueError("candidate trigger deadline elapsed")
    auth = TradeAuthorizationV15(
        plan_id=plan.plan_id,
        setup_id=fake_setup.setup_id,
        lifecycle_id=stable_id("c06.fake_lifecycle", plan.plan_id),
        one_use_nonce=plan.approval_nonce,
        approved_immutable_hash="pending",
        owner=OwnerIdentity(owner_ref="fake-owner", authentication_evidence_ref="fake-auth",
            mfa_evidence_ref="fake-mfa"),
        mode="POST_TRIGGER_APPROVAL",
        symbol=plan.symbol,
        side=plan.side,
        strategy_version=plan.strategy_version,
        strategy_policy_hash=fake_setup.strategy_policy_hash,
        trigger_policy_hash=stable_id("c06.fake_trigger_policy.v1", candidate.trigger_event_id),
        management_policy_hash=plan.management_policy_hash,
        frozen_anchor_ids=plan.anchor_ids,
        entry_min=plan.entry_min,
        entry_max=plan.entry_max,
        quantity_max=plan.proposed_quantity,
        notional_max=plan.notional_bound_usdt,
        leverage_max=D("2"),  # Existing C01 fake-owner contract ceiling.
        approved_max_risk_usdt=plan.modeled_loss_usdt,
        cost_profile_hash=plan.cost_profile_hash,
        stop_cost_per_unit=candidate.economics.loss_cost_per_unit,
        target_cost_per_unit=candidate.economics.win_cost_per_unit,
        geometry=candidate.geometry,
        readiness_ref=plan.immutable_hash,
        event_veto_ref=plan.event_evidence_ids[0],
        risk_veto_ref=plan.account_evidence_ids[0],
        approved_at=approved_at,
        approval_request_expires_at=plan.expires_at,
        armed_expires_at=plan.expires_at,
        setup_expires_at=fake_setup.expires_at,
        data_event_expires_at=plan.expires_at,
        trigger_submit_deadline_ms=deadline_ms,
        state="APPROVED_ARMED",
    )
    auth = auth.model_copy(update={"approved_immutable_hash": auth.immutable_hash()})
    if auth.readiness_ref != plan.immutable_hash or auth.one_use_nonce != plan.approval_nonce:
        raise ValueError("fake authorization does not bind the immutable plan and nonce")
    return fake_setup, auth


def _new_owner(root: Path, clock: FakeClock):
    venue = FakeVenue(root / "venue.sqlite", clock)
    owner = FakeOwner(root / "owner.sqlite", venue, clock, equity=FIXTURE_EQUITY)
    if not owner.reconnect():
        raise RuntimeError("fake owner failed initial reconciliation")
    return owner, venue


class FixtureOwnerDecision:
    """Explicit fixture-only owner boundary; never registered as an agent tool."""

    def __init__(self, *, plan, candidate, setup, owner: FakeOwner, clock: FakeClock,
                 plans: PlanRegistry, journal: EventJournal, lifecycle_id: str):
        self.plan, self.candidate, self.setup = plan, candidate, setup
        self.owner, self.clock, self.plans, self.journal = owner, clock, plans, journal
        self.lifecycle_id = lifecycle_id

    def approve(self):
        if self.clock.now >= self.plan.expires_at:
            raise ValueError("expired proposal cannot be approved")
        if self.plans._states.get(self.plan.plan_id) != "PROPOSED_RESEARCH_ONLY":
            raise ValueError("only a proposed plan can receive fixture-owner approval")
        fake_setup, auth = make_fake_authorization(self.plan, self.candidate, self.setup, self.clock.now)
        bound = (
            auth.plan_id == self.plan.plan_id
            and auth.one_use_nonce == self.plan.approval_nonce
            and auth.readiness_ref == self.plan.immutable_hash
            and auth.setup_id == self.plan.setup_id
            and auth.symbol == self.plan.symbol and auth.side == self.plan.side
            and auth.strategy_version == self.plan.strategy_version
            and auth.frozen_anchor_ids == self.plan.anchor_ids
            and auth.entry_min == self.plan.entry_min and auth.entry_max == self.plan.entry_max
            and auth.quantity_max == self.plan.proposed_quantity
            and auth.notional_max == self.plan.notional_bound_usdt
            and auth.approved_max_risk_usdt == self.plan.modeled_loss_usdt
            and auth.cost_profile_hash == self.plan.cost_profile_hash
            and auth.geometry == self.candidate.geometry
            and auth.stop_cost_per_unit == self.candidate.economics.loss_cost_per_unit
            and auth.target_cost_per_unit == self.candidate.economics.win_cost_per_unit
            and auth.trigger_policy_hash == stable_id(
                "c06.fake_trigger_policy.v1", self.candidate.trigger_event_id)
            and auth.strategy_policy_hash == fake_setup.strategy_policy_hash
            and auth.event_veto_ref in self.plan.event_evidence_ids
            and auth.risk_veto_ref in self.plan.account_evidence_ids
            and auth.leverage_max == D("2")
            and auth.management_policy_hash == self.plan.management_policy_hash
            and auth.approval_request_expires_at == self.plan.expires_at
            and auth.armed_expires_at == self.plan.expires_at
            and auth.data_event_expires_at == self.plan.expires_at
            and auth.setup_expires_at == fake_setup.expires_at
        )
        if not bound:
            raise ValueError("fixture-owner approval does not bind the exact persisted proposal")
        self.owner.register_approval(auth, fake_setup)
        # The fake owner ledger and C06 proposal store are separate SQLite files.
        # A crash here is reconciled from the authoritative fake-owner ledger.
        self.plans.observe_external_state(self.plan.plan_id, "FAKE_OWNER_APPROVED",
            occurred_at=self.clock.now)
        self.journal.append(occurred_at=self.clock.now, actor="fake_owner",
            event_type="FAKE_OWNER_APPROVED", plan_id=self.plan.plan_id,
            lifecycle_id=self.lifecycle_id,
            details={"authorization_hash": auth.approved_immutable_hash,
                "proposal_hash": self.plan.immutable_hash, "nonce": auth.one_use_nonce,
                "expires_at": auth.approval_request_expires_at.isoformat(),
                "owner_identity": "FIXTURE_ONLY_NOT_REAL_MFA"})
        return fake_setup, auth

    def reject(self):
        if self.plans._states.get(self.plan.plan_id) != "PROPOSED_RESEARCH_ONLY":
            raise ValueError("only a proposed plan can be rejected")
        self.plans.observe_external_state(self.plan.plan_id, "OWNER_REJECTED",
            occurred_at=self.clock.now)
        self.journal.append(occurred_at=self.clock.now, actor="fake_owner",
            event_type="FAKE_OWNER_REJECTED", plan_id=self.plan.plan_id,
            lifecycle_id=self.lifecycle_id,
            details={"proposal_hash": self.plan.immutable_hash, "new_exposure": False,
                "owner_identity": "FIXTURE_ONLY_NOT_REAL_MFA"})

    def expire(self):
        if self.clock.now < self.plan.expires_at:
            self.clock.now = self.plan.expires_at
        status = self.plans.get(self.plan.plan_id, self.clock.now).status
        if status != "EXPIRED":
            raise ValueError("paper proposal did not enter expired status")
        self.journal.append(occurred_at=self.clock.now, actor="fake_owner",
            event_type="FAKE_OWNER_EXPIRED", plan_id=self.plan.plan_id,
            lifecycle_id=self.lifecycle_id,
            details={"proposal_hash": self.plan.immutable_hash, "new_exposure": False,
                "expires_at": self.plan.expires_at.isoformat()})

    def consume(self, auth, *, trigger_at: datetime):
        if auth.readiness_ref != self.plan.immutable_hash or auth.one_use_nonce != self.plan.approval_nonce:
            raise ValueError("claim does not match fixture-owner approval")
        intent_id = self.owner.claim(auth, quantity=self.plan.proposed_quantity,
            quote=self.plan.entry_max, trigger_at=trigger_at)
        if not intent_id:
            return None
        self.plans.observe_external_state(self.plan.plan_id, "CONSUMED",
            occurred_at=self.clock.now)
        self.journal.append(occurred_at=self.clock.now, actor="fake_owner",
            event_type="APPROVAL_CONSUMED_ONCE", plan_id=self.plan.plan_id,
            lifecycle_id=self.lifecycle_id,
            details={"nonce": auth.one_use_nonce, "intent_id": intent_id,
                "duplicate_claim": "REJECTED"})
        return intent_id


def run_demo(*, data_dir: Path | str | None = None) -> dict[str, object]:
    storage_path = None
    if data_dir is not None:
        data_dir = Path(data_dir)
        if any((data_dir / name).exists() for name in ("c06_state.sqlite", "owner.sqlite", "venue.sqlite")):
            raise FileExistsError("paper data already exists; use --resume to reopen it")
        data_dir.mkdir(parents=True, exist_ok=True)
        storage_path = data_dir / "c06_state.sqlite"
    fixture = build_fixture(storage_path=storage_path)
    gateway: C06ToolGateway = fixture["gateway"]
    coordinator = DeterministicOfflineCoordinator(gateway)
    plans: PlanRegistry = fixture["plans"]
    journal: EventJournal = fixture["journal"]
    candidate = fixture["candidate"]
    setup = fixture["setup"]
    as_of = fixture["as_of"]
    if candidate is None or setup is None:
        raise RuntimeError("expected deterministic C03 research-only fixture candidate")

    scan = coordinator.call("scan_opportunities", {"as_of": as_of})
    symbol_result = coordinator.call("evaluate_symbol", {"symbol": candidate.symbol, "as_of": as_of})
    candidates = coordinator.call("evaluate_candidates", {"candidate_ids": (candidate.decision_id,)})
    if candidates.decision != "RESEARCH_CANDIDATE" or candidate.executable:
        raise RuntimeError("C03 candidate did not remain research-only")

    # The schema rejects a coordinator-authored risk override before plan creation.
    try:
        coordinator.call("prepare_plan", {"candidate_id": candidate.decision_id,
            "approved_max_risk_usdt": "999999"})
        raise AssertionError("risk override unexpectedly passed the typed tool schema")
    except ValidationError:
        pass
    if len(plans) != 0:
        raise RuntimeError("invalid tool input created a plan before schema rejection")
    plan = coordinator.call("prepare_plan", {"candidate_id": candidate.decision_id})
    if not plan.verify_hash() or plan.executable or plan.research_status != "RESEARCH_ONLY":
        raise RuntimeError("paper proposal must remain immutable and non-executable")
    lifecycle_id = stable_id("c06.fake_lifecycle", plan.plan_id)
    journal.append(occurred_at=as_of, actor="offline_test_driver", event_type="PROPOSAL_PREPARED",
        plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
        details={"plan_hash": plan.immutable_hash, "candidate_status": plan.research_status,
            "fixture": "SYNTHETIC_FIXTURE"})

    trigger_at = candidate.earliest_hypothetical_entry_at
    approval_at = trigger_at + timedelta(milliseconds=100)
    run_directory = nullcontext(str(data_dir)) if data_dir is not None else tempfile.TemporaryDirectory(
        prefix="astrabot-c06-positive-")
    with run_directory as temp:
        owner_root = Path(temp)
        clock = FakeClock(approval_at)
        owner, venue = _new_owner(owner_root, clock)
        decisions = FixtureOwnerDecision(plan=plan, candidate=candidate, setup=setup,
            owner=owner, clock=clock, plans=plans, journal=journal, lifecycle_id=lifecycle_id)
        fake_setup, auth = make_fake_authorization(plan, candidate, setup, approval_at)

        # A tampered numeric limit breaks the C01 immutable approval hash.
        tampered_auth = auth.model_copy(update={
            "approved_max_risk_usdt": auth.approved_max_risk_usdt * D("100")})
        try:
            owner.register_approval(tampered_auth, fake_setup)
            raise AssertionError("tampered numerical risk value unexpectedly registered")
        except ValueError:
            pass
        writes_after_tamper = len(venue.state.read()["writes"])
        if writes_after_tamper != 0:
            raise RuntimeError("tampered C01 approval caused a fake venue write")
        journal.append(occurred_at=clock.now, actor="offline_test_driver",
            event_type="RISK_OVERRIDE_REJECTED", plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
            details={"authorized_hash_unchanged": True, "venue_writes": writes_after_tamper})

        fake_setup, auth = decisions.approve()
        intent_id = decisions.consume(auth, trigger_at=trigger_at)
        if not intent_id:
            raise RuntimeError("fake owner rejected the unmodified bounded plan")
        writes_before_replay = len(venue.state.read()["writes"])
        replay_intent = owner.claim(auth, quantity=plan.proposed_quantity, quote=plan.entry_max,
            trigger_at=trigger_at)
        writes_after_replay = len(venue.state.read()["writes"])
        if replay_intent is not None or writes_after_replay != writes_before_replay:
            raise RuntimeError("one-use authorization replay was not rejected")
        journal.append(occurred_at=clock.now, actor="fake_owner", event_type="APPROVAL_CONSUMED_ONCE",
            plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
            details={"nonce": auth.one_use_nonce, "duplicate_claim": "REJECTED"})

        owner.submit(intent_id, quote=plan.entry_max)
        clock.advance(milliseconds=50)
        entry_client_id = "entry-" + auth.plan_id
        venue.fill(entry_client_id, "fixture-entry-fill", plan.proposed_quantity,
            plan.entry_max, at=clock.now)
        owner.detect_fills()
        state = owner.ledger.read()
        position = state["positions"][auth.lifecycle_id]
        plans.observe_external_state(plan.plan_id, "SIMULATED_OPEN", occurred_at=clock.now)
        if not position["stop_ids"] or position["first_fill_at"] is None:
            raise RuntimeError("fake fill did not receive immediate simulated protection")
        journal.append(occurred_at=clock.now, actor="fake_owner", event_type="SIMULATED_ENTRY_PROTECTED",
            plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
            details={"quantity": position["entry_quantity"], "first_fill_at": position["first_fill_at"],
                "stop_order_id": position["stop_ids"][0], "stop_price": str(plan.stop),
                "price_fidelity": "SYNTHETIC_FIXTURE"})

        tp_ids = owner.add_targets(auth.lifecycle_id)
        if len(tp_ids) != 2:
            raise RuntimeError("expected C01 fake two-target management capability")
        clock.advance(milliseconds=100)
        first_target, first_fraction = plan.targets[0]
        partial_quantity = plan.proposed_quantity * first_fraction
        venue.fill(tp_ids[0], "fixture-partial-tp1", partial_quantity, first_target, at=clock.now)
        owner.detect_fills()
        position_after_partial = owner.ledger.read()["positions"][auth.lifecycle_id]
        if D(position_after_partial["quantity"]) <= 0:
            raise RuntimeError("partial target unexpectedly closed the whole position")
        if position_after_partial["first_fill_at"] != position["first_fill_at"]:
            raise RuntimeError("first-fill holding clock changed after partial exit")
        journal.append(occurred_at=clock.now, actor="fake_owner", event_type="SIMULATED_PARTIAL_EXIT",
            plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
            details={"target_order_id": tp_ids[0], "exited_quantity": str(partial_quantity),
                "remaining_quantity": position_after_partial["quantity"],
                "first_fill_at_unchanged": True})

        # The fake coordinator and journal role both go unavailable after entry.
        journal.append(occurred_at=clock.now, actor="offline_test_driver",
            event_type="COORDINATOR_AND_JOURNAL_UNAVAILABLE", plan_id=plan.plan_id,
            lifecycle_id=lifecycle_id,
            details={"open_quantity": position_after_partial["quantity"],
                "protected": bool(position_after_partial["stop_ids"])})
        coordinator_online = False
        coordinator.available = False
        journal.available = False
        try:
            journal.summary(lifecycle_id)
            raise AssertionError("unavailable journal unexpectedly served a summary")
        except RuntimeError:
            pass
        try:
            coordinator.call("get_plan_status", {"plan_id": plan.plan_id, "as_of": clock.now})
            raise AssertionError("unavailable coordinator unexpectedly served a tool call")
        except RuntimeError:
            pass
        first_fill_at = datetime.fromisoformat(position_after_partial["first_fill_at"])
        flatten_at = first_fill_at + timedelta(hours=11, minutes=55)
        clock.now = flatten_at
        owner.timers()  # Existing C01 first-fill-based deterministic timer.
        closed_latch = owner.ledger.read()["positions"][auth.lifecycle_id]["latch"]
        if closed_latch is None or closed_latch["reason"] != "TIME_LIMIT":
            raise RuntimeError("independent 11h55m supervisor did not request a reduce-only exit")

        state = owner.ledger.read()
        exit_id = next(cid for cid, item in state["management"].items()
            if item["lifecycle_id"] == auth.lifecycle_id and item["params"]["kind"] == "MARKET")
        remaining = D(state["positions"][auth.lifecycle_id]["quantity"])
        venue.fill(exit_id, "fixture-time-exit-fill", remaining, plan.entry_max, at=clock.now)
        # Existing fake venue cancellation clears dormant target/stop instructions
        # before C01's terminal flat reconciliation checks every instruction.
        for client_id in (*position_after_partial["stop_ids"], *tp_ids):
            order = venue.state.read()["orders"].get(client_id)
            if order and order["status"] not in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}:
                venue.cancel(client_id)
        owner.detect_fills()
        if not owner.terminal(auth.lifecycle_id):
            raise RuntimeError("C01 fake terminal flat reconciliation failed")
        if owner.ledger.read()["positions"][auth.lifecycle_id]["state"] != "FLAT_RECONCILED":
            raise RuntimeError("fake position did not confirm closed")
        journal.available = True
        coordinator.available = True
        coordinator_online = True
        plans.observe_external_state(plan.plan_id, "CLOSED_RECONCILED", occurred_at=clock.now)
        journal.append(occurred_at=clock.now, actor="fake_supervisor",
            event_type="TIME_LIMIT_REDUCE_ONLY_EXIT_AND_FLAT_CONFIRMATION",
            plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
            details={"latch_reason": closed_latch["reason"], "timer_from_first_fill": "11h55m",
                "reduce_only_order_id": exit_id, "closed_state": "FLAT_RECONCILED",
                "coordinator_online": coordinator_online, "journal_recovered": journal.available})

        # The fake owner has no second exposure path; the consumed nonce is still spent.
        final_status = coordinator.call("get_plan_status", {"plan_id": plan.plan_id, "as_of": clock.now})
        summary = coordinator.call("get_operations_summary", {"lifecycle_id": lifecycle_id})
        venue_state = venue.state.read()
        position_final = owner.ledger.read()["positions"][auth.lifecycle_id]
        if D(position_final["quantity"]) != 0 or len(venue_state["writes"]) < 1:
            raise RuntimeError("paper lifecycle has no closed position or entry write")

        return {
            "fixture": "C04_SYNTHETIC_FULLY_ELIGIBLE_TEST_FIXTURE",
            "openbot_integration": "NOT_VERIFIED",
            "tool_calls": [
                {"tool": "scan_opportunities", "shortlist": scan.symbols,
                    "status": scan.opportunities[0].state, "fixture": scan.fixture_label},
                {"tool": "evaluate_symbol", "decision_ids": symbol_result.decision_ids,
                    "readiness": symbol_result.readiness},
                {"tool": "evaluate_candidates", "decision": candidates.decision,
                    "research_status": candidates.research_status},
                {"tool": "prepare_plan", "plan_id": plan.plan_id,
                    "proposal_hash": plan.immutable_hash, "executable": plan.executable},
                {"tool": "get_plan_status", "status": final_status.status},
                {"tool": "get_operations_summary", "event_count": summary.event_count,
                    "event_digest": summary.event_digest},
            ],
            "positive_trace": {
                "fake_owner": "approved exact immutable C01 authorization",
                "authorization_hash": auth.approved_immutable_hash,
                "nonce": auth.one_use_nonce,
                "expires_at": auth.approval_request_expires_at.isoformat(),
                "duplicate_claim": "REJECTED",
                "entry_quantity": str(plan.proposed_quantity),
                "entry_price_fixture": str(plan.entry_max),
                "first_fill_at": position["first_fill_at"],
                "immediate_protection": position["stop_ids"][0],
                "partial_exit_quantity": str(partial_quantity),
                "remaining_before_timer": position_after_partial["quantity"],
                "coordinator_unavailable_after_open": True,
                "journal_unavailable_during_timer_exit": True,
                "timer_exit_at": clock.now.isoformat(),
                "reduce_only_exit": exit_id,
                "final_position_state": position_final["state"],
                "final_quantity": position_final["quantity"],
                "plan_status": final_status.status,
                "journal_summary": summary.model_dump(mode="json"),
            },
            "negative_checks": {
                "coordinator_risk_override": "REJECTED_BY_TYPED_SCHEMA",
                "tampered_owner_risk_hash": "REJECTED_BY_C01_FAKE_OWNER",
                "approval_nonce_reuse": "REJECTED_WITH_NO_SECOND_ENTRY",
                "coordinator_and_journal_outage": "TIME_EXIT_AND_CLOSE_CONTINUED",
            },
            "machine_events": [e.model_dump(mode="json") for e in journal.events],
        }


def run_negative_cases() -> dict[str, object]:
    output: dict[str, object] = {}

    # An explicit fake-owner rejection leaves the venue write ledger empty.
    rejected = build_fixture()
    gateway = rejected["gateway"]
    candidate = rejected["candidate"]
    plan = gateway.call("prepare_plan", {"candidate_id": candidate.decision_id})
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-rejected-") as temp:
        clock = FakeClock(rejected["as_of"])
        owner, venue = _new_owner(Path(temp), clock)
        decisions = FixtureOwnerDecision(plan=plan, candidate=candidate, setup=rejected["setup"],
            owner=owner, clock=clock, plans=rejected["plans"], journal=rejected["journal"],
            lifecycle_id=stable_id("c06.fake_lifecycle", plan.plan_id))
        decisions.reject()
        output["owner_rejected"] = {"status": gateway.call("get_plan_status", {
            "plan_id": plan.plan_id, "as_of": clock.now}).status,
            "plan_id": plan.plan_id, "plan_hash": plan.immutable_hash,
            "nonce": plan.approval_nonce, "venue_writes": len(venue.state.read()["writes"]),
            "new_exposure": False}

    expired_decision = build_fixture()
    expired_candidate = expired_decision["candidate"]
    expired_plan = expired_decision["gateway"].call("prepare_plan", {
        "candidate_id": expired_candidate.decision_id})
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-owner-expiry-") as temp:
        clock = FakeClock(expired_decision["as_of"])
        owner, venue = _new_owner(Path(temp), clock)
        decision = FixtureOwnerDecision(plan=expired_plan, candidate=expired_candidate,
            setup=expired_decision["setup"], owner=owner, clock=clock,
            plans=expired_decision["plans"], journal=expired_decision["journal"],
            lifecycle_id=stable_id("c06.fake_lifecycle", expired_plan.plan_id))
        decision.expire()
        output["owner_expired"] = {"status": expired_decision["gateway"].call(
            "get_plan_status", {"plan_id": expired_plan.plan_id, "as_of": clock.now}).status,
            "venue_writes": len(venue.state.read()["writes"]), "new_exposure": False}

    # Approval exists but is attempted after the immutable plan expiry.
    expired = build_fixture()
    candidate = expired["candidate"]
    setup = expired["setup"]
    plan = expired["gateway"].call("prepare_plan", {"candidate_id": candidate.decision_id})
    trigger = candidate.earliest_hypothetical_entry_at
    approved_at = trigger + timedelta(milliseconds=100)
    fake_setup, auth = make_fake_authorization(plan, candidate, setup, approved_at)
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-expired-") as temp:
        clock = FakeClock(approved_at)
        owner, venue = _new_owner(Path(temp), clock)
        owner.register_approval(auth, fake_setup)
        clock.now = plan.expires_at + timedelta(seconds=1)
        intent = owner.claim(auth, quantity=plan.proposed_quantity,
            quote=plan.entry_max, trigger_at=trigger)
        output["approval_expired"] = {"claim": "REJECTED" if intent is None else "UNEXPECTED",
            "venue_writes": len(venue.state.read()["writes"]), "new_exposure": False,
            "expired_at": plan.expires_at.isoformat()}

    # With required event evidence absent, C02/C03 fail closed and no plan exists.
    missing = build_fixture(event_evidence=False)
    gateway = missing["gateway"]
    decisions = missing["evaluation"].emitted
    no_trade = next((d for d in decisions if d.decision == "NO_TRADE"), None)
    scanned = gateway.call("scan_opportunities", {"as_of": missing["as_of"]})
    output["missing_event_evidence"] = {
        "shortlist": scanned.symbols,
        "decision": no_trade.decision if no_trade else "NO_TRADE",
        "reason_codes": no_trade.rejection_reason_codes if no_trade else ("MISSING_CANDIDATE",),
        "plan_created": False,
        "new_exposure": False,
    }
    if no_trade is not None:
        try:
            gateway.call("prepare_plan", {"candidate_id": no_trade.decision_id})
        except ValueError:
            output["missing_event_evidence"]["prepare_plan"] = "REJECTED"
        else:
            raise RuntimeError("missing evidence unexpectedly produced a proposal")
    missing_market = build_fixture(market_evidence=False)
    market_gateway = missing_market["gateway"]
    market_no_trade = next((d for d in missing_market["evaluation"].emitted
        if d.decision == "NO_TRADE"), None)
    market_scan = market_gateway.call("scan_opportunities", {"as_of": missing_market["as_of"]})
    output["missing_market_evidence"] = {
        "shortlist": market_scan.symbols,
        "decision": market_no_trade.decision if market_no_trade else "NO_TRADE",
        "reason_codes": market_no_trade.rejection_reason_codes if market_no_trade else ("MISSING_CANDIDATE",),
        "plan_created": False,
        "new_exposure": False,
    }
    if market_no_trade is not None:
        try:
            market_gateway.call("prepare_plan", {"candidate_id": market_no_trade.decision_id})
        except ValueError:
            output["missing_market_evidence"]["prepare_plan"] = "REJECTED"
        else:
            raise RuntimeError("missing market evidence unexpectedly produced a proposal")
    return output


def prepare_persistent_proposal(data_dir: Path | str) -> dict[str, object]:
    """Persist one research proposal and empty fake accounts before owner approval."""
    data_dir = Path(data_dir)
    if any((data_dir / name).exists() for name in ("c06_state.sqlite", "owner.sqlite", "venue.sqlite")):
        raise FileExistsError("paper data already exists; proposal preparation never overwrites it")
    data_dir.mkdir(parents=True, exist_ok=True)
    fixture = build_fixture(storage_path=data_dir / "c06_state.sqlite")
    candidate, setup = fixture["candidate"], fixture["setup"]
    if candidate is None or setup is None:
        raise RuntimeError("synthetic research fixture produced no proposal-capable candidate")
    plan = fixture["gateway"].call("prepare_plan", {"candidate_id": candidate.decision_id})
    lifecycle_id = stable_id("c06.fake_lifecycle", plan.plan_id)
    fixture["journal"].append(occurred_at=fixture["as_of"], actor="offline_test_driver",
        event_type="PROPOSAL_PREPARED", plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
        details={"plan_hash": plan.immutable_hash, "candidate_status": plan.research_status,
            "fixture": "SYNTHETIC_FIXTURE"})
    clock = FakeClock(candidate.earliest_hypothetical_entry_at + timedelta(milliseconds=100))
    owner, venue = _new_owner(data_dir, clock)
    return {"plan_id": plan.plan_id, "plan_hash": plan.immutable_hash,
        "plan_status": fixture["plans"]._states[plan.plan_id],
        "owner_approval_exists": plan.plan_id in owner.ledger.read()["approvals"],
        "venue_write_count": len(venue.state.read()["writes"]),
        "evidence_paths": {"c06_state": str(data_dir / "c06_state.sqlite"),
            "owner_ledger": str(data_dir / "owner.sqlite"), "fake_venue": str(data_dir / "venue.sqlite")}}


def _continue_after_restart(*, fixture, plan, auth, owner, venue, clock, journal, plans):
    """Finish a recovered deterministic lifecycle from authoritative fake state."""
    lifecycle_id = auth.lifecycle_id
    owner_state = owner.ledger.read()
    intent_id = "intent-" + plan.plan_id
    intent_payload = owner_state["intents"].get(intent_id)
    newly_claimed = intent_payload is None
    if intent_payload is None:
        decision = FixtureOwnerDecision(plan=plan, candidate=fixture["candidate"],
            setup=fixture["setup"], owner=owner, clock=clock, plans=plans,
            journal=journal, lifecycle_id=lifecycle_id)
        intent_id = decision.consume(auth, trigger_at=fixture["candidate"].earliest_hypothetical_entry_at)
        if not intent_id:
            raise RuntimeError("restored fake owner rejected the exact one-use authorization")
        owner_state = owner.ledger.read()
        intent_payload = owner_state["intents"][intent_id]

    if intent_payload["state"] == "PERSISTED" and newly_claimed:
        owner.submit(intent_id, quote=plan.entry_max)
        intent_payload = owner.ledger.read()["intents"][intent_id]
    if intent_payload["state"] in {"PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION"}:
        raise RuntimeError("entry acknowledgment remains unresolved; it will not be resubmitted")
    snapshot = venue.snapshot()
    entry_id = intent_payload["client_order_id"]
    entry_order = snapshot["orders"].get(entry_id)
    if not entry_order:
        raise RuntimeError("persisted entry intent has no correlated fake-venue order")
    if entry_order["status"] not in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}:
        remaining_entry = max(D(0), plan.proposed_quantity - D(entry_order["filled"]))
        if remaining_entry:
            fill_index = len([f for f in snapshot["fills"].values() if f["client_id"] == entry_id])
            venue.fill(entry_id, f"fixture-recovery-entry-{fill_index}", remaining_entry,
                plan.entry_max, at=clock.now)
    owner.detect_fills()
    state = owner.ledger.read()
    snapshot = venue.snapshot()
    position = state["positions"].get(lifecycle_id)
    if not position:
        raise RuntimeError("restored fake owner has no lifecycle position record")
    if D(position["quantity"]) > 0:
        visible_stops = [cid for cid in position["stop_ids"] if cid in snapshot["orders"]
            and snapshot["orders"][cid]["visible"]
            and snapshot["orders"][cid]["status"] in {"ACKNOWLEDGED", "PARTIAL"}]
        if not visible_stops:
            raise RuntimeError("restored active fake exposure lacks verified stop protection")
        if plans._states[plan.plan_id] == "CONSUMED":
            plans.observe_external_state(plan.plan_id, "SIMULATED_OPEN", occurred_at=clock.now)
        snapshot = venue.snapshot()
        target_intents = [cid for cid, entry in state.get("management", {}).items()
            if entry["lifecycle_id"] == lifecycle_id and entry["params"]["kind"] == "LIMIT"]
        if not position["tp_ids"] and not target_intents:
            owner.add_targets(lifecycle_id)
            state = owner.ledger.read()
        elif position["tp_ids"]:
            target_one = position["tp_ids"][0]
            target_order = venue.snapshot()["orders"].get(target_one)
            already_hit = any(fill["client_id"] == target_one for fill in
                venue.snapshot()["fills"].values())
            if target_order and not already_hit and target_order["status"] not in {
                "FILLED", "CANCELLED", "REJECTED", "EXPIRED",
            }:
                quantity = D(target_order["params"]["quantity"]) - D(target_order["filled"])
                if quantity > 0:
                    venue.fill(target_one, "fixture-recovery-partial-target-one", quantity,
                        D(target_order["params"]["price"]), at=clock.now)
                    owner.detect_fills()

    state = owner.ledger.read()
    position = state["positions"][lifecycle_id]
    if position["first_fill_at"] and D(position["quantity"]) > 0:
        first_fill = datetime.fromisoformat(position["first_fill_at"])
        deadline = first_fill + timedelta(hours=11, minutes=55)
        if clock.now < deadline:
            clock.now = deadline
        owner.timers()
        state = owner.ledger.read()
        position = state["positions"][lifecycle_id]
        if D(position["quantity"]) > 0:
            snapshot = venue.snapshot()
            market_ids = [cid for cid, entry in state.get("management", {}).items()
                if entry["lifecycle_id"] == lifecycle_id and entry["params"]["kind"] == "MARKET"]
            exit_id = next((cid for cid in reversed(market_ids)
                if cid in snapshot["orders"] and snapshot["orders"][cid]["status"] not in {
                    "FILLED", "CANCELLED", "REJECTED", "EXPIRED",
                }), None)
            if exit_id is None:
                if any(cid not in snapshot["orders"] for cid in market_ids):
                    raise RuntimeError("exit submission remains ambiguous; it will not be resubmitted")
                exit_id = owner.reduce(lifecycle_id)
                snapshot = venue.snapshot()
            exit_order = snapshot["orders"].get(exit_id) if exit_id else None
            if not exit_order:
                raise RuntimeError("exit order has no correlated fake-venue evidence")
            if exit_order["status"] not in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}:
                remaining = D(position["quantity"])
                if remaining > 0:
                    fill_index = len([f for f in snapshot["fills"].values()
                        if f["client_id"] == exit_id])
                    venue.fill(exit_id, f"fixture-recovery-time-exit-{fill_index}", remaining,
                        plan.entry_min, at=clock.now)

    snapshot = venue.snapshot()
    for client_id, order in snapshot["orders"].items():
        if order["lifecycle_id"] == lifecycle_id and order["status"] not in {
            "FILLED", "CANCELLED", "REJECTED", "EXPIRED",
        }:
            venue.cancel(client_id)
    owner.detect_fills()
    if not owner.terminal(lifecycle_id):
        raise RuntimeError("restored fake lifecycle remains unresolved; terminal state withheld")
    state = owner.ledger.read()
    if state["positions"][lifecycle_id]["state"] != "FLAT_RECONCILED":
        raise RuntimeError("fake terminal reconciliation did not prove flat")
    current = plans._states[plan.plan_id]
    if current == "FAKE_OWNER_APPROVED":
        plans.observe_external_state(plan.plan_id, "CONSUMED", occurred_at=clock.now)
        current = "CONSUMED"
    if current == "CONSUMED" and state["positions"][lifecycle_id]["first_fill_at"]:
        plans.observe_external_state(plan.plan_id, "SIMULATED_OPEN", occurred_at=clock.now)
        current = "SIMULATED_OPEN"
    if current in {"CONSUMED", "SIMULATED_OPEN"}:
        plans.observe_external_state(plan.plan_id, "CLOSED_RECONCILED", occurred_at=clock.now)
    journal.append(occurred_at=clock.now, actor="fake_supervisor",
        event_type="RECOVERY_FLAT_RECONCILIATION", plan_id=plan.plan_id,
        lifecycle_id=lifecycle_id,
        details={"position_state": "FLAT_RECONCILED", "quantity": "0",
            "entry_intent": intent_id, "owner_reconciled": owner.ready})


def reopen_persisted_demo(data_dir: Path | str, *, clock_at: datetime | None = None,
                          owner_decision: str | None = None,
                          pause_after_approval: bool = False) -> dict[str, object]:
    """Restore a durable C06/C01 fixture, reconcile truth, and continue safely."""
    data_dir = Path(data_dir)
    state_path = data_dir / "c06_state.sqlite"
    if not all((data_dir / name).is_file() for name in
               ("c06_state.sqlite", "owner.sqlite", "venue.sqlite")):
        raise FileNotFoundError("--resume requires existing C06, fake-owner and fake-venue state")
    fixture = build_fixture(storage_path=state_path)
    plans: PlanRegistry = fixture["plans"]
    journal: EventJournal = fixture["journal"]
    if len(plans) != 1:
        raise ValueError("demo expects exactly one persisted paper plan")
    plan = next(iter(plans._plans.values()))
    lifecycle_id = stable_id("c06.fake_lifecycle", plan.plan_id)
    candidate, setup = fixture["candidate"], fixture["setup"]
    if candidate is None or setup is None or candidate.decision_id != plan.candidate_id:
        raise ValueError("persisted paper plan no longer matches the deterministic research fixture")
    latest_at = journal.events[-1].occurred_at if journal.events else fixture["as_of"]
    now = clock_at or latest_at
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if owner_decision == "approve" and now < candidate.earliest_hypothetical_entry_at:
        now = candidate.earliest_hypothetical_entry_at + timedelta(milliseconds=100)
    if now < latest_at:
        raise ValueError("resume clock cannot precede the latest persisted machine event")
    clock = FakeClock(now)
    venue = FakeVenue(data_dir / "venue.sqlite", clock)
    owner = FakeOwner(data_dir / "owner.sqlite", venue, clock, equity=FIXTURE_EQUITY)
    c01_state = owner.ledger.read()
    known_times = []
    approval = c01_state["approvals"].get(plan.plan_id)
    if approval:
        known_times.append(datetime.fromisoformat(approval["approved_at"]))
    known_times.extend(datetime.fromisoformat(position["first_fill_at"])
        for position in c01_state["positions"].values() if position["first_fill_at"])
    venue_state = venue.state.read()
    known_times.extend(datetime.fromisoformat(fill["at"]) for fill in venue_state["fills"].values())
    latest_owner_time = max(known_times, default=now)
    if clock_at is not None and now < latest_owner_time:
        raise ValueError("resume clock cannot precede persisted fake-owner or fake-venue activity")
    if clock_at is None and clock.now < latest_owner_time:
        clock.now = latest_owner_time
    now = clock.now
    if not owner.reconnect():
        raise RuntimeError("fake owner could not reconcile persisted state; new entries remain halted")

    owner_state = owner.ledger.read()
    auth_payload = owner_state["approvals"].get(plan.plan_id)
    current = plans._states[plan.plan_id]
    position = owner_state["positions"].get(lifecycle_id)
    if auth_payload:
        auth = TradeAuthorizationV15.model_validate_json(json.dumps(auth_payload))
        _, expected_auth = make_fake_authorization(plan, candidate, setup, auth.approved_at)
        if (auth.immutable_hash() != auth.approved_immutable_hash
            or auth != expected_auth
            or auth.readiness_ref != plan.immutable_hash
            or auth.one_use_nonce != plan.approval_nonce
            or auth.lifecycle_id != lifecycle_id or auth.setup_id != plan.setup_id
            or auth.approved_max_risk_usdt != plan.modeled_loss_usdt):
            raise ValueError("persisted fake-owner approval disagrees with immutable paper plan")
        if current == "PROPOSED_RESEARCH_ONLY":
            plans.observe_external_state(plan.plan_id, "FAKE_OWNER_APPROVED", occurred_at=now)
            current = "FAKE_OWNER_APPROVED"
        elif current in {"OWNER_REJECTED", "EXPIRED"}:
            if current == "OWNER_REJECTED":
                raise ValueError("owner-rejected plan also has a persisted approval")
        elif current not in {"FAKE_OWNER_APPROVED", "CONSUMED", "SIMULATED_OPEN", "CLOSED_RECONCILED"}:
            raise ValueError("persisted plan and owner authorization states disagree")
        consumed = plan.plan_id in owner_state["consumed"]
        nonce_spent = plan.approval_nonce in owner_state["nonces"]
        if consumed != nonce_spent:
            raise ValueError("persisted fake-owner plan/nonce consumption is inconsistent")
        if consumed and current in {"OWNER_REJECTED", "EXPIRED"}:
            raise ValueError("consumed fake-owner authorization conflicts with terminal plan status")
        if consumed and not position:
            raise ValueError("one-use claim has no persisted lifecycle position record")
        if consumed and current == "FAKE_OWNER_APPROVED":
            plans.observe_external_state(plan.plan_id, "CONSUMED", occurred_at=now)
            current = "CONSUMED"
        if position and position["first_fill_at"] and current == "CONSUMED":
            current = "SIMULATED_OPEN"
            plans.observe_external_state(plan.plan_id, current, occurred_at=now)
        if position and position["state"] == "FLAT_RECONCILED" and current in {
            "CONSUMED", "SIMULATED_OPEN",
        }:
            current = "CLOSED_RECONCILED"
            plans.observe_external_state(plan.plan_id, current, occurred_at=now)
        if current == "SIMULATED_OPEN" and (not position or not position["first_fill_at"]):
            raise ValueError("simulated-open plan status has no persisted first fill")
        if current == "CLOSED_RECONCILED" and (
            not position or position["state"] != "FLAT_RECONCILED"
            or D(position["quantity"]) != 0 or not position.get("terminal_proof")
        ):
            raise ValueError("closed plan status lacks C01 fake flat-reconciliation proof")
        if (not consumed and current == "FAKE_OWNER_APPROVED" and now >= plan.expires_at):
            plans.observe_external_state(plan.plan_id, "EXPIRED", occurred_at=now)
            current = "EXPIRED"
        if position and D(position["quantity"]) > 0:
            snapshot = venue.snapshot()
            visible_stops = [cid for cid in position["stop_ids"] if cid in snapshot["orders"]
                and snapshot["orders"][cid]["visible"]
                and snapshot["orders"][cid]["status"] in {"ACKNOWLEDGED", "PARTIAL"}]
            if not visible_stops or not owner.ready:
                raise RuntimeError("active fake position is not protected and reconciled")
    else:
        if current not in {"PROPOSED_RESEARCH_ONLY", "OWNER_REJECTED", "EXPIRED"}:
            raise ValueError("persisted plan status has no matching fake-owner approval")
        if plan.plan_id in owner_state["consumed"] or plan.approval_nonce in owner_state["nonces"]:
            raise ValueError("fake-owner consumption exists without its persisted approval")
        venue_truth = venue.state.read()
        if any(order["lifecycle_id"] == lifecycle_id for order in venue_truth["orders"].values()):
            raise ValueError("fake venue has lifecycle orders without a persisted owner approval")

    # Every fake venue order for this lifecycle must be correlated to a C01
    # entry intent or durable management intent; orphan instructions fail closed.
    venue_truth = venue.state.read()
    known_orders = {intent["client_order_id"] for intent in owner_state["intents"].values()
        if intent["lifecycle_id"] == lifecycle_id}
    known_orders.update(client_id for client_id, request in owner_state.get("management", {}).items()
        if request["lifecycle_id"] == lifecycle_id)
    if any(order["lifecycle_id"] == lifecycle_id and client_id not in known_orders
        for client_id, order in venue_truth["orders"].items()):
        raise ValueError("fake venue lifecycle contains an unowned order")

    if current == "PROPOSED_RESEARCH_ONLY" and now >= plan.expires_at:
        current = plans.get(plan.plan_id, now).status
    if owner_decision:
        if current != "PROPOSED_RESEARCH_ONLY" or auth_payload:
            raise ValueError("fixture-owner decision is only available for an unapproved proposal")
        decision = FixtureOwnerDecision(plan=plan, candidate=candidate, setup=setup,
            owner=owner, clock=clock, plans=plans, journal=journal,
            lifecycle_id=lifecycle_id)
        if owner_decision == "approve":
            _, auth = decision.approve()
            auth_payload = owner.ledger.read()["approvals"][plan.plan_id]
            current = "FAKE_OWNER_APPROVED"
        elif owner_decision == "reject":
            decision.reject()
            current = "OWNER_REJECTED"
        elif owner_decision == "expire":
            decision.expire()
            current = "EXPIRED"
        else:
            raise ValueError("owner_decision must be approve, reject or expire")
        now = clock.now
    event = journal.append(occurred_at=now, actor="offline_test_driver",
        event_type="PERSISTED_STATE_REOPENED", plan_id=plan.plan_id,
        lifecycle_id=lifecycle_id,
        details={"owner_reconciled": owner.ready, "plan_status": current,
            "fixture_owner_identity": "NOT_REAL_MFA"})
    if (auth_payload and not pause_after_approval
        and current in {"FAKE_OWNER_APPROVED", "CONSUMED", "SIMULATED_OPEN"}):
        auth = TradeAuthorizationV15.model_validate_json(json.dumps(auth_payload))
        _continue_after_restart(fixture=fixture, plan=plan, auth=auth, owner=owner,
            venue=venue, clock=clock, journal=journal, plans=plans)
        current = plans._states[plan.plan_id]
    summary = journal.summary(lifecycle_id)
    venue_snapshot = venue.state.read()
    final = owner.ledger.read()
    position = final["positions"].get(lifecycle_id)
    return {
        "fixture": "C04_SYNTHETIC_FULLY_ELIGIBLE_TEST_FIXTURE",
        "plan_id": plan.plan_id,
        "plan_hash": plan.immutable_hash,
        "lifecycle_id": lifecycle_id,
        "plan_status": current,
        "owner_reconciled": owner.ready,
        "first_fill_at": position["first_fill_at"] if position else None,
        "position_state": position["state"] if position else None,
        "position_quantity": position["quantity"] if position else "0",
        "venue_write_count": len(venue_snapshot["writes"]),
        "event_id": event.event_id,
        "journal_summary": summary.model_dump(mode="json"),
        "evidence_paths": {"c06_state": str(state_path), "owner_ledger": str(data_dir / "owner.sqlite"),
            "fake_venue": str(data_dir / "venue.sqlite")},
    }


def _parse_clock(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or reopen the offline synthetic AstraBot paper fixture.")
    parser.add_argument("--fake-only", action="store_true",
        help="required explicit confirmation that all state and orders are synthetic/fake")
    parser.add_argument("--data-dir", type=Path,
        help="optional persistent test directory for C06, fake-owner and fake-venue SQLite files")
    parser.add_argument("--resume", action="store_true",
        help="reopen and reconcile existing files without starting a second lifecycle")
    parser.add_argument("--prepare-only", action="store_true",
        help="persist a proposal and empty fake accounts, then stop before the separate owner decision")
    parser.add_argument("--clock", type=_parse_clock,
        help="deterministic ISO-8601 clock override, valid with --resume")
    parser.add_argument("--owner-decision", choices=("approve", "reject", "expire"),
        help="explicit fixture-only owner decision for a persisted proposal, valid with --resume")
    parser.add_argument("--approve-only", action="store_true",
        help="persist the fixture-owner approval, then stop before the one-use claim")
    args = parser.parse_args()
    if not args.fake_only:
        parser.error("--fake-only is required; this executable has no Binance order capability")
    if args.resume and not args.data_dir:
        parser.error("--resume requires --data-dir")
    if args.clock and not args.resume:
        parser.error("--clock is supported with --resume")
    if args.owner_decision and not args.resume:
        parser.error("--owner-decision is supported with --resume")
    if args.prepare_only and (args.resume or not args.data_dir):
        parser.error("--prepare-only requires --data-dir and cannot be combined with --resume")
    if args.approve_only and (not args.resume or args.owner_decision != "approve"):
        parser.error("--approve-only requires --resume --owner-decision approve")

    if args.resume:
        result = reopen_persisted_demo(args.data_dir, clock_at=args.clock,
            owner_decision=args.owner_decision, pause_after_approval=args.approve_only)
        print("C06-E offline durable paper runtime — reopened persisted synthetic state")
        print(json.dumps(result, sort_keys=True))
        return

    if args.prepare_only:
        result = prepare_persistent_proposal(args.data_dir)
        print("C06-E offline proposal prepared — fake owner decision is pending")
        print(json.dumps(result, sort_keys=True))
        return

    result = run_demo(data_dir=args.data_dir)
    negatives = run_negative_cases()
    positive = result["positive_trace"]
    print("C06-E offline durable paper runtime — SYNTHETIC / FAKE ONLY")
    print(f"Fixture: {result['fixture']}; OpenBot integration: {result['openbot_integration']}")
    print("Lifecycle: proposal -> fake owner approval -> one-use claim -> protected fill -> "
        "two targets -> first-fill 11h55m exit -> flat reconciliation")
    print("Terminal: {} quantity={}; plan status={}".format(
        positive["final_position_state"], positive["final_quantity"], positive["plan_status"]))
    print("Journal: {} events; digest={}".format(
        positive["journal_summary"]["event_count"], positive["journal_summary"]["event_digest"]))
    print("Negative cases: {}".format(json.dumps(negatives, sort_keys=True)))
    print("No network requests, credentials, Binance endpoints, or real owner MFA were used.")
    if args.data_dir:
        print("Stored evidence: " + json.dumps({name: str(args.data_dir / name) for name in
            ("c06_state.sqlite", "owner.sqlite", "venue.sqlite")}, sort_keys=True))


if __name__ == "__main__":
    main()
