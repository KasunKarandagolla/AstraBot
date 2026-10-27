"""Run the integrated strict C05 economic research decision packet offline."""
from __future__ import annotations

import argparse
from datetime import timedelta
import gzip
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astrabot.research.integrated import build_packet, evaluation_times, render_packet
from astrabot.research.replay import load_c02_panel, load_public_um_archive_panel
from astrabot.data.models import config_hash
from c05_historical_research import load_snapshots, parse_utc, _diagnostic_summary


def _save_operator(report, directory):
    from astrabot.c06.research_operator import owner_summary
    directory.mkdir(parents=True, exist_ok=True)
    report['content_sha256'] = config_hash(report)
    encoded = (json.dumps(report, sort_keys=True, indent=2)+'\n').encode()
    (directory/'OPERATOR_PACKET.json').write_bytes(encoded)
    with (directory/'OPERATOR_PACKET.json.gz').open('wb') as output:
        with gzip.GzipFile(fileobj=output, filename='', mode='wb', mtime=0) as compressed:
            compressed.write(encoded)
    (directory/'OWNER_SUMMARY.md').write_text(owner_summary(report))
    (directory/'EVENTS.jsonl').write_text(''.join(json.dumps(event, sort_keys=True)+'\n'
        for event in report['journal']['events']))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('authentic', 'synthetic'),
        help='RC1 operator workflow; omitted retains the original C05 research CLI')
    parser.add_argument("--manifest", type=Path, default=ROOT / "research/c04/historical_manifest.json")
    parser.add_argument("--data-root", type=Path, default=os.environ.get("ASTRABOT_DATA_ROOT"))
    parser.add_argument("--c02-panel", type=Path, help="alternative retained C02 panel directory")
    parser.add_argument("--start", type=parse_utc)
    parser.add_argument("--end", type=parse_utc)
    parser.add_argument("--interval", choices=("5m", "15m", "1h", "4h"))
    parser.add_argument("--feed-data-root", type=Path, help="local owner original G feed directory; never downloaded")
    parser.add_argument("--source-manifest", type=Path, help="existing C05-G source manifest")
    parser.add_argument("--symbol", default="SOLUSDT")
    parser.add_argument("--date", default="2024-10-01")
    parser.add_argument("--evidence-manifest", type=Path, help="existing C05-H manifest, with local pinned artifacts")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        args.output_dir = args.output_dir or (ROOT/'work/research-mvp' if args.mode else ROOT/'research/c05')
        if args.mode == 'synthetic':
            if any((args.data_root, args.c02_panel, args.feed_data_root, args.source_manifest,
                    args.evidence_manifest, args.start, args.end, args.interval)):
                raise ValueError('synthetic mode cannot consume historical inputs or scope flags')
            from rc1_synthetic import run_synthetic
            directory = args.output_dir/'synthetic'
            report = run_synthetic(directory/'state')
            _save_operator(report, directory)
            print(json.dumps({'run_id': report['run_id'], 'evidence_class': 'SYNTHETIC_ONLY',
                'scenarios': list(report['scenarios']), 'output_directory': str(directory)}))
            return 0
        if args.mode == 'authentic' and not args.data_root and not args.c02_panel:
            args.c02_panel = ROOT/'research/c02_panel'
        if args.c02_panel:
            panel = load_c02_panel(args.c02_panel)
        elif args.data_root:
            if args.mode == 'authentic':
                # PR #28's source bound is now independently merged at 2f2ea0b.
                # Open only source months needed by the explicit operator scope.
                end = args.end or (args.start or parse_utc('2024-09-01T00:00:00Z'))+timedelta(days=1)
                last_month = (end-timedelta(microseconds=1)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0)
                source_end = (last_month+timedelta(days=32)).replace(day=1)
                panel = load_public_um_archive_panel(args.manifest, args.data_root,
                    source_end_exclusive=source_end)
            else:
                panel = load_public_um_archive_panel(args.manifest, args.data_root)
        else:
            raise ValueError("--data-root or ASTRABOT_DATA_ROOT must identify retained external C04 archives")
        args.interval = args.interval or ('1h' if args.mode == 'authentic' else '5m')
        if args.mode == 'authentic':
            if panel.source_manifest.get('evidence_class', '').startswith('SYNTHETIC') or any(
                    r.get('synthetic') for r in panel.source_manifest.get('records', [])):
                raise ValueError('authentic mode refuses synthetic source manifests')
            times = evaluation_times(panel, start=None, end=None, interval=args.interval)
            if not times:
                raise ValueError('no source-backed candle cutoffs in the requested interval')
            # Archive mode defaults to one bounded development day; retained
            # C02 mode defaults to the full tiny authentic normalization sample.
            args.start = args.start or (times[0] if args.c02_panel else parse_utc('2024-09-01T00:00:00Z'))
            args.end = args.end or (times[-1]+timedelta(seconds=1) if args.c02_panel
                                   else args.start+timedelta(days=1))
            maximum = {'5m': 288, '15m': 96, '1h': 24, '4h': 6}[args.interval]
            if len(evaluation_times(panel, start=args.start, end=args.end, interval=args.interval)) > maximum:
                raise ValueError('RC1 operator scope is bounded to at most one day; use original C05 CLI for longer research')
            args.output_dir = args.output_dir/'authentic'
        else:
            args.start = args.start or parse_utc('2024-10-01T00:00:00Z')
            args.end = args.end or parse_utc('2024-10-02T00:00:00Z')
        if args.end <= args.start:
            raise ValueError("end must follow start")
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
            if args.mode == 'authentic' and synthetic:
                raise ValueError('authentic mode refuses synthetic original-feed fixtures')
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
        if args.mode == 'authentic':
            from astrabot.c06.research_operator import present_historical
            from astrabot.research.integrated import attach_snapshots
            operator_panel = attach_snapshots(panel, snapshots, feed_provenance=provenance) if snapshots else panel
            at = evaluation_times(panel, start=args.start, end=args.end, interval=args.interval)[-1]
            report, operator_snapshots = present_historical(operator_panel, packet, at=at)
            for symbol, snapshot in operator_snapshots.items():
                (args.output_dir/f'{symbol}_MCP_SNAPSHOT.json').write_text(json.dumps(snapshot, sort_keys=True, indent=2)+'\n')
            _save_operator(report, args.output_dir)
        print(json.dumps({"decision": report['decision'] if args.mode else packet["decision"],
            **({'status': report['status'], 'run_id': report['run_id'],
                'economic_verdict': packet['decision']} if args.mode else {}),
            "packet_sha256": packet["packet_sha256"],
            "normalized_rows": packet["provenance"]["normalized_historical_rows"],
            "funnel": {k: packet["funnel"][k] for k in ("symbol_evaluation_windows",
                "eligible_symbol_windows", "strict_candidate_decisions", "price_only_formations")},
            "output_directory": str(args.output_dir)}, sort_keys=True))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
