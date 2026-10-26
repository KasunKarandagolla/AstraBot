"""Offline, deterministic replay of original Binance USD-M quote/book/ticker feeds."""
from __future__ import annotations

import argparse
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astrabot.data.historical_replay import (  # noqa: E402
    FreshnessLimits,
    SAMPLER_CONFIG,
    SOURCE_CONFIG_HASH,
    replay_observations,
)
from astrabot.data.historical_sources import (  # noqa: E402
    DERIVATIVE_HEADER,
    EXCHANGE,
    HistoricalDataError,
    SOURCE_VERSION,
    FeedDiagnostics,
    iter_books,
    iter_derivative_tickers,
    iter_quotes,
    new_diagnostics,
    verify_source,
)
from astrabot.data.historical_evidence import EVIDENCE_VERSION, load_evidence  # noqa: E402
from astrabot.data.models import config_hash  # noqa: E402

MANIFEST_VERSION = "c05g.historical-source-manifest.v1"
ORIGINAL_MANIFEST = {
    "manifest_version": MANIFEST_VERSION,
    "exchange": EXCHANGE,
    "symbol": "SOLUSDT",
    "date": "2024-10-01",
    "synthetic": False,
    "feeds": {
        "quotes": {
            "file": "binance-futures_quotes_2024-10-01_SOLUSDT.csv.gz",
            "sha256": "ce31562cbfa20312aeda0246caf2d83754ce90835ce7579aeca40988b50f68cc",
        },
        "derivative_ticker": {
            "file": "binance-futures_derivative_ticker_2024-10-01_SOLUSDT.csv.gz",
            "sha256": "8c7301a2b3aa22de1430af3844afac9bb05de061dfc28a65a7bdc4920c1357d7",
        },
        "book_snapshot_25": {
            "file": "binance-futures_book_snapshot_25_2024-10-01_SOLUSDT.csv.gz",
            "sha256": "19655523821b384f741715a2d4bf5db2fe1f825fddbed66ecaf9ef1796a6e3ba",
        },
    },
}
DATASET_HEADERS = {
    "quotes": None,  # exact schema is defined in the adapter module
    "derivative_ticker": DERIVATIVE_HEADER,
    "book_snapshot_25": None,
}
DEFAULT_DECISION_HOURS = ("00:30:00", "01:05:00", "03:05:00", "08:05:00",
                          "12:05:00", "16:05:00", "20:05:00", "23:59:00")
FIXED_C05F_CUTOFFS = ("00:30:00", "01:05:00", "08:05:00", "16:05:00")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "model_dump"):
        return _safe(value.model_dump(mode="python"))
    if is_dataclass(value):
        return {field.name: _safe(getattr(value, field.name)) for field in fields(value)
                if not field.name.startswith("_")}
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe(item) for item in value]
    return value


def parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timestamp must be ISO-8601 with an explicit UTC offset") from exc
    if parsed.utcoffset() != timedelta(0):
        raise argparse.ArgumentTypeError("timestamp must be UTC")
    return parsed


def _decision_times(date: str, supplied: list[str] | None) -> tuple[datetime, ...]:
    if supplied:
        values = tuple(parse_utc(value) for value in supplied)
        if len(set(values)) != len(values):
            raise HistoricalDataError("decision timestamps must be distinct")
        return values
    return tuple(datetime.fromisoformat(f"{date}T{time}+00:00") for time in DEFAULT_DECISION_HOURS)


