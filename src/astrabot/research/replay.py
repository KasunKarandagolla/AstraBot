"""Causal historical panel loading and a thin adapter around C02/C03.

This module performs no network access. It consumes a checksummed manifest and
retained files, advances only at source availability times, and persists a C03
ResearchState per symbol across snapshots.
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from astrabot.data.models import Candle, binance_usdm_instrument_id, config_hash, stable_id
from astrabot.data.replay import normalize_agg_trades, normalize_klines, trade_quality
from astrabot.research.engine import evaluate, point_in_time
from astrabot.research.models import CostProfile, ResearchAccount, ResearchState
from astrabot.research.statistics import cluster_bootstrap, summarize
from astrabot.universe.eligibility import SymbolData, scan_universe


@dataclass(frozen=True)
class HistoricalPanel:
    symbols: dict[str, SymbolData]
    partitions: tuple[dict[str, Any], ...]
    source_manifest: dict[str, Any]


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


def _funnel_event(kind: str, at: datetime, symbol: str, details: dict[str, Any], *,
                  source_time: datetime | None = None,
                  available_at: datetime | None = None) -> dict[str, Any]:
    event_id = stable_id("c04.funnel.v1", kind, at, symbol, details, source_time, available_at)
    return {"event_id": event_id, "event_type": kind,
            "source_time": source_time.isoformat() if source_time else None,
            "available_at": available_at.isoformat() if available_at else None,
            "processing_time": at.isoformat(), "symbol": symbol, "details": details}


def replay_panel(panel: HistoricalPanel, *, shortlist_limit: int = 15) -> dict[str, Any]:
    """Replay event snapshots through point-in-time C02 and persistent C03.

    The policy ledger uses only C02-selected symbols. A separate diagnostics
    ledger calls C03 on up to 15 observed symbols to preserve honest NO_TRADE
    reasons even when a tiny source panel cannot pass eligibility.
    """
    if not 1 <= shortlist_limit <= 15:
        raise ValueError("shortlist limit must be between 1 and 15")
    times = sorted({c.available_at for data in panel.symbols.values()
        for c in (*data.candles_5m, *data.candles_15m, *data.candles_1h, *data.candles_4h)})
    config = {"schema_version": "c04.replay-config.v1", "engine": "thin-c02-c03-event-adapter.v1",
        "shortlist_limit": shortlist_limit, "policy_versions": {"T1": "T1.reclaim.v1",
        "R1": "R1.sweep.v1", "B1": "B1.original-ladder.v1"},
        "c03_state_persistence": "per-symbol JSON state carried between snapshots",
        "account": "synthetic 10,000 USDT research model; never a Binance account",
        "cost_profile": synthetic_cost_profile().model_dump(mode="json"),
        "selection": "C02 deterministic point-in-time eligibility/shortlist",
        "execution": "E0 policy truth; E1/E2 isolated counterfactual adapter"}
    config_digest = config_hash(config)
    source_digests = sorted(p["retained_input_sha256"] for p in panel.partitions)
    run_id = stable_id("c04.run.v1", config_digest, source_digests)
    events: list[dict[str, Any]] = []
    strict_decisions: list[dict[str, Any]] = []
    diagnostic_decisions: list[dict[str, Any]] = []
    strict_states: dict[str, ResearchState] = {}
    diagnostic_states: dict[str, ResearchState] = {}
    discovered_at: dict[str, datetime] = {}
    eligibility_latest: dict[str, dict[str, Any]] = {}
    coverage_symbols = {p["symbol"] for p in panel.partitions}
    profile = synthetic_cost_profile()
    tracemalloc.start()
    started = time.perf_counter()
    for at in times:
        visible = {symbol: point_in_time(data, at) for symbol, data in panel.symbols.items()}
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
            diagnostic_states[symbol] = result.state
            for decision in result.emitted:
                serialized = decision.model_dump(mode="json")
                diagnostic_decisions.append(serialized)
                events.append(_funnel_event("EXPLORATORY_SIGNAL_DIAGNOSTIC", at, symbol,
                    {"decision_id": decision.decision_id, "decision": decision.decision,
                     "reasons": list(decision.rejection_reason_codes), "mandatory_gates_bypassed": []},
                    source_time=last_source.event_time if last_source else None,
                    available_at=last_source.available_at if last_source else None))
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
    for row in diagnostic_decisions:
        for reason in row["rejection_reason_codes"]:
            no_trade_reasons[reason] = no_trade_reasons.get(reason, 0) + 1
    core = {"run_id": run_id, "config_hash": config_digest, "config": config,
        "source_checksums": source_digests, "partitions": list(panel.partitions),
        "time_range": {"first_available_at": times[0].isoformat() if times else None,
                       "last_available_at": times[-1].isoformat() if times else None,
                       "evaluation_windows": len(times)},
        "modes": {"STRICT_POLICY_REPLAY": {"evidence_class": "OBSERVED_HISTORICAL_INPUTS_INCOMPLETE",
            "symbol_count": len(panel.symbols), "eligible_symbol_count_latest": len(eligible_latest),
            "shortlisted_symbol_windows": sum(1 for e in events if e["event_type"] == "SHORTLISTED"),
            "strict_decision_count": len(strict_decisions), "candidate_count": len(strict_candidates),
            "status": "BLOCKED_BY_DATA" if not strict_candidates else "RESEARCH_CANDIDATES_ONLY"},
            "EXPLORATORY_SIGNAL_DIAGNOSTICS": {"evidence_class": "OBSERVED_HISTORICAL_DIAGNOSTICS",
                "decision_count": len(diagnostic_decisions), "candidate_count": sum(
                    d["decision"] == "RESEARCH_CANDIDATE" for d in diagnostic_decisions),
                "mandatory_gates_bypassed": [], "policy_eligible_trade_count": 0}},
        "funnel": {"symbols_discovered": len(discovered_at), "symbols_with_source_coverage": len(coverage_symbols),
            "symbols_eligible_latest": len(eligible_latest), "symbol_evaluations_latest": len(eligibility_latest),
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
            "diagnostic_no_trade_decisions": sum(d["decision"] == "NO_TRADE" for d in diagnostic_decisions),
            "vetoes_by_reason": dict(sorted(no_trade_reasons.items())),
            "approval_requested": 0, "approved": 0, "rejected": 0, "expired": 0,
            "order_submission_scenarios": 0, "filled_scenarios": 0, "partial_fills": 0,
            "protected_positions": 0, "tp1": 0, "tp2": 0, "stops": 0,
            "forced_flatten": 0, "unresolved_positions": 0},
        "strict_decisions": strict_decisions, "diagnostic_decisions": diagnostic_decisions,
        "funnel_events": events,
        "scenario_outcomes": {"E0": [], "E1": [], "E2": []},
        "statistics": {"status": "NOT_TESTABLE", "reason": "No strict qualified fills or complete outcomes.",
            "outcomes": summarize([]),
            "market_time_block_bootstrap": cluster_bootstrap([], replicates=2000, seed=20261025)},
        "holdout": {"development": None, "validation": None, "untouched_evaluation": None,
            "status": "NOT_TESTABLE", "reason": "The retained panel does not provide contiguous multi-symbol warm-up or valid policy opportunities."}}
    core["output_manifest"] = {"schema_version": "c04.output-manifest.v1", "run_id": run_id,
        "decision_ledger_sha256": config_hash({"strict": strict_decisions, "diagnostic": diagnostic_decisions}),
        "funnel_ledger_sha256": config_hash(events), "source_partition_sha256": source_digests,
        "replay_version": "c04.thin-event-adapter.v1"}
    core["measurements"] = {"runtime_seconds": elapsed, "peak_traced_memory_bytes": peak_bytes,
        "evaluation_windows_per_second": len(times)/elapsed if elapsed else None,
        "funnel_events_per_second": len(events)/elapsed if elapsed else None}
    return core


def run_c02_panel(panel_dir: str | Path) -> dict[str, Any]:
    panel = load_c02_panel(panel_dir)
    return replay_panel(panel)
