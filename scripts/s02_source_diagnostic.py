"""Offline S02 source verification; fixed source-only October 1 cutoffs.

No vendor requests, account access, collectors or strategy outcomes. Original
hash pins are intentionally not CLI-overridable. Detailed rows stay owner-local.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astrabot.data.historical_sources import (  # noqa: E402
    QUOTE_HEADER, _DiskDuplicateDetector, iter_books, iter_derivative_tickers,
    new_diagnostics, verify_source,
)
from astrabot.data.source_clock import (  # noqa: E402
    BBOObservationV2, MarketObservationV2, SampleClockV2, SamplingDiagnostic,
    quote_from_cells, sample_bbo,
)

ORIGINALS = {
    "quotes": ("ce31562cbfa20312aeda0246caf2d83754ce90835ce7579aeca40988b50f68cc", 1064711),
    "derivative_ticker": ("8c7301a2b3aa22de1430af3844afac9bb05de061dfc28a65a7bdc4920c1357d7", 119927),
    "book_snapshot_25": ("19655523821b384f741715a2d4bf5db2fe1f825fddbed66ecaf9ef1796a6e3ba", 1522898),
}
CUTOFFS = tuple(datetime(2024, 10, 1, hour, minute, tzinfo=timezone.utc)
                for hour, minute in ((0, 30), (1, 5), (8, 5), (16, 5)))


def canonical(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, default=str) + "\n"


def deterministic_gzip(payload):
    # gzip.compress(mtime=0) in Python 3.12 can emit a platform-specific OS byte.
    stream = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as packed:
        packed.write(payload)
    return stream.getvalue()


def _microseconds(delta):
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def _quote_rows(path, digest, scope, counts):
    """Full-day clock/duplicate audit with C05-G's bounded disk identity set."""
    previous_event = previous_arrival = None
    event_minutes, arrival_minutes, pending_ids = set(), set(), []
    for name in ("raw_quote_rows", "duplicate_source_rows", "event_time_regressions",
                 "arrival_time_regressions", "inverted_arrivals", "invalid_or_locked_bbo",
                 "maximum_provider_arrival_gap_microseconds", "maximum_provider_delay_microseconds"):
        counts[name] = 0
    with tempfile.TemporaryDirectory(prefix="astrabot-s02-") as temporary:
        detector = _DiskDuplicateDetector(Path(temporary) / "quote-ids.sqlite3")
        try:
            with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream, strict=True)
                if tuple(next(reader)) != QUOTE_HEADER:
                    raise ValueError("quote header mismatch")
                for number, values in enumerate(reader, 2):
                    row = quote_from_cells(tuple(values), source_sha256=digest,
                                           row_number=number, scope=scope)
                    if row.symbol != "SOLUSDT" or row.exchange_event_time.date().isoformat() != "2024-10-01":
                        raise ValueError("quote outside frozen diagnostic instrument/day")
                    e, p = row.exchange_event_time, row.provider_arrival_time
                    counts["raw_quote_rows"] += 1
                    counts["event_time_regressions"] += int(previous_event is not None and e < previous_event)
                    counts["arrival_time_regressions"] += int(previous_arrival is not None and p < previous_arrival)
                    counts["inverted_arrivals"] += int(p < e)
                    counts["invalid_or_locked_bbo"] += int(row.bid_price <= 0 or row.ask_price <= row.bid_price or min(row.bid_quantity, row.ask_quantity) < 0)
                    if previous_arrival is not None:
                        counts["maximum_provider_arrival_gap_microseconds"] = max(
                            counts["maximum_provider_arrival_gap_microseconds"], _microseconds(p - previous_arrival))
                    counts["maximum_provider_delay_microseconds"] = max(
                        counts["maximum_provider_delay_microseconds"], _microseconds(p-e))
                    previous_event, previous_arrival = e, p
                    event_minutes.add(e.replace(second=0, microsecond=0))
                    arrival_minutes.add(p.replace(second=0, microsecond=0))
                    pending_ids.append(row.source_row_id)
                    if len(pending_ids) == 256:
                        counts["duplicate_source_rows"] += sum(detector.duplicates(pending_ids))
                        pending_ids.clear()
                    yield row
                counts["duplicate_source_rows"] += sum(detector.duplicates(pending_ids))
        finally:
            detector.close()
    counts["distinct_exchange_event_minutes"] = len(event_minutes)
    counts["distinct_provider_arrival_minutes"] = len(arrival_minutes)


