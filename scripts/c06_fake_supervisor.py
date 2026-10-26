#!/usr/bin/env python3
"""Independent deterministic supervisor for the C06 synthetic paper fixture."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

from astrabot.c06.paper_mvp import EventJournal, PlanRegistry
from astrabot.data.models import stable_id
from c01_fake import FakeClock, FakeOwner, FakeVenue
from c06_fixture_paths import prepare_synthetic_state_dir
from c06_paper_demo import build_fixture


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _read_state_file(path: Path, default: dict) -> dict:
    if not path.is_file():
        return default
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as db:
        row = db.execute("SELECT payload FROM state WHERE id=1").fetchone()
    if not row:
        raise ValueError(f"fake state store is missing its state row: {path.name}")
    value = json.loads(row[0])
    if not isinstance(value, dict):
        raise ValueError(f"fake state store is not an object: {path.name}")
    return value


def _open(state_dir: Path, at: datetime | None):
    state_dir = prepare_synthetic_state_dir(state_dir)
    fixture = build_fixture(storage_path=state_dir / "c06_state.sqlite")
    if len(fixture["plans"]._plans) != 1:
        raise ValueError("supervisor requires exactly one immutable persisted proposal")
    plan = next(iter(fixture["plans"]._plans.values()))
    lifecycle = stable_id("c06.fake_lifecycle", plan.plan_id)
    latest = fixture["journal"].events[-1].occurred_at if fixture["journal"].events else fixture["as_of"]
    owner_path, venue_path = state_dir / "owner.sqlite", state_dir / "venue.sqlite"
    owner_state = _read_state_file(owner_path, {"approvals": {}, "positions": {},
        "intents": {}, "exit_requests": {}})
    venue_state = _read_state_file(venue_path, {"orders": {}, "fills": {},
        "positions": {}, "writes": []})
    known = [latest]
    approval = owner_state.get("approvals", {}).get(plan.plan_id)
    if approval:
        known.append(datetime.fromisoformat(approval["approved_at"]))
    for position in owner_state.get("positions", {}).values():
        if position.get("first_fill_at"):
            known.append(datetime.fromisoformat(position["first_fill_at"]))
    for intent in owner_state.get("intents", {}).values():
        for key in ("persisted_at", "submitted_at"):
            if intent.get(key):
                known.append(datetime.fromisoformat(intent[key]))
    for fill in venue_state.get("fills", {}).values():
        known.append(datetime.fromisoformat(fill["at"]))
    for request in owner_state.get("exit_requests", {}).values():
        for key in ("requested_at", "resolved_at"):
            if request.get(key):
                known.append(datetime.fromisoformat(request[key]))
    for position in owner_state.get("positions", {}).values():
        latch = position.get("latch") or {}
        if latch.get("at"):
            known.append(datetime.fromisoformat(latch["at"]))
    if at is not None and at < max(known):
        raise ValueError("simulation clock cannot precede persisted owner, venue or journal state")
    clock = FakeClock(at or max(known))
    venue = FakeVenue(venue_path, clock)
    owner = FakeOwner(owner_path, venue, clock)
    return state_dir, fixture, plan, lifecycle, clock, venue, owner


def _status(state_dir, fixture, plan, lifecycle, venue, owner) -> dict:
    owner_state = owner.ledger.read()
    venue_state = venue.state.read()
    position = owner_state.get("positions", {}).get(lifecycle)
    related_orders = {cid: item for cid, item in venue_state["orders"].items()
        if item["lifecycle_id"] == lifecycle}
    visible_stops = [cid for cid in (position or {}).get("stop_ids", [])
        if cid in related_orders and related_orders[cid]["visible"]
        and related_orders[cid]["status"] in {"ACKNOWLEDGED", "PARTIAL"}]
    unresolved = [iid for iid, item in owner_state.get("intents", {}).items()
        if item["lifecycle_id"] == lifecycle
        and item["state"] in {"PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION"}]
    entry_intent = owner_state.get("intents", {}).get("intent-" + plan.plan_id)
    unresolved_management = [cid for cid, item in owner_state.get("management", {}).items()
        if item["lifecycle_id"] == lifecycle
        and item["status"] in {"PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION"}]
    management_intents = [{"client_order_id": cid, **item}
        for cid, item in sorted(owner_state.get("management", {}).items())
        if item["lifecycle_id"] == lifecycle]
    exit_request = owner_state.get("exit_requests", {}).get(lifecycle)
    return {"fixture": "SYNTHETIC_ONLY", "plan_id": plan.plan_id,
        "plan_hash": plan.immutable_hash, "plan_status": fixture["plans"]._states[plan.plan_id],
        "lifecycle_id": lifecycle, "owner_reconciled": owner_state.get("reconciled", False),
        "position_state": (position or {}).get("state", "NO_POSITION"),
        "position_quantity": (position or {}).get("quantity", "0"),
        "first_fill_at": (position or {}).get("first_fill_at"),
        "protection": "FLAT" if not position or D(position["quantity"]) == 0 else
            ("VERIFIED" if visible_stops else "MISSING"),
        "visible_stop_ids": visible_stops, "entry_intent_state": entry_intent["state"] if entry_intent else None,
        "unresolved_entry_intents": unresolved,
        "unresolved_management_intents": unresolved_management,
        "management_intents": management_intents,
        "exit_request": exit_request,
        "venue_orders": related_orders,
        "venue_write_count": len(venue_state["writes"]),
        "venue_position": venue_state["positions"].get(lifecycle, "0"),
        "coordinator_dependency": False}


def _has_verified_close_only_exit(owner: FakeOwner, venue: FakeVenue,
                                  lifecycle: str) -> bool:
    """Permit only a correlated reduce-only fill after other checks fail."""
    state = owner.ledger.read()
    request = state.get("exit_requests", {}).get(lifecycle)
    if not request or request.get("status") == "FLAT_RECONCILED":
        return False
    if any(item.get("lifecycle_id") == lifecycle
        and item.get("state") in {"PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION"}
        for item in state.get("intents", {}).values()):
        return False
    try:
        snapshot = venue.snapshot()
    except ConnectionError:
        return False
    active = [(cid, order) for cid, order in snapshot["orders"].items()
        if order.get("lifecycle_id") == lifecycle
        and order.get("status") in {"ACKNOWLEDGED", "PARTIAL"}
        and order.get("params", {}).get("kind") == "MARKET"
        and order.get("params", {}).get("reduce_only") is True]
    if len(active) != 1 or active[0][0] != request.get("client_order_id"):
        return False
    order = active[0][1]
    signed = D(snapshot["positions"].get(lifecycle, "0"))
    expected_side = "SELL" if signed > 0 else "BUY"
    return signed != 0 and order["params"].get("side") == expected_side


def _append_event(journal: EventJournal, *, now, plan, lifecycle, action, status, available):
    if not available:
        journal.available = False
        return "UNAVAILABLE"
    try:
        journal.append(occurred_at=now, actor="fake_supervisor",
            event_type="SUPERVISOR_STEP", plan_id=plan.plan_id,
            lifecycle_id=lifecycle,
            details={"action": action, "plan_status": status,
                "fixture": "SYNTHETIC_ONLY"})
        return "VERIFIED"
    except Exception as exc:
        return f"UNAVAILABLE: {type(exc).__name__}"


def run(args) -> dict:
    state_dir, fixture, plan, lifecycle, clock, venue, owner = _open(args.state_dir, args.at)
    plans: PlanRegistry = fixture["plans"]
    journal: EventJournal = fixture["journal"]
    if args.action == "status":
        return _status(state_dir, fixture, plan, lifecycle, venue, owner)

    if args.unknown_exit_ack:
        original_submit = venue.submit
        def unknown_market_ack(client_id, params, **kwargs):
            if params.kind == "MARKET":
                return original_submit(client_id, params, result="UNKNOWN", **kwargs)
            return original_submit(client_id, params, **kwargs)
        venue.submit = unknown_market_ack

    owner_state = owner.ledger.read()
    auth_raw = owner_state.get("approvals", {}).get(plan.plan_id)
    if not auth_raw:
        raise ValueError("no persisted fixture-owner approval; supervisor cannot start exposure")
    if plan.plan_id not in owner_state.get("consumed", []):
        raise ValueError("approval has not been consumed under the C01 one-use claim")
    intent_id = "intent-" + plan.plan_id
    entry_id = "entry-" + plan.plan_id
    if intent_id not in owner_state.get("intents", {}):
        raise ValueError("consumed authorization has no matching C01 entry intent")

    # A disconnected time-exit pass uses only durable local owner state to latch
    # and persist the requested reduction. It performs no venue reads or writes.
    if args.action == "disconnect-exit":
        position = owner_state.get("positions", {}).get(lifecycle)
        first_fill = (datetime.fromisoformat(position["first_fill_at"])
            if position and position.get("first_fill_at") else None)
        if not first_fill:
            raise ValueError("cannot schedule the time exit before an authoritative fake fill")
        clock.now = first_fill + timedelta(hours=11, minutes=55)
        venue.connected = False
        writes_before = len(venue.state.read()["writes"])
        owner.timers()
        event_state = _append_event(journal, now=clock.now, plan=plan, lifecycle=lifecycle,
            action=args.action, status=plans._states[plan.plan_id], available=not args.journal_unavailable)
        result = _status(state_dir, fixture, plan, lifecycle, venue, owner)
        result.update({"action": args.action, "journal_state": event_state,
            "disconnected": True,
            "venue_write_delta": len(venue.state.read()["writes"]) - writes_before})
        return result

    if args.action in {"time-exit", "emergency"}:
        position = owner_state.get("positions", {}).get(lifecycle)
        first_fill = (datetime.fromisoformat(position["first_fill_at"])
            if position and position.get("first_fill_at") else None)
        if not first_fill:
            raise ValueError("time exit requires an authoritative fake first fill")
        clock.now = first_fill + (timedelta(hours=11, minutes=55)
            if args.action == "time-exit" else timedelta(hours=12))

    if not owner.reconnect():
        close_only = args.action in {"tick", "time-exit", "emergency", "fill-exit"}
        if not close_only or not _has_verified_close_only_exit(owner, venue, lifecycle):
            raise RuntimeError("C01 fake owner/venue reconciliation failed; no new submission is allowed")

    if args.action == "submit-entry":
        intent = owner.ledger.read()["intents"][intent_id]
        order = venue.snapshot()["orders"].get(entry_id)
        if order:
            if order["lifecycle_id"] != lifecycle:
                raise RuntimeError("entry client ID is owned by a different fake lifecycle")
        elif intent["state"] == "PERSISTED":
            if not owner.proves_unsubmitted_intent(intent_id):
                raise RuntimeError("entry submission is ambiguous; it will not be retried")
            if args.entry_absent_ack:
                venue.connected = False
                owner.submit(intent_id, quote=plan.entry_max)
            else:
                owner.submit(intent_id, quote=plan.entry_max, result=args.entry_result)
        else:
            raise RuntimeError("entry submission state is unresolved; no new write was attempted")

    elif args.action in {"fill-entry", "partial-entry"}:
        order = venue.snapshot()["orders"].get(entry_id)
        if not order and owner.ledger.read()["intents"][intent_id]["state"] == "PERSISTED":
            if not owner.proves_unsubmitted_intent(intent_id):
                raise RuntimeError("entry submission is ambiguous; fill simulation halted")
            owner.submit(intent_id, quote=plan.entry_max)
            order = venue.snapshot()["orders"].get(entry_id)
        if not order or order["status"] not in {"ACKNOWLEDGED", "PARTIAL"}:
            raise RuntimeError("no acknowledged fake entry is available to fill")
        existing_fill = any(fill["client_id"] == entry_id for fill in venue.snapshot()["fills"].values())
        if not existing_fill:
            auth = auth_raw
            price = D(plan.entry_max if auth["side"] == "LONG" else plan.entry_min)
            remaining = D(order["params"]["quantity"]) - D(order["filled"])
            if remaining <= 0:
                raise RuntimeError("fake entry has no fillable remainder")
            quantity = remaining if args.action == "fill-entry" else remaining / 2
            venue.fill(entry_id, "c06f-entry-" + plan.plan_id, quantity, price, at=clock.now)
        owner.detect_fills(stop_result=args.stop_result)
        state = owner.ledger.read()
        position = state["positions"][lifecycle]
        if D(position["quantity"]) <= 0 or not position["stop_ids"]:
            raise RuntimeError("entry fill did not result in verified fake stop protection")
        if not position["tp_ids"]:
            owner.add_targets(lifecycle)

    elif args.action == "late-entry-fill":
        snapshot = venue.snapshot()
        order = snapshot["orders"].get(entry_id)
        if not order or order["status"] not in {"CANCELLED", "REJECTED", "EXPIRED"}:
            raise RuntimeError("late-fill fixture requires a terminal partially filled entry")
        remaining = D(order["params"]["quantity"]) - D(order["filled"])
        if remaining <= 0:
            raise RuntimeError("terminal entry has no remaining quantity for a late-fill fault")
        price = D(plan.entry_max if auth_raw["side"] == "LONG" else plan.entry_min)
        venue.fill(entry_id, "c06f-late-entry-" + plan.plan_id, remaining,
            price, at=clock.now, late=True)
        owner.detect_fills()

    elif args.action == "partial-tp1":
        state = owner.ledger.read()
        position = state.get("positions", {}).get(lifecycle)
        if not position or D(position["quantity"]) <= 0:
            raise RuntimeError("partial target requires an open fake position")
        target_ids = position["tp_ids"] or owner.add_targets(lifecycle)
        if not target_ids:
            raise RuntimeError("no approved fake target intent is available")
        target_id = target_ids[0]
        snapshot = venue.snapshot()
        order = snapshot["orders"].get(target_id)
        if not order or order["status"] not in {"ACKNOWLEDGED", "PARTIAL"}:
            raise RuntimeError("first approved target is not active on the fake venue")
        if not any(fill["client_id"] == target_id for fill in snapshot["fills"].values()):
            remaining = D(order["params"]["quantity"]) - D(order["filled"])
            venue.fill(target_id, "c06f-tp1-" + plan.plan_id, remaining,
                D(order["params"]["price"]), at=clock.now)
        owner.detect_fills()

    elif args.action in {"tick", "time-exit", "emergency"}:
        owner.detect_fills()
        owner.timers()

    elif args.action == "fill-exit":
        state = owner.ledger.read()
        position = state.get("positions", {}).get(lifecycle)
        if not position or D(position["quantity"]) <= 0:
            raise RuntimeError("no open fake position requires an exit fill")
        snapshot = venue.snapshot()
        exit_orders = [(cid, order) for cid, order in snapshot["orders"].items()
            if order["lifecycle_id"] == lifecycle
            and order["params"]["kind"] == "MARKET" and order["params"]["reduce_only"]]
        active = [(cid, order) for cid, order in exit_orders
            if order["status"] in {"ACKNOWLEDGED", "PARTIAL"}]
        if len(active) != 1:
            raise RuntimeError("no acknowledged reduce-only exit intent can be filled")
        exit_id, exit_order = active[-1]
        # Do not finalize over an unresolved entry: it could create late
        # exposure after the reduce-only close. Dormant stops and targets are
        # canceled in this deterministic venue before flat reconciliation.
        unresolved_entry = [cid for cid, order in snapshot["orders"].items()
            if order["lifecycle_id"] == lifecycle
            and cid == entry_id and order["status"] not in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}]
        if unresolved_entry:
            raise RuntimeError("entry order is not terminal; fake exit cannot be finalized")
        for client_id, order in snapshot["orders"].items():
            if (order["lifecycle_id"] == lifecycle and client_id != exit_id
                and order["status"] in {"ACKNOWLEDGED", "PARTIAL"}
                and (order["params"]["reduce_only"] or order["params"]["close_position"])):
                venue.cancel(client_id)
        snapshot = venue.snapshot()
        if any(order["lifecycle_id"] == lifecycle and client_id != exit_id
            and order["status"] not in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
            for client_id, order in snapshot["orders"].items()):
            raise RuntimeError("a correlated fake order remains unresolved after cancel")
        if not any(fill["client_id"] == exit_id for fill in snapshot["fills"].values()):
            remaining = abs(D(snapshot["positions"].get(lifecycle, "0")))
            if remaining <= 0:
                raise RuntimeError("fake position is already flat in venue truth")
            venue.fill(exit_id, "c06f-exit-" + plan.plan_id, remaining,
                D(plan.entry_min), at=clock.now)
        owner.detect_fills()
        if owner.terminal(lifecycle) and not args.journal_unavailable:
            state = owner.ledger.read()
            if plans._states[plan.plan_id] in {"CONSUMED", "SIMULATED_OPEN"}:
                plans.observe_external_state(plan.plan_id, "CLOSED_RECONCILED", occurred_at=clock.now)

    else:
        raise ValueError("unknown supervisor action")

    state = owner.ledger.read()
    position = state.get("positions", {}).get(lifecycle)
    current_venue = venue.state.read()
    pending_exit = state.get("exit_requests", {}).get(lifecycle)
    terminal_reconciled = bool(pending_exit
        and D(current_venue["positions"].get(lifecycle, "0")) == 0
        and owner.terminal(lifecycle))
    if terminal_reconciled:
        if (not args.journal_unavailable
            and plans._states[plan.plan_id] in {"CONSUMED", "SIMULATED_OPEN"}):
            plans.observe_external_state(plan.plan_id, "CLOSED_RECONCILED", occurred_at=clock.now)
    elif (position and position.get("first_fill_at")
        and plans._states[plan.plan_id] == "CONSUMED" and not args.journal_unavailable):
        plans.observe_external_state(plan.plan_id, "SIMULATED_OPEN", occurred_at=clock.now)
    status = plans._states[plan.plan_id]
    event_state = _append_event(journal, now=clock.now, plan=plan, lifecycle=lifecycle,
        action=args.action, status=status, available=not args.journal_unavailable)
    result = _status(state_dir, fixture, plan, lifecycle, venue, owner)
    result.update({"action": args.action, "journal_state": event_state,
        "deadline_11h55": (datetime.fromisoformat(position["first_fill_at"])
            + timedelta(hours=11, minutes=55)).isoformat() if position and position.get("first_fill_at") else None,
        "emergency_boundary_12h": (datetime.fromisoformat(position["first_fill_at"])
            + timedelta(hours=12)).isoformat() if position and position.get("first_fill_at") else None,
        "fault_halt": state.get("fault_halt", False)})
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake-only", action="store_true",
        help="required confirmation that all venue state and fills are synthetic")
    parser.add_argument("--state-dir", type=Path, required=True,
        help="dedicated synthetic-only C06 directory")
    parser.add_argument("--at", type=_parse_time,
        help="deterministic UTC simulation time; cannot precede persisted activity")
    parser.add_argument("--journal-unavailable", action="store_true",
        help="simulate reporting-journal outage; C01 protection/reconciliation remains independent")
    parser.add_argument("--coordinator-unavailable", action="store_true",
        help="record that the OpenBot coordinator is offline; this process does not call it")
    parser.add_argument("--entry-result", choices=("ACKNOWLEDGED", "UNKNOWN", "REJECTED"),
        default="ACKNOWLEDGED", help="deterministic fake venue entry response for fault tests")
    parser.add_argument("--entry-absent-ack", action="store_true",
        help="simulate a connection loss before any fake venue entry write")
    parser.add_argument("--stop-result", choices=("ACKNOWLEDGED", "UNKNOWN", "REJECTED", "ABSENT"),
        default="ACKNOWLEDGED", help="deterministic fake stop result for protection fault tests")
    parser.add_argument("--unknown-exit-ack", action="store_true",
        help="simulate a lost acknowledgement after a fake reduce-only exit write")
    parser.add_argument("action", choices=("status", "submit-entry", "fill-entry", "partial-entry",
        "late-entry-fill", "partial-tp1", "tick", "disconnect-exit", "time-exit",
        "emergency", "fill-exit"))
    args = parser.parse_args(argv)
    if not args.fake_only:
        parser.error("--fake-only is required; this executable cannot access Binance")
    try:
        result = run(args)
        result["coordinator_unavailable"] = args.coordinator_unavailable
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        parser.exit(2, f"C06 fake supervisor halted: {exc}\n")


if __name__ == "__main__":
    main()
