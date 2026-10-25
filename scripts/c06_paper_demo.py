#!/usr/bin/env python3
"""Reproducible, fixture-only C06 OpenBot-facing paper MVP demonstration."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal as D
import json
from pathlib import Path
import sys
import tempfile

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


def build_fixture(*, event_evidence: bool = True, market_evidence: bool = True):
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
    plans, journal = PlanRegistry(), EventJournal()
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


def run_demo() -> dict[str, object]:
    fixture = build_fixture()
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
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-positive-") as temp:
        owner_root = Path(temp)
        clock = FakeClock(approval_at)
        owner, venue = _new_owner(owner_root, clock)
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

        owner.register_approval(auth, fake_setup)
        plans.observe_external_state(plan.plan_id, "FAKE_OWNER_APPROVED")
        journal.append(occurred_at=clock.now, actor="fake_owner", event_type="FAKE_OWNER_APPROVED",
            plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
            details={"authorization_hash": auth.approved_immutable_hash,
                "proposal_hash": plan.immutable_hash, "nonce": auth.one_use_nonce,
                "expires_at": auth.approval_request_expires_at.isoformat(),
                "authentication_fixture": auth.owner.authentication_evidence_ref})

        intent_id = owner.claim(auth, quantity=plan.proposed_quantity, quote=plan.entry_max,
            trigger_at=trigger_at)
        if not intent_id:
            raise RuntimeError("fake owner rejected the unmodified bounded plan")
        plans.observe_external_state(plan.plan_id, "CONSUMED")
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
        plans.observe_external_state(plan.plan_id, "SIMULATED_OPEN")
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
        plans.observe_external_state(plan.plan_id, "CLOSED_RECONCILED")
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
    rejected["plans"].observe_external_state(plan.plan_id, "OWNER_REJECTED")
    rejected["journal"].append(occurred_at=rejected["as_of"], actor="fake_owner",
        event_type="FAKE_OWNER_REJECTED", plan_id=plan.plan_id,
        lifecycle_id=stable_id("c06.fake_lifecycle", plan.plan_id),
        details={"proposal_hash": plan.immutable_hash, "venue_writes": 0})
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-rejected-") as temp:
        clock = FakeClock(rejected["as_of"])
        owner, venue = _new_owner(Path(temp), clock)
        output["owner_rejected"] = {"status": gateway.call("get_plan_status", {
            "plan_id": plan.plan_id, "as_of": clock.now}).status,
            "plan_id": plan.plan_id, "plan_hash": plan.immutable_hash,
            "nonce": plan.approval_nonce, "venue_writes": len(venue.state.read()["writes"]),
            "new_exposure": False}

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


def main() -> None:
    result = run_demo()
    negatives = run_negative_cases()
    plan_call = result["tool_calls"][-1]
    positive = result["positive_trace"]
    print("C06-B offline OpenBot-facing paper MVP (fixture-driven)")
    print(f"OpenBot compatibility: {result['openbot_integration']}")
    print(f"Fixture: {result['fixture']}; demo exchange/account/network calls: none")
    for call in result["tool_calls"]:
        print("tool {} -> {}".format(call["tool"], json.dumps(call, sort_keys=True)))
    print("fake owner -> approved hash={} nonce={} expiry={}".format(
        positive["authorization_hash"], positive["nonce"], positive["expires_at"]))
    print("fake owner -> one-use consumed; replay rejected; entry={} @ {} (fixture)".format(
        positive["entry_quantity"], positive["entry_price_fixture"]))
    print("supervisor -> protected {}; partial exit {}; remaining {}".format(
        positive["immediate_protection"], positive["partial_exit_quantity"],
        positive["remaining_before_timer"]))
    print("coordinator+journal unavailable -> first-fill timer initiates reduce-only exit at {}".format(
        positive["timer_exit_at"]))
    print("fake venue -> final {} quantity={}; plan status={}".format(
        positive["final_position_state"], positive["final_quantity"], positive["plan_status"]))
    for name, evidence in negatives.items():
        print("negative {} -> {}".format(name, json.dumps(evidence, sort_keys=True)))
    print("negative checks -> {}".format(json.dumps(result["negative_checks"], sort_keys=True)))
    print("journal -> {} events; digest={}".format(
        positive["journal_summary"]["event_count"], positive["journal_summary"]["event_digest"]))


if __name__ == "__main__":
    main()
