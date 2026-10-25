#!/usr/bin/env python3
"""Local fixture-only owner decisions for the C06 offline paper harness."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

from astrabot.c06.paper_mvp import EventJournal, PlanRegistry
from astrabot.contracts import TradeAuthorizationV15
from astrabot.data.models import stable_id
from c01_fake import FakeClock, FakeOwner, FakeVenue
from c06_fixture_paths import prepare_synthetic_state_dir
from c06_paper_demo import FixtureOwnerDecision, build_fixture, make_fake_authorization


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _load_fixture(state_dir: Path):
    state_dir = prepare_synthetic_state_dir(state_dir)
    fixture = build_fixture(storage_path=state_dir / "c06_state.sqlite")
    if not fixture["plans"]._plans:
        raise ValueError("no persisted proposal; prepare one through the positive MCP fixture first")
    if len(fixture["plans"]._plans) != 1:
        raise ValueError("fixture owner CLI requires exactly one persisted synthetic proposal")
    plan = next(iter(fixture["plans"]._plans.values()))
    if not plan.verify_hash() or plan.research_status != "RESEARCH_ONLY" or plan.executable:
        raise ValueError("persisted proposal is not a verified non-executable research plan")
    if plan.candidate_id != fixture["candidate"].decision_id:
        raise ValueError("proposal does not match the selected deterministic fixture")
    return state_dir, fixture, plan


def _read_store(path: Path) -> dict | None:
    if not path.is_file():
        return None
    import sqlite3

    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as db:
        row = db.execute("SELECT payload FROM state WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def _print(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def run(args) -> dict:
    state_dir = prepare_synthetic_state_dir(args.state_dir)
    if args.command == "list":
        fixture = build_fixture(storage_path=state_dir / "c06_state.sqlite")
        return {"fixture": "SYNTHETIC_ONLY", "proposals": [
            {"plan_id": p.plan_id, "plan_hash": p.immutable_hash,
             "symbol": p.symbol, "side": p.side, "status": fixture["plans"]._states[pid],
             "expires_at": p.expires_at.isoformat(), "executable": False}
            for pid, p in sorted(fixture["plans"]._plans.items())]}

    state_dir, fixture, plan = _load_fixture(state_dir)
    if args.plan_id != plan.plan_id:
        raise ValueError("plan ID does not match the persisted immutable proposal")
    plans: PlanRegistry = fixture["plans"]
    journal: EventJournal = fixture["journal"]
    lifecycle_id = stable_id("c06.fake_lifecycle", plan.plan_id)
    latest = journal.events[-1].occurred_at if journal.events else fixture["as_of"]
    now = args.now or latest
    if args.command in {"approve", "consume"}:
        trigger = fixture["candidate"].earliest_hypothetical_entry_at
        now = max(now, trigger + timedelta(milliseconds=100))
    if args.command == "expire":
        now = max(now, plan.expires_at)
    owner_state = _read_store(state_dir / "owner.sqlite") or {
        "approvals": {}, "consumed": [], "nonces": [], "intents": {}}
    current = plans._states[plan.plan_id]
    approval_payload = owner_state["approvals"].get(plan.plan_id)

    if args.command == "show":
        # Inspection is deliberately read-only. In particular, it must not
        # reconnect the C01 supervisor, run timers, initialize a missing owner
        # database, or rewrite any fixture state.
        venue_state = _read_store(state_dir / "venue.sqlite") or {"writes": []}
        if not isinstance(owner_state, dict) or not isinstance(venue_state, dict):
            raise ValueError("fixture owner or venue state is malformed")
        intent = next((item for item in owner_state["intents"].values()
            if item["lifecycle_id"] == lifecycle_id), None)
        return {"fixture": "SYNTHETIC_ONLY", "identity": "FIXTURE_OWNER_NOT_REAL_MFA",
            "plan": plan.model_dump(mode="json"), "status": current,
            "approval_present": plan.plan_id in owner_state["approvals"],
            "approval_consumed": plan.plan_id in owner_state["consumed"],
            "nonce_consumed": plan.approval_nonce in owner_state["nonces"],
            "entry_intent": intent, "venue_write_count": len(venue_state["writes"])}

    # Only one-use consumption needs the live C01 readiness barrier. Approval,
    # rejection and expiry mutate the local fixture decision record but must
    # not unexpectedly run the independent supervisor's recovery timers.
    clock = FakeClock(now)
    venue = FakeVenue(state_dir / "venue.sqlite", clock)
    owner = FakeOwner(state_dir / "owner.sqlite", venue, clock)
    owner_state = owner.ledger.read()
    approval_payload = owner_state["approvals"].get(plan.plan_id)
    current = plans._states[plan.plan_id]
    decision = FixtureOwnerDecision(plan=plan, candidate=fixture["candidate"],
        setup=fixture["setup"], owner=owner, clock=clock, plans=plans,
        journal=journal, lifecycle_id=lifecycle_id)

    if args.command == "approve":
        if approval_payload:
            auth = TradeAuthorizationV15.model_validate_json(json.dumps(approval_payload))
            _, expected = make_fake_authorization(plan, fixture["candidate"], fixture["setup"], auth.approved_at)
            if auth != expected or auth.immutable_hash() != auth.approved_immutable_hash:
                raise ValueError("persisted fixture approval does not bind the original plan")
            if current not in {"PROPOSED_RESEARCH_ONLY", "FAKE_OWNER_APPROVED"}:
                raise ValueError("C01 approval conflicts with the persisted proposal status")
            if current == "PROPOSED_RESEARCH_ONLY":
                plans.observe_external_state(plan.plan_id, "FAKE_OWNER_APPROVED", occurred_at=now)
            return {"fixture": "SYNTHETIC_ONLY", "status": "ALREADY_APPROVED",
                "plan_id": plan.plan_id, "plan_hash": plan.immutable_hash,
                "authorization_hash": auth.approved_immutable_hash,
                "identity": "FIXTURE_OWNER_NOT_REAL_MFA"}
        if current != "PROPOSED_RESEARCH_ONLY":
            raise ValueError("only a pending proposal can receive fixture-owner approval")
        decision.approve()
        auth = TradeAuthorizationV15.model_validate_json(
            json.dumps(owner.ledger.read()["approvals"][plan.plan_id]))
        return {"fixture": "SYNTHETIC_ONLY", "status": "FAKE_OWNER_APPROVED",
            "plan_id": plan.plan_id, "plan_hash": plan.immutable_hash,
            "authorization_hash": auth.approved_immutable_hash,
            "nonce": auth.one_use_nonce, "identity": "FIXTURE_OWNER_NOT_REAL_MFA"}

    if args.command == "reject":
        if approval_payload:
            raise ValueError("a persisted C01 approval must be reconciled before rejection")
        decision.reject()
        return {"fixture": "SYNTHETIC_ONLY", "status": "OWNER_REJECTED",
            "plan_id": plan.plan_id, "venue_write_count": len(venue.state.read()["writes"]),
            "identity": "FIXTURE_OWNER_NOT_REAL_MFA"}

    if args.command == "expire":
        decision.expire()
        return {"fixture": "SYNTHETIC_ONLY", "status": "EXPIRED",
            "plan_id": plan.plan_id, "venue_write_count": len(venue.state.read()["writes"]),
            "identity": "FIXTURE_OWNER_NOT_REAL_MFA"}

    if args.command == "consume":
        if not approval_payload:
            raise ValueError("only an approved exact plan can be consumed")
        auth = TradeAuthorizationV15.model_validate_json(json.dumps(approval_payload))
        _, expected = make_fake_authorization(plan, fixture["candidate"], fixture["setup"], auth.approved_at)
        if auth != expected or auth.immutable_hash() != auth.approved_immutable_hash:
            raise ValueError("persisted fixture approval does not bind the original plan")
        if (auth.one_use_nonce != plan.approval_nonce or auth.readiness_ref != plan.immutable_hash
            or auth.plan_id != plan.plan_id):
            raise ValueError("approval hash or nonce does not bind the immutable plan")
        if current == "PROPOSED_RESEARCH_ONLY":
            plans.observe_external_state(plan.plan_id, "FAKE_OWNER_APPROVED", occurred_at=now)
            current = "FAKE_OWNER_APPROVED"
        if plan.plan_id in owner_state["consumed"]:
            existing_intent = next((item for item in owner_state["intents"].values()
                if item["approval_id"] == plan.plan_id), None)
            if (not existing_intent or existing_intent["lifecycle_id"] != lifecycle_id
                or existing_intent["client_order_id"] != "entry-" + plan.plan_id
                or existing_intent["approved_hash"] != auth.approved_immutable_hash):
                raise ValueError("C01 consumed state lacks the exact original entry intent")
            if current == "FAKE_OWNER_APPROVED":
                plans.observe_external_state(plan.plan_id, "CONSUMED", occurred_at=now)
            return {"fixture": "SYNTHETIC_ONLY", "status": "ALREADY_CONSUMED",
                "plan_id": plan.plan_id, "intent_id": existing_intent["intent_id"] if existing_intent else None,
                "venue_write_count": len(venue.state.read()["writes"])}
        if current != "FAKE_OWNER_APPROVED":
            raise ValueError("only a pending approved plan can consume its authorization")
        if not owner.reconnect():
            raise RuntimeError("fake C01 state is unresolved; one-use claim is halted")
        intent_id = decision.consume(auth, trigger_at=fixture["candidate"].earliest_hypothetical_entry_at)
        if not intent_id:
            raise RuntimeError("C01 rejected the exact one-use fixture authorization")
        return {"fixture": "SYNTHETIC_ONLY", "status": "CONSUMED",
            "plan_id": plan.plan_id, "plan_hash": plan.immutable_hash,
            "intent_id": intent_id, "client_order_id": "entry-" + plan.plan_id,
            "nonce": auth.one_use_nonce, "venue_write_count": len(venue.state.read()["writes"])}

    raise ValueError("unsupported fixture owner command")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake-only", action="store_true",
        help="required confirmation that decisions and state are synthetic")
    parser.add_argument("--state-dir", type=Path, required=True,
        help="dedicated synthetic-only C06 directory; never use market-data storage")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list persisted proposals")
    for name in ("show", "approve", "reject", "expire", "consume"):
        command = sub.add_parser(name)
        command.add_argument("plan_id")
        command.add_argument("--now", type=_parse_time,
            help="optional deterministic UTC simulation time")
    args = parser.parse_args(argv)
    if not args.fake_only:
        parser.error("--fake-only is required; this CLI cannot authorize real trading")
    try:
        _print(run(args))
    except Exception as exc:
        parser.exit(2, f"C06 fixture owner halted: {exc}\n")


if __name__ == "__main__":
    main()
