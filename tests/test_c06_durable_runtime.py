from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal as D
from hashlib import sha256
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from astrabot.c06.paper_mvp import EventJournal, PaperPlan, PlanRegistry
from astrabot.data.models import stable_id
from c01_fake import FakeClock, FakeOwner, FakeVenue
from c06_paper_demo import (
    build_fixture, make_fake_authorization, reopen_persisted_demo, run_demo,
)


def _world(root):
    c06_path = root / "c06_state.sqlite"
    fixture = build_fixture(storage_path=c06_path)
    candidate, setup = fixture["candidate"], fixture["setup"]
    plan = fixture["gateway"].call("prepare_plan", {"candidate_id": candidate.decision_id})
    lifecycle_id = stable_id("c06.fake_lifecycle", plan.plan_id)
    fixture["journal"].append(occurred_at=fixture["as_of"], actor="offline_test_driver",
        event_type="PROPOSAL_PREPARED", plan_id=plan.plan_id, lifecycle_id=lifecycle_id,
        details={"plan_hash": plan.immutable_hash, "fixture": "SYNTHETIC_FIXTURE"})
    clock = FakeClock(candidate.earliest_hypothetical_entry_at + timedelta(milliseconds=100))
    venue = FakeVenue(root / "venue.sqlite", clock)
    owner = FakeOwner(root / "owner.sqlite", venue, clock)
    assert owner.reconnect()
    return {"root": root, "fixture": fixture, "candidate": candidate, "setup": setup,
        "plan": plan, "life": lifecycle_id, "clock": clock, "venue": venue, "owner": owner}


def _approve_and_claim(world, *, submit=True, result="ACKNOWLEDGED"):
    w = world
    fake_setup, auth = make_fake_authorization(w["plan"], w["candidate"], w["setup"], w["clock"].now)
    w["owner"].register_approval(auth, fake_setup)
    w["fixture"]["plans"].observe_external_state(w["plan"].plan_id, "FAKE_OWNER_APPROVED")
    intent = w["owner"].claim(auth, quantity=w["plan"].proposed_quantity,
        quote=w["plan"].entry_max,
        trigger_at=w["candidate"].earliest_hypothetical_entry_at)
    assert intent
    w["fixture"]["plans"].observe_external_state(w["plan"].plan_id, "CONSUMED")
    if submit:
        w["owner"].submit(intent, quote=w["plan"].entry_max, result=result)
    return auth, intent


def _checkpoint(w, event_type):
    w["fixture"]["journal"].append(occurred_at=w["clock"].now,
        actor="offline_test_driver", event_type=event_type, plan_id=w["plan"].plan_id,
        lifecycle_id=w["life"], details={"fixture_restart_boundary": event_type})


