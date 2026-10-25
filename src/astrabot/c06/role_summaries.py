"""Typed, read-only evidence summaries for the offline C06 fixture roles.

These values distinguish synthetic exercise evidence from authentic market
clearance. Journal state is reconstructed from the durable C06 hash chain and
the existing C01 fake owner/venue stores; this module adds no write path.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict

from astrabot.c06.paper_mvp import EventJournal, JournalEvent, PaperPlan, PlanRegistry
from astrabot.data.models import stable_id
from astrabot.universe.eligibility import EventClearance


class _Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NewsEventsEvidenceSummary(_Summary):
    evidence_state: Literal[
        "VERIFIED_SYNTHETIC", "VETO_SYNTHETIC", "UNKNOWN_UNAVAILABLE"]
    event_state: Literal["CLEAR", "VETO", "UNKNOWN"]
    verification_state: Literal["VERIFIED", "UNVERIFIED"]
    fixture_label: Literal["SYNTHETIC_FIXTURE"] = "SYNTHETIC_FIXTURE"
    source_ids: tuple[str, ...] = ()
    as_of: datetime | None = None
    reason: str | None = None
    authentic_clearance: Literal["UNKNOWN"] = "UNKNOWN"


def summarize_news_events(clearance: EventClearance | None, *,
                          unavailable_reason: str | None = None) -> NewsEventsEvidenceSummary:
    """Label fixture evidence without ever promoting it to authentic clearance."""
    if clearance is None:
        return NewsEventsEvidenceSummary(evidence_state="UNKNOWN_UNAVAILABLE",
            event_state="UNKNOWN", verification_state="UNVERIFIED",
            reason=unavailable_reason or "event evidence unavailable")
    if clearance.state == "CLEAR" and clearance.verification_state == "VERIFIED" and clearance.source_ids:
        label = "VERIFIED_SYNTHETIC"
    elif clearance.state == "VETO" and clearance.verification_state == "VERIFIED" and clearance.source_ids:
        label = "VETO_SYNTHETIC"
    else:
        label = "UNKNOWN_UNAVAILABLE"
    return NewsEventsEvidenceSummary(evidence_state=label, event_state=clearance.state,
        verification_state=clearance.verification_state, source_ids=clearance.source_ids,
        as_of=clearance.as_of, reason=clearance.reason)


class JournalEventRecord(_Summary):
    event_id: str
    occurred_at: datetime
    received_at: datetime
    actor: str
    event_type: str
    plan_id: str
    lifecycle_id: str
    correlation_id: str
    details: tuple[tuple[str, str], ...]


class JournalRoleSummary(_Summary):
    verification_state: Literal["VERIFIED", "UNAVAILABLE", "INCONSISTENT"]
    fixture_label: Literal["SYNTHETIC_FIXTURE"] = "SYNTHETIC_FIXTURE"
    plan_id: str | None = None
    plan_hash: str | None = None
    plan_status: str | None = None
    lifecycle_id: str | None = None
    lifecycle_state: str | None = None
    owner_reconciled: bool | None = None
    readiness: Literal["READY", "UNRESOLVED", "NOT_STARTED", "UNAVAILABLE", "INCONSISTENT"]
    owner_position_quantity: str | None = None
    venue_position_quantity: str | None = None
    approved_max_risk_usdt: str | None = None
    reserved_risk_usdt: str | None = None
    reservation_status: str | None = None
    protection: Literal[
        "VERIFIED", "MISSING_OR_UNVERIFIED", "FLAT_RECONCILED", "NOT_STARTED", "UNAVAILABLE"]
    unresolved_intents: tuple[str, ...] = ()
    active_order_ids: tuple[str, ...] = ()
    event_count: int = 0
    event_ids: tuple[str, ...] = ()
    correlation_ids: tuple[str, ...] = ()
    event_types: tuple[tuple[str, int], ...] = ()
    event_digest: str | None = None
    events: tuple[JournalEventRecord, ...] = ()
    error: str | None = None


def _read_c01_state(path: Path) -> dict | None:
    if not path.is_file():
        return None
    uri = path.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as db:
        result = db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("C01 SQLite integrity check failed")
        row = db.execute("SELECT payload FROM state WHERE id=1").fetchone()
    if not row:
        raise ValueError("C01 state row is missing")
    value = json.loads(row[0])
    if not isinstance(value, dict):
        raise ValueError("C01 state payload is not an object")
    return value


def _event_records(journal: EventJournal, lifecycle_id: str) -> tuple[JournalEventRecord, ...]:
    return tuple(JournalEventRecord(event_id=event.event_id,
        occurred_at=event.occurred_at, received_at=event.received_at,
        actor=event.actor, event_type=event.event_type, plan_id=event.plan_id,
        lifecycle_id=event.lifecycle_id, correlation_id=event.correlation_id,
        details=event.details)
        for event in journal.events if event.lifecycle_id == lifecycle_id)


def _read_verified_c06(path: Path) -> tuple[dict[str, PaperPlan], dict[str, str], tuple[JournalEvent, ...]]:
    """Validate C06 tables using a read-only SQLite connection and snapshot."""
    if not path.is_file():
        raise FileNotFoundError(path.name)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as db:
        result = db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("C06 SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("C06 foreign-key check failed")
        db.execute("BEGIN")
        rows = db.execute("SELECT plan_id, lifecycle_id, immutable_hash, payload, expires_at, status "
            "FROM paper_plans ORDER BY plan_id").fetchall()
        plans: dict[str, PaperPlan] = {}
        statuses: dict[str, str] = {}
        allowed = set(PlanRegistry._transitions)
        allowed.update(target for targets in PlanRegistry._transitions.values() for target in targets)
        for plan_id, lifecycle_id, plan_hash, payload, expires_at, status in rows:
            try:
                plan = PaperPlan.model_validate_json(payload)
            except Exception as exc:
                raise ValueError("corrupted persisted paper plan") from exc
            if (plan.plan_id != plan_id or plan.immutable_hash != plan_hash or not plan.verify_hash()
                or plan.expires_at.isoformat() != expires_at
                or lifecycle_id != stable_id("c06.fake_lifecycle", plan_id)
                or status not in allowed):
                raise ValueError("inconsistent persisted paper plan identity, hash, expiry or status")
            history = db.execute("SELECT sequence, from_status, to_status FROM paper_plan_transitions "
                "WHERE plan_id=? ORDER BY sequence", (plan_id,)).fetchall()
            if not history or history[0] != (0, None, "PROPOSED_RESEARCH_ONLY"):
                raise ValueError("persisted paper plan transition history is invalid")
            prior = None
            for index, (sequence, from_status, to_status) in enumerate(history):
                if sequence != index or to_status not in allowed:
                    raise ValueError("persisted paper plan transition sequence is invalid")
                if index == 0:
                    if from_status is not None:
                        raise ValueError("persisted initial plan transition is invalid")
                elif from_status != prior or to_status not in PlanRegistry._transitions[prior]:
                    raise ValueError("persisted plan transition is not allowed")
                prior = to_status
            if prior != status:
                raise ValueError("persisted status disagrees with its transition history")
            plans[plan_id], statuses[plan_id] = plan, status

        event_rows = db.execute("SELECT sequence, event_id, occurred_at, received_at, actor, event_type, "
            "plan_id, lifecycle_id, correlation_id, details_json, previous_hash, record_hash "
            "FROM machine_events ORDER BY sequence").fetchall()
        events: list[JournalEvent] = []
        previous_hash = "0" * 64
        previous_occurred = previous_received = None
        for expected, row in enumerate(event_rows, start=1):
            (sequence, event_id, occurred_at, received_at, actor, event_type, plan_id,
                lifecycle_id, correlation_id, details_json, stored_previous, stored_hash) = row
            if sequence != expected or stored_previous != previous_hash:
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
            plan = plans.get(plan_id)
            if (event_id != EventJournal._event_id(body)
                or stored_hash != EventJournal._record_hash(event, previous_hash)
                or not plan or lifecycle_id != stable_id("c06.fake_lifecycle", plan_id)
                or correlation_id not in {plan_id, lifecycle_id}
                or (previous_occurred and event.occurred_at < previous_occurred)
                or (previous_received and event.received_at < previous_received)):
                raise ValueError("persisted C06 machine event or correlation is inconsistent")
            events.append(event)
            previous_hash = stored_hash
            previous_occurred, previous_received = event.occurred_at, event.received_at
    return plans, statuses, tuple(events)


def summarize_fixture_journal(state_dir: str | Path, *,
                              lifecycle_id: str | None = None) -> JournalRoleSummary:
    """Read and verify one synthetic lifecycle without mutating any store."""
    path = Path(state_dir).expanduser().resolve()
    marker = path / ".astrabot-c06-synthetic"
    if not path.is_dir() or not marker.is_file() or marker.read_text(encoding="utf-8") != "SYNTHETIC_ONLY\n":
        raise ValueError("journal summary requires a marked synthetic-only state directory")
    state_path = path / "c06_state.sqlite"
    try:
        plans, statuses, all_events = _read_verified_c06(state_path)
    except FileNotFoundError as exc:
        return JournalRoleSummary(verification_state="UNAVAILABLE", readiness="UNAVAILABLE",
            protection="UNAVAILABLE", error="C06 durable journal or plan store is unavailable")
    except Exception as exc:
        return JournalRoleSummary(verification_state="INCONSISTENT", readiness="INCONSISTENT",
            protection="UNAVAILABLE", error=f"C06 durable verification failed: {type(exc).__name__}")

    plan_ids = sorted(plans)
    if lifecycle_id is None:
        if len(plan_ids) > 1:
            return JournalRoleSummary(verification_state="INCONSISTENT", readiness="INCONSISTENT",
                protection="UNAVAILABLE", error="multiple fixture plans require an explicit lifecycle ID")
        if not plan_ids:
            return JournalRoleSummary(verification_state="VERIFIED", readiness="NOT_STARTED",
                protection="NOT_STARTED", event_digest=stable_id("c06.journal_summary.v1", ()))
        plan_id = plan_ids[0]
        plan = plans[plan_id]
        lifecycle_id = stable_id("c06.fake_lifecycle", plan_id)
    else:
        plan = next((p for p in plans.values()
            if stable_id("c06.fake_lifecycle", p.plan_id) == lifecycle_id), None)
        if plan is None:
            return JournalRoleSummary(verification_state="INCONSISTENT", readiness="INCONSISTENT",
                protection="UNAVAILABLE", lifecycle_id=lifecycle_id,
                error="requested lifecycle has no verified immutable plan")
        plan_id = plan.plan_id

    records = tuple(JournalEventRecord(event_id=event.event_id,
        occurred_at=event.occurred_at, received_at=event.received_at,
        actor=event.actor, event_type=event.event_type, plan_id=event.plan_id,
        lifecycle_id=event.lifecycle_id, correlation_id=event.correlation_id,
        details=event.details) for event in all_events if event.lifecycle_id == lifecycle_id)
    event_ids = tuple(record.event_id for record in records)
    event_types = tuple(sorted(Counter(record.event_type for record in records).items()))
    common = {"plan_id": plan_id, "plan_hash": plan.immutable_hash,
        "plan_status": statuses[plan_id], "lifecycle_id": lifecycle_id,
        "event_count": len(records), "event_ids": event_ids,
        "correlation_ids": tuple(record.correlation_id for record in records),
        "event_types": event_types,
        "event_digest": stable_id("c06.journal_summary.v1", event_ids), "events": records}

    try:
        owner = _read_c01_state(path / "owner.sqlite")
        venue = _read_c01_state(path / "venue.sqlite")
    except Exception as exc:
        return JournalRoleSummary(verification_state="INCONSISTENT", readiness="INCONSISTENT",
            protection="UNAVAILABLE", **common,
            error=f"C01 durable verification failed: {type(exc).__name__}")
    if owner is None and venue is None:
        return JournalRoleSummary(verification_state="UNAVAILABLE", readiness="UNAVAILABLE",
            protection="UNAVAILABLE", **common,
            error="C01 owner/venue lifecycle stores have not been initialized")
    if owner is None or venue is None:
        return JournalRoleSummary(verification_state="INCONSISTENT", readiness="INCONSISTENT",
            protection="UNAVAILABLE", **common,
            error="only one of the separate C01 owner/venue stores is present")

    try:
        owner_positions = owner["positions"]
        venue_positions = venue["positions"]
        position = owner_positions.get(lifecycle_id)
        venue_position = Decimal(venue_positions.get(lifecycle_id, "0"))
        owner_quantity = Decimal(position["quantity"]) if position else Decimal(0)
        if owner_quantity != abs(venue_position):
            raise ValueError("C01 owner quantity disagrees with fake venue truth")
        if not position and venue_position != 0:
            raise ValueError("venue position has no C01 owner lifecycle")
        if position and position.get("state") == "FLAT_RECONCILED" and venue_position != 0:
            raise ValueError("C01 flat terminal state disagrees with fake venue position")
        auth = owner.get("approvals", {}).get(plan_id)
        reservation = owner.get("reservations", {}).get("res-" + plan_id)
        intent_rows = [item for item in owner.get("intents", {}).values()
            if item.get("lifecycle_id") == lifecycle_id
            and item.get("state") in {"PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION"}]
        management_rows = [cid for cid, item in owner.get("management", {}).items()
            if item.get("lifecycle_id") == lifecycle_id
            and item.get("status") in {"PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION"}]
        exit_request = owner.get("exit_requests", {}).get(lifecycle_id)
        if exit_request and exit_request.get("status") != "FLAT_RECONCILED":
            management_rows.append(exit_request.get("client_order_id", "unidentified-exit-request"))
        orders = {cid: order for cid, order in venue["orders"].items()
            if order.get("lifecycle_id") == lifecycle_id}
        active_order_ids = tuple(sorted(cid for cid, order in orders.items()
            if order.get("status") in {"ACKNOWLEDGED", "PARTIAL"}))
        stop_ids = (position or {}).get("stop_ids", [])
        verified_stops = [cid for cid in stop_ids if cid in orders
            and orders[cid].get("visible") is True
            and orders[cid].get("status") in {"ACKNOWLEDGED", "PARTIAL"}]
        if not position:
            protection = "NOT_STARTED"
        elif owner_quantity == 0 and position.get("state") == "FLAT_RECONCILED":
            protection = "FLAT_RECONCILED"
        elif owner_quantity == 0:
            protection = "NOT_STARTED"
        elif len(verified_stops) == len(stop_ids) and bool(stop_ids):
            protection = "VERIFIED"
        else:
            protection = "MISSING_OR_UNVERIFIED"
        unresolved = tuple(sorted([item["intent_id"] for item in intent_rows] + management_rows))
        owner_reconciled = bool(owner.get("reconciled", False))
        is_inconsistent = not owner_reconciled or bool(unresolved) or (
            owner_quantity > 0 and protection != "VERIFIED")
        readiness = "UNRESOLVED" if is_inconsistent else (
            "READY" if position else "NOT_STARTED")
        return JournalRoleSummary(verification_state="VERIFIED", readiness=readiness,
            lifecycle_state=(position or {}).get("state", "NOT_STARTED"),
            owner_reconciled=owner_reconciled, owner_position_quantity=str(owner_quantity),
            venue_position_quantity=str(venue_position),
            approved_max_risk_usdt=str(auth["approved_max_risk_usdt"]) if auth else None,
            reserved_risk_usdt=str(reservation["risk"]) if reservation else None,
            reservation_status=reservation.get("status") if reservation else None,
            protection=protection, unresolved_intents=unresolved,
            active_order_ids=active_order_ids, **common)
    except Exception as exc:
        return JournalRoleSummary(verification_state="INCONSISTENT", readiness="INCONSISTENT",
            protection="UNAVAILABLE", **common,
            error=f"C01 state does not reconcile: {type(exc).__name__}")
