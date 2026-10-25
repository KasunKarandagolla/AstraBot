#!/usr/bin/env python3
"""Safely reset only known SQLite files in a marked C06 synthetic fixture."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from c06_fixture_paths import reset_synthetic_state_dir


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake-only", action="store_true",
        help="required confirmation that this is a synthetic C06 fixture")
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.fake_only:
        parser.error("--fake-only is required")
    try:
        path = reset_synthetic_state_dir(args.state_dir)
    except Exception as exc:
        parser.exit(2, f"C06 fixture reset refused: {exc}\n")
    print(json.dumps({"fixture": "SYNTHETIC_ONLY", "state_dir": str(path),
        "marker_retained": True, "known_sqlite_files_removed": True},
        sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
