"""Run the bounded, OHLCV-only C04 historical research pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astrabot.research.replay import load_public_um_archive_panel, replay_panel  # noqa: E402


SOURCE_START = datetime(2024, 7, 1, tzinfo=timezone.utc)
STUDY_START = datetime(2024, 9, 1, tzinfo=timezone.utc)
STUDY_END = datetime(2024, 11, 1, 0, 0, 0, 1000, tzinfo=timezone.utc)
WINDOWS = {
    "development": (datetime(2024, 9, 1, tzinfo=timezone.utc), datetime(2024, 10, 1, tzinfo=timezone.utc)),
    "validation": (datetime(2024, 10, 1, tzinfo=timezone.utc), datetime(2024, 10, 15, tzinfo=timezone.utc)),
    "untouched_evaluation": (datetime(2024, 10, 15, tzinfo=timezone.utc), datetime(2024, 11, 1, tzinfo=timezone.utc)),
}
HISTORY_LIMITS = {"5m": 288, "15m": 21, "1h": 735, "4h": 200}
REPLAY_INTERVAL = "1h"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _event_time(available_at: str) -> datetime:
    # Binance inclusive close_time + one millisecond availability proxy.
    return _time(available_at) - timedelta(milliseconds=1)


def _window_name(event_at: datetime) -> str | None:
    for name, (start, end) in WINDOWS.items():
        if start <= event_at < end:
            return name
    return None


def _warmup(panel) -> dict[str, Any]:
    requirements = {
        "C02_price_history": {"5m": 20, "15m": 21, "1h": 720, "4h": 200},
        "C03_context_history": {"5m": 15, "15m": 21, "1h": 735, "4h": 53},
    }
    results = {}
    for name, counts in requirements.items():
        ready_at = []
        per_symbol = {}
        for symbol, data in sorted(panel.symbols.items()):
            arrivals = {}
            for interval, count in counts.items():
                bars = getattr(data, f"candles_{interval}")
                if len(bars) < count:
                    raise ValueError(f"{symbol} {interval} history does not meet {name} count {count}")
                arrival = bars[count - 1].available_at
                arrivals[interval] = arrival.isoformat()
                ready_at.append(arrival)
            per_symbol[symbol] = arrivals
        results[name] = {
            "required_closed_contiguous_bars": counts,
            "earliest_ohlcv_history_ready_at_utc": max(ready_at).isoformat(),
            "at_development_open": {
                symbol: {interval: sum(c.available_at <= STUDY_START
                    for c in getattr(data, f"candles_{interval}"))
                    for interval in counts}
                for symbol, data in sorted(panel.symbols.items())
            },
            "per_symbol_threshold_arrivals_utc": per_symbol,
            "note": "OHLCV history readiness only; missing mandatory C02 evidence still blocks STRICT_POLICY_REPLAY.",
        }
    return {
        "source_only_warmup": {"start": SOURCE_START.isoformat(), "end_exclusive": STUDY_START.isoformat()},
        "c02": results["C02_price_history"],
        "c03": results["C03_context_history"],
        "august_only_4h_rows_per_symbol": 186,
        "c02_4h_gate_rows": requirements["C02_price_history"]["4h"],
        "august_only_is_insufficient_for_c02_4h_gate": True,
    }


def _aggregate_run(run: dict[str, Any]) -> dict[str, Any]:
    per_window = {name: {
        "eligibility_windows": 0,
        "eligibility_states": Counter(),
        "strict_no_trade_reasons": Counter(),
        "diagnostic_snapshots": 0,
        "diagnostic_decisions": Counter(),
        "diagnostic_context_readiness": Counter(),
        "diagnostic_no_trade_reasons": Counter(),
    } for name in WINDOWS}
    for event in run["funnel_events"]:
        if event["event_type"] == "ELIGIBILITY_WINDOW":
            bucket = _window_name(_event_time(event["processing_time"]))
            if bucket:
                item = per_window[bucket]
                item["eligibility_windows"] += 1
                item["eligibility_states"][event["details"]["state"]] += 1
                item["strict_no_trade_reasons"].update(event["details"]["reasons"])
        elif event["event_type"] == "EXPLORATORY_SIGNAL_SNAPSHOT":
            bucket = _window_name(_event_time(event["processing_time"]))
            if bucket:
                item = per_window[bucket]
                item["diagnostic_snapshots"] += 1
                item["diagnostic_decisions"].update(event["details"]["decision_counts"])
                item["diagnostic_context_readiness"].update(event["details"]["context_readiness_counts"])
                item["diagnostic_no_trade_reasons"].update(event["details"]["reason_counts"])
    return {name: {key: (dict(sorted(value.items())) if isinstance(value, Counter) else value)
                   for key, value in row.items()} for name, row in per_window.items()}


def build_pilot(manifest_path: Path, data_root: Path) -> tuple[dict[str, Any], str]:
    panel = load_public_um_archive_panel(manifest_path, data_root)
    sample_times = tuple(start + timedelta(hours=1) for start, _ in WINDOWS.values())
    run = replay_panel(panel,
        # The first 1h availability at Sep 1 00:00 belongs to the final August
        # source-only bar. Start when the first September 1h bar is closed.
        replay_start=STUDY_START + timedelta(hours=1),
        replay_end=STUDY_END,
        evaluation_interval=REPLAY_INTERVAL,
        history_limits=HISTORY_LIMITS,
        compact_diagnostics=True,
        diagnostic_sample_times=sample_times,
    )
    if (run["modes"]["STRICT_POLICY_REPLAY"]["status"] != "BLOCKED_BY_DATA"
            or run["modes"]["STRICT_POLICY_REPLAY"]["candidate_count"] != 0
            or run["modes"]["STRICT_POLICY_REPLAY"]["shortlisted_symbol_windows"] != 0
            or run["modes"]["EXPLORATORY_SIGNAL_DIAGNOSTICS"]["mandatory_gates_bypassed"]):
        raise ValueError("historical OHLCV pilot did not remain fail-closed")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest["archives"]
    by_interval: dict[str, dict[str, Any]] = {}
    for interval in ("5m", "15m", "1h", "4h"):
        group = [row for row in records if row["interval"] == interval]
        by_interval[interval] = {
            "archive_count": len(group),
            "archive_bytes": sum(row["actual_bytes"] for row in group),
            "normalized_rows": sum(row["quality"]["actual_rows"] for row in group),
            "duplicate_open_times": sum(row["quality"]["duplicate_open_times"] for row in group),
            "out_of_order_open_times": sum(row["quality"]["out_of_order_open_times"] for row in group),
            "missing_intervals": sum(row["quality"]["missing_intervals"] for row in group),
            "coverage_start": min(row["coverage_start"] for row in group),
            "coverage_end": max(row["coverage_end"] for row in group),
        }
    split_summary = _aggregate_run(run)
    price_context_samples = {}
    for window_name, (window_start, _) in WINDOWS.items():
        as_of = window_start + timedelta(minutes=15)
        price_context_samples[window_name] = {"as_of": as_of.isoformat(), "symbols": {}}
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            data = panel.symbols[symbol]
            price_context_samples[window_name]["symbols"][symbol] = {}
            for interval in ("5m", "15m", "1h", "4h"):
                available = [candle for candle in getattr(data, f"candles_{interval}")
                             if candle.available_at <= as_of and candle.event_time <= as_of]
                last = available[-1]
                price_context_samples[window_name]["symbols"][symbol][interval] = {
                    "event_time": last.event_time.isoformat(),
                    "available_at": last.available_at.isoformat(),
                    "close": str(last.close),
                    "source_record_id": last.source_record_id,
                }
    manifest_digest = _sha256(manifest_path)
    smoke_manifest = ROOT / "research/c04/smoke_manifest.json"
    smoke_manifest_digest = _sha256(smoke_manifest) if smoke_manifest.is_file() else None
    smoke_records = (json.loads(smoke_manifest.read_text(encoding="utf-8"))["archives"]
                     if smoke_manifest.is_file() else [])
    smoke_verification = {
        "date_utc": "2025-10-23",
        "archive_count": len(smoke_records),
        "archive_bytes": sum(row["actual_bytes"] for row in smoke_records),
        "rows": sum(row["quality"]["actual_rows"] for row in smoke_records),
        "http_statuses": dict(sorted(Counter(str(row["http_status"]) for row in smoke_records).items())),
        "integrity_pass_count": sum(row["quality"]["status"] == "PASS" for row in smoke_records),
        "duplicate_open_times": sum(row["quality"]["duplicate_open_times"] for row in smoke_records),
        "out_of_order_open_times": sum(row["quality"]["out_of_order_open_times"] for row in smoke_records),
        "missing_intervals": sum(row["quality"]["missing_intervals"] for row in smoke_records),
        "files": [{
            "archive_id": row["archive_id"],
            "symbol": row["symbol"],
            "http_status": row["http_status"],
            "actual_bytes": row["actual_bytes"],
            "sha256": row["sha256"],
            "member": row["members"][0],
            "rows": row["quality"]["actual_rows"],
            "first_open_time": row["quality"]["first_open_time"],
            "last_open_time": row["quality"]["last_open_time"],
            "quality_status": row["quality"]["status"],
        } for row in smoke_records],
    }
    if (smoke_verification["archive_count"] != 7
            or smoke_verification["rows"] != 7 * 1440
            or smoke_verification["http_statuses"] != {"200": 7}
            or smoke_verification["integrity_pass_count"] != 7
            or smoke_verification["duplicate_open_times"]
            or smoke_verification["out_of_order_open_times"]
            or smoke_verification["missing_intervals"]):
        raise ValueError("the declared seven-archive ingestion smoke manifest is incomplete or failed quality checks")
    data_quality = {
        "archive_http_statuses": dict(sorted(Counter(str(row["http_status"]) for row in records).items())),
        "archive_integrity_pass_count": sum(row["quality"]["status"] == "PASS" for row in records),
        "archive_integrity_fail_count": sum(row["quality"]["status"] != "PASS" for row in records),
        "cross_archive_continuity": panel.source_manifest["cross_archive_continuity"],
    }
    compact = {
        "schema_version": "astrabot.c04.historical-pilot-summary.v1",
        "source_manifest_sha256": manifest_digest,
        "smoke_manifest_sha256": smoke_manifest_digest,
        "c04_run_id": run["run_id"],
        "c04_config_sha256": run["config_hash"],
        "decision_ledger_sha256": run["output_manifest"]["decision_ledger_sha256"],
        "funnel_ledger_sha256": run["output_manifest"]["funnel_ledger_sha256"],
        "evidence_class": panel.source_manifest["evidence_class"],
        "market": manifest["market"],
        "declared_cohort": manifest["symbols"],
        "cohort_limit": manifest["cohort_limit"],
        "study_windows": manifest["window"],
        "archive_count": len(records),
        "archive_bytes": sum(row["actual_bytes"] for row in records),
        "normalized_rows": sum(row["normalized_row_count"] for row in panel.partitions),
        "smoke_verification": smoke_verification,
        "archives_by_interval": by_interval,
        "data_quality": data_quality,
        "warmup": _warmup(panel),
        "replay": {
            "replay_interval": REPLAY_INTERVAL,
            "replay_start_available_at_inclusive": run["time_range"]["first_available_at"],
            "replay_end_available_at_inclusive": run["time_range"]["last_available_at"],
            "snapshot_count": run["time_range"]["evaluation_windows"],
            "history_limits_by_interval": HISTORY_LIMITS,
            "source_files_keep_full_coverage": True,
            "status": run["modes"]["STRICT_POLICY_REPLAY"]["status"],
            "strict_candidate_count": run["funnel"]["strict_candidate_decisions"],
            "shortlisted_symbol_windows": run["modes"]["STRICT_POLICY_REPLAY"]["shortlisted_symbol_windows"],
            "strict_eligibility_latest": run["funnel"]["eligibility_state_counts_latest"],
            "strict_reasons_latest": run["funnel"]["vetoes_by_reason"],
            "diagnostic_decision_counts": run["diagnostic_summary"]["decision_counts"],
            "diagnostic_context_readiness_counts": run["diagnostic_summary"]["context_readiness_counts"],
            "diagnostic_reason_counts": run["diagnostic_summary"]["reason_counts"],
            "per_window": split_summary,
            "causal_price_samples": price_context_samples,
            "sample_decisions": [{key: row.get(key) for key in (
                "as_of", "symbol", "strategy_id", "side", "decision", "readiness", "setup_id",
                "rejection_reason_codes", "dependencies")}
                for row in run["diagnostic_decisions"]
                if row.get("symbol") in {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
                and row.get("strategy_id") == "T1" and row.get("side") == "LONG"],
            "mandatory_gates_bypassed": [],
            "holdout_outcomes_used_for_selection": False,
        },
        "statistics": {
            "status": run["statistics"]["status"],
            "strict_historical_outcomes": sum(len(rows) for rows in run["scenario_outcomes"].values()),
            "market_time_block_ci95": run["statistics"]["market_time_block_bootstrap"]["ci95"],
            "profitability_claim": False,
        },
        "execution_limitations": [
            "STRICT_POLICY_REPLAY remains fail-closed because point-in-time contract metadata and exchange filters, fresh ticker, spread samples, depth, validated OI notional, and verified event clearance are absent.",
            "Historical funding settlements, bid/ask depth, market impact, original archive publication latency, and observed IOC fills are unavailable and are not inferred from OHLCV.",
            "Any E1/E2 OHLC execution is a counterfactual bar model, not a historical fill. The model's one-second IOC cannot be resolved from 5m OHLCV; no execution scenarios were eligible in this pilot.",
            "1h diagnostic snapshots can miss transient setup changes between hourly evaluations; they are not a full 15m or 5m setup/execution replay. C03 outputs remain strict NO_TRADE diagnostics.",
        ],
        "measurements": {"runtime_seconds": run["measurements"]["runtime_seconds"],
                         "peak_traced_memory_bytes": run["measurements"]["peak_traced_memory_bytes"]},
    }
    report = render_report(compact)
    return compact, report


def render_report(summary: dict[str, Any]) -> str:
    replay = summary["replay"]
    lines = [
        "# C04 authentic USDⓈ-M historical pilot",
        "",
        f"**Source manifest SHA256:** `{summary['source_manifest_sha256']}`",
        f"**Smoke manifest SHA256:** `{summary['smoke_manifest_sha256']}`",
        f"**C04 run:** `{summary['c04_run_id']}`",
        f"**Decision ledger SHA256:** `{summary['decision_ledger_sha256']}`",
        f"**Funnel ledger SHA256:** `{summary['funnel_ledger_sha256']}`",
        "",
        "This is an OHLCV-only historical research diagnostic. It makes no profitability or economic GO claim.",
        "",
        "## Acquisition and coverage",
        "",
        f"- Public source: `https://data.binance.vision/`; USDⓈ-M, USDT-settled kline archives only.",
        f"- Ingestion smoke (`{summary['smoke_verification']['date_utc']}`, 1m): {summary['smoke_verification']['archive_count']} daily archives, {summary['smoke_verification']['archive_bytes']:,} bytes and {summary['smoke_verification']['rows']:,} rows; HTTP statuses `{summary['smoke_verification']['http_statuses']}`, ZIP/CSV checks passed for {summary['smoke_verification']['integrity_pass_count']}, duplicates {summary['smoke_verification']['duplicate_open_times']}, out-of-order opens {summary['smoke_verification']['out_of_order_open_times']}, and gaps {summary['smoke_verification']['missing_intervals']}. Each member, exact schema, full-day timestamps and checksum is recorded in the smoke manifest.",
        f"- Fixed declared cohort: {', '.join(summary['declared_cohort'])}. This cohort is not evidence of a point-in-time dynamic universe.",
        f"- Monthly archives: {summary['archive_count']} files, {summary['archive_bytes']:,} compressed bytes, {summary['normalized_rows']:,} normalized rows.",
        f"- Archive HTTP statuses: `{summary['data_quality']['archive_http_statuses']}`; ZIP/CSV checks passed for {summary['data_quality']['archive_integrity_pass_count']} archives.",
        "- The bounded pilot uses one direct monthly archive for each of 7 symbols × 4 intervals × 4 months (112 files). It avoids interval resampling and full 1m history; 1m is limited to the one-day ingestion smoke test.",
        "",
        "Smoke archive checksums and exact member/row totals:",
        "",
        "| Archive | HTTP | Bytes | SHA256 | Member | Rows | Quality |",
        "|---|---:|---:|---|---|---:|---|",
    ]
    for row in summary["smoke_verification"]["files"]:
        lines.append(f"| {row['archive_id']} | {row['http_status']} | {row['actual_bytes']:,} | `{row['sha256']}` | {row['member']} | {row['rows']:,} | {row['quality_status']} |")
    lines.extend([
        "",
        "- Raw archives remain outside Git under `ASTRABOT_DATA_ROOT`; committed manifests contain source URLs, member names, actual sizes, SHA256 values, schema and continuity findings.",
        "",
        "| Interval | Archives | Rows | Compressed bytes | Coverage UTC | Duplicate opens | Missing intervals |",
        "|---|---:|---:|---:|---|---:|---:|",
    ])
    for interval in ("5m", "15m", "1h", "4h"):
        row = summary["archives_by_interval"][interval]
        lines.append(f"| {interval} | {row['archive_count']} | {row['normalized_rows']:,} | {row['archive_bytes']:,} | {row['coverage_start']} – {row['coverage_end']} | {row['duplicate_open_times']} | {row['missing_intervals']} |")
    lines.extend([
        "",
        "Each monthly file had the expected row count, exact Binance 12-column kline schema, one expected CSV member, valid ZIP contents, and zero timestamp duplicates, regressions or gaps. Cross-month checks also found zero duplicates, ordering errors or missing intervals for every symbol/timeframe.",
        "",
        "## Frozen windows and warm-up",
        "",
        "| Window | UTC range | Role |",
        "|---|---|---|",
        "| Source-only warm-up | 2024-07-01 through 2024-08-31 | Provide history only; no strategy outcomes used |",
        "| Development | 2024-09-01 through 2024-09-30 | Previously declared C04 development window |",
        "| Validation | 2024-10-01 through 2024-10-14 | Previously declared validation window |",
        "| Untouched evaluation | 2024-10-15 through 2024-10-31 | Held out; no strategy or cohort selection from its outcomes |",
        "",
        f"C02 requires 720 1h bars and 200 4h bars; C03 context requires 735 1h bars and 53 4h bars. The longest OHLCV-only threshold was reached by **{summary['warmup']['c02']['earliest_ohlcv_history_ready_at_utc']} UTC** from the first July archive bar. At the development open, every symbol had {summary['warmup']['c02']['at_development_open']['BTCUSDT']['1h']:,} 1h and {summary['warmup']['c02']['at_development_open']['BTCUSDT']['4h']:,} 4h bars available. August alone contains 186 4h bars per symbol and cannot meet C02's 200-bar gate.",
        "",
        "These counts establish source-history warm-up only. Missing point-in-time metadata and the other C02 evidence still prevent symbol eligibility.",
        "",
        "## C04 causal diagnostics",
        "",
        f"- C04 scanned {replay['snapshot_count']:,} UTC {replay['replay_interval']} availability snapshots across {len(summary['declared_cohort'])} symbols, using the existing C02 eligibility, C03 evaluator and C04 event replay. The window begins at `{replay['replay_start_available_at_inclusive']}` and ends at `{replay['replay_end_available_at_inclusive']}`.",
        "- The first September hourly evaluation starts at 01:00 UTC, when the 00:00–00:59 candle is closed; the 00:00 availability carrying the final August close is excluded from strategy diagnostics.",
        f"- Local replay runtime was {summary['measurements']['runtime_seconds']:.1f} seconds with {summary['measurements']['peak_traced_memory_bytes']:,} bytes of peak traced Python allocation; this is an executor-specific measurement, not a capacity guarantee.",
        f"- C02/C03 snapshot history caps were 288×5m, 21×15m, 735×1h and 200×4h bars. Raw source coverage remains complete; the bounded tails meet the existing indicator and eligibility lookbacks.",
        "- The 1h C04 cadence bounds runtime while retaining all source intervals in the as-of context. It can miss transient setup changes between hourly snapshots; this is not a full 15m or 5m setup/execution replay.",
        f"- STRICT_POLICY_REPLAY: **{replay['status']}**, {replay['shortlisted_symbol_windows']:,} shortlist windows, {replay['strict_candidate_count']} strict candidates. No mandatory gates were bypassed.",
        f"- Price/setup diagnostics: `{replay['diagnostic_decision_counts']}`; context readiness: `{replay['diagnostic_context_readiness_counts']}`.",
        f"- Latest strict eligibility NO_TRADE reasons/counts: `{replay['strict_reasons_latest']}`.",
        f"- C03 price/setup NO_TRADE reason counts: `{replay['diagnostic_reason_counts']}`. These are diagnostics only; no policy-qualified trade passed.",
        "",
        "Causal closed-bar prices at the first availability snapshot in each frozen window (archive source bytes are pinned by the manifest):",
        "",
        "| Window | As-of UTC | Symbol | Interval | Event close time | Close (USDT) | Available at | Source record ID |",
        "|---|---|---|---|---|---:|---|---|",
    ])
    for window_name, sample in replay["causal_price_samples"].items():
        for symbol, intervals in sample["symbols"].items():
            for interval, bar in intervals.items():
                lines.append(f"| {window_name} | {sample['as_of']} | {symbol} | {interval} | {bar['event_time']} | {bar['close']} | {bar['available_at']} | `{bar['source_record_id']}` |")
    lines.extend([
        "",
        "Representative C03 diagnostics at the first hourly snapshot in each frozen window retain their dependency reasons:",
        "",
        "| As-of UTC | Symbol | Strategy / side | Decision | C02/C03 reasons |",
        "|---|---|---|---|---|",
    ])
    for row in replay["sample_decisions"]:
        if row.get("symbol") not in {"BTCUSDT", "ETHUSDT", "SOLUSDT"} or row.get("strategy_id") != "T1" or row.get("side") != "LONG":
            continue
        reasons = ", ".join(row.get("rejection_reason_codes") or ())
        lines.append(f"| {row.get('as_of')} | {row.get('symbol')} | {row.get('strategy_id')} / {row.get('side')} | {row.get('decision')} | {reasons} |")
    lines.extend([
        "",
        "## Execution limits and statistics",
        "",
    ])
    lines.extend(f"- {item}" for item in summary["execution_limitations"])
    lines.extend([
        "",
        f"Statistics status is **{summary['statistics']['status']}**: there are {summary['statistics']['strict_historical_outcomes']} strict historical execution outcomes, so no expectancy interval or performance statistic is reported. The 12-hour purge/embargo remains declared at the split boundaries; no outcome-based holdout analysis was performed.",
        "",
        "## Next data requirements",
        "",
        "- Dated USDⓈ-M contract listing/status and exchange-filter snapshots, plus a point-in-time universe with historical inactive/delisted contracts and turnover inputs.",
        "- Historical ticker and bid/ask quote/depth snapshots sufficient to reproduce spread, executable liquidity and impact at each decision time.",
        "- Validated open-interest observations with documented units, freshness and contract conversion; authoritative event clearance records with observed availability times.",
        "- Historical funding, mark/index price and liquidation evidence where the strategy policy uses them.",
        "- Exchange publication/ingestion latency and calibrated IOC/partial-fill/stop execution traces or higher-frequency quote/trade data. Do not infer these from klines.",
        "",
        "## Reproduction",
        "",
        "```sh",
        "ASTRABOT_DATA_ROOT=/path/outside/the/repository work/c04-venv/bin/python scripts/c04_historical_pilot.py",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 work/c04-venv/bin/python -m pytest -q",
        "```",
        "",
        "The acquisition can be replayed in 7-archive batches with `scripts/c04_acquire_binance_um.py`; manifests pin the exact source bytes. Existing C04 `--check` remains the offline regression for the original retained panel.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "research/c04/historical_manifest.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/c04")
    args = parser.parse_args()
    configured_root = os.environ.get("ASTRABOT_DATA_ROOT")
    if not configured_root:
        parser.error("ASTRABOT_DATA_ROOT must point to the external raw-archive directory")
    summary, report = build_pilot(args.manifest.resolve(), Path(configured_root).resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "pilot_summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "historical_pilot.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "source_manifest_sha256": summary["source_manifest_sha256"],
        "smoke_manifest_sha256": summary["smoke_manifest_sha256"],
        "c04_run_id": summary["c04_run_id"],
        "decision_ledger_sha256": summary["decision_ledger_sha256"],
        "funnel_ledger_sha256": summary["funnel_ledger_sha256"],
        "archive_count": summary["archive_count"],
        "archive_bytes": summary["archive_bytes"],
        "strict_status": summary["replay"]["status"],
        "strict_candidates": summary["replay"]["strict_candidate_count"],
        "replay_snapshots": summary["replay"]["snapshot_count"],
        "statistics_status": summary["statistics"]["status"],
        "runtime_seconds": summary["measurements"]["runtime_seconds"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