def _reopen_to(w, stage):
    """Create a process boundary after the requested persisted lifecycle point."""
    if stage == "proposal":
        return
    if stage == "approval":
        fake_setup, auth = make_fake_authorization(
            w["plan"], w["candidate"], w["setup"], w["clock"].now)
        w["owner"].register_approval(auth, fake_setup)
        # Deliberately crash between the fake-owner DB commit and C06 mirror.
        return
    auth, intent = _approve_and_claim(w, submit=False)
    if stage == "intent":
        # C01 persisted the intent before the external call; leave it unsubmitted.
        return
    if stage == "unknown_entry":
        w["owner"].submit(intent, quote=w["plan"].entry_max, result="UNKNOWN")
        _checkpoint(w, "ENTRY_ACK_UNKNOWN")
        return
    if stage == "unknown_entry_absent":
        w["venue"].connected = False
        w["owner"].submit(intent, quote=w["plan"].entry_max)
        assert w["owner"].ledger.read()["intents"][intent]["state"] == "UNKNOWN_SUBMISSION"
        _checkpoint(w, "ENTRY_ACK_UNKNOWN")
        return
    w["owner"].submit(intent, quote=w["plan"].entry_max)
    entry_id = "entry-" + w["plan"].plan_id
    if stage == "partial_entry":
        w["clock"].advance(milliseconds=50)
        w["venue"].fill(entry_id, "restart-partial-entry", w["plan"].proposed_quantity / 2,
            w["plan"].entry_max, at=w["clock"].now)
        _checkpoint(w, "ENTRY_PARTIAL_FILL")
        return
    w["clock"].advance(milliseconds=50)
    w["venue"].fill(entry_id, "restart-full-entry", w["plan"].proposed_quantity,
        w["plan"].entry_max, at=w["clock"].now)
    w["owner"].detect_fills()
    w["fixture"]["plans"].observe_external_state(w["plan"].plan_id, "SIMULATED_OPEN")
    if stage == "protection":
        _checkpoint(w, "ENTRY_PROTECTED")
        return
    tp_ids = w["owner"].add_targets(w["life"])
    w["clock"].advance(milliseconds=100)
    target, fraction = w["plan"].targets[0]
    w["venue"].fill(tp_ids[0], "restart-partial-tp1", w["plan"].proposed_quantity * fraction,
        target, at=w["clock"].now)
    w["owner"].detect_fills()
    if stage == "partial_tp":
        _checkpoint(w, "PARTIAL_TAKE_PROFIT")
        return
    first_fill = datetime.fromisoformat(w["owner"].ledger.read()["positions"][w["life"]]["first_fill_at"])
    deadline = first_fill + timedelta(hours=11, minutes=55)
    if stage == "near_deadline":
        w["clock"].now = deadline - timedelta(minutes=1)
        w["owner"].timers()
        _checkpoint(w, "NEAR_TIME_EXIT_DEADLINE")
        return
    w["clock"].now = deadline
    original_submit = w["venue"].submit

    def unknown_exit(client_id, params, **kwargs):
        if params.kind == "MARKET":
            return original_submit(client_id, params, result="UNKNOWN", **kwargs)
        return original_submit(client_id, params, **kwargs)

    w["venue"].submit = unknown_exit
    w["owner"].timers()
    exit_id = next(cid for cid, item in w["owner"].ledger.read()["management"].items()
        if item["lifecycle_id"] == w["life"] and item["params"]["kind"] == "MARKET")
    assert w["venue"].state.read()["orders"][exit_id]["status"] == "ACKNOWLEDGED"
    if stage == "exit_unknown":
        _checkpoint(w, "EXIT_ACK_UNKNOWN")
        return
    remaining = D(w["owner"].ledger.read()["positions"][w["life"]]["quantity"])
    w["venue"].fill(exit_id, "restart-terminal-exit-fill", remaining,
        w["plan"].entry_min, at=w["clock"].now)
    _checkpoint(w, "EXIT_FILLED_AWAITING_TERMINAL_RECONCILIATION")


@pytest.mark.parametrize("stage", [
    "proposal", "approval", "unknown_entry", "partial_entry", "protection",
    "partial_tp", "near_deadline", "exit_unknown", "terminal_unresolved",
])
def test_fresh_objects_restore_and_reconcile_persistent_lifecycle(tmp_path, stage):
    w = _world(tmp_path)
    _reopen_to(w, stage)
    prior_writes = len(w["venue"].state.read()["writes"])
    if stage == "proposal":
        # A proposal alone remains unapproved; only this explicit fake-owner call may approve it.
        pending = reopen_persisted_demo(tmp_path)
        assert pending["plan_status"] == "PROPOSED_RESEARCH_ONLY"
        assert pending["venue_write_count"] == 0
        result = reopen_persisted_demo(tmp_path, owner_decision="approve")
    else:
        result = reopen_persisted_demo(tmp_path)
    assert result["plan_status"] == "CLOSED_RECONCILED"
    assert result["position_state"] == "FLAT_RECONCILED"
    assert D(result["position_quantity"]) == 0
    assert result["owner_reconciled"] is True
    assert len(w["venue"].state.read()["writes"]) >= prior_writes
    fresh_plans = PlanRegistry(tmp_path / "c06_state.sqlite")
    fresh_journal = EventJournal(tmp_path / "c06_state.sqlite")
    assert fresh_plans.get(w["plan"].plan_id, w["clock"].now).status == "CLOSED_RECONCILED"
    assert fresh_journal.summary(w["life"]).event_count >= 2


def test_absent_unknown_entry_ack_stays_halted_without_duplicate_submission(tmp_path):
    w = _world(tmp_path)
    _reopen_to(w, "unknown_entry_absent")
    with pytest.raises(RuntimeError, match="could not reconcile"):
        reopen_persisted_demo(tmp_path)
    state = w["owner"].ledger.read()
    assert state["reconciled"] is False
    assert state["reservations"]["res-" + w["plan"].plan_id]["status"] == "UNKNOWN"
    assert len(w["venue"].state.read()["writes"]) == 0


