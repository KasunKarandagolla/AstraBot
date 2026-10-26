"""Regenerate the tiny, deterministic synthetic gzip feeds used by C05-G tests."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from astrabot.data.historical_sources import BOOK_HEADER, DERIVATIVE_HEADER, QUOTE_HEADER

OUTPUT = Path(__file__).resolve().parent
DATE = "2024-10-01"
SYMBOL = "SOLUSDT"
BASE = datetime(2024, 10, 1, tzinfo=timezone.utc)


def epoch_us(value: datetime) -> str:
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return str(delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds)


def write_gzip_csv(path: Path, header: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=header, lineterminator="\n", extrasaction="raise")
                writer.writeheader()
                writer.writerows(rows)


quote_rows: list[dict[str, str]] = []
for minute in range(1, 61):
    endpoint = BASE + timedelta(minutes=minute)
    event = endpoint - timedelta(milliseconds=250 + (minute % 7) * 50)
    arrival = event + timedelta(milliseconds=3 + minute % 4)
    mid = 100 + minute / 100
    quote_rows.append({
        "exchange": "binance-futures", "symbol": SYMBOL,
        "timestamp": epoch_us(event), "local_timestamp": epoch_us(arrival),
        "ask_amount": "12.5", "ask_price": f"{mid + 0.01:.4f}",
        "bid_price": f"{mid - 0.01:.4f}", "bid_amount": "11.5",
    })
# An exact duplicate must be detected and discarded, not counted twice.
quote_rows.append(dict(quote_rows[-1]))
# Event precedes the decision while provider arrival follows it: causally late.
late_event = BASE + timedelta(hours=1) - timedelta(milliseconds=100)
late_arrival = BASE + timedelta(hours=1, milliseconds=500)
quote_rows.append({
    "exchange": "binance-futures", "symbol": SYMBOL,
    "timestamp": epoch_us(late_event), "local_timestamp": epoch_us(late_arrival),
    "ask_amount": "13", "ask_price": "100.63", "bid_price": "100.61", "bid_amount": "12",
})
# A future event/arrival pair is present in the file and must not leak backward.
future_event = BASE + timedelta(hours=1, seconds=1)
quote_rows.append({
    "exchange": "binance-futures", "symbol": SYMBOL,
    "timestamp": epoch_us(future_event), "local_timestamp": epoch_us(future_event + timedelta(milliseconds=3)),
    "ask_amount": "13", "ask_price": "100.64", "bid_price": "100.62", "bid_amount": "12",
})


def derivative_row(event: datetime, arrival: datetime, oi: str, *, price: str = "100.5") -> dict[str, str]:
    funding_at = BASE + timedelta(hours=8)
    return {
        "exchange": "binance-futures", "symbol": SYMBOL,
        "timestamp": epoch_us(event), "local_timestamp": epoch_us(arrival),
        "funding_timestamp": epoch_us(funding_at), "funding_rate": "0.0001",
        "predicted_funding_rate": "", "open_interest": oi,
        "last_price": price, "index_price": "100.45", "mark_price": price,
    }


derivative_rows = [
    derivative_row(BASE + timedelta(minutes=59, seconds=58), BASE + timedelta(minutes=59, seconds=58, milliseconds=100), "1000"),
    # Exchange timestamp tie with later arrival: stable selection must prefer this row.
    derivative_row(BASE + timedelta(minutes=59, seconds=58), BASE + timedelta(minutes=59, seconds=58, milliseconds=200), "1000", price="100.6"),
    derivative_row(BASE + timedelta(minutes=59, seconds=59), BASE + timedelta(minutes=59, seconds=59, milliseconds=200), "1000"),
    derivative_row(BASE + timedelta(minutes=59, seconds=59, milliseconds=500), BASE + timedelta(hours=1, milliseconds=500), "999"),
]


def book_row(event: datetime, arrival: datetime, shift: str = "0") -> dict[str, str]:
    result = {
        "exchange": "binance-futures", "symbol": SYMBOL,
        "timestamp": epoch_us(event), "local_timestamp": epoch_us(arrival),
    }
    for level in range(25):
        result[f"asks[{level}].price"] = str(Decimal("100.01") + Decimal(shift) + Decimal(level) / 100)
        result[f"asks[{level}].amount"] = str(Decimal(2) + Decimal(level) / 10)
        result[f"bids[{level}].price"] = str(Decimal("99.99") + Decimal(shift) - Decimal(level) / 100)
        result[f"bids[{level}].amount"] = str(Decimal(3) + Decimal(level) / 10)
    return result


book_rows = [
    book_row(BASE + timedelta(minutes=59, seconds=40), BASE + timedelta(minutes=59, seconds=40, milliseconds=2)),
    book_row(BASE + timedelta(minutes=59, seconds=59, milliseconds=500), BASE + timedelta(minutes=59, seconds=59, milliseconds=510)),
]

files = {
    "quotes": (f"binance-futures_quotes_{DATE}_{SYMBOL}.csv.gz", QUOTE_HEADER, quote_rows),
    "derivative_ticker": (f"binance-futures_derivative_ticker_{DATE}_{SYMBOL}.csv.gz", DERIVATIVE_HEADER, derivative_rows),
    "book_snapshot_25": (f"binance-futures_book_snapshot_25_{DATE}_{SYMBOL}.csv.gz", BOOK_HEADER, book_rows),
}
feed_manifest = {}
for name, (filename, header, rows) in files.items():
    path = OUTPUT / filename
    write_gzip_csv(path, header, rows)
    feed_manifest[name] = {"file": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

manifest = {
    "manifest_version": "c05g.historical-source-manifest.v1",
    "exchange": "binance-futures", "symbol": SYMBOL, "date": DATE,
    "synthetic": True, "feeds": feed_manifest,
}
(OUTPUT / "manifest.json").write_text(
    json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps({"fixture_dir": str(OUTPUT), "rows": {key: len(value[2]) for key, value in files.items()}, "manifest": manifest}, indent=2))
