from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import socket
import sys
import urllib.request

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from astrabot.c06.paper_mvp import C06ToolGateway, EventJournal
from c06_paper_demo import (
    DeterministicOfflineCoordinator, build_fixture, run_demo, run_negative_cases,
)


SIX_TOOLS = (
    "scan_opportunities", "evaluate_symbol", "evaluate_candidates", "prepare_plan",
    "get_plan_status", "get_operations_summary",
)


def test_typed_six_tool_boundary_and_immutable_non_executable_proposal():
    fixture = build_fixture()
    gateway: C06ToolGateway = fixture["gateway"]
    candidate = fixture["candidate"]
    assert gateway.tool_names == SIX_TOOLS
    for name in ("approve", "claim", "submit", "place_order", "set_plan_status"):
        assert not hasattr(gateway, name)
    coordinator = DeterministicOfflineCoordinator(gateway)
    exposed_methods = {name for name in dir(coordinator) if not name.startswith("_")
        and callable(getattr(coordinator, name))}
    assert exposed_methods == {"call"}
    assert not hasattr(coordinator, "owner") and not hasattr(coordinator, "venue")
    with pytest.raises(ValidationError):
        gateway.call("prepare_plan", {"candidate_id": candidate.decision_id,
            "approved_max_risk_usdt": "999999"})
    assert not gateway._plans._plans
    with pytest.raises(ValueError, match="immutable offline evaluation"):
        gateway.call("scan_opportunities", {"as_of": fixture["as_of"] + timedelta(seconds=1)})
    plan = gateway.call("prepare_plan", {"candidate_id": candidate.decision_id})
    assert plan.verify_hash()
    assert plan.research_status == "RESEARCH_ONLY" and plan.executable is False
    assert plan.entry_min == candidate.entry_min and plan.entry_max == candidate.entry_max
    assert plan.modeled_loss_usdt == candidate.economics.proposed_modeled_loss_usdt
    assert plan.proposed_quantity == candidate.economics.proposed_quantity
    with pytest.raises(ValidationError):
        plan.executable = True


def test_positive_fake_owner_lifecycle_timer_and_journal_are_reproducible():
    first = run_demo()
    second = run_demo()
    positive = first["positive_trace"]
    assert tuple(call["tool"] for call in first["tool_calls"]) == SIX_TOOLS
    assert first["fixture"] == "C04_SYNTHETIC_FULLY_ELIGIBLE_TEST_FIXTURE"
    assert first["openbot_integration"] == "NOT_VERIFIED"
    assert positive["final_position_state"] == "FLAT_RECONCILED"
    assert positive["final_quantity"] == "0.0"
    assert positive["plan_status"] == "CLOSED_RECONCILED"
    assert positive["duplicate_claim"] == "REJECTED"
    assert positive["partial_exit_quantity"] == "4.0"
    assert positive["remaining_before_timer"] == "6.0"
    assert positive["coordinator_unavailable_after_open"] is True
    assert positive["journal_unavailable_during_timer_exit"] is True
    assert first["machine_events"] == second["machine_events"]
    assert positive["journal_summary"]["event_digest"] == second["positive_trace"]["journal_summary"]["event_digest"]
    first_fill = next(e for e in first["machine_events"] if e["event_type"] == "SIMULATED_ENTRY_PROTECTED")
    timer_exit = next(e for e in first["machine_events"]
        if e["event_type"] == "TIME_LIMIT_REDUCE_ONLY_EXIT_AND_FLAT_CONFIRMATION")
    fill_details = dict(first_fill["details"])
    assert datetime.fromisoformat(timer_exit["occurred_at"]) == (
        datetime.fromisoformat(fill_details["first_fill_at"]) + timedelta(hours=11, minutes=55)
    )
    timestamps = [datetime.fromisoformat(e["occurred_at"])
        for e in first["machine_events"]]
    assert timestamps == sorted(timestamps)


def test_negative_owner_expiry_missing_evidence_replay_and_risk_tamper_fail_closed():
    negative = run_negative_cases()
    assert negative["owner_rejected"]["status"] == "OWNER_REJECTED"
    assert negative["owner_rejected"]["venue_writes"] == 0
    assert negative["owner_rejected"]["new_exposure"] is False
    assert negative["approval_expired"]["claim"] == "REJECTED"
    assert negative["approval_expired"]["venue_writes"] == 0
    assert negative["approval_expired"]["new_exposure"] is False
    assert negative["missing_event_evidence"]["decision"] == "NO_TRADE"
    assert negative["missing_event_evidence"]["plan_created"] is False
    assert negative["missing_event_evidence"]["new_exposure"] is False
    assert negative["missing_market_evidence"]["decision"] == "NO_TRADE"
    assert negative["missing_market_evidence"]["plan_created"] is False
    assert negative["missing_market_evidence"]["new_exposure"] is False
    checks = run_demo()["negative_checks"]
    assert checks["coordinator_risk_override"] == "REJECTED_BY_TYPED_SCHEMA"
    assert checks["tampered_owner_risk_hash"] == "REJECTED_BY_C01_FAKE_OWNER"
    assert checks["approval_nonce_reuse"] == "REJECTED_WITH_NO_SECOND_ENTRY"


def test_offline_driver_and_c01_fakes_make_no_socket_or_url_requests(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("offline C06 demonstration attempted network access")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    result = run_demo()
    assert result["positive_trace"]["final_position_state"] == "FLAT_RECONCILED"


def test_machine_journal_is_append_only_and_summary_is_repeatable():
    journal = EventJournal()
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = journal.append(occurred_at=at, actor="offline_test_driver", event_type="ONE",
        plan_id="plan", lifecycle_id="life")
    prefix = journal.events
    journal.append(occurred_at=at + timedelta(seconds=1), actor="fake_owner", event_type="TWO",
        plan_id="plan", lifecycle_id="life")
    assert journal.events[:1] == prefix == (first,)
    with pytest.raises(ValidationError):
        first.event_type = "REWRITTEN"
    assert journal.summary("life") == journal.summary("life")
    with pytest.raises(ValueError, match="monotonic"):
        journal.append(occurred_at=at, actor="fake_owner", event_type="BACKDATED",
            plan_id="plan", lifecycle_id="life")
