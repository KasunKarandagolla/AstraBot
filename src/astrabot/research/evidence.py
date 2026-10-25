"""C03 point-in-time candle boundary shared by context and policy wrappers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from astrabot.data.models import Candle

INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}


class EvidenceError(ValueError):
    """A deterministic, machine-readable missing/invalid evidence result."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def history(
    candles: Sequence[Candle], *, interval: str, symbol: str,
    instrument_id: str, as_of: datetime, minimum: int = 1,
    fresh: bool = False,
) -> tuple[Candle, ...]:
    """Select an available closed prefix, then validate it without repairing it.

    Future observations (including their readiness flags) cannot influence an
    earlier result. A missing available observation in the middle of a prefix
    produces a gap, rather than an interpolated bar. Binance inclusive close
    timestamps and explicit post-close availability follow the C02 contract.
    """
    if as_of.utcoffset() != timedelta(0):
        raise EvidenceError("CLOCK_NOT_UTC")
    if interval not in INTERVALS:
        raise EvidenceError("UNSUPPORTED_TIMEFRAME")
    rows = tuple(c for c in candles if c.confirmed_at(as_of))
    suffix = interval.upper()
    if any(c.symbol != symbol or c.instrument_id != instrument_id for c in rows):
        raise EvidenceError(f"INSTRUMENT_MISMATCH_{suffix}")
    if any(c.interval != interval for c in rows):
        raise EvidenceError(f"TIMEFRAME_MISMATCH_{suffix}")
    if any(c.readiness != "READY" or c.quality != "VALID" for c in rows):
        raise EvidenceError(f"NON_READY_OR_INVALID_{suffix}")
    ids = [c.source_record_id for c in rows]
    observation_ids = [c.observation_id for c in rows]
    if len(set(ids)) != len(ids) or len(set(observation_ids)) != len(observation_ids):
        raise EvidenceError(f"DUPLICATE_{suffix}")
    seconds = INTERVALS[interval]
    step = timedelta(seconds=seconds)
    for c in rows:
        if (c.open_time.microsecond != 0 or int(c.open_time.timestamp()) % seconds
                or c.close_time != c.open_time + step - timedelta(milliseconds=1)):
            raise EvidenceError(f"MALFORMED_INTERVAL_{suffix}")
    if any(b.open_time <= a.open_time for a, b in zip(rows, rows[1:])):
        raise EvidenceError(f"OUT_OF_ORDER_{suffix}")
    if any(b.open_time - a.open_time != step for a, b in zip(rows, rows[1:])):
        raise EvidenceError(f"GAP_{suffix}")
    if fresh:
        expected = datetime.fromtimestamp(
            (int(as_of.timestamp()) // seconds) * seconds, timezone.utc
        ) - step
        if not rows or rows[-1].open_time != expected:
            raise EvidenceError(f"MISSING_LATEST_CLOSED_{suffix}")
    if len(rows) < minimum:
        raise EvidenceError(f"INSUFFICIENT_{suffix}_HISTORY_{minimum}")
    return rows
