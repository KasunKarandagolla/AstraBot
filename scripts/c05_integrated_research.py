"""Run the integrated strict C05 economic research decision packet offline."""
from __future__ import annotations

import argparse
import gzip
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astrabot.research.integrated import build_packet, evaluation_times, render_packet
from astrabot.research.replay import load_c02_panel, load_public_um_archive_panel
from c05_historical_research import load_snapshots, parse_utc, _diagnostic_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "research/c04/historical_manifest.json")
    parser.add_argument("--data-root", type=Path, default=os.environ.get("ASTRABOT_DATA_ROOT"))
    parser.add_argument("--c02-panel", type=Path, help="alternative retained C02 panel directory")
    parser.add_argument("--start", type=parse_utc, default=parse_utc("2024-10-01T00:00:00Z"))
    parser.add_argument("--end", type=parse_utc, default=parse_utc("2024-10-02T00:00:00Z"))
    parser.add_argument("--interval", choices=("5m", "15m", "1h", "4h"), default="5m")
    parser.add_argument("--feed-data-root", type=Path, help="local owner original G feed directory; never downloaded")
    parser.add_argument("--source-manifest", type=Path, help="existing C05-G source manifest")
    parser.add_argument("--symbol", default="SOLUSDT")
    parser.add_argument("--date", default="2024-10-01")
    parser.add_argument("--evidence-manifest", type=Path, help="existing C05-H manifest, with local pinned artifacts")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/c05")
    args = parser.parse_args()
    try:
        if args.end <= args.start:
            raise ValueError("end must follow start")
        if args.c02_panel:
            panel = load_c02_panel(args.c02_panel)
        elif args.data_root:
            panel = load_public_um_archive_panel(args.manifest, args.data_root)
        else:
            raise ValueError("--data-root or ASTRABOT_DATA_ROOT must identify retained external C04 archives")
        if (args.source_manifest or args.evidence_manifest) and not args.feed_data_root:
            raise ValueError("--feed-data-root is required to consume original-feed/evidence manifests")
        snapshots = ()
        provenance = None
        if args.feed_data_root:
            times = evaluation_times(panel, start=args.start, end=args.end, interval=args.interval)
            if not times:
                raise ValueError("no historical candle evaluation times in scope")
            feed_args = argparse.Namespace(data_root=args.feed_data_root, symbol=args.symbol, date=args.date,
                source_manifest=args.source_manifest, evidence_manifest=args.evidence_manifest,
                decision_time=[t.isoformat() for t in times])
            (manifest, synthetic, hashes, decisions, diagnostics, evidence, freshness, snapshots) = load_snapshots(feed_args)
            provenance = {"source_manifest": manifest, "synthetic": synthetic, "source_sha256": hashes,
                "evidence_manifest_sha256": evidence.manifest_sha256 if evidence else None,
                "evidence_manifest": evidence.manifest.model_dump(mode="json") if evidence else None,
                "feeds": [_diagnostic_summary(d) for d in diagnostics.values()],
                "cutoff_policy": "exact candle evaluation cutoffs; no converted snapshot forward-fill"}
        packet = build_packet(panel, replay_start=args.start, replay_end=args.end,
            evaluation_interval=args.interval, snapshots=snapshots, feed_provenance=provenance)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.output_dir / "C05_J_DECISION_PACKET.json"
        json_path.write_text(
            json.dumps(packet, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        # Retain the full audit ledger without a large generated Git diff.
        with (args.output_dir / "C05_J_DECISION_PACKET.json.gz").open("wb") as output:
            with gzip.GzipFile(fileobj=output, filename="", mode="wb", mtime=0) as compressed:
                compressed.write(json_path.read_bytes())
        (args.output_dir / "C05_J_DECISION_PACKET.md").write_text(render_packet(packet), encoding="utf-8")
        print(json.dumps({"decision": packet["decision"], "packet_sha256": packet["packet_sha256"],
            "normalized_rows": packet["provenance"]["normalized_historical_rows"],
            "funnel": {k: packet["funnel"][k] for k in ("symbol_evaluation_windows",
                "eligible_symbol_windows", "strict_candidate_decisions", "price_only_formations")},
            "output_directory": str(args.output_dir)}, sort_keys=True))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
