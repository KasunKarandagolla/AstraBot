"""Research-only M4 source-clock primitives; no network, orders, P&L or signal decisions.

Integrates with existing AstraBot Candle and Trade contracts. Source completeness
is externally attested; historical exchange timestamps are NOT owner receipt.
A caller must not assert archive completeness without upstream verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import TYPE_CHECKING, Literal, Sequence

if TYPE_CHECKING:
    from astrabot.data.models import Candle, Trade

UTC = timezone.utc
ONE_MS = timedelta(milliseconds=1)
ONE_MIN = timedelta(minutes=1)
THIRTY_SECONDS = timedelta(seconds=30)


class SourceNotReady(ValueError):
    """Fail-closed historical-source condition, not a trading instruction."""


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise SourceNotReady(f"{field}: UTC-aware timestamp required")
    return value.astimezone(UTC)


def _symbol_and_instrument(rows: Sequence[object]) -> tuple[str, str]:
    if any(not hasattr(r, "symbol") or not hasattr(r, "instrument_id") for r in rows):
        raise SourceNotReady("missing symbol/instrument identity")
    identities = {(r.symbol, r.instrument_id) for r in rows}
    if len(identities) != 1:
        raise SourceNotReady("mixed symbol/instrument identities")
    return next(iter(identities))


@dataclass(frozen=True)
class PriorDayReference:
    symbol: str
    instrument_id: str
    reference_day: date
    as_of: datetime
    available_at: datetime
    high: Decimal
    low: Decimal
    candle_count: int
    source_digest: str
    fidelity: Literal["VENUE_REPORTED_1M_EXCHANGE_CLOSE_PROXY"] = (
        "VENUE_REPORTED_1M_EXCHANGE_CLOSE_PROXY"
    )


def prior_utc_day_reference(
    candles: Sequence[Candle], *, day: date, as_of: datetime,
) -> PriorDayReference:
    """Compute PDH/PDL only if all 1440 complete 1-minute bars are available.

    Binance close_time commonly ends at HH:MM:59.999; close+1ms reaches the
    next minute boundary. Do not add a second millisecond to available_at.
    """
    as_of = _utc(as_of, "as_of")
    start_current = datetime(day.year, day.month, day.day, tzinfo=UTC)
    previous = start_current - timedelta(days=1)
    if as_of < start_current:
        raise SourceNotReady("reference cannot be used before UTC-day boundary")

    selected = [c for c in candles if previous <= _utc(c.open_time, "open_time") < start_current]
    if len(selected) != 1440:
        raise SourceNotReady(f"prior UTC day requires 1440 candle rows; found {len(selected)}")
    symbol, instrument = _symbol_and_instrument(selected)
    by_open = {}
    for c in selected:
        if c.interval != "1m" or not c.is_closed or c.quality != "VALID":
            raise SourceNotReady("not a closed, valid 1m candle")
        opened = _utc(c.open_time, "open_time")
        ended = _utc(c.close_time, "close_time")
        available = _utc(c.available_at, "available_at")
        if opened in by_open:
            raise SourceNotReady("duplicate prior-day minute")
        if ended != opened + ONE_MIN - ONE_MS:
            raise SourceNotReady("unexpected 1m candle close boundary")
        if available < ended:
            raise SourceNotReady("source available_at precedes candle close")
        if available > as_of:
            raise SourceNotReady("prior-day candle was not available as of decision")
        if not (c.low <= c.open <= c.high and c.low <= c.close <= c.high):
            raise SourceNotReady("invalid candle OHLC")
        by_open[opened] = c
    if any(previous + i * ONE_MIN not in by_open for i in range(1440)):
        raise SourceNotReady("missing prior-day minute")
    ordered = [by_open[previous + i * ONE_MIN] for i in range(1440)]
    latest_available = max(_utc(c.available_at, "available_at") for c in ordered)
    # The digest must change if the market values change under the SAME source IDs.
    # It attests to this derived reference, not to an archive's original identity.
    digest_rows = [
        [c.source_record_id, c.observation_id, c.open_time.isoformat(),
         c.available_at.isoformat(), str(c.open), str(c.high), str(c.low),
         str(c.close), c.source_sha256]
        for c in ordered
    ]
    digest = sha256(json.dumps(digest_rows, separators=(",", ":")).encode()).hexdigest()
    return PriorDayReference(
        symbol=symbol, instrument_id=instrument, reference_day=previous.date(),
        as_of=as_of, available_at=latest_available,
        high=max(Decimal(c.high) for c in ordered),
        low=min(Decimal(c.low) for c in ordered), candle_count=1440,
        source_digest=digest,
    )


@dataclass(frozen=True)
class SourceCompleteness:
    """External evidence that source rows have been checked and hashed.

    complete_through: exclusive verified event-time watermark.
    observed_at: first time this verification may be used by replay.
    Does NOT establish original owner receipt or archive creation time.
    """
    complete_through: datetime
    observed_at: datetime
    source_digest: str
    provenance: Literal["SYNTHETIC_FIXTURE", "HASH_VERIFIED_ARCHIVE_REPLAY"]


@dataclass(frozen=True)
class TradeDerived30sBar:
    symbol: str
    instrument_id: str
    open_time: datetime
    end_exclusive: datetime
    available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_quantity: Decimal
    aggressive_buy_quantity: Decimal
    aggressive_sell_quantity: Decimal
    signed_aggressive_quantity: Decimal
    aggregate_print_count: int
    first_aggregate_id: str
    last_aggregate_id: str
    source_digest: str
    input_digest: str
    fidelity: Literal["TRADE_AGG_30S_DERIVED"] = "TRADE_AGG_30S_DERIVED"


def aggregate_verified_30s(
    trades: Sequence[Trade], *, bucket_start: datetime, as_of: datetime,
    completeness: SourceCompleteness,
) -> TradeDerived30sBar:
    """30s OHLC and signed volume derived ONLY from verified aggTrades.

    Refuses 1m-candle reconstruction, missing coverage attestations, future
    observations, duplicate IDs and noncontiguous aggregate trade sequences.
    Child trade fills and forced liquidations cannot be identified here.
    """
    if not isinstance(completeness, SourceCompleteness):
        raise SourceNotReady("explicit source-completeness evidence required")
    bucket_start = _utc(bucket_start, "bucket_start")
    as_of = _utc(as_of, "as_of")
    if bucket_start.second not in (0, 30) or bucket_start.microsecond:
        raise SourceNotReady("bucket must align to UTC 00/30 second")
    end = bucket_start + THIRTY_SECONDS
    watermark = _utc(completeness.complete_through, "complete_through")
    watermark_visible = _utc(completeness.observed_at, "completeness.observed_at")
    if watermark < end or watermark_visible > as_of:
        raise SourceNotReady("verified source-completeness watermark unavailable")
    if as_of < end + ONE_MS:
        raise SourceNotReady("30s bar is not yet closed/available")
    if (not isinstance(completeness.source_digest, str)
            or len(completeness.source_digest) != 64
            or any(ch not in "0123456789abcdefABCDEF" for ch in completeness.source_digest)):
        raise SourceNotReady("missing or malformed completeness source SHA-256")
    if completeness.provenance not in ("HASH_VERIFIED_ARCHIVE_REPLAY", "SYNTHETIC_FIXTURE"):
        raise SourceNotReady("unsupported completeness provenance")

    required = (
        "aggregate_trade_id", "trade_id", "price", "base_quantity", "buyer_is_maker",
        "aggressor_side", "available_at", "quality", "event_time",
    )
    if any(not all(hasattr(t, field) for field in required) for t in trades):
        raise SourceNotReady("requires original trade-derived records, not OHLC candles")
    selected = [t for t in trades if bucket_start <= _utc(t.event_time, "event_time") < end]
    if not selected:
        raise SourceNotReady("empty 30s window; cannot infer OHLC")
    symbol, instrument = _symbol_and_instrument(selected)
    if completeness.provenance == "HASH_VERIFIED_ARCHIVE_REPLAY":
        if any(t.source_sha256 != completeness.source_digest for t in selected):
            raise SourceNotReady("archive record hash differs from completeness source hash")
    seen = set()
    previous = None
    for t in selected:
        available = _utc(t.available_at, "trade.available_at")
        event = _utc(t.event_time, "trade.event_time")
        if available < event or available > as_of:
            raise SourceNotReady("trade timestamp is causally unavailable")
        if t.quality != "VALID":
            raise SourceNotReady("trade source quality is not VALID")
        identifier = str(t.aggregate_trade_id or t.trade_id)
        if not identifier.isascii() or not identifier.isdecimal():
            raise SourceNotReady("aggregate trade ID must be decimal integer")
        if identifier in seen:
            raise SourceNotReady("duplicate aggregate trade identifier")
        if previous is not None:
            prev_time, prev_id = previous
            if event < prev_time or (event == prev_time and int(identifier) <= int(prev_id)):
                raise SourceNotReady("trade event/ID order regression")
            if int(identifier) != int(prev_id) + 1:
                raise SourceNotReady("aggregate trade ID continuity gap")
        seen.add(identifier)
        expected = "SELL" if t.buyer_is_maker else "BUY"
        if t.aggressor_side != expected:
            raise SourceNotReady("buyer-maker aggressor mapping mismatch")
        if Decimal(t.price) <= 0 or Decimal(t.base_quantity) <= 0:
            raise SourceNotReady("nonpositive trade price or quantity")
        previous = (event, identifier)
    prices = [Decimal(t.price) for t in selected]
    volumes = [Decimal(t.base_quantity) for t in selected]
    buy = sum((Decimal(t.base_quantity) for t in selected if t.aggressor_side == "BUY"), Decimal(0))
    sell = sum((Decimal(t.base_quantity) for t in selected if t.aggressor_side == "SELL"), Decimal(0))
    ids = [str(t.aggregate_trade_id or t.trade_id) for t in selected]
    input_rows = [
        [str(t.aggregate_trade_id or t.trade_id), t.event_time.isoformat(),
         t.available_at.isoformat(), str(t.price), str(t.base_quantity),
         t.aggressor_side, t.source_sha256]
        for t in selected
    ]
    input_digest = sha256(json.dumps(input_rows, separators=(",", ":")).encode()).hexdigest()
    return TradeDerived30sBar(
        symbol=symbol, instrument_id=instrument,
        open_time=bucket_start, end_exclusive=end,
        available_at=max(end + ONE_MS, *(_utc(t.available_at, "trade.available_at") for t in selected), watermark_visible),
        open=prices[0], high=max(prices), low=min(prices), close=prices[-1],
        base_quantity=sum(volumes, Decimal(0)),
        aggressive_buy_quantity=buy, aggressive_sell_quantity=sell,
        signed_aggressive_quantity=buy - sell,
        aggregate_print_count=len(selected), first_aggregate_id=ids[0], last_aggregate_id=ids[-1],
        source_digest=completeness.source_digest,
        input_digest=input_digest,
    )
