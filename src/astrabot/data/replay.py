"""Deterministic raw normalization, coverage checks, and feed manifests."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Sequence

from .binance import BinancePublic, _dt, _raw_agg_trade
from .models import Candle, DataGap, FeedManifest, Trade


def canonical_json(records) -> str:
    return json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def checksum(records) -> str:
    return hashlib.sha256(canonical_json(records).encode("utf-8")).hexdigest()


def normalize_klines(
    records,
    *,
    symbol: str,
    interval: str,
    as_of: datetime,
    ingested_at: datetime | None = None,
) -> tuple[Candle, ...]:
    """Normalize raw Binance kline arrays with close-boundary availability.

    Archive rows lack the original pipeline ingestion timestamp. Replays default
    it to the supplied cutoff for deterministic output; captured values can be
    supplied explicitly. The close-boundary availability is an exchange-time
    proxy and must be stated in the data manifest.
    """
    replay_ingestion = ingested_at or as_of
    api = BinancePublic(
        transport=lambda _url, _timeout: records,
        clock=lambda: replay_ingestion,
        max_pages=1,
        max_retries=0,
        sleep=lambda _delay: None,
    )
    return api.klines(
        symbol,
        interval,
        as_of=as_of,
        ingested_at=replay_ingestion,
        availability_mode="EXCHANGE_CLOSE_PROXY",
    )


def normalize_agg_trades(
    records: Sequence[dict],
    *,
    symbol: str,
    as_of: datetime,
    ingested_at: datetime | None = None,
) -> tuple[Trade, ...]:
    """Normalize raw aggTrade rows for offline replay without a network call."""
    replay_ingestion = ingested_at or as_of
    return tuple(
        _raw_agg_trade(
            record,
            symbol=symbol,
            as_of=as_of,
            ingested_at=replay_ingestion,
            available_at=_dt(record["T"]),
        )
        for record in records
    )


def candle_quality(candles: Sequence[Candle]) -> tuple[DataGap, ...]:
    """Detect duplicate, out-of-order, and missing candle intervals."""
    gaps = []
    seen = set()
    previous = None
    for candle in candles:
        if candle.open_time in seen:
            gaps.append(DataGap(
                symbol=candle.symbol,
                instrument_id=candle.instrument_id,
                feed=f"klines:{candle.interval}",
                start_time=candle.open_time,
                end_time=candle.close_time,
                reason="DUPLICATE",
            ))
            continue
        seen.add(candle.open_time)
        if previous is not None:
            if candle.open_time < previous.open_time:
                start, end = sorted((candle.open_time, previous.open_time))
                gaps.append(DataGap(
                    symbol=candle.symbol,
                    instrument_id=candle.instrument_id,
                    feed=f"klines:{candle.interval}",
                    start_time=start,
                    end_time=end,
                    reason="OUT_OF_ORDER",
                ))
            elif candle.open_time > previous.open_time:
                expected = previous.close_time + timedelta(milliseconds=1)
                if candle.open_time > expected:
                    gaps.append(DataGap(
                        symbol=candle.symbol,
                        instrument_id=candle.instrument_id,
                        feed=f"klines:{candle.interval}",
                        start_time=expected,
                        end_time=candle.open_time - timedelta(milliseconds=1),
                        reason="MISSING_INTERVAL",
                    ))
        previous = candle
    return tuple(gaps)


def trade_quality(trades: Sequence[Trade]) -> tuple[DataGap, ...]:
    """Detect aggTrade identity gaps, duplicates, and source-order violations."""
    gaps = []
    seen = set()
    previous = None
    for trade in trades:
        identity = trade.aggregate_trade_id or trade.trade_id
        if identity in seen:
            gaps.append(DataGap(
                symbol=trade.symbol,
                instrument_id=trade.instrument_id,
                feed="aggTrades",
                start_time=trade.event_time,
                end_time=trade.event_time,
                reason="DUPLICATE",
            ))
            continue
        seen.add(identity)
        if previous is not None:
            current_id = int(identity)
            previous_id = int(previous.aggregate_trade_id or previous.trade_id)
            if current_id <= previous_id or trade.event_time < previous.event_time:
                gaps.append(DataGap(
                    symbol=trade.symbol,
                    instrument_id=trade.instrument_id,
                    feed="aggTrades",
                    start_time=min(previous.event_time, trade.event_time),
                    end_time=max(previous.event_time, trade.event_time),
                    reason="OUT_OF_ORDER",
                ))
            elif current_id != previous_id + 1:
                gaps.append(DataGap(
                    symbol=trade.symbol,
                    instrument_id=trade.instrument_id,
                    feed="aggTrades",
                    start_time=previous.event_time,
                    end_time=trade.event_time,
                    reason="MISSING_INTERVAL",
                ))
        previous = trade
    return tuple(gaps)


def manifest(
    *,
    feed: str,
    symbol: str,
    instrument_id: str,
    source: str,
    source_url: str,
    source_version: str,
    records,
    start_time: datetime,
    end_time: datetime,
    synthetic: bool,
    timestamp_interpretation: str = "Binance epoch milliseconds UTC",
    availability_assumption: str = "available_at set by source-specific normalization",
    original_units: str = "Binance USD-M raw wire units",
    fidelity: str | None = None,
    missing_periods: tuple[DataGap, ...] = (),
    corrections: tuple[str, ...] = (),
    archive_id: str | None = None,
    normalization_version: str = "c02-replay-v1",
) -> FeedManifest:
    """Build a checksummed feed manifest from the exact retained raw records."""
    if fidelity is None:
        fidelity = "SYNTHETIC_FIXTURE" if synthetic else "VENUE_REPORTED"
    return FeedManifest(
        feed=feed,
        symbol=symbol,
        instrument_id=instrument_id,
        source=source,
        source_url=source_url,
        archive_id=archive_id,
        source_version=source_version,
        start_time=start_time,
        end_time=end_time,
        record_count=len(records),
        checksum_sha256=checksum(records),
        missing_periods=missing_periods,
        corrections=corrections,
        timestamp_interpretation=timestamp_interpretation,
        availability_assumption=availability_assumption,
        original_units=original_units,
        fidelity=fidelity,
        normalization_version=normalization_version,
        synthetic=synthetic,
    )
