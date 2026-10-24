"""Small causal smoke providers for feature families A01-A03."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from astrabot.data.models import Candle, FeatureObservation, Trade, config_hash, stable_id

VERSION = "c02.features.v1"
SOURCE = "astrabot.c02.smoke"


def _base(
    family: str,
    name: str,
    symbol: str,
    instrument_id: str,
    event_time: datetime,
    available_at: datetime,
    ingested_at: datetime,
    as_of: datetime,
    units: str,
    fidelity: str,
    readiness: str,
    ids: list[str],
    config: dict,
    *,
    data_source: str = SOURCE,
    source_version: str = "local-normalization-v1",
    value=None,
    payload=None,
    reason=None,
) -> FeatureObservation:
    hashed_config = config_hash(config)
    observation_id = stable_id(
        family, name, VERSION, hashed_config, *ids, as_of.isoformat()
    )
    return FeatureObservation(
        feature_family=family,
        feature_name=name,
        symbol=symbol,
        instrument_id=instrument_id,
        event_time=event_time,
        available_at=available_at,
        ingested_at=ingested_at,
        as_of=as_of,
        data_source=data_source,
        source_version=source_version,
        feature_version=VERSION,
        units=units,
        fidelity=fidelity,
        readiness=readiness,
        observation_id=observation_id,
        config_hash=hashed_config,
        value=value,
        payload=payload or {},
        reason=reason,
    )


def _input_source(observations, fallback: str = SOURCE) -> tuple[str, str]:
    sources = sorted({item.data_source for item in observations})
    versions = sorted({item.source_version for item in observations})
    return ",".join(sources) or fallback, ",".join(versions) or "local-normalization-v1"


def cvd(
    trades: Sequence[Trade],
    *,
    as_of: datetime,
    coverage_complete: bool,
    symbol: str,
    instrument_id: str,
    stream_id: str = "binance-agg-trades",
) -> FeatureObservation:
    """Return signed base volume for an explicitly bounded aggTrade window.

    This adapter does not invent a session reset. The caller identifies the
    covered window, and aggregate-trade IDs must be continuous within it.
    """
    candidates = [
        trade for trade in trades
        if trade.event_time < as_of and trade.available_at <= as_of
    ]
    identity_mismatch = any(
        trade.symbol != symbol or trade.instrument_id != instrument_id
        for trade in candidates
    )
    in_scope = [
        trade for trade in candidates
        if trade.symbol == symbol and trade.instrument_id == instrument_id
    ]
    unavailable_input = any(trade.readiness == "UNAVAILABLE" for trade in in_scope)
    invalid_input = any(trade.readiness != "READY" or trade.quality != "VALID" for trade in in_scope)
    ids = [trade.trade_id for trade in in_scope]
    aggregate_ids = [trade.aggregate_trade_id for trade in in_scope]
    ordered = sorted(in_scope, key=lambda trade: (trade.event_time, trade.trade_id))
    event_time = max((trade.event_time for trade in ordered), default=as_of)
    available_at = max((trade.available_at for trade in ordered), default=as_of)
    ingested_at = max((trade.ingested_at for trade in ordered), default=as_of)
    data_source, source_version = _input_source(in_scope)

    readiness = "READY"
    reason = None
    if unavailable_input:
        readiness, reason = "UNAVAILABLE", "one or more required trade observations are explicitly unavailable"
    elif identity_mismatch:
        readiness, reason = "DEGRADED", "input window contains another symbol or instrument identity"
    elif invalid_input:
        readiness, reason = "DEGRADED", "trade input contains a non-ready or invalid-quality observation"
    elif not coverage_complete:
        readiness, reason = "WARMING", "trade coverage is not certified complete for the requested window"
    elif not ordered:
        readiness, reason = "WARMING", "no eligible trade records cover the requested window"
    elif len(ids) != len(set(ids)) or len([x for x in aggregate_ids if x is not None]) != len(set(x for x in aggregate_ids if x is not None)):
        readiness, reason = "DEGRADED", "duplicate trade or aggregate-trade identity in source window"
    else:
        try:
            source_ids = [int(trade.aggregate_trade_id or trade.trade_id) for trade in in_scope]
            time_ordered_ids = [int(trade.aggregate_trade_id or trade.trade_id) for trade in ordered]
            if any(right <= left for left, right in zip(source_ids, source_ids[1:])):
                readiness, reason = "DEGRADED", "trade IDs are out of order in source order"
            elif any(right != left + 1 for left, right in zip(time_ordered_ids, time_ordered_ids[1:])):
                readiness, reason = "DEGRADED", "aggregate-trade IDs have a gap; CVD continuity is unknown"
        except ValueError:
            readiness, reason = "DEGRADED", "trade IDs are not numeric Binance identities"

    value = None
    if readiness == "READY":
        value = sum(
            (trade.base_quantity if trade.aggressor_side == "BUY" else -trade.base_quantity
             for trade in ordered),
            Decimal(0),
        )
    return _base(
        "A01", "cvd_window", symbol, instrument_id, event_time, available_at,
        ingested_at, as_of, "base_asset", "TRADE_AGG", readiness,
        [stream_id, *ids],
        {"stream": stream_id, "coverage_complete": coverage_complete,
         "reset_policy": "EXPLICIT_WINDOW_ONLY"},
        data_source=data_source,
        source_version=source_version,
        value=value,
        payload={
            "window_id": stable_id(stream_id, ids[0] if ids else None, ids[-1] if ids else None),
            "reset_policy": "EXPLICIT_WINDOW_ONLY",
            "trade_ids": ids,
            "aggregate_trade_ids": aggregate_ids,
            "first_trade_id": ids[0] if ids else None,
            "last_trade_id": ids[-1] if ids else None,
            "stream_id": stream_id,
        },
        reason=reason,
    )


def session_vwap(
    candles: Sequence[Candle],
    *,
    as_of: datetime,
    symbol: str,
    instrument_id: str,
) -> FeatureObservation:
    """UTC-midnight candle VWAP from closed 5m typical-price × base volume."""
    utc_as_of = as_of.astimezone(timezone.utc)
    day = utc_as_of.date()
    session_start = datetime.combine(day, time.min, timezone.utc)
    eligible = sorted(
        (
            candle for candle in candles
            if candle.symbol == symbol
            and candle.instrument_id == instrument_id
            and candle.interval == "5m"
            and candle.readiness == "READY"
            and candle.quality == "VALID"
            and candle.is_closed
            and candle.open_time.astimezone(timezone.utc).date() == day
            and candle.confirmed_at(as_of)
        ),
        key=lambda candle: candle.open_time,
    )
    event_time = max((candle.close_time for candle in eligible), default=as_of)
    available_at = max((candle.available_at for candle in eligible), default=as_of)
    ingested_at = max((candle.ingested_at for candle in eligible), default=as_of)
    source, source_version = _input_source(eligible, fallback="binance_usdm_public_klines")
    candle_ids = [candle.source_record_id for candle in eligible]

    elapsed_seconds = max(0.0, (utc_as_of - session_start).total_seconds())
    expected = int(elapsed_seconds // 300)
    expected_opens = [session_start + timedelta(minutes=5 * index) for index in range(expected)]
    actual_opens = [candle.open_time.astimezone(timezone.utc) for candle in eligible]
    coverage_complete = actual_opens == expected_opens
    numerator = sum(
        (candle.typical_price * candle.base_volume for candle in eligible),
        Decimal(0),
    )
    denominator = sum((candle.base_volume for candle in eligible), Decimal(0))

    invalid_session_input = any(
        candle.symbol == symbol and candle.instrument_id == instrument_id
        and candle.interval == "5m"
        and candle.open_time.astimezone(timezone.utc).date() == day
        and candle.open_time < as_of
        and (candle.readiness != "READY" or candle.quality != "VALID")
        for candle in candles
    )
    if expected == 0:
        readiness, value = "WARMING", None
        reason = "no closed 5m bars are expected yet in the UTC session"
    elif invalid_session_input:
        readiness, value = "DEGRADED", None
        reason = "session includes an invalid-quality or non-ready source candle"
    elif not coverage_complete:
        readiness, value = ("WARMING" if not eligible else "DEGRADED"), None
        reason = "missing, duplicate, or out-of-order expected closed 5m session bars"
    elif denominator == 0:
        readiness, value = "UNAVAILABLE", None
        reason = "confirmed UTC session candles have zero cumulative base volume"
    else:
        readiness, value, reason = "READY", numerator / denominator, None

    session_id = f"UTC:{day.isoformat()}"
    return _base(
        "A02", "utc_session_vwap", symbol, instrument_id, event_time,
        available_at, ingested_at, as_of, "quote_per_base", "BAR_DERIVED_APPROX",
        readiness, [session_id, *candle_ids],
        {"anchor": "UTC_MIDNIGHT", "interval": "5m",
         "price": "typical_price", "volume": "base_volume"},
        data_source=source,
        source_version=source_version,
        value=value,
        payload={
            "anchor_id": session_id,
            "session_id": session_id,
            "candle_ids": candle_ids,
            "expected_closed_bars": expected,
            "observed_closed_bars": len(eligible),
            "coverage_complete": coverage_complete,
            "reset_policy": "UTC_MIDNIGHT",
        },
        reason=reason,
    )


def smc_structure(
    candles: Sequence[Candle],
    *,
    as_of: datetime,
    symbol: str,
    instrument_id: str,
) -> FeatureObservation:
    """Fail-closed qualification gate for retrospective upstream SMC outputs."""
    eligible = sorted(
        (
            candle for candle in candles
            if candle.symbol == symbol
            and candle.instrument_id == instrument_id
            and candle.readiness == "READY"
            and candle.quality == "VALID"
            and candle.is_closed
            and candle.confirmed_at(as_of)
        ),
        key=lambda candle: candle.close_time,
    )
    event_time = max((candle.close_time for candle in eligible), default=as_of)
    available_at = max((candle.available_at for candle in eligible), default=as_of)
    ingested_at = max((candle.ingested_at for candle in eligible), default=as_of)
    source_version = (
        "smart-money-concepts@1b62fd6c41e1f508e7ed76831a039fa4c82d42f6;"
        "pyvsmc@55008a6dce09e0e36691d2e34150f0f499ac4f4b"
    )
    reason = (
        "UNQUALIFIED: smart-money-concepts@1b62fd6c41e1f508e7ed76831a039fa4c82d42f6 "
        "uses fvg shift(-1), centered/full-series swing and BOS labels; "
        "pyvsmc@55008a6dce09e0e36691d2e34150f0f499ac4f4b uses centered rolling swings "
        "and future mitigation scans. Expanding-prefix outputs can change and true "
        "right-side confirmation availability is not established."
    )
    return _base(
        "A03", "smc_structure", symbol, instrument_id, event_time,
        available_at, ingested_at, as_of, "event", "BAR_DERIVED_APPROX",
        "UNAVAILABLE", [candle.source_record_id for candle in eligible],
        {"qualification": "expanding-prefix-v1", "status": "UNAVAILABLE"},
        data_source="unqualified_upstream_comparison",
        source_version=source_version,
        value=None,
        payload={
            "qualification_path": ["swing", "BOS/CHOCH", "liquidity", "order_block", "FVG"],
            "prefix_causality": "not qualified",
            "candidate_sources": source_version,
        },
        reason=reason,
    )
