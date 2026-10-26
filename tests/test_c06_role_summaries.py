from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

from astrabot.c06.role_summaries import summarize_fixture_journal, summarize_news_events
from astrabot.universe.eligibility import EventClearance
from c01_fake import FakeClock, FakeOwner, FakeVenue
from c06_fixture_paths import prepare_synthetic_state_dir, reset_synthetic_state_dir
from c06_paper_demo import build_fixture
from astrabot.data.models import stable_id


def test_news_event_role_distinguishes_synthetic_clear_veto_and_unknown():
    at = datetime(2025, 2, 1, tzinfo=timezone.utc)
    clear = summarize_news_events(EventClearance(state="CLEAR", verification_state="VERIFIED",
        as_of=at, source_ids=("synthetic-source-1",)))
    veto = summarize_news_events(EventClearance(state="VETO", verification_state="VERIFIED",
        as_of=at, source_ids=("synthetic-source-2",), reason="fixture veto"))
    unknown = summarize_news_events(EventClearance(state="UNKNOWN", verification_state="UNVERIFIED",
        as_of=at))
    unavailable = summarize_news_events(None, unavailable_reason="not supplied")

    assert clear.evidence_state == "VERIFIED_SYNTHETIC"
    assert veto.evidence_state == "VETO_SYNTHETIC"
    assert unknown.evidence_state == unavailable.evidence_state == "UNKNOWN_UNAVAILABLE"
    assert all(item.authentic_clearance == "UNKNOWN" for item in (clear, veto, unknown, unavailable))
    assert clear.fixture_label == veto.fixture_label == "SYNTHETIC_FIXTURE"


def test_journal_role_reports_unavailable_before_c01_and_verified_after(tmp_path):
    state_dir = prepare_synthetic_state_dir(tmp_path / "synthetic")
    fixture = build_fixture(storage_path=state_dir / "c06_state.sqlite")
    plan = fixture["gateway"].call("prepare_plan", {"candidate_id": fixture["candidate"].decision_id})
    before_owner = summarize_fixture_journal(state_dir)
    assert before_owner.verification_state == "UNAVAILABLE"
    assert before_owner.readiness == "UNAVAILABLE"
    assert before_owner.plan_id == plan.plan_id

    clock = FakeClock(fixture["as_of"])
    venue = FakeVenue(state_dir / "venue.sqlite", clock)
    owner = FakeOwner(state_dir / "owner.sqlite", venue, clock)
    assert owner.reconnect()
    summary = summarize_fixture_journal(state_dir)
    assert summary.verification_state == "VERIFIED"
    assert summary.readiness == "NOT_STARTED"
    assert summary.lifecycle_state == "NOT_STARTED"
    assert summary.owner_position_quantity == summary.venue_position_quantity == "0"
    assert summary.protection == "NOT_STARTED"
    assert summary.event_count >= 1
    assert summary.events[0].correlation_id == stable_id("c06.fake_lifecycle", plan.plan_id)


def test_journal_role_reports_hash_chain_tampering_as_inconsistent(tmp_path):
    state_dir = prepare_synthetic_state_dir(tmp_path / "synthetic")
    fixture = build_fixture(storage_path=state_dir / "c06_state.sqlite")
    fixture["gateway"].call("prepare_plan", {"candidate_id": fixture["candidate"].decision_id})
    path = state_dir / "c06_state.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER machine_events_are_append_only_update")
        db.execute("UPDATE machine_events SET event_type='TAMPERED' WHERE sequence=1")
    summary = summarize_fixture_journal(state_dir)
    assert summary.verification_state == "INCONSISTENT"
    assert summary.readiness == "INCONSISTENT"
    assert "verification failed" in summary.error


def test_reset_only_removes_known_files_from_marked_synthetic_directory(tmp_path):
    state_dir = prepare_synthetic_state_dir(tmp_path / "synthetic")
    (state_dir / "owner.sqlite").write_text("synthetic test database placeholder", encoding="utf-8")
    reset_synthetic_state_dir(state_dir)
    assert (state_dir / ".astrabot-c06-synthetic").is_file()
    assert not (state_dir / "owner.sqlite").exists()
    (state_dir / "notes.txt").write_text("unrelated", encoding="utf-8")
    try:
        reset_synthetic_state_dir(state_dir)
    except ValueError as exc:
        assert "unrelated files" in str(exc)
    else:
        raise AssertionError("fixture reset removed a directory containing unrelated data")
