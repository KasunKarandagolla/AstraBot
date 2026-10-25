"""Causal historical panel loading and a thin adapter around C02/C03.

This module performs no network access. It consumes a checksummed manifest and
retained files, advances only at source availability times, and persists a C03
ResearchState per symbol across snapshots.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import time
import tracemalloc
import zipfile
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path
from typing import Any, Sequence

from astrabot.data.models import Candle, binance_usdm_instrument_id, config_hash, stable_id
from astrabot.data.replay import candle_quality, normalize_agg_trades, normalize_klines, trade_quality
from astrabot.research.engine import evaluate
from astrabot.research.models import CostProfile, ResearchAccount, ResearchDecision, ResearchState
from astrabot.research.simulation import (
    ExecutionScenario, PortfolioLedger, ScenarioOutcome, simulate_decision,
)
from astrabot.research.statistics import cluster_bootstrap, summarize
from astrabot.universe.eligibility import SymbolData, scan_universe


@dataclass(frozen=True)
class HistoricalPanel:
    symbols: dict[str, SymbolData]
    partitions: tuple[dict[str, Any], ...]
    source_manifest: dict[str, Any]
    observation_history: dict[str, dict[str, tuple[Any, ...]]] = field(default_factory=dict)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_klines(rows: list[dict[str, str]], symbol: str, interval: str, as_of: datetime):
    raw = [[int(r["open_time"]), r["open"], r["high"], r["low"], r["close"], r["volume"],
            int(r["close_time"]), r["quote_volume"], int(r["count"]), r["taker_buy_volume"],
            r["taker_buy_quote_volume"], r["ignore"]] for r in rows]
    return normalize_klines(raw, symbol=symbol, interval=interval, as_of=as_of)


def _parse_agg_trades(rows: list[dict[str, str]], symbol: str, as_of: datetime):
    raw = [{"a": int(r["agg_trade_id"]), "p": r["price"], "q": r["quantity"],
            "f": int(r["first_trade_id"]), "l": int(r["last_trade_id"]),
            "T": int(r["transact_time"]), "m": r["is_buyer_maker"].lower() == "true"}
           for r in rows]
    return normalize_agg_trades(raw, symbol=symbol, as_of=as_of)


def load_c02_panel(panel_dir: str | Path) -> HistoricalPanel:
    """Load the retained C02 Binance sample and verify every retained checksum."""
    root = Path(panel_dir).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    symbols: dict[str, SymbolData] = {}
    partitions: list[dict[str, Any]] = []
    candles: dict[str, dict[str, list]] = {}
    for record in manifest["records"]:
        relative = Path(record["file"])
        retained = (root / relative).resolve()
        if root not in retained.parents:
            raise ValueError("panel record path escapes manifest directory")
        digest = _sha256(retained)
        if digest != record["retained_file_sha256"]:
            raise ValueError(f"retained file checksum mismatch: {relative}")
        with retained.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        feed = record["feed"]
        symbol = record["symbol"]
        if feed.startswith("klines:"):
            latest_close = max(int(r["close_time"]) for r in rows)
            cutoff = datetime.fromtimestamp((latest_close + 1) / 1000, timezone.utc)
            interval = feed.split(":", 1)[1]
            normalized = _parse_klines(rows, symbol, interval, cutoff)
            candles.setdefault(symbol, {}).setdefault(interval, []).extend(normalized)
            event_times = [c.close_time for c in normalized]
            available_times = [c.available_at for c in normalized]
            unit = record.get("original_units", "OHLC in quote per base; base volume in base; quote volume in quote")
            fidelity = "VENUE_REPORTED"
            quality = []
            source_timestamp = "kline close_time; inclusive close in epoch milliseconds"
            available_assumption = "close_time + 1 millisecond proxy; archive transport latency unavailable"
            policy_input = True
        elif feed.startswith("aggTrades:"):
            latest = max(int(r["transact_time"]) for r in rows)
            cutoff = datetime.fromtimestamp(latest / 1000, timezone.utc)
            normalized = _parse_agg_trades(rows, symbol, cutoff)
            quality = [g.model_dump(mode="json") for g in trade_quality(normalized)]
            event_times = [t.event_time for t in normalized]
            available_times = [t.available_at for t in normalized]
            interval = "trade-event"
            unit = record.get("original_units", "Price/quantity and buyer-maker flag")
            fidelity = "TRADE_AGG"
            source_timestamp = "aggregate transact_time in epoch milliseconds"
            available_assumption = "exchange transaction time proxy; archive publication and ingestion unavailable"
            policy_input = False
        else:
            raise ValueError(f"unsupported C02 panel feed: {feed}")
        partitions.append({
            "feed": feed, "symbol": symbol, "instrument_id": record["instrument_id"],
            "contract_type": "PERPETUAL", "settlement_asset": "USDT",
            "source": "Binance public historical archive mirrored in pinned Freqtrade test fixture",
            "source_url": record["source_url"], "archive_id": record.get("archive_id"),
            "mirror_url": record.get("mirror_url"), "source_version": record.get("mirror_commit"),
            "retrieved_at": None, "retrieval_date": "2026-10-24 journal observation; exact per-file retrieval time unavailable",
            "raw_archive_sha256": record.get("archive_sha256"),
            "retained_input_sha256": digest, "retained_bytes": retained.stat().st_size,
            "coverage_start": record["coverage_start"], "coverage_end": record["coverage_end"],
            "first_event_time": min(event_times).isoformat(), "last_event_time": max(event_times).isoformat(),
            "actual_row_count": len(rows), "normalized_row_count": len(normalized),
            "source_event_time": source_timestamp,
            "known_available_at": available_assumption,
            "ingested_at_observed": False,
            "replay_ingested_at": max(available_times).isoformat(),
            "interval": interval, "original_units": unit,
            "known_missing_intervals": record.get("known_gaps", []), "corrections": record.get("corrections", []),
            "historical_listing_metadata": "UNAVAILABLE; no point-in-time exchangeInfo snapshots retained",
            "fidelity": fidelity,
            "could_be_known_at_replay_time": "UNVERIFIED",
            "availability_status": "OBSERVED_WITH_EXPLICIT_AVAILABILITY_PROXY",
            "used_for_policy": policy_input,
            "quality_findings": quality,
        })
    for symbol, intervals in candles.items():
        fields = {f"candles_{interval}": tuple(sorted(rows,
            key=lambda c: (c.open_time, c.source_record_id))) for interval, rows in intervals.items()}
        symbols[symbol] = SymbolData.model_validate(fields)
    for record in manifest["records"]:
        symbols.setdefault(record["symbol"], SymbolData())
    return HistoricalPanel(symbols=symbols, partitions=tuple(partitions), source_manifest=manifest)


def load_public_um_archive_panel(manifest_path: str | Path, data_root: str | Path) -> HistoricalPanel:
    """Load a fully verified external archive manifest through the C02 normalizer."""
    from astrabot.data.public_archive import planned_archives, validate_archive_bytes

    manifest_file = Path(manifest_path).resolve()
    root = Path(data_root).resolve()
    if len(manifest_file.parents) < 3:
        raise ValueError("pilot manifest path does not identify a repository root")
    repo_root = manifest_file.parents[2]
    if root == repo_root or repo_root in root.parents:
        raise ValueError("raw archive data root must remain outside the Git repository")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != "astrabot.binance-um-archives.v1"
            or manifest.get("phase") != "pilot"
            or manifest.get("archive_host") != "data.binance.vision"):
        raise ValueError("expected the verified public Binance USDⓈ-M pilot manifest")
    plan = planned_archives("pilot")
    expected_symbols = list(dict.fromkeys(spec.symbol for spec in plan))
    expected_window = {
        "source_only_warmup": {"start": "2024-07-01T00:00:00Z", "end_exclusive": "2024-09-01T00:00:00Z"},
        "development": {"start": "2024-09-01T00:00:00Z", "end_exclusive": "2024-10-01T00:00:00Z"},
        "validation": {"start": "2024-10-01T00:00:00Z", "end_exclusive": "2024-10-15T00:00:00Z"},
        "untouched_evaluation": {"start": "2024-10-15T00:00:00Z", "end_exclusive": "2024-11-01T00:00:00Z"},
        "outcome_purge_embargo_hours": 12,
    }
    if (manifest.get("symbols") != expected_symbols
            or manifest.get("cadence") != "monthly"
            or manifest.get("intervals") != ["5m", "15m", "1h", "4h"]
            or manifest.get("window") != expected_window):
        raise ValueError("pilot manifest cohort, intervals, cadence, or frozen study windows mismatch")
    by_id = {spec.filename: spec for spec in plan}
    records = manifest.get("archives", [])
    if (manifest.get("archive_count_planned") != len(plan)
            or manifest.get("archive_count_completed") != len(plan)
            or len(records) != len(plan)
            or manifest.get("total_actual_bytes") != sum(
                int(record.get("actual_bytes", -1)) for record in records)
            or {record.get("archive_id") for record in records} != set(by_id)):
        raise ValueError("pilot manifest is incomplete or exceeds the declared fixed plan")
    manifest_digest = _sha256(manifest_file)
    symbols: dict[str, dict[str, list[Candle]]] = {}
    partitions: list[dict[str, Any]] = []
    step_ms = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
    for record in records:
        spec = by_id[record["archive_id"]]
        if (record.get("symbol") != spec.symbol
                or record.get("interval") != spec.interval
                or record.get("cadence") != spec.cadence
                or record.get("period_utc") != spec.period
                or record.get("source_url") != spec.url
                or record.get("data_root_relative_path") != spec.relative_path
                or record.get("http_status") != 200):
            raise ValueError(f"source plan/status mismatch for {spec.filename}")
        relative = Path(record["data_root_relative_path"])
        archive_path = (root / relative).resolve()
        if root not in archive_path.parents:
            raise ValueError(f"archive path escapes external data root: {spec.filename}")
        if not archive_path.is_file() or archive_path.stat().st_size != record.get("actual_bytes"):
            raise ValueError(f"archive missing or size mismatch: {spec.filename}")
        if _sha256(archive_path) != record.get("sha256"):
            raise ValueError(f"archive SHA256 mismatch: {spec.filename}")
        blob = archive_path.read_bytes()
        validation = validate_archive_bytes(blob, spec)
        if (validation["quality"]["status"] != "PASS"
                or validation["csv_schema"] != record.get("csv_schema")
                or validation["csv_member_bytes"] != record.get("csv_member_bytes")
                or validation["csv_member_sha256"] != record.get("csv_member_sha256")
                or validation["members"] != record.get("members")
                or validation["coverage_start"] != record.get("coverage_start")
                or validation["coverage_end"] != record.get("coverage_end")
                or validation["quality"] != record.get("quality")):
            raise ValueError(f"archive/manifest content validation mismatch: {spec.filename}")
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            csv_bytes = archive.read(spec.member)
        text = csv_bytes.decode("utf-8-sig", errors="strict")
        rows = list(csv.DictReader(io.StringIO(text, newline="")))
        interval = spec.interval
        latest_close = max(int(row["close_time"]) for row in rows)
        cutoff = datetime.fromtimestamp((latest_close + 1) / 1000, timezone.utc)
        normalized = _parse_klines(rows, spec.symbol, interval, cutoff)
        if len(normalized) != record["quality"]["actual_rows"]:
            raise ValueError(f"C02 normalizer row count mismatch: {spec.filename}")
        symbols.setdefault(spec.symbol, {}).setdefault(interval, []).extend(normalized)
        bars = sorted(normalized, key=lambda candle: candle.open_time)
        instrument_id = binance_usdm_instrument_id(spec.symbol)
        partitions.append({
            "feed": f"klines:{interval}", "symbol": spec.symbol, "instrument_id": instrument_id,
            "contract_type": "PERPETUAL", "settlement_asset": "USDT",
            "source": "Binance public historical archive (data.binance.vision)",
            "source_url": spec.url, "archive_id": spec.filename,
            "retrieved_at": record["retrieved_at_utc"], "raw_archive_sha256": record["sha256"],
            "retained_input_sha256": validation["csv_member_sha256"],
            "archive_bytes": record["actual_bytes"], "retained_bytes": validation["csv_member_bytes"],
            "coverage_start": validation["coverage_start"], "coverage_end": validation["coverage_end"],
            "first_event_time": min(c.close_time for c in bars).isoformat(),
            "last_event_time": max(c.close_time for c in bars).isoformat(),
            "actual_row_count": len(rows), "normalized_row_count": len(normalized),
            "source_event_time": "Binance kline inclusive close_time in epoch milliseconds UTC",
            "known_available_at": "close_time + 1 millisecond proxy; archive publication/ingestion latency unavailable",
            "ingested_at_observed": False,
            "replay_ingested_at": max(c.available_at for c in bars).isoformat(),
            "interval": interval,
            "original_units": "OHLC in USDT per base asset; base volume in base; quote volume in USDT",
            "known_missing_intervals": [], "duplicates": 0, "corrections": [],
            "historical_listing_metadata": "UNAVAILABLE; the declared cohort is not a historical dynamic universe",
            "fidelity": "VENUE_REPORTED",
            "could_be_known_at_replay_time": "UNVERIFIED; archive close-time proxy only",
            "availability_status": "OBSERVED_WITH_EXPLICIT_AVAILABILITY_PROXY",
            "used_for_policy": True, "quality_findings": record["quality"],
            "http_status": record["http_status"], "row_step_ms": step_ms[interval],
        })
    symbol_data: dict[str, SymbolData] = {}
    cross_archive_quality: dict[str, dict[str, int]] = {}
    for symbol, intervals in symbols.items():
        for interval, rows in intervals.items():
            findings = candle_quality(sorted(rows, key=lambda candle: candle.open_time))
            counts = {reason: sum(gap.reason == reason for gap in findings)
                      for reason in ("DUPLICATE", "OUT_OF_ORDER", "MISSING_INTERVAL")}
            cross_archive_quality[f"{symbol}:{interval}"] = counts
            if any(counts.values()):
                raise ValueError(f"cross-archive {interval} continuity failure for {symbol}: {counts}")
        fields = {f"candles_{interval}": tuple(sorted(rows,
            key=lambda candle: (candle.open_time, candle.source_record_id)))
            for interval, rows in intervals.items()}
        symbol_data[symbol] = SymbolData.model_validate(fields)
    for symbol in manifest["symbols"]:
        symbol_data.setdefault(symbol, SymbolData())
    source_manifest = {
        "evidence_class": manifest["evidence_class"],
        "manifest_path": "research/c04/historical_manifest.json",
        "archive_manifest_sha256": manifest_digest,
        "archive_count": len(records), "total_archive_bytes": manifest["total_actual_bytes"],
        "symbols": list(manifest["symbols"]), "cohort_limit": manifest["cohort_limit"],
        "study_windows": manifest["window"],
        "cross_archive_continuity": cross_archive_quality,
        "historical_contract_metadata": "UNAVAILABLE; no point-in-time exchangeInfo snapshot",
        "validated_open_interest": "UNAVAILABLE; no OI archive included",
        "verified_event_clearance": "UNAVAILABLE; no historical event/news source included",
        "quotes_or_depth": "UNAVAILABLE; not derivable from OHLCV",
        "funding_settlements": "UNAVAILABLE; no funding archive included",
        "observed_ioc_fills": "UNAVAILABLE; bars do not establish orders or fills",
    }
    return HistoricalPanel(symbols=symbol_data, partitions=tuple(sorted(partitions,
        key=lambda row: (row["symbol"], row["interval"], row["coverage_start"]))),
        source_manifest=source_manifest)


def derive_4h_from_1h(candles: tuple[Candle, ...]) -> tuple[Candle, ...]:
    """Aggregate only complete, contiguous UTC 1H groups into 4H OHLCV bars.

    Semantics: first open, maximum high, minimum low, last close; sum base/quote
    volume and trade counts. `available_at` is the latest component availability
    and the 4H bar is marked `BAR_DERIVED_APPROX` with source IDs in its stable
    record ID. Incomplete/gapped groups are dropped rather than interpolated.
    """
    from collections import defaultdict
    from datetime import timedelta

    groups: dict[tuple[str, str, datetime], list[Candle]] = defaultdict(list)
    for bar in candles:
        if bar.interval != "1h" or not bar.is_closed or bar.quality != "VALID":
            continue
        start_hour = bar.open_time.replace(minute=0, second=0, microsecond=0)
        bucket_hour = (start_hour.hour // 4) * 4
        bucket = start_hour.replace(hour=bucket_hour)
        groups[(bar.symbol, bar.instrument_id, bucket)].append(bar)
    result = []
    hour = timedelta(hours=1)
    four_hours = timedelta(hours=4)
    millisecond = timedelta(milliseconds=1)
    for (symbol, instrument_id, start), group in sorted(groups.items()):
        group = sorted(group, key=lambda b: b.open_time)
        expected = tuple(start + hour*i for i in range(4))
        if len(group) != 4 or tuple(b.open_time for b in group) != expected:
            continue
        close_time = group[-1].close_time
        if close_time != start + four_hours - millisecond:
            continue
        source_ids = tuple(b.source_record_id for b in group)
        available = max(b.available_at for b in group)
        ingested = max(b.ingested_at for b in group)
        quote = None if any(b.quote_volume is None for b in group) else sum((b.quote_volume for b in group), D(0))
        result.append(Candle(
            symbol=symbol, instrument_id=instrument_id, event_time=close_time,
            available_at=available, ingested_at=ingested, as_of=max(b.as_of for b in group),
            data_source="C04_DERIVED_FROM_BINANCE_UM_1H", source_version="c04.aggregate-4h.v1",
            units=group[0].units, fidelity="BAR_DERIVED_APPROX", readiness="READY", quality="VALID",
            observation_id=stable_id("c04.derived-4h.v1", source_ids),
            config_hash=config_hash({"algorithm": "first-max-min-last-sum", "source_ids": source_ids}),
            interval="4h", open_time=start, close_time=close_time, open=group[0].open,
            high=max(b.high for b in group), low=min(b.low for b in group), close=group[-1].close,
            base_volume=sum((b.base_volume for b in group), D(0)), quote_volume=quote,
            trade_count=sum(b.trade_count for b in group), is_closed=True,
            source_record_id=stable_id("c04.derived-bar-record.v1", source_ids)))
    return tuple(result)


def synthetic_cost_profile() -> CostProfile:
    """Explicit research overlay; it cannot make missing market feeds ready."""
    return CostProfile(version="c04.synthetic-research-cost.v1",
        evidence_ids=("C04_SYNTHETIC_ASSUMPTION_NOT_VALIDATED",),
        entry_fee_rate="0.0005", ordinary_exit_fee_rate="0.0005", stop_exit_fee_rate="0.0005",
        ordinary_exit_spread_per_unit="0.01", ordinary_exit_slippage_per_unit="0.02",
        stop_spread_per_unit="0.02", stop_slippage_per_unit="0.05", funding_per_unit="0.05")


def synthetic_account(as_of: datetime) -> ResearchAccount:
    return ResearchAccount(source_id="C04_SYNTHETIC_ACCOUNT_NOT_BINANCE", as_of=as_of,
        equity_usdt="10000", pending_open_risk_usdt="0", pending_open_notional_usdt="0",
        isolated_margin_available_usdt="10000", occupied_slots=0, reconciled=True,
        daily_entry_halt=False)


def synthetic_eligible_panel() -> HistoricalPanel:
    """Build an explicitly synthetic C02-eligible panel that yields a C03 candidate.

    This fixture exists to exercise the complete policy-to-simulator pipeline.
    None of its observations are historical or included in empirical summaries.
    """
    from .demo import START, account, candle, costs, market, roll_market

    symbol = "ALTUSDT"
    instrument_id = binance_usdm_instrument_id(symbol)
    formed_at = START + timedelta(seconds=5)
    original = market(formed_at)
    formation = evaluate(original, symbol=symbol, instrument_id=instrument_id, as_of=formed_at,
        account=account(formed_at), profile=costs(), requested_quantity=D("10"),
        strategies=("T1",), sides=("LONG",))
    confirmed_at = START + timedelta(minutes=5, seconds=5)
    confirmation = candle(START, open="99.9", high="100.5", low="99.8", close="100.4")
    snapshot = roll_market(original, confirmed_at, extra=(confirmation,))
    confirmed = evaluate(snapshot, symbol=symbol, instrument_id=instrument_id, as_of=confirmed_at,
        account=account(confirmed_at), profile=costs(), state=formation.state,
        requested_quantity=D("10"), strategies=("T1",), sides=("LONG",))
    decision = next(d for d in confirmed.emitted if d.decision == "RESEARCH_CANDIDATE")
    arrival = decision.earliest_hypothetical_entry_at
    if arrival is None or decision.geometry is None:
        raise ValueError("synthetic C03 fixture did not produce its expected candidate")
    entry = decision.entry_max
    target1, target2 = (target.price for target in decision.geometry.targets)
    entry_bar = candle(arrival, open=str(entry), high=str(entry + D("0.1")),
        low=str(entry - D("0.1")), close=str(entry))
    tp1_bar = candle(arrival + timedelta(minutes=5), open=str(entry),
        high=str(target1 + D("0.1")), low=str(entry - D("0.1")), close=str(target1))
    tp2_bar = candle(arrival + timedelta(minutes=10), open=str(target1),
        high=str(target2 + D("0.1")), low=str(target1 - D("0.1")), close=str(target2))
    candles_5m = tuple(sorted((*snapshot.candles_5m, entry_bar, tp1_bar, tp2_bar),
        key=lambda bar: (bar.open_time, bar.source_record_id)))
    warmup_batch_at = START-timedelta(minutes=15)
    candles_5m = tuple(bar.model_copy(update={"available_at": warmup_batch_at,
        "ingested_at": warmup_batch_at, "as_of": warmup_batch_at})
        if bar.open_time < warmup_batch_at else bar for bar in candles_5m)
    data = snapshot.model_copy(update={
        "candles_5m": candles_5m,
        "candles_15m": tuple(bar.model_copy(update={"available_at": START,
            "ingested_at": START, "as_of": START}) for bar in snapshot.candles_15m),
        "candles_1h": tuple(bar.model_copy(update={"available_at": START,
            "ingested_at": START, "as_of": START}) for bar in snapshot.candles_1h),
        "candles_4h": tuple(bar.model_copy(update={"available_at": START,
            "ingested_at": START, "as_of": START}) for bar in snapshot.candles_4h),
    })
    initial_spreads = tuple(row.model_copy(update={"available_at": formed_at})
        for row in original.spread_samples)
    later_spreads = tuple(row.model_copy(update={"available_at": confirmed_at})
        for row in snapshot.spread_samples if row.event_time > original.spread_samples[-1].event_time)
    observation_history = {symbol: {
        "metadata": (original.metadata, snapshot.metadata),
        "ticker": (original.ticker, snapshot.ticker),
        "depth": (original.depth, snapshot.depth),
        "open_interest": (original.open_interest, snapshot.open_interest),
        "event_clearance": (original.event_clearance, snapshot.event_clearance),
        "spread_samples": (*initial_spreads, *later_spreads),
    }}
    encoded = json.dumps({"data": data.model_dump(mode="json"), "observation_history": {
        key: [row.model_dump(mode="json") for row in rows]
        for key, rows in observation_history[symbol].items()}}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    all_times = [row.event_time for rows in observation_history[symbol].values()
        for row in rows if hasattr(row, "event_time")]
    all_times.extend(row.as_of for row in observation_history[symbol]["event_clearance"])
    source_count = sum(len(rows) for rows in observation_history[symbol].values()) + sum(
        len(getattr(data, name)) for name in ("candles_5m", "candles_15m", "candles_1h", "candles_4h"))
    return HistoricalPanel(symbols={symbol: data}, partitions=({
        "feed": "synthetic-eligible-c02-c03-execution-panel", "symbol": symbol,
        "instrument_id": instrument_id, "retained_input_sha256": digest,
        "fidelity": "SYNTHETIC_FIXTURE", "availability_status": "SYNTHETIC_FIXTURE",
        "historical_listing_metadata": "NOT_APPLICABLE_SYNTHETIC_FIXTURE",
        "could_be_known_at_replay_time": "SYNTHETIC_FIXTURE_ONLY", "used_for_policy": True,
        "first_event_time": min(all_times).isoformat(), "last_event_time": max(all_times).isoformat(),
        "actual_row_count": source_count, "normalized_row_count": source_count,
    },), source_manifest={"evidence_class": "SYNTHETIC_FULLY_ELIGIBLE_TEST_FIXTURE",
        "fixture_version": "c04.synthetic-eligible-pipeline.v1", "performance_evidence": False},
        observation_history=observation_history)


def _funnel_event(kind: str, at: datetime, symbol: str, details: dict[str, Any], *,
                  source_time: datetime | None = None,
                  available_at: datetime | None = None) -> dict[str, Any]:
    event_id = stable_id("c04.funnel.v1", kind, at, symbol, details, source_time, available_at)
    return {"event_id": event_id, "event_type": kind,
            "source_time": source_time.isoformat() if source_time else None,
            "available_at": available_at.isoformat() if available_at else None,
            "processing_time": at.isoformat(), "symbol": symbol, "details": details}


def _panel_point_in_time(panel: HistoricalPanel, symbol: str, as_of: datetime,
                         history_limits: dict[str, int] | None = None) -> SymbolData:
    data = panel.symbols[symbol]
    history = panel.observation_history.get(symbol, {})
    updates: dict[str, Any] = {}
    for name in ("metadata", "ticker", "depth", "open_interest", "event_clearance"):
        if name == "event_clearance":
            rows = [row for row in history.get(name, ()) if row.as_of <= as_of]
        else:
            rows = [row for row in history.get(name, ())
                if row.available_at <= as_of and row.event_time <= as_of]
        if name in history:
            updates[name] = max(rows, key=lambda row: (
                getattr(row, "available_at", getattr(row, "as_of", as_of)),
                getattr(row, "event_time", getattr(row, "as_of", as_of)))) if rows else None
    if "spread_samples" in history:
        updates["spread_samples"] = tuple(sorted((row for row in history["spread_samples"]
            if row.available_at <= as_of and row.event_time <= as_of), key=lambda row: row.event_time))
    for interval in ("5m", "15m", "1h", "4h"):
        name = f"candles_{interval}"
        rows = getattr(data, name)
        if not rows:
            continue
        # Candle partitions are sorted by open time and archive availability
        # is monotonic. Binary search avoids rescanning months of history at
        # every bounded replay timestamp.
        end = bisect_right(rows, as_of, key=lambda candle: candle.available_at)
        visible = rows[:end]
        limit = history_limits.get(interval) if history_limits else None
        if limit is not None:
            if limit <= 0:
                raise ValueError(f"history limit for {interval} must be positive")
            visible = visible[-limit:]
        updates[name] = visible
    return data.model_copy(update=updates)


def _panel_availability_times(panel: HistoricalPanel) -> list[datetime]:
    times = {c.available_at for data in panel.symbols.values()
        for c in (*data.candles_5m, *data.candles_15m, *data.candles_1h, *data.candles_4h)}
    for fields in panel.observation_history.values():
        for rows in fields.values():
            times.update(row.available_at for row in rows if hasattr(row, "available_at"))
            times.update(row.as_of for row in rows if hasattr(row, "as_of") and not hasattr(row, "available_at"))
    return sorted(times)


def _execution_replay(
    decisions: Sequence[ResearchDecision], panel: HistoricalPanel, profile: CostProfile,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], dict[str, Any]]:
    """Run strict candidates through each scenario and a separate portfolio ledger."""
    candle_availability = [c.available_at for data in panel.symbols.values()
        for c in (*data.candles_5m, *data.candles_15m, *data.candles_1h, *data.candles_4h)]
    sample_end = max(candle_availability, default=max(
        (decision.expires_at for decision in decisions), default=datetime.max.replace(tzinfo=timezone.utc)))
    evidence_class = ("SYNTHETIC_MODELLED_EXECUTION"
        if panel.source_manifest.get("evidence_class", "").startswith("SYNTHETIC_")
        else "MODELLED_EXECUTION")
    scenarios = {
        "E0": ExecutionScenario.no_execution(),
        "E1": ExecutionScenario.conservative(sample_end=sample_end),
        "E2": ExecutionScenario.stress(sample_end=sample_end),
    }
    outcome_rows: dict[str, list[dict[str, Any]]] = {key: [] for key in scenarios}
    execution_events: list[dict[str, Any]] = []
    portfolio_summaries: dict[str, Any] = {}

    def append_event(kind: str, decision: ResearchDecision, scenario_id: str,
                     at: datetime, details: dict[str, Any]) -> None:
        row = _funnel_event(kind, at, decision.symbol,
            {"scenario_id": scenario_id, "decision_id": decision.decision_id, **details},
            available_at=at)
        execution_events.append(row)

    ordered = sorted({d.decision_id: d for d in decisions}.values(),
        key=lambda d: (d.as_of, d.decision_id))
    for scenario_id, scenario in scenarios.items():
        ledger = None if scenario_id == "E0" else PortfolioLedger(
            equity_usdt=D("10000"), daily_start_equity_usdt=D("10000"))
        pending: list[dict[str, Any]] = []

        def settle_due(cutoff: datetime) -> None:
            nonlocal pending
            due = sorted((p for p in pending if p["at"] <= cutoff),
                key=lambda p: (p["at"], p["decision_id"], p["action"]))
            due_ids = {id(p) for p in due}
            pending = [p for p in pending if id(p) not in due_ids]
            for item in due:
                if item["action"] == "RELEASE":
                    ledger.release(item["decision_id"], realized_pnl_usdt=item["realized_pnl_usdt"], at=item["at"])
                    append_event("PORTFOLIO_RISK_RELEASED", item["decision"], scenario_id, item["at"], {
                        "realized_pnl_usdt": str(item["realized_pnl_usdt"]),
                        "equity_usdt": str(ledger.equity_usdt),
                        "realized_pnl_today_usdt": str(ledger.realized_pnl_today_usdt),
                        "daily_entry_halt": ledger.halted})
                else:
                    ledger.mark_to_market(unrealized_pnl_usdt=item["mark_pnl_usdt"], at=item["at"])
                    append_event("PORTFOLIO_POSITION_MARKED_AT_SAMPLE_END", item["decision"], scenario_id,
                        item["at"], {"marked_pnl_usdt": str(item["mark_pnl_usdt"]),
                            "daily_entry_halt": ledger.halted})

        for decision in ordered:
            if ledger is not None:
                settle_due(decision.as_of)
                admitted, reject_reason = ledger.admit(decision, as_of=decision.as_of)
                append_event("PORTFOLIO_ADMISSION_ATTEMPT", decision, scenario_id, decision.as_of, {
                    "accepted": admitted, "reason": reject_reason,
                    "proposed_risk_usdt": str(decision.economics.proposed_modeled_loss_usdt),
                    "proposed_quantity": str(decision.economics.proposed_quantity)})
                if not admitted:
                    outcome = ScenarioOutcome(evidence_class=evidence_class,
                        scenario_id=scenario_id, decision_id=decision.decision_id, symbol=decision.symbol,
                        status="REJECTED", fill_fidelity="NONE",
                        reasons=(f"PORTFOLIO_{reject_reason}",))
                    outcome_rows[scenario_id].append(outcome.model_dump(mode="json"))
                    append_event("PORTFOLIO_RISK_REJECTED", decision, scenario_id, decision.as_of, {
                        "reason": reject_reason,
                        "proposed_risk_usdt": str(decision.economics.proposed_modeled_loss_usdt)})
                    append_event("SCENARIO_OUTCOME_RECORDED", decision, scenario_id, decision.as_of, {
                        "status": outcome.status, "reasons": list(outcome.reasons)})
                    continue
                reserved_total = sum((D(row["risk_usdt"]) for row in ledger.reservations.values()), D(0))
                append_event("PORTFOLIO_RISK_RESERVED", decision, scenario_id, decision.as_of, {
                    "risk_usdt": str(decision.economics.proposed_modeled_loss_usdt),
                    "reserved_total_risk_usdt": str(reserved_total),
                    "reservation_count": len(ledger.reservations),
                    "reserved_symbols": sorted(row["symbol"] for row in ledger.reservations.values())})
                if scenario.approval_mode == "PREAPPROVED_ARMED":
                    append_event("APPROVAL_PREAUTHORIZED", decision, scenario_id, decision.as_of, {
                        "approval_mode": scenario.approval_mode})
                elif scenario.approval_mode in ("POST_TRIGGER_IMMEDIATE", "HUMAN_DELAY"):
                    append_event("APPROVAL_REQUESTED", decision, scenario_id, decision.as_of, {
                        "approval_mode": scenario.approval_mode})
                    approval_at = max(decision.as_of+timedelta(microseconds=1),
                        decision.earliest_hypothetical_entry_at or decision.as_of) + scenario.approval_delay
                    if scenario.approval_outcome == "APPROVED":
                        append_event("APPROVAL_GRANTED", decision, scenario_id, approval_at, {
                            "approval_mode": scenario.approval_mode,
                            "approval_delay_seconds": scenario.approval_delay.total_seconds()})
                    elif scenario.approval_outcome == "REJECTED":
                        append_event("APPROVAL_REJECTED", decision, scenario_id, approval_at, {
                            "approval_mode": scenario.approval_mode})
                    else:
                        append_event("APPROVAL_EXPIRED", decision, scenario_id, decision.expires_at, {
                            "approval_mode": scenario.approval_mode})

            outcome = simulate_decision(decision, panel.symbols[decision.symbol],
                scenario=scenario, profile=profile,
                funding=tuple(panel.observation_history.get(decision.symbol, {}).get("funding", ())),
                evidence_class=evidence_class)
            outcome_rows[scenario_id].append(outcome.model_dump(mode="json"))
            arrival = max(decision.as_of+timedelta(microseconds=1),
                decision.earliest_hypothetical_entry_at or decision.as_of) + scenario.approval_delay
            can_submit = (scenario_id != "E0" and scenario.approval_outcome == "APPROVED"
                and decision.trigger_submit_deadline is not None
                and arrival <= decision.trigger_submit_deadline and arrival <= decision.expires_at)
            if can_submit:
                append_event("ORDER_SUBMISSION_ATTEMPTED", decision, scenario_id, arrival, {
                    "ioc_ttl_seconds": scenario.ioc_ttl.total_seconds(),
                    "fill_model": scenario.fill_model})
            if scenario_id != "E0" and outcome.status in (
                    "MISSED_ENTRY", "EXPIRED", "UNFILLED", "TARGET_LEG_INFEASIBLE"):
                status_event = {
                    "MISSED_ENTRY": "ENTRY_MISSED",
                    "EXPIRED": "ENTRY_EXPIRED",
                    "UNFILLED": "ENTRY_UNFILLED",
                    "TARGET_LEG_INFEASIBLE": "ENTRY_TARGET_LEG_INFEASIBLE",
                }[outcome.status]
                status_at = (decision.trigger_submit_deadline if outcome.status == "MISSED_ENTRY"
                    and decision.trigger_submit_deadline is not None else
                    decision.expires_at if outcome.status == "EXPIRED" else
                    min(sample_end, decision.expires_at))
                append_event(status_event, decision, scenario_id, status_at,
                    {"status": outcome.status, "reasons": list(outcome.reasons)})
            if outcome.filled_quantity > 0 and outcome.first_fill_at is not None:
                fill_details = {"quantity": str(outcome.filled_quantity),
                    "price": str(outcome.entry_price) if outcome.entry_price is not None else None,
                    "fill_fidelity": outcome.fill_fidelity,
                    "initial_modeled_risk_usdt": str(outcome.initial_modeled_risk_usdt)}
                append_event("MODELED_FILL", decision, scenario_id, outcome.first_fill_at, fill_details)
                if outcome.filled_quantity < decision.economics.proposed_quantity:
                    append_event("MODELED_PARTIAL_FILL", decision, scenario_id, outcome.first_fill_at,
                        {**fill_details, "proposed_quantity": str(decision.economics.proposed_quantity)})
                append_event("MODELED_POSITION_PROTECTED", decision, scenario_id, outcome.first_fill_at, {
                    "stop": str(decision.geometry.original_stop),
                    "targets": [str(target.price) for target in decision.geometry.targets],
                    "fill_fidelity": outcome.fill_fidelity})
            for event in outcome.exit_events:
                append_event("SIMULATED_" + event.event_type, decision, scenario_id, event.at,
                    dict(event.details))

            resolution_event_types = {"STOP", "TP1", "TP2", "FORCED_FLATTEN_11H55",
                "FORCED_FLATTEN_12H_HARD_LIMIT"}
            terminal_exits = [event for event in outcome.exit_events
                if event.event_type in resolution_event_types]
            if ledger is not None:
                if outcome.status == "FLAT":
                    resolution_at = max((event.at for event in terminal_exits), default=outcome.first_fill_at or decision.as_of)
                    pending.append({"action": "RELEASE", "at": resolution_at,
                        "decision_id": decision.decision_id, "decision": decision,
                        "realized_pnl_usdt": outcome.realized_pnl_usdt})
                elif outcome.filled_quantity > 0:
                    pending.append({"action": "MARK", "at": sample_end,
                        "decision_id": decision.decision_id, "decision": decision,
                        "mark_pnl_usdt": outcome.realized_pnl_usdt+outcome.unrealized_pnl_usdt})
                else:
                    if outcome.status == "MISSED_ENTRY":
                        resolution_at = decision.trigger_submit_deadline or decision.as_of
                    elif outcome.status == "EXPIRED":
                        resolution_at = decision.expires_at
                    else:
                        resolution_at = min(sample_end, decision.expires_at)
                    pending.append({"action": "RELEASE", "at": resolution_at,
                        "decision_id": decision.decision_id, "decision": decision,
                        "realized_pnl_usdt": D(0)})
            resolution_at = (max((event.at for event in terminal_exits), default=outcome.first_fill_at or decision.as_of)
                if outcome.status == "FLAT" else min(sample_end, decision.expires_at))
            append_event("SCENARIO_OUTCOME_RECORDED", decision, scenario_id, resolution_at, {
                "status": outcome.status, "filled_quantity": str(outcome.filled_quantity),
                "realized_pnl_usdt": str(outcome.realized_pnl_usdt),
                "realized_net_r": str(outcome.realized_net_r) if outcome.realized_net_r is not None else None,
                "reasons": list(outcome.reasons)})

        if ledger is not None:
            settle_due(sample_end)
            portfolio_summaries[scenario_id] = {
                "equity_usdt": str(ledger.equity_usdt), "daily_start_equity_usdt": str(ledger.daily_start_equity_usdt),
                "realized_pnl_today_usdt": str(ledger.realized_pnl_today_usdt),
                "daily_entry_halt": ledger.halted,
                "open_reservations": ledger.reservations,
                "open_risk_usdt": str(sum((D(row["risk_usdt"]) for row in ledger.reservations.values()), D(0))),
            }
        else:
            portfolio_summaries[scenario_id] = {"status": "NO_EXECUTION_POLICY", "open_reservations": {}}

    counts = Counter(event["event_type"] for event in execution_events)
    outcome_by_scenario = {scenario_id: [json.loads(json.dumps(row)) for row in rows]
        for scenario_id, rows in outcome_rows.items()}
    filled_risk = sum((D(str(event["details"]["initial_modeled_risk_usdt"]))
        for event in execution_events if event["event_type"] == "MODELED_FILL"), D(0))
    cumulative_reserved_risk = sum((D(str(event["details"]["risk_usdt"]))
        for event in execution_events if event["event_type"] == "PORTFOLIO_RISK_RESERVED"), D(0))
    peak_reserved_risk = max((D(str(event["details"]["reserved_total_risk_usdt"]))
        for event in execution_events if event["event_type"] == "PORTFOLIO_RISK_RESERVED"), default=D(0))
    released_pnl = sum((D(str(event["details"]["realized_pnl_usdt"]))
        for event in execution_events if event["event_type"] == "PORTFOLIO_RISK_RELEASED"), D(0))
    metrics = {
        "candidate_scenario_count": counts["SCENARIO_OUTCOME_RECORDED"],
        "approval_requested": counts["APPROVAL_REQUESTED"],
        "approved": counts["APPROVAL_GRANTED"], "preauthorized": counts["APPROVAL_PREAUTHORIZED"],
        "approval_rejected": counts["APPROVAL_REJECTED"],
        "portfolio_risk_rejected": counts["PORTFOLIO_RISK_REJECTED"],
        "rejected": counts["APPROVAL_REJECTED"]+counts["PORTFOLIO_RISK_REJECTED"],
        "approval_expired": counts["APPROVAL_EXPIRED"],
        "entry_expired": counts["ENTRY_EXPIRED"], "entries_missed": counts["ENTRY_MISSED"],
        "entries_unfilled": counts["ENTRY_UNFILLED"],
        "target_ladder_infeasible": counts["ENTRY_TARGET_LEG_INFEASIBLE"],
        "order_submission_scenarios": counts["ORDER_SUBMISSION_ATTEMPTED"],
        "filled_scenarios": counts["MODELED_FILL"], "partial_fills": counts["MODELED_PARTIAL_FILL"],
        "protected_positions": counts["MODELED_POSITION_PROTECTED"],
        "tp1": sum(1 for event in execution_events if event["event_type"] == "SIMULATED_TP1"),
        "tp2": sum(1 for event in execution_events if event["event_type"] == "SIMULATED_TP2"),
        "stops": sum(1 for event in execution_events if event["event_type"] == "SIMULATED_STOP"),
        "forced_flatten": sum(1 for event in execution_events if event["event_type"] in (
            "SIMULATED_FORCED_FLATTEN_11H55", "SIMULATED_FORCED_FLATTEN_12H_HARD_LIMIT")),
        "unresolved_positions": counts["PORTFOLIO_POSITION_MARKED_AT_SAMPLE_END"],
        "portfolio_admission_attempts": counts["PORTFOLIO_ADMISSION_ATTEMPT"],
        "cumulative_reserved_risk_usdt": str(cumulative_reserved_risk),
        "peak_open_reserved_risk_usdt": str(peak_reserved_risk),
        "filled_initial_risk_usdt": str(filled_risk),
        "risk_reservations": counts["PORTFOLIO_RISK_RESERVED"],
        "risk_releases": counts["PORTFOLIO_RISK_RELEASED"],
        "realized_pnl_released_usdt": str(released_pnl),
        "portfolio_end_state_by_scenario": portfolio_summaries,
    }
    return outcome_by_scenario, execution_events, metrics


def replay_panel(panel: HistoricalPanel, *, shortlist_limit: int = 15,
                 replay_start: datetime | None = None,
                 replay_end: datetime | None = None,
                 evaluation_interval: str | None = None,
                 history_limits: dict[str, int] | None = None,
                 compact_diagnostics: bool = False,
                 diagnostic_sample_times: Sequence[datetime] = ()) -> dict[str, Any]:
    """Replay event snapshots through point-in-time C02 and persistent C03.

    The policy ledger uses only C02-selected symbols. A separate diagnostics
    ledger calls C03 on up to 15 observed symbols to preserve honest NO_TRADE
    reasons even when a tiny source panel cannot pass eligibility.
    """
    if not 1 <= shortlist_limit <= 15:
        raise ValueError("shortlist limit must be between 1 and 15")
    if evaluation_interval is not None and evaluation_interval not in ("5m", "15m", "1h", "4h"):
        raise ValueError("evaluation_interval must be 5m, 15m, 1h, or 4h")
    if replay_start is not None and replay_start.utcoffset() != timedelta(0):
        raise ValueError("replay_start must be UTC")
    if replay_end is not None and replay_end.utcoffset() != timedelta(0):
        raise ValueError("replay_end must be UTC")
    if replay_start is not None and replay_end is not None and replay_end <= replay_start:
        raise ValueError("replay_end must be after replay_start")
    if any(sample.utcoffset() != timedelta(0) for sample in diagnostic_sample_times):
        raise ValueError("diagnostic sample times must be UTC")
    if evaluation_interval is None:
        times = _panel_availability_times(panel)
    else:
        candle_field = f"candles_{evaluation_interval}"
        times = sorted({c.available_at for data in panel.symbols.values()
            for c in getattr(data, candle_field)})
    if replay_start is not None:
        times = [at for at in times if at >= replay_start]
    if replay_end is not None:
        times = [at for at in times if at < replay_end]
    config = {"schema_version": "c04.replay-config.v1", "engine": "thin-c02-c03-event-adapter.v1",
        "shortlist_limit": shortlist_limit, "policy_versions": {"T1": "T1.reclaim.v1",
        "R1": "R1.sweep.v1", "B1": "B1.original-ladder.v1"},
        "panel_evidence_class": panel.source_manifest.get(
            "evidence_class", "OBSERVED_HISTORICAL_INPUTS_INCOMPLETE"),
        "c03_state_persistence": "per-symbol JSON state carried between snapshots",
        "account": "synthetic 10,000 USDT research model; never a Binance account",
        "cost_profile": synthetic_cost_profile().model_dump(mode="json"),
        "selection": "C02 deterministic point-in-time eligibility/shortlist",
        "execution": "E0 policy truth; E1/E2 counterfactual simulation with separate per-scenario PortfolioLedger",
        "portfolio_policy": "v1.5 per-trade/aggregate risk, slots, symbol lock, leverage and UTC loss halt"}
    if (evaluation_interval is not None or replay_start is not None or replay_end is not None
            or history_limits or compact_diagnostics or diagnostic_sample_times):
        config["bounded_replay_scope"] = {
            "evaluation_interval": evaluation_interval or "all_available_sources",
            "start_inclusive": replay_start.isoformat() if replay_start else None,
            "end_exclusive": replay_end.isoformat() if replay_end else None,
            "history_limits_by_interval": history_limits or {},
            "compact_diagnostics": compact_diagnostics,
            "diagnostic_sample_times": sorted(at.isoformat() for at in diagnostic_sample_times),
            "scope_note": "Source files retain full declared coverage; snapshots are evaluated only at this bounded cadence/window.",
        }
    config_digest = config_hash(config)
    source_digests = sorted(p["retained_input_sha256"] for p in panel.partitions)
    run_id = stable_id("c04.run.v1", config_digest, source_digests)
    events: list[dict[str, Any]] = []
    strict_decisions: list[dict[str, Any]] = []
    strict_candidate_objects: list[ResearchDecision] = []
    diagnostic_decisions: list[dict[str, Any]] = []
    diagnostic_counts: Counter[str] = Counter()
    diagnostic_reasons: Counter[str] = Counter()
    diagnostic_context_readiness: Counter[str] = Counter()
    diagnostic_policy_eligible_count = 0
    diagnostic_samples = set(diagnostic_sample_times)
    strict_states: dict[str, ResearchState] = {}
    diagnostic_states: dict[str, ResearchState] = {}
    discovered_at: dict[str, datetime] = {}
    eligibility_latest: dict[str, dict[str, Any]] = {}
    coverage_symbols = {p["symbol"] for p in panel.partitions}
    profile = synthetic_cost_profile()
    tracemalloc.start()
    started = time.perf_counter()
    for at in times:
        visible = {symbol: _panel_point_in_time(panel, symbol, at, history_limits)
                   for symbol in panel.symbols}
        for symbol in sorted(coverage_symbols):
            if symbol not in discovered_at:
                discovered_at[symbol] = at
                symbol_partitions = [p for p in panel.partitions if p["symbol"] == symbol]
                earliest_source = min((datetime.fromisoformat(p["first_event_time"]) for p in symbol_partitions),
                                      default=at)
                events.append(_funnel_event("PANEL_SYMBOL_PRESENT", at, symbol,
                    {"source_partitions": [p["feed"] for p in symbol_partitions],
                     "historical_listing_status": "UNAVAILABLE"},
                    source_time=earliest_source, available_at=earliest_source))
        universe = scan_universe(visible, at, D("100"), limit=shortlist_limit)
        source_by_symbol: dict[str, Any] = {}
        for record in universe.considered:
            row = record.model_dump(mode="json")
            eligibility_latest[record.symbol] = row
            visible_candles = [c for c in (*visible[record.symbol].candles_5m,
                *visible[record.symbol].candles_15m, *visible[record.symbol].candles_1h,
                *visible[record.symbol].candles_4h) if c.confirmed_at(at)]
            last_source = max(visible_candles, key=lambda c: (c.event_time, c.source_record_id)) if visible_candles else None
            source_by_symbol[record.symbol] = last_source
            events.append(_funnel_event("ELIGIBILITY_WINDOW", at, record.symbol,
                {"state": record.state, "eligible": record.eligible, "reasons": list(record.reasons),
                 "shortlist_status": record.shortlist_status},
                source_time=last_source.event_time if last_source else None,
                available_at=last_source.available_at if last_source else None))
        for symbol in universe.shortlist:
            last_source = source_by_symbol.get(symbol)
            events.append(_funnel_event("SHORTLISTED", at, symbol,
                {"limit": universe.selection_limit, "purpose": "RESEARCH_WATCHLIST"},
                source_time=last_source.event_time if last_source else None,
                available_at=last_source.available_at if last_source else None))
            data = visible[symbol]
            instrument_id = data.metadata.instrument_id if data.metadata else binance_usdm_instrument_id(symbol)
            result = evaluate(data, symbol=symbol, instrument_id=instrument_id, as_of=at,
                account=synthetic_account(at), profile=profile, requested_quantity=D("1"),
                state=strict_states.get(symbol, ResearchState()))
            strict_states[symbol] = result.state
            for decision in result.emitted:
                serialized = decision.model_dump(mode="json")
                strict_decisions.append(serialized)
                if decision.decision == "RESEARCH_CANDIDATE":
                    strict_candidate_objects.append(decision)
                events.append(_funnel_event("STRICT_POLICY_DECISION", at, symbol,
                    {"decision_id": decision.decision_id, "decision": decision.decision,
                     "reasons": list(decision.rejection_reason_codes)},
                    source_time=last_source.event_time if last_source else None,
                    available_at=last_source.available_at if last_source else None))
        # Diagnostic mode intentionally does not relax C03's mandatory gates.
        for symbol in sorted(visible)[:15]:
            last_source = source_by_symbol.get(symbol)
            data = visible[symbol]
            instrument_id = data.metadata.instrument_id if data.metadata else binance_usdm_instrument_id(symbol)
            result = evaluate(data, symbol=symbol, instrument_id=instrument_id, as_of=at,
                account=synthetic_account(at), profile=profile, requested_quantity=D("1"),
                state=diagnostic_states.get(symbol, ResearchState()))
            diagnostic_states[symbol] = (result.state.model_copy(update={"decisions": ()})
                if compact_diagnostics else result.state)
            decision_counts: Counter[str] = Counter()
            reason_counts: Counter[str] = Counter()
            context_readiness_counts: Counter[str] = Counter()
            for decision in result.emitted:
                serialized = decision.model_dump(mode="json")
                diagnostic_counts[decision.decision] += 1
                decision_counts[decision.decision] += 1
                for reason in decision.rejection_reason_codes:
                    diagnostic_reasons[reason] += 1
                    reason_counts[reason] += 1
                context_dependency = next((dep for dep in decision.dependencies
                    if dep.name == "CONTEXT"), None)
                if context_dependency is not None:
                    diagnostic_context_readiness[context_dependency.readiness] += 1
                    context_readiness_counts[context_dependency.readiness] += 1
                if decision.decision == "RESEARCH_CANDIDATE" and any(
                        dep.name == "C02_UNIVERSE" and dep.readiness == "READY"
                        for dep in decision.dependencies):
                    diagnostic_policy_eligible_count += 1
                if not compact_diagnostics or at in diagnostic_samples:
                    diagnostic_decisions.append(serialized)
                if not compact_diagnostics:
                    events.append(_funnel_event("EXPLORATORY_SIGNAL_DIAGNOSTIC", at, symbol,
                        {"decision_id": decision.decision_id, "decision": decision.decision,
                         "reasons": list(decision.rejection_reason_codes), "mandatory_gates_bypassed": []},
                        source_time=last_source.event_time if last_source else None,
                        available_at=last_source.available_at if last_source else None))
            if compact_diagnostics:
                events.append(_funnel_event("EXPLORATORY_SIGNAL_SNAPSHOT", at, symbol,
                    {"decision_count": sum(decision_counts.values()),
                     "decision_counts": dict(sorted(decision_counts.items())),
                     "reason_counts": dict(sorted(reason_counts.items())),
                     "context_readiness_counts": dict(sorted(context_readiness_counts.items())),
                     "mandatory_gates_bypassed": []},
                    source_time=last_source.event_time if last_source else None,
                    available_at=last_source.available_at if last_source else None))
    scenario_outcomes, execution_events, execution_metrics = _execution_replay(
        strict_candidate_objects, panel, profile)
    events.extend(execution_events)
    elapsed = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    events.sort(key=lambda e: (e["processing_time"], e["event_type"], e["symbol"], e["event_id"]))
    eligible_latest = [x for x in eligibility_latest.values() if x["eligible"]]
    eligibility_states: dict[str, int] = {}
    for row in eligibility_latest.values():
        eligibility_states[row["state"]] = eligibility_states.get(row["state"], 0) + 1
    strict_candidates = [d for d in strict_decisions if d["decision"] == "RESEARCH_CANDIDATE"]
    diagnostic_setups = [setup for state in diagnostic_states.values() for setup in state.setups]
    setup_state_counts: dict[str, int] = {}
    for setup in diagnostic_setups:
        state_name = setup.snapshot.state
        setup_state_counts[state_name] = setup_state_counts.get(state_name, 0) + 1
    no_trade_reasons: dict[str, int] = {}
    for row in eligibility_latest.values():
        for reason in row["reasons"]:
            no_trade_reasons[reason] = no_trade_reasons.get(reason, 0) + 1
    for reason, count in diagnostic_reasons.items():
        no_trade_reasons[reason] = no_trade_reasons.get(reason, 0) + count
    synthetic_panel = panel.source_manifest.get("evidence_class", "").startswith("SYNTHETIC_")
    strict_status = ("SYNTHETIC_PIPELINE_TEST_ONLY" if synthetic_panel else
        ("BLOCKED_BY_DATA" if not strict_candidates else "RESEARCH_CANDIDATES_ONLY"))
    e1_complete = [row for row in scenario_outcomes["E1"]
        if row["status"] == "FLAT" and row["realized_net_r"] is not None]
    e1_values = [float(row["realized_net_r"]) for row in e1_complete]
    e1_blocks = [str(row["first_fill_at"])[:10] for row in e1_complete]
    stats_status = ("SYNTHETIC_PIPELINE_TEST_ONLY" if synthetic_panel else
        ("MODELLED_COUNTERFACTUALS_ONLY" if e1_complete else "NOT_TESTABLE"))
    statistics = {"status": stats_status,
        "reason": ("Synthetic fixture outcomes are mechanics evidence only." if synthetic_panel else
            ("E1 outcomes are bar-model counterfactuals; they do not qualify the policy." if e1_complete else
             "No strict candidate produced a complete E1 outcome.")),
        "outcomes": summarize(e1_values, time_blocks=e1_blocks),
        "market_time_block_bootstrap": cluster_bootstrap([
            {"market_time_block": block, "net_r": value} for block, value in zip(e1_blocks, e1_values)],
            replicates=2000, seed=20261025)}
    core = {"run_id": run_id, "config_hash": config_digest, "config": config,
        "source_checksums": source_digests, "partitions": list(panel.partitions),
        "source_manifest": panel.source_manifest,
        "time_range": {"first_available_at": times[0].isoformat() if times else None,
                       "last_available_at": times[-1].isoformat() if times else None,
                       "evaluation_windows": len(times)},
        "modes": {"STRICT_POLICY_REPLAY": {"evidence_class": config["panel_evidence_class"],
            "symbol_count": len(panel.symbols), "eligible_symbol_count_latest": len(eligible_latest),
            "shortlisted_symbol_windows": sum(1 for e in events if e["event_type"] == "SHORTLISTED"),
            "strict_decision_count": len(strict_decisions), "candidate_count": len(strict_candidates),
            "status": strict_status},
            "EXPLORATORY_SIGNAL_DIAGNOSTICS": {"evidence_class": "SYNTHETIC_DIAGNOSTICS" if synthetic_panel
                else "OBSERVED_HISTORICAL_DIAGNOSTICS",
                "decision_count": sum(diagnostic_counts.values()), "candidate_count": diagnostic_counts["RESEARCH_CANDIDATE"],
                "mandatory_gates_bypassed": [],
                "policy_eligible_trade_count": diagnostic_policy_eligible_count},
        },
        "funnel": {"symbols_discovered": len(discovered_at), "symbols_with_source_coverage": len(coverage_symbols),
            "symbols_eligible_latest": len(eligible_latest), "symbol_evaluations_latest": len(eligibility_latest),
            "eligible_symbol_windows": sum(e["event_type"] == "ELIGIBILITY_WINDOW"
                and bool(e["details"]["eligible"]) for e in events),
            "eligibility_state_counts_latest": dict(sorted(eligibility_states.items())),
            "symbol_evaluation_windows": len(times)*len(panel.symbols),
            "strict_context_evaluations": sum(1 for e in events if e["event_type"] == "SHORTLISTED"),
            "diagnostic_context_evaluations": len(times)*min(15, len(panel.symbols)),
            "symbols_shortlisted_latest": len(panel.symbols) and sum(
                r["shortlist_status"] == "SELECTED" for r in eligibility_latest.values()) or 0,
            "setup_state_counts_diagnostic": dict(sorted(setup_state_counts.items())),
            "setups_armed": sum(setup_state_counts.get(x, 0) for x in ("FORMING", "ARMED")),
            "setups_confirmed": sum(1 for setup in diagnostic_setups if setup.snapshot.confirmed_at is not None),
            "setups_consumed": setup_state_counts.get("CONSUMED", 0),
            "strict_candidate_decisions": len(strict_candidates),
            "diagnostic_no_trade_decisions": diagnostic_counts["NO_TRADE"],
            "vetoes_by_reason": dict(sorted(no_trade_reasons.items())),
            **{k: v for k, v in execution_metrics.items() if k not in (
                "candidate_scenario_count", "portfolio_end_state_by_scenario")}},
        "strict_decisions": strict_decisions, "diagnostic_decisions": diagnostic_decisions,
        "funnel_events": events,
        "scenario_outcomes": scenario_outcomes,
        "execution_events": execution_events,
        "execution_statistics": execution_metrics,
        "portfolio_end_state_by_scenario": execution_metrics["portfolio_end_state_by_scenario"],
        "statistics": statistics,
        "holdout": {"development": None, "validation": None, "untouched_evaluation": None,
            "status": "NOT_TESTABLE", "reason": "The retained panel does not provide contiguous multi-symbol warm-up or valid policy opportunities."}}
    decision_ledger = {"strict": strict_decisions, "diagnostic": diagnostic_decisions,
        "scenario_outcomes": scenario_outcomes}
    if compact_diagnostics:
        core["diagnostic_summary"] = {
            "decision_counts": dict(sorted(diagnostic_counts.items())),
            "reason_counts": dict(sorted(diagnostic_reasons.items())),
            "context_readiness_counts": dict(sorted(diagnostic_context_readiness.items())),
            "sample_count": len(diagnostic_decisions), "compact": True}
        decision_ledger["diagnostic_summary"] = core["diagnostic_summary"]
    core["output_manifest"] = {"schema_version": "c04.output-manifest.v1", "run_id": run_id,
        "decision_ledger_sha256": config_hash(decision_ledger),
        "funnel_ledger_sha256": config_hash(events), "source_partition_sha256": source_digests,
        "replay_version": "c04.thin-event-adapter.v2"}
    core["measurements"] = {"runtime_seconds": elapsed, "peak_traced_memory_bytes": peak_bytes,
        "evaluation_windows_per_second": len(times)/elapsed if elapsed else None,
        "funnel_events_per_second": len(events)/elapsed if elapsed else None}
    return core


def run_c02_panel(panel_dir: str | Path) -> dict[str, Any]:
    panel = load_c02_panel(panel_dir)
    return replay_panel(panel)