def schema_contract():
    return {
        "version": "s02.source-contract.v1",
        "status": "PROPOSED_RESEARCH_ONLY_OWNER_APPROVAL_PENDING",
        "schemas": {cls.__name__: cls.model_json_schema() for cls in
                    (MarketObservationV2, BBOObservationV2, SampleClockV2, SamplingDiagnostic)},
        "default_clock": SampleClockV2().model_dump(mode="json"),
        "wire_time": "explicit UTC ISO8601; source CSV integer epoch microseconds; never float epoch",
        "source_fields": dict(zip(QUOTE_HEADER, (
            "provider exchange id", "venue symbol", "source event clock; validate no fallback",
            "provider arrival, never owner arrival", "unvalidated native quantity",
            "USDT per base asset subject to effective metadata", "same price unit", "unvalidated native quantity"))),
        "slots": {
            "endpoint_i": "60s*floor(cutoff/60s) - (59-i)*60s, i in [0,59]",
            "age": "0 <= endpoint - exchange_event_time <= 60s (inclusive)",
            "availability": "PROVIDER_HISTORY: provider<=endpoint; OWNER_RECEIPT: evidenced owner<=endpoint and provider<=endpoint if recorded",
            "selection": "ascending endpoints; max(event,provider_or_event,record_number,row_id), excluding already-used event identities",
            "identity": "native venue ID if independently mapped; otherwise instrument/class/event/bid/ask/quantities fingerprint, excluding arrival and row locator",
            "statistic": "median((ask-bid)/((ask+bid)/2)), Decimal precision 28 ROUND_HALF_EVEN; null unless 60 selected; pass<=0.001 plus last source event age at actual cutoff<=60s",
            "duplicates": "same source row offered again rejected; same event payload under another arrival rejected; contradictory same native ID quarantines members known by endpoint, never rewrites earlier slots",
            "out_of_order": "source record order authoritative; event or provider clock below prior high-water mark quarantined; never sorted to repair",
            "missingness": "no observed event in inclusive age band => MISSING_EVIDENCE; observed but all excluded => OBSERVED_REJECTED",
            "audit_scope": "exclusion counters and retained rejected rows are retrospective diagnostic evidence, never causal trading features",
        },
        "original_files": {k: {"sha256": v[0], "rows": v[1]} for k, v in ORIGINALS.items()},
        "cutoffs_utc": [v.isoformat() for v in CUTOFFS],
        "bound": "100000 offered rows per pure call; exceeding it aborts, never truncates",
        "acceptance": "hash/schema/chronology consistency does not certify origin, rights, completeness, owner receipt or any other C02 gate",
        "production_c02_changed": False,
    }