def test_durable_registry_journal_reopen_hashes_idempotency_and_no_overwrite(tmp_path):
    w = _world(tmp_path)
    first_summary = w["fixture"]["journal"].summary(w["life"])
    event = w["fixture"]["journal"].events[-1]
    plans = PlanRegistry(tmp_path / "c06_state.sqlite")
    journal = EventJournal(tmp_path / "c06_state.sqlite")
    assert plans._plans[w["plan"].plan_id].immutable_hash == w["plan"].immutable_hash
    assert plans.get(w["plan"].plan_id, w["clock"].now).status == "PROPOSED_RESEARCH_ONLY"
    assert journal.summary(w["life"]) == first_summary
    payload = w["plan"].model_dump(mode="json", exclude={"immutable_hash"})
    payload["proposed_quantity"] = str(w["plan"].proposed_quantity + D("1"))
    immutable_hash = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    mutated = PaperPlan.model_validate_json(json.dumps({**payload, "immutable_hash": immutable_hash}))
    with pytest.raises(ValueError, match="different immutable content"):
        plans.add(mutated)
    duplicate = journal.append(occurred_at=event.occurred_at, actor=event.actor,
        event_type=event.event_type, plan_id=event.plan_id, lifecycle_id=event.lifecycle_id,
        correlation_id=event.correlation_id, details=dict(event.details))
    assert duplicate.event_id == event.event_id
    assert journal.summary(w["life"]) == first_summary
    with pytest.raises(FileExistsError, match="--resume"):
        run_demo(data_dir=tmp_path)


@pytest.mark.parametrize("terminal_status", ["OWNER_REJECTED", "EXPIRED", "CONSUMED"])
def test_nonproposed_plans_cannot_be_reused(tmp_path, terminal_status):
    w = _world(tmp_path)
    registry = w["fixture"]["plans"]
    if terminal_status == "OWNER_REJECTED":
        registry.observe_external_state(w["plan"].plan_id, terminal_status)
    elif terminal_status == "EXPIRED":
        assert registry.get(w["plan"].plan_id, w["plan"].expires_at + timedelta(seconds=1)).status == "EXPIRED"
    else:
        registry.observe_external_state(w["plan"].plan_id, "FAKE_OWNER_APPROVED")
        registry.observe_external_state(w["plan"].plan_id, "CONSUMED")
    reopened = PlanRegistry(tmp_path / "c06_state.sqlite")
    with pytest.raises(ValueError, match="cannot be reused"):
        reopened.add(w["plan"])


def test_corrupted_persisted_plan_or_event_fails_closed(tmp_path):
    w = _world(tmp_path)
    path = tmp_path / "c06_state.sqlite"
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable paper plan"):
            db.execute("UPDATE paper_plans SET immutable_hash='tampered' WHERE plan_id=?",
                (w["plan"].plan_id,))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM machine_events WHERE sequence=1")
        db.execute("DROP TRIGGER paper_plan_identity_is_immutable")
        db.execute("UPDATE paper_plans SET payload='{}' WHERE plan_id=?", (w["plan"].plan_id,))
    with pytest.raises(ValueError, match="corrupted persisted paper plan"):
        PlanRegistry(path)

    clean = tmp_path / "event-corrupt"
    w2 = _world(clean)
    with sqlite3.connect(clean / "c06_state.sqlite") as db:
        db.execute("DROP TRIGGER machine_events_are_append_only_update")
        db.execute("UPDATE machine_events SET event_type='MUTATED' WHERE sequence=1")
    with pytest.raises(ValueError, match="event ID mismatch|hash mismatch"):
        EventJournal(clean / "c06_state.sqlite")


def test_full_runtime_persists_terminal_trace_and_reopen_is_idempotent(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("persistent offline runtime attempted network access")

    import socket
    import urllib.request
    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    result = run_demo(data_dir=tmp_path)
    with sqlite3.connect(tmp_path / "venue.sqlite") as db:
        before = len(json.loads(db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])["writes"])
    first = reopen_persisted_demo(tmp_path)
    after_first = first["venue_write_count"]
    second = reopen_persisted_demo(tmp_path)
    assert result["positive_trace"]["final_position_state"] == "FLAT_RECONCILED"
    assert first["plan_status"] == second["plan_status"] == "CLOSED_RECONCILED"
    assert after_first == second["venue_write_count"]
    assert before > 0
    assert first["journal_summary"]["event_count"] == second["journal_summary"]["event_count"]
