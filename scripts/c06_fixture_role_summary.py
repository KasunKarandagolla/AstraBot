#!/usr/bin/env python3
"""Read-only News/Events and Journal summaries for the C06 synthetic fixture."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from astrabot.c06.role_summaries import summarize_fixture_journal, summarize_news_events
from astrabot.universe.eligibility import EventClearance
from c06_fixture_paths import prepare_synthetic_state_dir


def _json(payload) -> None:
    print(json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake-only", action="store_true",
        help="required confirmation that all News/Events examples are synthetic")
    sub = parser.add_subparsers(dest="command", required=True)
    news = sub.add_parser("news-events", help="summarize one synthetic evidence fixture")
    news.add_argument("--fixture", choices=("clear", "veto", "unknown", "unavailable"),
        default="clear")
    journal = sub.add_parser("journal", help="read verified persisted machine events and C01 state")
    journal.add_argument("--state-dir", type=Path, required=True)
    journal.add_argument("--lifecycle-id")
    args = parser.parse_args(argv)
    if not args.fake_only:
        parser.error("--fake-only is required; this command never reads live event feeds")
    try:
        if args.command == "news-events":
            fixture = args.fixture
            if fixture == "unavailable":
                summary = summarize_news_events(None, unavailable_reason="synthetic fixture unavailable")
            else:
                state = "CLEAR" if fixture == "clear" else "VETO" if fixture == "veto" else "UNKNOWN"
                verified = fixture in {"clear", "veto"}
                summary = summarize_news_events(EventClearance(state=state,
                    verification_state="VERIFIED" if verified else "UNVERIFIED",
                    as_of=datetime(2025, 2, 1, 8, 5, tzinfo=timezone.utc),
                    source_ids=("synthetic-event-clearance-fixture",) if verified else (),
                    reason="fixture veto" if fixture == "veto" else None))
            _json(summary)
        else:
            _json(summarize_fixture_journal(args.state_dir, lifecycle_id=args.lifecycle_id))
    except Exception as exc:
        parser.exit(2, f"C06 read-only role summary unavailable: {exc}\n")


if __name__ == "__main__":
    main()
