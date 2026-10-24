"""FAKE_TESTED only. Fxx -> established v1.5 acceptance IDs, not demo evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from threading import Barrier
import json
import socket

import pytest
from pydantic import ValidationError

from astrabot.contracts import (Anchor, BoundedGeometry, EconomicsV15, FixedGeometry,
    OwnerIdentity, PositionLifecycleV15, SetupSnapshotV15, Target, TradeAuthorizationV15,
    scenario_net_rr)
from c01_fake import FakeClock, FakeOwner, FakeVenue, TERMINAL

NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
AT_MAPPING = {
    "F01": ("AT08", "AT84", "AT105", "AT107"), "F02": ("AT122",),
    "F03": ("AT08", "AT106"), "F04": ("AT108",), "F05": ("AT11", "AT109"),
    "F06": ("AT12", "AT27", "AT56", "AT121"), "F07": ("AT13", "AT87"),
    "F08": ("AT49", "AT50", "AT55", "AT56", "AT57", "AT114"),
    "F09": ("AT43", "AT51", "AT52", "AT53", "AT54", "AT113"),
    "F10": ("AT110", "AT111"), "F11": ("AT14", "AT88", "AT112", "AT115", "AT121"),
    "F12": ("AT27", "AT28", "AT29", "AT121"), "F13": ("AT84", "AT106"),
    "F14": ("AT100",), "F15": ("AT100",), "F16": ("AT112", "AT115"),
}
# AT37/85/86/89 (technical sole-writer/account-mode access) are NOT established
# by a fake. Source evidence and future demo/operational qualification live in ADR.


def setup_auth(n="1", *, side="LONG", symbol=None, mode="PREAPPROVED_ARMED_PLAN", **changes):
    symbol = symbol or "ALT" + n + "USDT"
    setup = SetupSnapshotV15(setup_id="setup-" + n, strategy_version="FAKE_QUALIFIED_FIXTURE_ONLY",
        strategy_policy_hash="strategy-v1", symbol=symbol, side=side, source_snapshot_id="snapshot-" + n,
        formed_event_id="formed-" + n,
        anchors=(Anchor(anchor_id="anchor-" + n, source_event_id="anchor-event-" + n, price="99", available_at=NOW - timedelta(minutes=1)),),
        frozen_atr="1", tolerance=".1", original_risk_parameters_hash="original-risk-v1",
        context_at_formation="original-context", formed_at=NOW - timedelta(minutes=1), available_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30), state="ARMED")
    g = FixedGeometry(original_stop="99" if side == "LONG" else "101",
        targets=(Target(price="103" if side == "LONG" else "97", fraction=".4"),
                 Target(price="105" if side == "LONG" else "95", fraction=".6")))
    auth = TradeAuthorizationV15(plan_id="plan-" + n, setup_id=setup.setup_id, lifecycle_id="life-" + n,
        one_use_nonce="nonce-" + n, approved_immutable_hash="pending",
        owner=OwnerIdentity(owner_ref="fake-owner", authentication_evidence_ref="fake-auth", mfa_evidence_ref="fake-mfa"),
        mode=mode, symbol=symbol, side=side, strategy_version=setup.strategy_version, strategy_policy_hash=setup.strategy_policy_hash,
        trigger_policy_hash="trigger-v1", management_policy_hash="manage-v1", frozen_anchor_ids=("anchor-" + n,),
        entry_min="99.9", entry_max="100.1", quantity_max="10", notional_max="1100", leverage_max="2",
        approved_max_risk_usdt="25", cost_profile_hash="fake-cost-v1", stop_cost_per_unit=".1", target_cost_per_unit=".1",
        geometry=g, readiness_ref="ready-1", event_veto_ref="event-1", risk_veto_ref="risk-1", approved_at=NOW,
        approval_request_expires_at=NOW + timedelta(seconds=90), armed_expires_at=NOW + timedelta(minutes=30),
        setup_expires_at=setup.expires_at, data_event_expires_at=NOW + timedelta(minutes=30),
        trigger_submit_deadline_ms=1000, state="APPROVED_ARMED")
    if changes:
        auth = TradeAuthorizationV15.model_validate_json(auth.model_copy(update=changes).model_dump_json())
    auth = auth.model_copy(update={"approved_immutable_hash": auth.immutable_hash()})
    return setup, auth


@pytest.fixture
def world(tmp_path):
    clock = FakeClock(NOW)
    venue = FakeVenue(tmp_path / "venue.sqlite", clock)
    owner = FakeOwner(tmp_path / "ledger.sqlite", venue, clock)
    owner.reconnect()
    return owner, venue, clock


def prepare(world, n="1", **kwargs):
    owner, _, _ = world
    setup, auth = setup_auth(n, **kwargs)
    owner.register_approval(auth, setup)
    return auth


def enter(world, n="1", *, quantity=D("10"), result="ACKNOWLEDGED", **kwargs):
    owner, _, clock = world
    auth = prepare(world, n, **kwargs)
    intent = owner.claim(auth, quantity=quantity, quote=D("100"), trigger_at=clock.now)
    assert intent
    owner.submit(intent, result=result)
    return auth, intent, "entry-" + auth.plan_id


def filled(world, **kwargs):
    auth, intent, cid = enter(world, **kwargs)
    owner, venue, _ = world
    venue.fill(cid, "fill-" + auth.plan_id, "10", "100")
    owner.detect_fills()
    return auth, intent, cid


def pos(owner, auth):
    return owner.ledger.read()["positions"][auth.lifecycle_id]


@pytest.mark.parametrize("fault", ["missing", "invalid_owner", "hash", "expired", "disarmed", "symbol", "quantity", "readiness", "event", "risk", "replay"])
def test_f01_unauthorized_entry_zero_writes(world, fault):
    owner, venue, clock = world
    auth = prepare(world)
    extra, q = {}, D("10")
    if fault == "missing":
        auth = None
    elif fault == "invalid_owner":
        auth = auth.model_copy(update={"owner": OwnerIdentity(owner_ref="impostor", authentication_evidence_ref="fake-auth", mfa_evidence_ref="fake-mfa")})
    elif fault == "hash":
        auth = auth.model_copy(update={"approved_immutable_hash": "wrong"})
    elif fault == "expired":
        clock.advance(minutes=31)
    elif fault == "disarmed":
        auth = auth.model_copy(update={"state": "DISARMED"})
    elif fault == "symbol":
        auth = auth.model_copy(update={"symbol": "OTHERUSDT"})
    elif fault == "quantity":
        q = D("11")
    elif fault in {"readiness", "event", "risk"}:
        extra[{"readiness": "readiness", "event": "event_ok", "risk": "risk_ok"}[fault]] = False
    elif fault == "replay":
        assert owner.claim(auth, quantity=q, quote=D("100"), trigger_at=NOW)
    assert owner.claim(auth, quantity=q, quote=D("100"), trigger_at=clock.now, **extra) is None
    assert venue.state.read()["writes"] == []


def test_f02_callback_exception_and_force_route_fail_closed(world):
    owner, venue, _ = world
    auth = prepare(world)
    def broken():
        raise RuntimeError("callback failure")
    assert owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW, callback=broken) is None
    assert owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW, callback=lambda: False) is None
    # Alternate route cannot submit an unpersisted authorized intent.
    with pytest.raises(KeyError):
        owner.submit("force-entry-without-approval")
    assert venue.state.read()["writes"] == []


def test_f03_atomic_consumption_actual_thread_contention(world):
    owner, venue, _ = world
    auth = prepare(world)
    barrier = Barrier(8)
    def contender(_):
        barrier.wait()
        return owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW)
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(contender, range(8)))
    assert sum(x is not None for x in claims) == 1
    assert len(owner.ledger.read()["intents"]) == 1
    owner.submit(next(x for x in claims if x))
    assert len(venue.state.read()["writes"]) == 1


def test_f04_reservation_cas_and_risk_slots_contention(world):
    owner, _, _ = world
    approvals = [prepare(world, str(i)) for i in range(4)]
    version = owner.ledger.read()["version"]
    barrier = Barrier(4)
    def contender(auth):
        barrier.wait()
        return owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW, expected_version=version)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(contender, approvals))
    assert sum(x is not None for x in results) == 1
    remaining = [a for a, r in zip(approvals, results) if r is None]
    # Fresh contenders with no stale CAS still compete atomically for last slot.
    barrier = Barrier(3)
    def retry(auth):
        barrier.wait()
        return owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(retry, remaining))
    assert sum(x is not None for x in results) == 1
    active = owner.ledger.read()["reservations"].values()
    assert sum(D(r["risk"]) for r in active) == D("50")
    assert len(active) == 2


@pytest.mark.parametrize("constraint", ["pertrade", "leverage", "symbol"])
def test_f04_separate_account_constraints(world, constraint):
    owner, _, _ = world
    if constraint == "pertrade":
        auth = prepare(world, approved_max_risk_usdt=D("25.01"))
        q = D(1)
    elif constraint == "leverage":
        # Risk is tiny; only notional > 2x rejects this claim.
        g = FixedGeometry(original_stop="99.99", targets=(Target(price="101", fraction="1"),))
        auth = prepare(world, quantity_max=D(210), notional_max=D(22000), entry_min=D(100), entry_max=D(100), geometry=g, stop_cost_per_unit=D(0))
        q = D(201)
    else:
        first = prepare(world, "first", symbol="SAMEUSDT")
        assert owner.claim(first, quantity=D(1), quote=D(100), trigger_at=NOW)
        auth = prepare(world, "second", symbol="SAMEUSDT")
        q = D(1)
    assert owner.claim(auth, quantity=q, quote=D(100), trigger_at=NOW) is None


def test_f05_unknown_ioc_reconciles_original_without_duplicate(world):
    owner, venue, _ = world
    auth, iid, cid = enter(world, result="UNKNOWN")
    assert owner.ledger.read()["intents"][iid]["state"] == "UNKNOWN_SUBMISSION"
    assert owner.ledger.read()["reservations"]["res-" + auth.plan_id]["status"] == "UNKNOWN"
    venue.fill(cid, "lost-response-fill", "10", "100")
    owner.submit(iid)
    owner.reconnect()
    owner.detect_fills()
    assert owner.ledger.read()["intents"][iid]["state"] == "RECONCILED"
    assert len([w for w in venue.state.read()["writes"] if not w["params"]["close_position"]]) == 1
    assert pos(owner, auth)["quantity"] == "10"


def test_f06_partial_out_of_order_dedup_and_immediate_protection(world):
    owner, venue, clock = world
    auth, _, cid = enter(world)
    venue.fill(cid, "second", "3", "100", at=NOW + timedelta(seconds=1))
    clock.advance(seconds=2)
    owner.detect_fills()
    p = pos(owner, auth)
    assert p["quantity"] == "3" and p["first_fill_at"] == (NOW + timedelta(seconds=1)).isoformat()
    assert len(p["stop_ids"]) == 1 and p["risk_final"] is None
    venue.fill(cid, "first", "2", "99.9", at=NOW)
    venue.fill(cid, "first", "2", "99.9", at=NOW)
    owner.detect_fills()
    assert pos(owner, auth)["quantity"] == "5"
    assert pos(owner, auth)["first_fill_at"] == NOW.isoformat()
    assert len(pos(owner, auth)["stop_ids"]) == 1  # whole-position fake coverage
    latency = owner.ledger.read()["latencies"][auth.lifecycle_id]
    assert latency["detected_at"] != latency["exchange_first_fill_at"]


@pytest.mark.parametrize("result,delay", [("REJECTED", 0), ("UNKNOWN", 0), ("ABSENT", 0), ("ACKNOWLEDGED", 2001)])
def test_f07_missing_stop_or_detection_deadline_emergency(world, result, delay):
    owner, venue, _ = world
    auth, _, cid = enter(world)
    venue.stop_ack_delay_ms = delay
    venue.fill(cid, "initial", "4", "100")
    owner.detect_fills(stop_result=result)
    state = owner.ledger.read()
    p = pos(owner, auth)
    assert state["fault_halt"] and p["latch"] and p["quantity"] == "4"
    assert p["state"] == "EXIT_REQUESTED"  # submission is never proof flat
    exits = [w for w in venue.state.read()["writes"] if w["params"]["kind"] == "MARKET"]
    assert len(exits) == 1 and exits[0]["params"]["reduce_only"]
    assert state["faults"][-1] == ("PROTECTION_DEADLINE" if delay > 2000 else "MISSING_PROTECTION")


def test_f07_exact_two_second_boundary_protected(world):
    owner, venue, _ = world
    venue.stop_ack_delay_ms = 2000
    auth, _, cid = enter(world)
    venue.fill(cid, "initial", "4", "100")
    owner.detect_fills()
    assert pos(owner, auth)["stop_ids"]
    assert not owner.ledger.read()["fault_halt"]


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize("stop_first", [True, False])
def test_f08_two_target_and_stop_races_never_reverse(world, side, stop_first):
    owner, venue, _ = world
    auth, _, _ = filled(world, side=side)
    tp1, tp2 = owner.add_targets(auth.lifecycle_id)
    stop = pos(owner, auth)["stop_ids"][0]
    venue.price_touch("105")
    assert pos(owner, auth)["quantity"] == "10"
    tp1_price = "103" if side == "LONG" else "97"
    venue.fill(tp1, "tp-part-2", "1", tp1_price, at=NOW + timedelta(seconds=2))
    venue.fill(tp1, "tp-part-1", "1", tp1_price, at=NOW + timedelta(seconds=1))
    venue.fill(tp1, "tp-part-1", "1", tp1_price)
    owner.detect_fills()
    assert pos(owner, auth)["quantity"] == "8"
    ordered = [stop, tp2] if stop_first else [tp2, stop]
    for index, cid in enumerate(ordered):
        price = ("105" if side == "LONG" else "95") if cid == tp2 else ("99" if side == "LONG" else "101")
        venue.fill(cid, "race-" + str(index), "100", price)
    assert D(venue.state.read()["orders"][tp1]["filled"]) == D(2)
    assert D(venue.state.read()["orders"][tp2]["filled"]) == (D(0) if stop_first else D(6))
    assert D(venue.state.read()["orders"][tp2]["filled"]) <= D(6)
    owner.detect_fills()
    assert D(venue.state.read()["positions"][auth.lifecycle_id]) == 0
    assert D(pos(owner, auth)["quantity"]) == 0
    assert all(venue.state.read()["orders"][cid]["params"]["reduce_only"] for cid in (tp1, tp2))


@pytest.mark.parametrize("case", ["unsafe", "widen", "REJECTED", "UNKNOWN", "ABSENT", "success"])
def test_f09_stop_replacement_never_cancel_first(world, case):
    owner, venue, _ = world
    auth, _, _ = filled(world)
    old = pos(owner, auth)["stop_ids"][0]
    accepted = owner.tighten(auth.lifecycle_id, D("98") if case == "widen" else D("99.5"),
        overlap_safe=case != "unsafe", result=case if case in {"REJECTED", "UNKNOWN", "ABSENT"} else "ACKNOWLEDGED")
    if case == "success":
        assert accepted and venue.state.read()["orders"][old]["status"] == "CANCELLED"
        assert len(pos(owner, auth)["stop_ids"]) == 2
    else:
        assert not accepted and venue.state.read()["orders"][old]["status"] == "ACKNOWLEDGED"
        assert pos(owner, auth)["stop_ids"] == [old]


def test_f10_exit_latch_cancel_unknown_and_late_fill_reduced(world):
    owner, venue, _ = world
    auth, iid, cid = enter(world)
    venue.fill(cid, "partial", "3", "100")
    owner.detect_fills()
    owner.latch(auth.lifecycle_id, "THESIS_INVALID", cancel_unknown=True)
    assert venue.state.read()["orders"][cid]["status"] == "UNKNOWN_CANCEL"
    exit1 = next(k for k in venue.state.read()["orders"] if k.startswith("exit-"))
    venue.fill(exit1, "exit-first", "3", "100")
    venue.fill(cid, "late-fill", "2", "100", at=NOW + timedelta(seconds=1), late=True)
    owner.detect_fills()
    exits = [k for k in venue.state.read()["orders"] if k.startswith("exit-")]
    assert len(exits) == 2
    venue.fill(exits[-1], "exit-late", "2", "100")
    owner.detect_fills()
    owner.submit(iid)
    assert len([w for w in venue.state.read()["writes"] if w["client_id"].startswith("entry-")]) == 1
    assert D(pos(owner, auth)["quantity"]) == 0 and pos(owner, auth)["latch"]
    assert not owner.terminal(auth.lifecycle_id)  # pending entry and protection remain


def test_f11_restart_new_objects_restores_unknown_and_protection_before_entry(world, tmp_path):
    owner, venue, clock = world
    auth, iid, cid = enter(world, result="UNKNOWN")
    venue.fill(cid, "partial", "3", "100")
    owner.detect_fills()
    original = pos(owner, auth)
    replacement_venue = FakeVenue(tmp_path / "venue.sqlite", clock)
    restarted = FakeOwner(tmp_path / "ledger.sqlite", replacement_venue, clock)
    new = prepare((restarted, replacement_venue, clock), "new")
    assert restarted.claim(new, quantity=D(1), quote=D(100), trigger_at=NOW) is None
    replacement_venue.connected = False
    assert not restarted.reconnect()
    replacement_venue.connected = True
    assert not restarted.reconnect(disagree=True)
    assert restarted.claim(new, quantity=D(1), quote=D(100), trigger_at=NOW) is None
    assert restarted.reconnect()
    restored = pos(restarted, auth)
    assert restored["first_fill_at"] == original["first_fill_at"] and restored["stop_ids"] == original["stop_ids"]
    assert restarted.ledger.read()["intents"][iid]["state"] == "RECONCILED"
    assert restarted.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW) is None


def test_f12_hold_clock_restart_later_fills_and_disconnect(world, tmp_path):
    owner, venue, clock = world
    auth, _, cid = enter(world)
    venue.fill(cid, "first", "2", "100")
    owner.detect_fills()
    clock.advance(minutes=10)
    venue.fill(cid, "later", "2", "100")
    owner.detect_fills()
    clock.advance(hours=11, minutes=44, seconds=59)
    owner.timers()
    assert not pos(owner, auth)["latch"]
    # Restart exactly at +11h55m, restore clock from durable first fill.
    clock.advance(seconds=1)
    restarted = FakeOwner(tmp_path / "ledger.sqlite", FakeVenue(tmp_path / "venue.sqlite", clock), clock)
    restarted.reconnect()
    assert pos(restarted, auth)["latch"]["reason"] == "TIME_LIMIT"
    assert pos(restarted, auth)["first_fill_at"] == NOW.isoformat()
    restarted.venue.connected = False
    clock.advance(minutes=5)
    restarted.timers()
    assert "TIME_EXIT_BREACH" in restarted.ledger.read()["faults"]
    assert pos(restarted, auth)["state"] == "EXIT_REQUESTED"
    assert not restarted.ledger.read()["reconciled"]
    restarted.venue.connected = True
    restarted.reconnect()
    assert any(k.startswith("exit-") for k in restarted.venue.state.read()["orders"])


@pytest.mark.parametrize("side,bad,limit", [("LONG", "100.11", "100.1"), ("SHORT", "99.89", "99.9")])
def test_f13_ioc_side_correct_adverse_bound(world, side, bad, limit):
    owner, venue, _ = world
    auth = prepare(world, side=side)
    assert owner.claim(auth, quantity=D(1), quote=D(bad), trigger_at=NOW) is None
    iid = owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW)
    owner.submit(iid)
    order = venue.state.read()["orders"]["entry-" + auth.plan_id]
    assert order["params"]["price"] == limit and order["params"]["time_in_force"] == "IOC"
    with pytest.raises(ValueError):
        venue.fill("entry-" + auth.plan_id, "bad", "1", bad)
    # A favorable fill below the long corridor is possible for a buy limit.
    if side == "LONG":
        assert venue.fill("entry-" + auth.plan_id, "favorable", "1", "99") == 1


def test_f14_b1_exact_ladder_and_cost_boundary():
    gross = D(".4") * D(1) + D(".6") * D(2)
    assert gross == D("1.6")
    assert scenario_net_rr(gross, D(1), D(".04"), D(".04")) == D("1.5")
    assert scenario_net_rr(gross, D(1), D(".04001"), D(".04001")) < D("1.5")
    assert scenario_net_rr(gross, D(1), D(".25"), D(".25")) == D("1.08")


def test_f15_initial_risk_actual_quantity_costs_and_immutable_denominator(world):
    owner, venue, _ = world
    auth, _, cid = enter(world)
    venue.fill(cid, "partial", "4", "100")
    owner.detect_fills()
    assert pos(owner, auth)["risk_final"] is None
    venue.cancel(cid)
    owner.detect_fills()
    assert D(pos(owner, auth)["risk_final"]) == D("4.4")
    assert auth.approved_max_risk_usdt == D(25)
    tp1, _ = owner.add_targets(auth.lifecycle_id)
    venue.fill(tp1, "target", "1.6", "103")
    owner.detect_fills()
    owner.tighten(auth.lifecycle_id, D("99.5"), overlap_safe=True)
    assert D(pos(owner, auth)["risk_final"]) == D("4.4")
    record = EconomicsV15(approved_max_risk_usdt="25", actual_entry_quantity="4", weighted_initial_entry="100",
        original_stop="99", modeled_stop_cost_per_unit=".1", initial_entry_terminal=True,
        realized_net_pnl_usdt="4.4", realized_fees_usdt=".2", realized_funding_usdt="-.1", cost_profile_hash="cost-v1")
    assert record.d0_price == 1 and record.initial_modeled_risk_usdt == D("4.4")
    assert record.cost_r == D(".1") and record.net_r == 1
    assert scenario_net_rr(D("1.6"), D(1), D(".1"), D(".1")) != record.net_r
    nofill = EconomicsV15.model_validate_json(record.model_copy(update={"actual_entry_quantity": D(0), "weighted_initial_entry": None,
        "realized_net_pnl_usdt": D(0)}).model_dump_json())
    assert nofill.net_r is None and nofill.initial_modeled_risk_usdt == 0


@pytest.mark.parametrize("unresolved", ["unknown_entry", "working_stop", "working_tp", "unknown_exit", "uncorrelated"])
def test_f16_flat_snapshot_or_operation_failure_not_terminal(world, unresolved):
    owner, venue, _ = world
    auth, iid, cid = filled(world)
    stop = pos(owner, auth)["stop_ids"][0]
    targets = owner.add_targets(auth.lifecycle_id)
    venue.fill(stop, "stop-fill", "10", "99")
    for k in targets:
        venue.cancel(k)
    if unresolved == "unknown_entry":
        owner.ledger.change(lambda s: s["intents"][iid].update(state="UNKNOWN_SUBMISSION", client_order_id="lost-original-id"))
    elif unresolved == "working_stop":
        owner.tighten(auth.lifecycle_id, D("99.5"), overlap_safe=True)  # terminal old -> no replacement
        # an orphan algo still requires cancellation, even with flat position
        venue.state.change(lambda s: s["orders"][stop].update(status="ACKNOWLEDGED"))
    elif unresolved == "working_tp":
        venue.state.change(lambda s: s["orders"][targets[0]].update(status="ACKNOWLEDGED"))
    elif unresolved == "unknown_exit":
        owner.ledger.change(lambda s: s.setdefault("management", {}).update({"unknown-exit": {"lifecycle_id": auth.lifecycle_id, "params": {"kind": "MARKET"}, "status": "FAILED"}}))
    assert not owner.terminal(auth.lifecycle_id, correlated=unresolved != "uncorrelated")
    assert pos(owner, auth)["state"] != "FLAT_RECONCILED"
    assert owner.ledger.read()["reservations"]["res-" + auth.plan_id]["status"] != "RELEASED"


def test_f16_proven_flat_and_cleared_orders_releases_reservation(world):
    owner, venue, _ = world
    auth, _, _ = filled(world)
    stop = pos(owner, auth)["stop_ids"][0]
    venue.fill(stop, "stop-fill", "10", "99")
    assert owner.terminal(auth.lifecycle_id)
    assert pos(owner, auth)["state"] == "FLAT_RECONCILED"
    assert owner.ledger.read()["reservations"]["res-" + auth.plan_id]["status"] == "RELEASED"


def test_daily_utc_halt_latches_without_flatten_and_accounts_transfers(world):
    owner, venue, clock = world
    auth, _, _ = filled(world)
    writes = len(venue.state.read()["writes"])
    owner.mark_equity(D(11000), net_external_transfer=D(1000))
    assert not owner.ledger.read()["daily_halt"]
    owner.mark_equity(D(10890))  # 1% of transfer-adjusted baseline
    assert owner.ledger.read()["daily_halt"]
    owner.mark_equity(D(11200))
    assert owner.ledger.read()["daily_halt"]
    assert not pos(owner, auth)["latch"] and len(venue.state.read()["writes"]) == writes
    new = prepare(world, "daily")
    assert owner.claim(new, quantity=D(1), quote=D(100), trigger_at=NOW) is None
    clock.advance(hours=12)
    owner.mark_equity(D(11200))
    assert not owner.ledger.read()["daily_halt"]


def test_real_post_trigger_clock_includes_owner_delay(world):
    owner, _, clock = world
    auth = prepare(world, mode="POST_TRIGGER_APPROVAL")
    assert owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW - timedelta(milliseconds=600))
    late = prepare(world, "late", mode="POST_TRIGGER_APPROVAL")
    clock.advance(milliseconds=500)
    assert owner.claim(late, quantity=D(1), quote=D(100), trigger_at=NOW - timedelta(milliseconds=600)) is None


def test_bounded_formula_hashed_anchors_and_risk_recheck(world):
    owner, _, _ = world
    formula = BoundedGeometry(source_id="future-approved-event", permitted_anchor_type="CONFIRMED_SWING",
        anchor_min="98.9", anchor_max="99.1", stop_offset="0", max_stop_distance="1.2",
        target_multiples=(D(3), D(5)), target_fractions=(D(".4"), D(".6")),
        minimum_scenario_net_rr="1.5", anchor_deadline=NOW + timedelta(seconds=1))
    auth = prepare(world, geometry=formula)
    evidence = {"anchor": Anchor(anchor_id="future-anchor", source_event_id="future-approved-event", price="99", available_at=NOW),
        "anchor_type": "CONFIRMED_SWING"}
    assert owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW) is None
    assert owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW, geometry=evidence)
    with pytest.raises(ValidationError):
        BoundedGeometry.model_validate_json('{"kind":"ARBITRARY_UNBOUNDED_FORMULA","formula":"anything"}')
    with pytest.raises(ValueError):
        formula.resolve(entry=D(100), side="LONG", now=NOW, anchor=Anchor(anchor_id="bad", source_event_id="unapproved", price="99", available_at=NOW), anchor_type="CONFIRMED_SWING")


def test_setup_frozen_anchors_monotonic_and_strict_wire():
    setup, auth = setup_auth()
    confirmed = setup.advance("CONFIRMED", confirmed_at=NOW, confirmed_event_id="confirmed-1")
    consumed = confirmed.advance("CONSUMED", consumed_by="plan-1")
    with pytest.raises(ValueError):
        consumed.advance("ARMED")
    with pytest.raises(ValueError):
        setup.advance("CONFIRMED", anchors=())
    with pytest.raises(ValidationError):
        Target(price=100.0, fraction="1")
    wire = json.loads(auth.model_dump_json())
    wire["entry_max"] = 100.1
    with pytest.raises(ValidationError):
        TradeAuthorizationV15.model_validate_json(json.dumps(wire))
    wire = json.loads(setup.model_dump_json())
    wire["formed_at"] = "2026-10-24T11:59:00"
    with pytest.raises(ValidationError):
        SetupSnapshotV15.model_validate_json(json.dumps(wire))
    with pytest.raises(AssertionError, match="prohibit"):
        socket.socket()


def test_late_fill_after_risk_finalization_preserves_denominator_and_faults(world):
    owner, venue, _ = world
    auth, _, cid = enter(world)
    venue.fill(cid, "known", "3", "100")
    venue.cancel(cid)
    owner.detect_fills()
    risk = pos(owner, auth)["risk_final"]
    venue.fill(cid, "late-discovered", "2", "100", late=True)
    owner.detect_fills()
    assert pos(owner, auth)["quantity"] == "5"
    assert pos(owner, auth)["risk_final"] == risk
    assert "LATE_FILL_AFTER_FINALIZATION" in owner.ledger.read()["faults"]
    assert owner.ledger.read()["fault_halt"]


@pytest.mark.parametrize("veto", ["deadline", "quote", "readiness", "event", "risk", "daily"])
def test_claim_cannot_delay_or_bypass_fresh_submission_checks(world, veto):
    owner, venue, clock = world
    auth = prepare(world)
    iid = owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW)
    kwargs = {}
    if veto == "deadline":
        clock.advance(milliseconds=1001)
    elif veto == "quote":
        kwargs["quote"] = D("101")
    elif veto in {"readiness", "event", "risk"}:
        kwargs[{"readiness": "readiness", "event": "event_ok", "risk": "risk_ok"}[veto]] = False
    else:
        owner.mark_equity(D(9900))
    owner.submit(iid, **kwargs)
    assert venue.state.read()["writes"] == []
    assert owner.ledger.read()["intents"][iid]["state"] == "REJECTED"
    assert auth.plan_id in owner.ledger.read()["consumed"]


def test_restart_absent_unknown_and_unowned_position_remain_closed(world, tmp_path):
    owner, venue, clock = world
    auth = prepare(world)
    iid = owner.claim(auth, quantity=D(1), quote=D(100), trigger_at=NOW)
    venue.connected = False
    owner.submit(iid)
    assert owner.ledger.read()["intents"][iid]["state"] == "UNKNOWN_SUBMISSION"
    restarted = FakeOwner(tmp_path / "ledger.sqlite", FakeVenue(tmp_path / "venue.sqlite", clock), clock)
    assert not restarted.reconnect()
    assert not restarted.ready and not restarted.ledger.read()["reconciled"]
    restarted.venue.state.change(lambda s: s["positions"].update({"manual-unowned": "2"}))
    assert not restarted.reconnect()
    assert "UNOWNED_POSITION" in restarted.ledger.read()["faults"]


def test_restart_missing_stop_reverified_and_protected_before_ready(world, tmp_path):
    owner, venue, clock = world
    auth, _, _ = filled(world)
    old = pos(owner, auth)["stop_ids"][0]
    venue.cancel(old)
    restarted = FakeOwner(tmp_path / "ledger.sqlite", FakeVenue(tmp_path / "venue.sqlite", clock), clock)
    assert restarted.reconnect()
    p = pos(restarted, auth)
    assert old not in p["stop_ids"] and len(p["stop_ids"]) == 1
    assert restarted.venue.state.read()["orders"][p["stop_ids"][0]]["status"] == "ACKNOWLEDGED"


def test_stop_trigger_latches_late_remainder_and_ttl_cancels(world):
    owner, venue, clock = world
    auth, _, cid = enter(world)
    venue.fill(cid, "partial", "2", "100")
    owner.detect_fills()
    stop = pos(owner, auth)["stop_ids"][0]
    venue.fill(stop, "stop-first", "2", "99")
    owner.detect_fills()
    assert pos(owner, auth)["latch"]["reason"] == "STOP_TRIGGERED"
    assert venue.state.read()["orders"][cid]["status"] == "CANCELLED"
    venue.fill(cid, "late-original-fill", "1", "100", late=True)
    owner.detect_fills()
    assert any(k.startswith("exit-") for k in venue.state.read()["orders"])
    assert pos(owner, auth)["quantity"] == "1"


def test_entry_ttl_ten_seconds_preserves_uncertain_exposure(world):
    owner, venue, clock = world
    auth, _, cid = enter(world)
    venue.fill(cid, "partial", "2", "100")
    owner.detect_fills()
    clock.advance(seconds=10)
    owner.timers()
    assert venue.state.read()["orders"][cid]["status"] == "CANCELLED"
    assert pos(owner, auth)["quantity"] == "2" and pos(owner, auth)["stop_ids"]
    assert not owner.terminal(auth.lifecycle_id)


def position_contract(**changes):
    payload = dict(lifecycle_id="life", management_policy_hash="manage-v1", first_fill_at=NOW,
        initial_filled_quantity=D(4), remaining_quantity=D(4), verified_stop_ids=("stop-1",), verified_tp_ids=(),
        exit_latch=None, outstanding_entry_ids=(), outstanding_exit_ids=(), outstanding_algo_ids=("stop-1",),
        reconciliation="CONSISTENT", approved_max_risk_usdt=D(25), initial_modeled_risk_usdt=D("4.4"),
        d0_price=D(1), initial_entry_terminal=True, initial_entry_reconciliation_ref="fake-terminal-fill-proof",
        state="SUPERVISED", action_version=1)
    return PositionLifecycleV15(**{**payload, **changes})


def test_contract_position_observed_risk_breach_and_frozen_history():
    position = position_contract()
    reduced = position.revise(remaining_quantity=D(2))
    assert reduced.action_version == 2 and reduced.initial_modeled_risk_usdt == D("4.4")
    for changes in ({"first_fill_at": NOW + timedelta(seconds=1)}, {"initial_modeled_risk_usdt": D(2)},
                    {"d0_price": D(".5")}, {"approved_max_risk_usdt": D(30)},
                    {"management_policy_hash": "other"}, {"lifecycle_id": "other"},
                    {"initial_filled_quantity": D(6)}, {"action_version": 100}, {"initial_entry_terminal": False}):
        with pytest.raises(ValueError):
            position.revise(**changes)
    with pytest.raises(ValueError):
        position_contract(initial_entry_reconciliation_ref=None)
    # Actual adverse fills can exceed the modeled authorization; record truth.
    breached = position_contract(initial_modeled_risk_usdt=D(30), state="RECONCILING")
    assert breached.initial_modeled_risk_usdt > breached.approved_max_risk_usdt
    earlier = position.revise(first_fill_at=NOW - timedelta(seconds=1))
    assert earlier.first_fill_at < position.first_fill_at


def test_contract_intent_unknown_cannot_resubmit_or_change_identity(world):
    from astrabot.contracts import OrderIntentV15
    owner, _, _ = world
    _, iid, _ = enter(world, result="UNKNOWN")
    intent = OrderIntentV15.model_validate_json(json.dumps(owner.ledger.read()["intents"][iid]))
    with pytest.raises(ValueError):
        intent.advance("SUBMITTED")
    with pytest.raises(ValueError):
        intent.advance("RECONCILED")
    reconciled = intent.advance("RECONCILED", exchange_order_id="original-id", reconciliation_evidence=("snapshot",))
    assert reconciled.action_version == intent.action_version + 1
    with pytest.raises(ValueError):
        reconciled.advance("FILLED", exchange_order_id="other-id")
    with pytest.raises(ValueError):
        reconciled.advance("FILLED", request=intent.request)
    schema = TradeAuthorizationV15.model_json_schema()
    assert schema["properties"]["quantity_max"]["type"] == "string"
    assert schema["properties"]["leverage_max"]["type"] == "string"


def test_contract_terminal_requires_correlated_proof_and_cleared_instructions():
    from astrabot.contracts import TerminalProof
    proof = TerminalProof(correlated_boundary_id="boundary", confirmed_at=NOW, venue_quantity="0",
        all_entry_intents_terminal=True, all_exit_orders_terminal=True, all_algo_orders_terminal=True)
    with pytest.raises(ValueError):
        position_contract(state="FLAT_RECONCILED", remaining_quantity=D(0), terminal_proof=proof)
    closed = position_contract(state="FLAT_RECONCILED", remaining_quantity=D(0), terminal_proof=proof,
        outstanding_algo_ids=(), verified_stop_ids=())
    # A past modeled-risk breach remains factual after verified closure; it
    # cannot prevent recording flatness or rewrite the original denominator.
    closed_breach = position_contract(state="FLAT_RECONCILED", remaining_quantity=D(0), terminal_proof=proof,
        outstanding_algo_ids=(), verified_stop_ids=(), initial_modeled_risk_usdt=D(30))
    assert closed_breach.initial_modeled_risk_usdt == D(30)
    assert closed_breach.approved_max_risk_usdt == D(25)
    with pytest.raises(ValueError):
        closed.revise(state="SUPERVISED")


@pytest.mark.parametrize("previous_state", ["ACKNOWLEDGED", "RECONCILED"])
def test_f16_missing_original_nonterminal_entry_not_proof_flat(world, previous_state):
    owner, venue, _ = world
    auth, iid, cid = enter(world)
    venue.fill(cid, "partial", "3", "100")
    owner.detect_fills()
    if previous_state == "RECONCILED":
        owner.ledger.change(lambda s: s["intents"][iid].update(state="RECONCILED", reconciliation_evidence=["earlier-boundary"]))
    stop = pos(owner, auth)["stop_ids"][0]
    venue.fill(stop, "stop-partial", "3", "99")
    venue.state.change(lambda s: s["orders"].pop(cid))
    assert not owner.terminal(auth.lifecycle_id)
    assert not pos(owner, auth)["entry_terminal"]
    assert pos(owner, auth)["state"] != "FLAT_RECONCILED"
    assert owner.ledger.read()["reservations"]["res-" + auth.plan_id]["status"] != "RELEASED"


def test_original_setup_expiry_cannot_be_extended_or_skipped_before_send(world):
    owner, venue, clock = world
    setup, auth = setup_auth()
    early_setup = SetupSnapshotV15.model_validate_json(setup.model_copy(update={"expires_at": NOW + timedelta(milliseconds=500)}).model_dump_json())
    with pytest.raises(ValueError, match="expiry"):
        owner.register_approval(auth, early_setup)
    bounded_auth = TradeAuthorizationV15.model_validate_json(auth.model_copy(update={"setup_expires_at": early_setup.expires_at}).model_dump_json())
    bounded_auth = bounded_auth.model_copy(update={"approved_immutable_hash": bounded_auth.immutable_hash()})
    owner.register_approval(bounded_auth, early_setup)
    iid = owner.claim(bounded_auth, quantity=D(1), quote=D(100), trigger_at=NOW)
    assert iid
    clock.advance(milliseconds=600)
    owner.submit(iid)
    assert venue.state.read()["writes"] == []
    assert owner.ledger.read()["intents"][iid]["state"] == "REJECTED"