def run(root: Path, output: Path, *, synthetic: bool = False):
    if (output / "S02_DIAGNOSTIC.json").exists():
        raise ValueError("output contains a prior report; choose a fresh directory for an independent run")
    if synthetic:
        fixture = json.loads((root / "manifest.json").read_text())
        if fixture.get("synthetic") is not True:
            raise ValueError("synthetic fixture manifest required")
        pins = {k: (v["sha256"], None) for k, v in fixture["feeds"].items()}
    else:
        pins = ORIGINALS
    paths = {k: root / f"binance-futures_{k}_2024-10-01_SOLUSDT.csv.gz" for k in pins}
    for kind, path in paths.items():
        verify_source(path, pins[kind][0])
    scope = "SYNTHETIC_ONLY" if synthetic else "ORIGINAL_SAMPLE_HASH_VERIFIED"
    # One extra, explicitly synthetic-only cutoff exercises the fixture's full
    # 60-slot positive mechanics. The authentic four cutoffs never change.
    cutoffs = tuple(sorted((*CUTOFFS, datetime(2024, 10, 1, 1, tzinfo=timezone.utc)))) if synthetic else CUTOFFS
    windows = {cutoff: [] for cutoff in cutoffs}
    counts = Counter()
    # Preserve all quote rows, including duplicates and inverted clocks. C05-G's
    # generic iterator intentionally removes these, so use its header/parsers/ID
    # utilities without its lossy iteration stage.
    for row in _quote_rows(paths["quotes"], pins["quotes"][0], scope, counts):
        for cutoff, retained in windows.items():
            start = cutoff - timedelta(minutes=60)
            if start <= row.exchange_event_time <= cutoff:
                if len(retained) == 100000:
                    raise ValueError("window exceeds frozen pure sampler bound")
                retained.append(row)
    feed_audits = {}
    for kind, iterator in (("derivative_ticker", iter_derivative_tickers),
                           ("book_snapshot_25", iter_books)):
        diagnostics = new_diagnostics(kind, paths[kind], pins[kind][0])
        for row in iterator(paths[kind], symbol="SOLUSDT", source_sha256=pins[kind][0],
                            diagnostics=diagnostics):
            if row.event_time.date().isoformat() != "2024-10-01":
                raise ValueError("feed outside frozen diagnostic day")
        audit = asdict(diagnostics)
        feed_audits[kind] = {k: v for k, v in audit.items() if not k.startswith("_") and k != "path"}
        if pins[kind][1] is not None and diagnostics.rows_seen != pins[kind][1]:
            raise ValueError(f"{kind} original row count mismatch")
    if pins["quotes"][1] is not None and counts["raw_quote_rows"] != pins["quotes"][1]:
        raise ValueError("original quote count mismatch")
    # Detect any source mutation during full CRC/schema traversal.
    for kind, path in paths.items():
        verify_source(path, pins[kind][0])
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for cutoff, rows in windows.items():
        result = sample_bbo(rows, symbol="SOLUSDT", source_sha256=pins["quotes"][0],
                            source_class="RECONSTRUCTED_L2_QUOTE", scope=scope, cutoff=cutoff)
        owner = sample_bbo(rows, symbol="SOLUSDT", source_sha256=pins["quotes"][0],
                           source_class="RECONSTRUCTED_L2_QUOTE", scope=scope, cutoff=cutoff,
                           clock=SampleClockV2(availability_clock="OWNER_RECEIPT"))
        # Exact original rows, selected identities and machine exclusions remain
        # owner-local. gzip mtime=0 and no filename make evidence reproducible.
        payload = result.model_dump_json(indent=2).encode() + b"\n"
        name = f"provider-{cutoff:%H%M}.json.gz"
        (output / name).write_bytes(deterministic_gzip(payload))
        summaries.append({
            "cutoff": cutoff.isoformat(), "raw_window_rows": len(rows),
            "outside_window_rows": counts["raw_quote_rows"] - len(rows),
            "accepted_selected_rows": result.selected_count,
            "unselected_rows": len(rows) - result.selected_count,
            "invalid_rows": sum("REJECTED_INVALID_OBSERVATION" in r.reasons for r in result.rows),
            "slot_states": dict(Counter(s.state for s in result.slots)),
            "reasons": dict(Counter(reason for r in result.rows for reason in r.reasons)),
            "median_spread_fraction": str(result.median_spread_fraction) if result.median_spread_fraction is not None else None,
            "strict_v1_exact_intervals": result.strict_v1_exact_event_intervals,
            "strict_v1_spread_diagnostic_pass": result.strict_v1_spread_diagnostic_pass,
            "proposed_v2_provider_diagnostic_pass": result.proposed_spread_diagnostic_pass,
            "owner_receipt_selected_count": owner.selected_count,
            "event_age_microseconds": [s.event_age_microseconds for s in result.slots],
            "evidence": name, "evidence_uncompressed_sha256": sha256(payload).hexdigest(),
        })
    summary = {
        "result": "PROPOSED_C02_SAMPLE_CLOCK_V2_DIAGNOSTIC", "scope": scope,
        "original_one_day_empirical_acceptance": "PENDING_OWNER_RUN" if synthetic else "HASH_PINNED_DIAGNOSTIC_ONLY_REQUIRES_REVIEW",
        "source_route": "SOURCE_CONTRACT_PARTIAL_BUT_IMPLEMENTABLE",
        "production_c02_eligibility": "NOT_EVALUATED_UNCHANGED",
        "feed_audits": feed_audits, "quote_counts": dict(counts), "cutoffs": summaries,
        "source_hashes": {k: v[0] for k, v in pins.items()},
        "version_hash_semantics": "SHA256 of UTF-8 text normalized to LF; original source_hashes remain exact compressed bytes",
        "version_hashes": {p.relative_to(ROOT).as_posix(): sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest() for p in (
            ROOT / "src/astrabot/data/source_clock.py", Path(__file__),
            ROOT / "src/astrabot/data/historical_sources.py", ROOT / "src/astrabot/data/models.py",
            ROOT / "src/astrabot/contracts.py", ROOT / "requirements-test.txt",
            ROOT / "research/p3/S02_SOURCE_CONTRACT.json", ROOT / "research/p3/S02_SOURCE_ACCEPTANCE.json")},
    }
    (output / "S02_DIAGNOSTIC.json").write_text(canonical(summary), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--original-root", type=Path)
    source.add_argument("--synthetic-fixture", action="store_true")
    source.add_argument("--write-contract", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "work/s02-source")
    args = parser.parse_args()
    if args.write_contract:
        (ROOT / "research/p3/S02_SOURCE_CONTRACT.json").write_text(canonical(schema_contract()), encoding="utf-8")
    else:
        result = run(ROOT / "tests/fixtures/c05g" if args.synthetic_fixture else args.original_root,
                     args.output_dir, synthetic=args.synthetic_fixture)
        print(canonical({"result": result["result"], "scope": result["scope"],
                         "output": str(args.output_dir), "cutoffs": len(result["cutoffs"])}))


if __name__ == "__main__":
    main()
