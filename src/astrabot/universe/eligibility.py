"""Point-in-time Binance USDⓈ-M eligibility and research shortlist.

The policy defaults reproduce the provisional v1.5 research gates. They are
not optimized, and a selected symbol remains a research/watchlist item only.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from astrabot.contracts import Contract, UTC
from astrabot.data.models import (
    Candle,
    DepthSnapshot,
    InstrumentMetadata,
    OpenInterestObservation,
    SpreadSample,
    Ticker24h,
    binance_usdm_instrument_id,
)


class FreshnessPolicy(Contract):
    """Explicit observation freshness cutoffs; v1.5 metadata cutoff is 1h."""

    metadata: timedelta = timedelta(hours=1)
    ticker: timedelta = timedelta(seconds=60)
    spread: timedelta = timedelta(seconds=60)
    depth: timedelta = timedelta(seconds=10)
    open_interest: timedelta = timedelta(seconds=300)
    candle_close_lag: timedelta = timedelta(seconds=10)
    event_clearance: timedelta = timedelta(hours=1)


class EventClearance(Contract):
    state: Literal["CLEAR", "VETO", "UNKNOWN"]
    verification_state: Literal["VERIFIED", "UNVERIFIED"]
    as_of: UTC
    source_ids: tuple[str, ...] = ()
    reason: str | None = None

    @model_validator(mode="after")
    def verified_claim_has_sources(self):
        if self.state in ("CLEAR", "VETO") and (
            self.verification_state != "VERIFIED" or not self.source_ids
        ):
            raise ValueError("clearance or veto requires verified source IDs")
        return self


class SymbolData(Contract):
    """Point-in-time public observations supplied for one exchange symbol."""

    metadata: InstrumentMetadata | None = None
    ticker: Ticker24h | None = None
    candles_5m: tuple[Candle, ...] = ()
    candles_15m: tuple[Candle, ...] = ()
    candles_1h: tuple[Candle, ...] = ()
    candles_4h: tuple[Candle, ...] = ()
    spread_samples: tuple[SpreadSample, ...] = ()
    depth: DepthSnapshot | None = None
    open_interest: OpenInterestObservation | None = None
    event_clearance: EventClearance | None = None


class EligibilityRecord(Contract):
    symbol: str
    instrument_id: str | None = None
    state: Literal["COLD", "WARMING", "READY", "DEGRADED", "UNAVAILABLE", "INELIGIBLE"]
    eligible: bool
    reasons: tuple[str, ...] = ()
    turnover_usdt: Decimal | None = None
    median_spread_fraction: Decimal | None = None
    bid_depth_usdt: Decimal | None = None
    ask_depth_usdt: Decimal | None = None
    oi_notional_usdt: Decimal | None = None
    event_source_ids: tuple[str, ...] = ()
    shortlist_status: Literal["SELECTED", "NOT_ELIGIBLE", "NO_CONTEXT", "RANKED_OUT_LIMIT"] = "NOT_ELIGIBLE"
    shortlist_reasons: tuple[str, ...] = ()
    structure_proximity: Decimal | None = None


class UniverseResult(Contract):
    as_of: UTC
    considered: tuple[EligibilityRecord, ...]
    shortlist: tuple[str, ...]
    purpose: Literal["RESEARCH_WATCHLIST"] = "RESEARCH_WATCHLIST"
    executable: Literal[False] = False
    policy_version: str = "c02-universe-v1"
    selection_limit: int = 15


def _fresh(observation, as_of: datetime, maximum_age: timedelta) -> bool:
    return (
        observation is not None
        and observation.readiness == "READY"
        and observation.quality == "VALID"
        and observation.available_at <= as_of
        and observation.event_time <= as_of
        and timedelta(0) <= as_of - observation.event_time <= maximum_age
    )


def _matching(items, symbol: str, instrument_id: str | None = None):
    return [item for item in items if item.symbol == symbol
            and (instrument_id is None or item.instrument_id == instrument_id)]


def _closed_contiguous(
    candles: tuple[Candle, ...],
    *,
    symbol: str,
    instrument_id: str | None,
    interval: str,
    count: int,
    as_of: datetime,
) -> tuple[bool, str | None, list[Candle]]:
    rows = _matching(candles, symbol, instrument_id)
    # A candle is evidence only once its post-close availability boundary has
    # passed. Closed status alone is insufficient for same-timestamp replay.
    confirmed = sorted(
        (c for c in rows if c.interval == interval and c.readiness == "READY"
         and c.quality == "VALID" and c.confirmed_at(as_of)),
        key=lambda c: c.open_time,
    )
    opens = [c.open_time for c in confirmed]
    if len(opens) != len(set(opens)):
        return False, "DUPLICATE_" + interval.upper() + "_CANDLES", confirmed
    if len(confirmed) < count:
        return False, f"INSUFFICIENT_{interval.upper()}_WARMUP", confirmed
    tail = confirmed[-count:]
    delta = {"5m": timedelta(minutes=5), "15m": timedelta(minutes=15),
             "1h": timedelta(hours=1), "4h": timedelta(hours=4)}[interval]
    if any(right.open_time - left.open_time != delta for left, right in zip(tail, tail[1:])):
        return False, f"GAP_OR_ORDER_{interval.upper()}_WARMUP", confirmed
    # Rows after a timestamp regression are rejected even if a sorted copy
    # would appear continuous. Source order is part of the quality contract.
    source_opens = [c.open_time for c in rows if c.interval == interval and c.readiness == "READY"
                    and c.quality == "VALID" and c.confirmed_at(as_of)]
    if any(right <= left for left, right in zip(source_opens, source_opens[1:])):
        return False, f"DUPLICATE_OR_OUT_OF_ORDER_{interval.upper()}_CANDLES", confirmed
    return True, None, confirmed


def _depth_within(depth: DepthSnapshot, side: Literal["BUY", "SELL"], threshold: Decimal) -> Decimal:
    mid = (depth.bids[0].price + depth.asks[0].price) / 2
    if side == "BUY":
        levels = (level for level in depth.asks if level.price <= mid * (Decimal(1) + threshold))
    else:
        levels = (level for level in depth.bids if level.price >= mid * (Decimal(1) - threshold))
    return sum((level.price * level.quantity for level in levels), Decimal(0))


def _structure_proximity(candles: list[Candle], symbol: str, instrument_id: str | None,
                         as_of: datetime,
                         lookback: int = 20) -> Decimal | None:
    eligible = [c for c in candles if c.symbol == symbol
                and (instrument_id is None or c.instrument_id == instrument_id)
                and c.interval == "5m"
                and c.readiness == "READY" and c.quality == "VALID" and c.confirmed_at(as_of)]
    if len(eligible) < lookback:
        return None
    bars = eligible[-lookback:]
    high = max(c.high for c in bars)
    low = min(c.low for c in bars)
    current = bars[-1].close
    width = high - low
    if width <= 0:
        return None
    # 1 means price is at the nearest edge of the recent range; 0 means near
    # its midpoint. This is a watchlist feature, not a breakout/setup label.
    edge_distance = min(abs(high - current), abs(current - low)) / width
    return max(Decimal(0), min(Decimal(1), Decimal(1) - edge_distance))


def _evaluate(
    symbol: str,
    data: SymbolData,
    as_of: datetime,
    max_test_order_notional_usdt: Decimal,
    freshness: FreshnessPolicy,
) -> EligibilityRecord:
    reasons: list[str] = []
    hard_reject = False
    unavailable_input = False
    degraded_input = False
    metadata = data.metadata
    instrument_id = metadata.instrument_id if metadata else None
    source_observations = [data.ticker, data.depth, data.open_interest,
                           *data.candles_5m, *data.candles_15m, *data.candles_1h,
                           *data.candles_4h, *data.spread_samples]
    if instrument_id is not None and any(
        observation is not None and observation.symbol == symbol
        and observation.instrument_id != instrument_id
        for observation in source_observations
    ):
        reasons.append("OBSERVATION_INSTRUMENT_ID_MISMATCH")
        degraded_input = True

    if metadata is None:
        reasons.append("METADATA_MISSING")
    else:
        if (metadata.symbol != symbol or metadata.instrument_id != binance_usdm_instrument_id(
            metadata.symbol, metadata.contract_type, metadata.settle_asset
        ) or metadata.quote_asset != "USDT" or metadata.settle_asset != "USDT"
                or metadata.contract_type != "PERPETUAL" or metadata.status != "TRADING"):
            reasons.append("INSTRUMENT_IDENTITY_OR_STATUS_INELIGIBLE")
            hard_reject = True
        elif ((metadata.onboard_time is not None and as_of < metadata.onboard_time)
              or (metadata.delivery_time is not None and as_of >= metadata.delivery_time)):
            reasons.append("CONTRACT_NOT_YET_ONBOARDED_OR_ALREADY_DELIVERED")
            hard_reject = True
        elif not metadata.valid_at(as_of):
            reasons.append("METADATA_NOT_VALID_OR_NOT_YET_AVAILABLE")
        elif not _fresh(metadata, as_of, freshness.metadata):
            reasons.append("METADATA_STALE")
        if (metadata.price_tick is None or metadata.quantity_step is None
                or metadata.minimum_quantity is None or metadata.minimum_notional is None
                or metadata.price_tick <= 0 or metadata.quantity_step <= 0
                or metadata.minimum_quantity <= 0 or metadata.minimum_notional < 0):
            reasons.append("INVALID_OR_INCOMPLETE_EXCHANGE_FILTERS")
            hard_reject = True
        filter_types = {f.filter_type for f in metadata.filters}
        if not {"PRICE_FILTER", "LOT_SIZE", "MIN_NOTIONAL"}.issubset(filter_types):
            reasons.append("REQUIRED_EXCHANGE_FILTERS_MISSING")
            hard_reject = True

    ticker = data.ticker
    turnover = None
    if ticker is None or ticker.symbol != symbol:
        reasons.append("TICKER_24H_MISSING")
    elif instrument_id is not None and ticker.instrument_id != instrument_id:
        reasons.append("TICKER_INSTRUMENT_ID_MISMATCH")
        degraded_input = True
    elif not _fresh(ticker, as_of, freshness.ticker):
        reasons.append("TICKER_24H_STALE")
    else:
        turnover = ticker.quote_volume
        if turnover < Decimal("20000000"):
            reasons.append("QUOTE_TURNOVER_BELOW_20M_USDT")
            hard_reject = True

    required = (("5m", data.candles_5m, 20), ("15m", data.candles_15m, 21),
                ("1h", data.candles_1h, 720), ("4h", data.candles_4h, 200))
    confirmed_by_interval = {}
    for interval, series, count in required:
        okay, issue, confirmed = _closed_contiguous(series, symbol=symbol,
                                                    instrument_id=instrument_id,
                                                    interval=interval, count=count,
                                                    as_of=as_of)
        confirmed_by_interval[interval] = confirmed
        if issue:
            reasons.append(issue)
    last5 = confirmed_by_interval["5m"]
    if last5:
        latest = last5[-1]
        expected_lag = as_of - latest.available_at
        if expected_lag < timedelta(0) or expected_lag > freshness.candle_close_lag:
            reasons.append("LATEST_5M_CANDLE_STALE_OR_LATE")

    samples = [s for s in _matching(data.spread_samples, symbol, instrument_id)
               if s.readiness == "READY" and s.quality == "VALID"
               and s.available_at <= as_of and s.event_time <= as_of]
    source_sample_times = [s.event_time for s in samples]
    spread_source_order_ok = all(right > left for left, right in
                                 zip(source_sample_times, source_sample_times[1:]))
    samples.sort(key=lambda s: s.event_time)
    spread_value = None
    if len(samples) < 60:
        reasons.append("SPREAD_WARMUP_LT_60_VALID_SAMPLES")
    else:
        tail = samples[-60:]
        unique = len({s.event_time for s in tail}) == 60
        regular = all(r.event_time - l.event_time == timedelta(minutes=1)
                      for l, r in zip(tail, tail[1:]))
        if not unique or not regular or not spread_source_order_ok:
            reasons.append("SPREAD_SAMPLE_GAP_DUPLICATE_OR_ORDER")
        if as_of - tail[-1].event_time > freshness.spread:
            reasons.append("SPREAD_SAMPLES_STALE")
        if unique and regular and spread_source_order_ok:
            spread_value = median([s.spread_fraction for s in tail])
            if spread_value > Decimal("0.001"):
                reasons.append("MEDIAN_SPREAD_ABOVE_0_10_PERCENT")
                hard_reject = True

    bid_depth = ask_depth = None
    if data.depth is None:
        reasons.append("DEPTH_MISSING")
    elif instrument_id is not None and data.depth.instrument_id != instrument_id:
        reasons.append("DEPTH_INSTRUMENT_ID_MISMATCH")
    elif not _fresh(data.depth, as_of, freshness.depth):
        reasons.append("DEPTH_STALE")
    else:
        bid_depth = _depth_within(data.depth, "SELL", Decimal("0.002"))
        ask_depth = _depth_within(data.depth, "BUY", Decimal("0.002"))
        minimum_depth = Decimal(5) * max_test_order_notional_usdt
        if min(bid_depth, ask_depth) < minimum_depth:
            reasons.append("SIDE_AWARE_DEPTH_BELOW_5X_WITHIN_0_20_PERCENT")
            hard_reject = True

    oi = data.open_interest
    oi_notional = None
    if oi is None:
        reasons.append("OPEN_INTEREST_MISSING")
    elif instrument_id is not None and oi.instrument_id != instrument_id:
        reasons.append("OPEN_INTEREST_INSTRUMENT_ID_MISMATCH")
    elif not _fresh(oi, as_of, freshness.open_interest):
        reasons.append("OPEN_INTEREST_STALE")
    elif not oi.unit_validated or oi.open_interest_notional_usdt is None:
        reasons.append("OPEN_INTEREST_UNIT_UNVALIDATED")
    else:
        oi_notional = oi.open_interest_notional_usdt
        if oi_notional < Decimal("5000000"):
            reasons.append("OPEN_INTEREST_BELOW_5M_USDT")
            hard_reject = True

    clearance = data.event_clearance
    event_ids: tuple[str, ...] = ()
    if clearance is None or clearance.as_of > as_of:
        reasons.append("EVENT_CLEARANCE_MISSING_OR_FUTURE")
    elif as_of - clearance.as_of > freshness.event_clearance:
        reasons.append("EVENT_CLEARANCE_STALE")
    elif clearance.verification_state != "VERIFIED":
        reasons.append("EVENT_CLEARANCE_UNKNOWN")
        event_ids = clearance.source_ids
    elif clearance.state == "UNKNOWN":
        reasons.append("EVENT_CLEARANCE_UNKNOWN")
        event_ids = clearance.source_ids
    elif clearance.state == "VETO":
        reasons.append("VERIFIED_EVENT_VETO")
        event_ids = clearance.source_ids
        hard_reject = True
    else:
        event_ids = clearance.source_ids

    observations = [data.metadata, data.ticker, data.depth, data.open_interest,
                    *data.candles_5m, *data.candles_15m, *data.candles_1h,
                    *data.candles_4h, *data.spread_samples]
    for observation in observations:
        if observation is None:
            continue
        if observation.readiness == "UNAVAILABLE":
            unavailable_input = True
        if observation.readiness in ("DEGRADED", "WARMING", "COLD") or observation.quality != "VALID":
            degraded_input = True

    reasons = list(dict.fromkeys(reasons))
    if hard_reject:
        state = "INELIGIBLE"
    elif unavailable_input:
        state = "UNAVAILABLE"
    elif not any(observations) and clearance is None:
        state = "COLD"
    elif reasons:
        # A present but malformed/discontinuous set is degraded; absent or
        # short history remains warming so scanner reports the missing coverage.
        degraded_tokens = ("GAP_", "DUPLICATE", "ORDER", "SAMPLE_GAP")
        state = "DEGRADED" if degraded_input or any(
            token in reason for reason in reasons for token in degraded_tokens
        ) else "WARMING"
    else:
        state = "READY"
    return EligibilityRecord(
        symbol=symbol,
        instrument_id=instrument_id,
        state=state,
        eligible=state == "READY",
        reasons=tuple(reasons),
        turnover_usdt=turnover,
        median_spread_fraction=spread_value,
        bid_depth_usdt=bid_depth,
        ask_depth_usdt=ask_depth,
        oi_notional_usdt=oi_notional,
        event_source_ids=event_ids,
    )


def scan_universe(
    symbols: dict[str, SymbolData],
    as_of: datetime,
    max_test_order_notional_usdt: Decimal,
    *,
    freshness: FreshnessPolicy | None = None,
    limit: int = 15,
) -> UniverseResult:
    """Evaluate every supplied symbol and select a deterministic watchlist.

    Ranking uses range-edge proximity, median spread and quote turnover as
    inexpensive data-quality/context proxies. No strategy expectancy, future
    profitability or executable trade candidate is produced.
    """
    if as_of.utcoffset() != timedelta(0):
        raise ValueError("explicit UTC as_of required")
    if max_test_order_notional_usdt <= 0 or limit < 1:
        raise ValueError("positive test order notional and shortlist limit required")
    policy = freshness or FreshnessPolicy()
    effective_limit = min(limit, 15)
    evaluated = []
    for symbol in sorted(symbols):
        record = _evaluate(symbol, symbols[symbol], as_of, max_test_order_notional_usdt, policy)
        proximity = _structure_proximity(list(symbols[symbol].candles_5m), symbol,
                                         record.instrument_id, as_of)
        if record.eligible and proximity is None:
            record = record.model_copy(update={
                "reasons": tuple((*record.reasons, "STRUCTURE_PROXIMITY_CONTEXT_UNAVAILABLE")),
                "eligible": False,
                "state": "WARMING",
                "shortlist_status": "NO_CONTEXT",
                "shortlist_reasons": ("NO_20_BAR_5M_RANGE_CONTEXT",),
            })
        else:
            record = record.model_copy(update={"structure_proximity": proximity})
        evaluated.append(record)

    eligible = [r for r in evaluated if r.eligible]
    # Higher edge proximity and turnover, lower spread, then stable symbol.
    ordered = sorted(
        eligible,
        key=lambda r: (-r.structure_proximity, r.median_spread_fraction,
                       -r.turnover_usdt, r.symbol),
    )
    selected_symbols = {r.symbol for r in ordered[:effective_limit]}
    audit = []
    for record in evaluated:
        if record.symbol in selected_symbols:
            audit.append(record.model_copy(update={
                "shortlist_status": "SELECTED",
                "shortlist_reasons": ("ELIGIBLE", "RANGE_EDGE_PROXIMITY", "LOWER_COST_THEN_TURNOVER_TIEBREAK"),
            }))
        elif record.eligible:
            audit.append(record.model_copy(update={
                "shortlist_status": "RANKED_OUT_LIMIT",
                "shortlist_reasons": ("SHORTLIST_LIMIT",),
            }))
        elif record.shortlist_status != "NO_CONTEXT":
            audit.append(record.model_copy(update={
                "shortlist_status": "NOT_ELIGIBLE",
                "shortlist_reasons": record.reasons,
            }))
        else:
            audit.append(record)
    return UniverseResult(
        as_of=as_of,
        considered=tuple(audit),
        shortlist=tuple(r.symbol for r in ordered[:effective_limit]),
        selection_limit=effective_limit,
    )
