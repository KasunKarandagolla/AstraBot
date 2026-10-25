"""Acquire one bounded batch of the declared public Binance USDⓈ-M kline plan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astrabot.data.public_archive import (  # noqa: E402
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_TOTAL_BYTES,
    ArchiveError,
    acquire_phase,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("smoke", "pilot"), required=True)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Small manifest path inside the repository")
    parser.add_argument("--batch-size", type=int, default=7,
                        help="Archives per invocation (maximum 7); pilot defaults to one symbol cohort per interval/month")
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    args = parser.parse_args()
    try:
        manifest = acquire_phase(args.phase, repo_root=ROOT,
            manifest_path=(ROOT / args.manifest if not args.manifest.is_absolute() else args.manifest),
            max_total_bytes=args.max_total_bytes, max_file_bytes=args.max_file_bytes,
            batch_size=args.batch_size)
    except ArchiveError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    completed = len(manifest.get("archives", []))
    planned = int(manifest["archive_count_planned"])
    print(json.dumps({"phase": args.phase, "archives_completed": completed,
        "archives_planned": planned, "total_actual_bytes": manifest.get("total_actual_bytes", 0),
        "manifest_path": str(args.manifest)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