def _load_manifest(data_root: Path, symbol: str, date: str,
                   manifest_path: Path | None) -> tuple[dict[str, Any], bool]:
    if manifest_path is not None:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HistoricalDataError(f"cannot read source manifest {manifest_path}: {exc}") from exc
    elif symbol == "SOLUSDT" and date == "2024-10-01":
        manifest = ORIGINAL_MANIFEST
    else:
        raise HistoricalDataError(
            "non-reference datasets require --source-manifest with exact filenames and SHA-256 values"
        )
    if (manifest.get("manifest_version") != MANIFEST_VERSION
            or manifest.get("exchange") != EXCHANGE
            or manifest.get("symbol") != symbol
            or manifest.get("date") != date
            or set(manifest.get("feeds", {})) != {"quotes", "derivative_ticker", "book_snapshot_25"}):
        raise HistoricalDataError("source manifest identity or feed set is invalid")
    for dataset, entry in manifest["feeds"].items():
        filename = entry.get("file", "")
        digest = entry.get("sha256", "")
        if (not filename or Path(filename).name != filename
                or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise HistoricalDataError(f"invalid file or SHA-256 entry for {dataset}")
    return manifest, bool(manifest.get("synthetic", False))


def _diagnostic_summary(diag: FeedDiagnostics) -> dict[str, Any]:
    return {
        "dataset": diag.dataset,
        "filename": Path(diag.path).name,
        "sha256": diag.sha256,
        "rows_seen": diag.rows_seen,
        "rows_valid": diag.rows_valid,
        "duplicates_rejected": diag.duplicates,
        "event_time_ties": diag.event_time_ties,
        "event_time_regressions": diag.event_time_regressions,
        "arrival_time_regressions": diag.arrival_time_regressions,
        "inverted_arrivals_rejected": diag.inverted_arrivals,
        "malformed_records": diag.malformed_records,
        "invalid_books": diag.invalid_books,
        "incomplete_books": diag.incomplete_books,
        "missing_open_interest": diag.missing_oi,
        "gzip_read_to_eof": True,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# C05-G/H historical research replay - {report['symbol']} {report['date']}",
        "",
        f"**Source integrity:** {'SYNTHETIC FIXTURE' if report['synthetic'] else 'SHA-256 verified original feeds'}; "
        f"configuration `{report['configuration_hash']}`.",
        "",
        "## Feed validation",
        "",
        "| Dataset | Rows | SHA-256 | Duplicates | Event ties | Event regressions | Arrival regressions |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for feed in report["feeds"]:
        lines.append(
            f"| {feed['dataset']} | {feed['rows_seen']:,} | `{feed['sha256']}` | "
            f"{feed['duplicates_rejected']} | {feed['event_time_ties']} | "
            f"{feed['event_time_regressions']} | {feed['arrival_time_regressions']} |"
        )
    lines.extend([
        "",
        "## Causal decision snapshots",
        "",
        "`event_time` and provider `available_at` are preserved. `available_at` is the source's `local_timestamp` arrival proxy. "
        "The minute sampler uses separate endpoint timestamps and does not change the C02 production scanner.",
        "",
        "| Decision UTC | Quote age | Book age | Spread slots | Median spread | Raw event 60s intervals | Raw bid / ask amount within 0.20% | Late derivative rows excluded | C02 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for snapshot in report["snapshots"]:
        median_value = snapshot["spread_median_fraction"]
        median_display = "N/A" if median_value is None else f"{Decimal(median_value):.10f}"
        bid = snapshot["depth_raw_bid_amount_within_0_20"]
        ask = snapshot["depth_raw_ask_amount_within_0_20"]
        depth_display = "N/A" if bid is None or ask is None else f"{bid} / {ask} (raw units)"
        lines.append(
            f"| {snapshot['decision_time']} | {snapshot['quote_event_age_seconds']}s | "
            f"{snapshot['depth_event_age_seconds']}s | "
            f"{snapshot['spread_slots_occupied']}/60 | {median_display} | "
            f"{snapshot['spread_source_event_exact_minute_intervals']}/59 | {depth_display} | "
            f"{snapshot['excluded_late_rows']['derivative_ticker']} | `{snapshot['c02_eligibility']}` |"
        )
    lines.extend([
        "",
        "The spread statistic is a research-only periodic sample on UTC minute boundaries using the latest quote in each `(endpoint - 60s, endpoint]` interval, "
        "with both source timestamps no later than that endpoint and a strict maximum age below 60 seconds. The median threshold remains 0.10%; "
        "60 distinct occupied endpoints are required. The adjacent raw event-time count is reported separately.",
        "",
        "Evidence checks below apply only to the pinned artifacts, effective intervals and datasets supplied. "
        "A VERIFIED synthetic check establishes validation mechanics only. Book notional is visible reconstructed depth, not executable liquidity. "
        "OI notional uses an explicitly supported same-row mark and measurement time; it is not a reported venue notional. "
        "Reported funding fields are not classified as settled funding. Event clearance, candles, fees, fills and complete C02 eligibility remain separate gates.",
        "",
        "## Historical metadata and quantity evidence",
        "",
        f"Evidence version: `{report['evidence_version']}`; manifest SHA-256: `{report['evidence_manifest_sha256']}`.",
        "",
        "| Decision UTC | Check | Status | Reasons | Evidence IDs |",
        "|---|---|---|---|---|",
    ])
    for snapshot in report["snapshots"]:
        validation = snapshot["evidence_validation"]
        for name, check in sorted(validation["checks"].items()):
            lines.append(f"| {snapshot['decision_time']} | {name} | {check['status']} | "
                         f"{', '.join(check['reasons'])} | {', '.join(check['evidence_ids'])} |")
    for snapshot in report["snapshots"]:
        validation = snapshot["evidence_validation"]
        lines.extend(["", f"At {snapshot['decision_time']}: OI measurement UTC `{validation['oi_measurement_at']}`; "
                      f"OI notional USDT `{validation['oi_notional_usdt']}`; "
                      f"visible bid/ask USDT within 0.20% `{validation['book_bid_notional_usdt_within_0_20']}` / "
                      f"`{validation['book_ask_notional_usdt_within_0_20']}`.", ""])
    lines.extend(["## Unresolved blockers", ""])
    all_blockers = sorted({blocker for item in report["snapshots"] for blocker in item["quality_blockers"]})
    lines.extend(f"- `{blocker}`" for blocker in all_blockers)
    lines.extend([
        "",
        "C02 eligibility and economic qualification remain fail-closed. This replay establishes data normalization and causal timing only; it does not establish profitability.",
        "",
    ])
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    data_root = args.data_root.expanduser().resolve()
    manifest, synthetic = _load_manifest(data_root, args.symbol, args.date, args.source_manifest)
    paths = {
        dataset: data_root / entry["file"]
        for dataset, entry in manifest["feeds"].items()
    }
    hashes = {
        dataset: verify_source(path, manifest["feeds"][dataset]["sha256"])
        for dataset, path in paths.items()
    }
    decisions = _decision_times(args.date, args.decision_time)
    diagnostics = {
        dataset: new_diagnostics(dataset, paths[dataset], hashes[dataset])
        for dataset in paths
    }
    evidence = load_evidence(args.evidence_manifest) if args.evidence_manifest else None
    freshness = FreshnessLimits()
    snapshots = replay_observations(
        symbol=args.symbol,
        decision_times=decisions,
        quotes=iter_quotes(paths["quotes"], symbol=args.symbol,
                           source_sha256=hashes["quotes"], diagnostics=diagnostics["quotes"]),
        books=iter_books(paths["book_snapshot_25"], symbol=args.symbol,
                         source_sha256=hashes["book_snapshot_25"], diagnostics=diagnostics["book_snapshot_25"]),
        derivatives=iter_derivative_tickers(
            paths["derivative_ticker"], symbol=args.symbol,
            source_sha256=hashes["derivative_ticker"],
            diagnostics=diagnostics["derivative_ticker"],
        ),
        quote_diagnostics=diagnostics["quotes"],
        book_diagnostics=diagnostics["book_snapshot_25"],
        derivative_diagnostics=diagnostics["derivative_ticker"],
        freshness=freshness, evidence=evidence, synthetic=synthetic,
    )
    run_config = {
        "source_version": SOURCE_VERSION,
        "source_sha256": hashes,
        "symbol": args.symbol,
        "date": args.date,
        "decision_times": [item.isoformat() for item in decisions],
        "source_config_hash": SOURCE_CONFIG_HASH,
        "sampler": SAMPLER_CONFIG,
        "freshness_seconds": {
            "quote": int(freshness.quote.total_seconds()),
            "depth": int(freshness.depth.total_seconds()),
            "open_interest_row": int(freshness.open_interest_row.total_seconds()),
        },
        "synthetic": synthetic,
        "evidence_version": EVIDENCE_VERSION,
        "evidence_manifest_sha256": evidence.manifest_sha256 if evidence else None,
    }
    report = {
        "report_version": "c05h.historical-research-report.v2",
        "evidence_version": EVIDENCE_VERSION,
        "evidence_manifest_sha256": evidence.manifest_sha256 if evidence else None,
        "evidence_manifest": _safe(evidence.manifest) if evidence else None,
        "symbol": args.symbol,
        "date": args.date,
        "exchange": EXCHANGE,
        "synthetic": synthetic,
        "source_manifest_version": manifest["manifest_version"],
        "source_version": SOURCE_VERSION,
        "configuration_hash": config_hash(run_config),
        "source_config_hash": SOURCE_CONFIG_HASH,
        "sampler_config": SAMPLER_CONFIG,
        "fixed_c05f_cutoffs_included": all(
            datetime.fromisoformat(f"{args.date}T{time}+00:00") in decisions
            for time in FIXED_C05F_CUTOFFS
        ),
        "feeds": [_diagnostic_summary(diagnostics[name])
                  for name in ("quotes", "derivative_ticker", "book_snapshot_25")],
        "snapshots": [_safe(item) for item in snapshots],
        "c02_complete_eligibility": False,
        "economic_qualification": "INSUFFICIENT_EVIDENCE",
    }
    report["markdown"] = _markdown(report)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"C05_G_HISTORICAL_RESEARCH_{args.symbol}_{args.date}"
    json_path = args.json_out or output_dir / f"{stem}.json"
    markdown_path = args.markdown_out or output_dir / f"{stem}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8", newline="\n")
    markdown_path.write_text(report["markdown"], encoding="utf-8", newline="\n")
    print(report["markdown"])
    print(f"\nJSON: {json_path}\nMarkdown: {markdown_path}")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True, help="UTC source date as YYYY-MM-DD")
    parser.add_argument("--source-manifest", type=Path,
                        help="checksummed manifest for non-reference datasets or synthetic fixtures")
    parser.add_argument("--evidence-manifest", type=Path,
                        help="optional versioned local historical metadata/unit evidence manifest")
    parser.add_argument("--decision-time", action="append", default=None,
                        help="explicit ISO-8601 UTC cutoff; repeat to supply multiple timestamps")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research" / "c05")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Z0-9]+", args.symbol):
        parser.error("symbol must contain uppercase letters and digits only")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("date must use YYYY-MM-DD")
    try:
        run(args)
    except (HistoricalDataError, OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
