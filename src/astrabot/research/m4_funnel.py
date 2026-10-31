"""Phase 6 M4 S1-S2 event intake; research diagnostics only, NEVER a trade signal.

Implements only the unambiguous frozen rules: prior-UTC-day PDH/PDL, first
trade at least one tick beyond the level, and 15-minute side/level dedup.
S3 participation, S4 failed response, S5 imbalance, S6 confirmation and
execution are deliberately NOT calculated: their missing metric definitions
cannot be silently invented. No network, orders, credentials or P&L.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Literal, Sequence, TYPE_CHECKING

from astrabot.research.m4_source_clock import PriorDayReference, SourceNotReady

if TYPE_CHECKING:
    from astrabot.data.models import Trade

UTC = timezone.utc
DEVELOPMENT_START = datetime(2022, 7, 1, tzinfo=UTC)
DEVELOPMENT_END = datetime(2023, 7, 1, tzinfo=UTC)
DEDUP = timedelta(minutes=15)
SHA_CHARS = set("0123456789abcdef")


@dataclass(frozen=True)
class SessionCoverage:
    """Explicit external coverage claim, not proof of historical owner receipt.

    session_start / complete_through describe a verified *event-time* interval
    [session_start, complete_through). replay_proxy_available_at is when a
    simulation may assume the coverage is usable; verified_at is when archived
    bytes were retrospectively authenticated (never a latency observation).
    """
    session_start: datetime
    complete_through: datetime
    replay_proxy_available_at: datetime
    source_digest: str
    provenance: Literal["SYNTHETIC_FIXTURE", "HASH_VERIFIED_ARCHIVE_REPLAY"]
    verified_at: datetime | None = None


@dataclass(frozen=True)
class Penetration:
    event_id: str
    symbol: str
    instrument_id: str
    side: Literal["LONG", "SHORT"]
    reference_type: Literal["PDL", "PDH"]
    reference_price: Decimal
    print_price: Decimal
    penetration_ticks: Decimal
    t1: datetime
    available_at: datetime
    aggregate_trade_id: str
    reference_digest: str
    source_digest: str


@dataclass(frozen=True)
class PenetrationFunnel:
    """Not an N6 event-yield census. Only stages S1 and S2 exist here."""
    status: Literal["RESEARCH_ONLY_S1_S2_NO_CONFIRMATION"]
    as_of: datetime
    n1_penetration_prints: int
    n2_deduplicated_events: int
    n3_participation_pass: None
    n4_no_extension_pass: None
    n5_imbalance_pass: None
    n6_confirmed_trigger: None
    candidates: tuple[Penetration, ...]
    unresolved: tuple[str, ...]


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise SourceNotReady(f"{label}: UTC-aware datetime required")
    return value.astimezone(UTC)


def _digest(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value.lower()) <= SHA_CHARS


def enumerate_m4_penetrations(
    trades: Sequence[Trade], *, reference: PriorDayReference,
    coverage: SessionCoverage, as_of: datetime, tick_size: Decimal,
) -> PenetrationFunnel:
    """Fail-closed offline M4 first-penetration census for ONE instrument/day.

    The caller must supply source provenance and explicit start/end coverage.
    This cannot establish owner's original receipt or authorize research data
    retrieval. It never outputs an approved or filled trading opportunity.
    """
    if not isinstance(reference, PriorDayReference) or not isinstance(coverage, SessionCoverage):
        raise SourceNotReady("reference and explicit session coverage are mandatory")
    cutoff = _utc(as_of, "as_of")
    start = _utc(coverage.session_start, "session_start")
    end = _utc(coverage.complete_through, "complete_through")
    proxy = _utc(coverage.replay_proxy_available_at, "replay_proxy_available_at")
    if not DEVELOPMENT_START <= start < DEVELOPMENT_END:
        raise SourceNotReady("outside authorised development window")
    if (start.hour, start.minute, start.second, start.microsecond) != (0, 0, 0, 0):
        raise SourceNotReady("session coverage must start at UTC midnight")
    if not start < cutoff <= end <= min(start + timedelta(days=1), DEVELOPMENT_END):
        raise SourceNotReady("incomplete session coverage or forbidden source range")
    if proxy > cutoff:
        raise SourceNotReady("source coverage not causally available as of cutoff")
    if not _digest(coverage.source_digest):
        raise SourceNotReady("coverage requires SHA-256 source identity")
    if coverage.provenance not in ("SYNTHETIC_FIXTURE", "HASH_VERIFIED_ARCHIVE_REPLAY"):
        raise SourceNotReady("unsupported source provenance")
    if coverage.provenance == "HASH_VERIFIED_ARCHIVE_REPLAY" and coverage.verified_at is None:
        raise SourceNotReady("archive verification timestamp missing")
    if coverage.verified_at is not None:
        _utc(coverage.verified_at, "verified_at")
    if (reference.reference_day != (start - timedelta(days=1)).date()
            or _utc(reference.as_of, "reference.as_of") > start
            or _utc(reference.available_at, "reference.available_at") > start):
        raise SourceNotReady("PDH/PDL reference unavailable at UTC day start")
    if reference.high <= reference.low or not _digest(reference.source_digest):
        raise SourceNotReady("invalid prior-day reference or provenance")
    if not isinstance(tick_size, Decimal) or not tick_size.is_finite() or tick_size <= 0:
        raise SourceNotReady("positive Decimal tick size required")
    if reference.high % tick_size or reference.low % tick_size:
        raise SourceNotReady("reference price not aligned to supplied tick")
    required = ("symbol", "instrument_id", "event_time", "available_at", "quality",
                "aggregate_trade_id", "trade_id", "price", "base_quantity",
                "buyer_is_maker", "aggressor_side", "fidelity", "source_sha256")
    if any(not all(hasattr(t, name) for name in required) for t in trades):
        raise SourceNotReady("trade input required; 1m OHLC cannot reconstruct prints")
    # Event-time cutoff is EXCLUSIVE. No later market observation may change this result.
    visible = [t for t in trades if start <= _utc(t.event_time, "trade.event_time") < cutoff]
    n1 = 0
    candidates: list[Penetration] = []
    previous_time: datetime | None = None
    previous_id: int | None = None
    last_selected: dict[str, datetime] = {}
    for t in visible:
        t_time = _utc(t.event_time, "trade.event_time")
        arrival = _utc(t.available_at, "trade.available_at")
        if (arrival < t_time or arrival > cutoff or t.symbol != reference.symbol
                or t.instrument_id != reference.instrument_id
                or t.quality != "VALID" or t.fidelity not in ("TRADE_AGG", "SYNTHETIC_FIXTURE")):
            raise SourceNotReady("trade chronology, identity, quality or fidelity invalid")
        if coverage.provenance == "HASH_VERIFIED_ARCHIVE_REPLAY" and t.source_sha256 != coverage.source_digest:
            raise SourceNotReady("trade provenance does not match session archive SHA-256")
        identifier = str(t.aggregate_trade_id or t.trade_id)
        if not identifier.isascii() or not identifier.isdecimal():
            raise SourceNotReady("non-numeric aggregate trade ID")
        numeric_id = int(identifier)
        if previous_id is not None and (
            numeric_id != previous_id + 1 or t_time < previous_time
        ):
            raise SourceNotReady("trade order/ID continuity gap; first-event proof invalid")
        previous_id, previous_time = numeric_id, t_time
        if t.aggressor_side != ("SELL" if t.buyer_is_maker else "BUY"):
            raise SourceNotReady("aggressor side conflicts with buyer-maker field")
        price, qty = Decimal(t.price), Decimal(t.base_quantity)
        if not price.is_finite() or price <= 0 or not qty.is_finite() or qty <= 0:
            raise SourceNotReady("invalid print price or quantity")
        if price % tick_size:
            raise SourceNotReady("print price not tick aligned")
        if price <= reference.low - tick_size:
            side, level, anchor, ticks = "LONG", "PDL", reference.low, (reference.low - price) / tick_size
        elif price >= reference.high + tick_size:
            side, level, anchor, ticks = "SHORT", "PDH", reference.high, (price - reference.high) / tick_size
        else:
            continue
        n1 += 1
        if side in last_selected and t_time - last_selected[side] < DEDUP:
            continue
        last_selected[side] = t_time
        identity = "|".join((reference.instrument_id, level, str(anchor), t_time.isoformat(),
                             identifier, reference.source_digest, coverage.source_digest))
        candidates.append(Penetration(
            event_id=sha256(identity.encode()).hexdigest()[:24],
            symbol=reference.symbol, instrument_id=reference.instrument_id,
            side=side, reference_type=level, reference_price=anchor,
            print_price=price, penetration_ticks=ticks,
            t1=t_time, available_at=arrival, aggregate_trade_id=identifier,
            reference_digest=reference.source_digest, source_digest=coverage.source_digest,
        ))
    return PenetrationFunnel(
        status="RESEARCH_ONLY_S1_S2_NO_CONFIRMATION",
        as_of=cutoff, n1_penetration_prints=n1,
        n2_deduplicated_events=len(candidates),
        n3_participation_pass=None, n4_no_extension_pass=None,
        n5_imbalance_pass=None, n6_confirmed_trigger=None,
        candidates=tuple(candidates),
        unresolved=(
            "S3 participation: freeze exact 30m median volume denominator and aggregation unit",
            "S4 failure: freeze ATR14(5m) estimator, volume-decay window and impact/volume proxy",
            "S5 signed 3m volume and S6 confirmation require independent verified source clock",
            "S7 economics/stop-cost gate remains pending F-02 and licence/P1",
        ),
    )
