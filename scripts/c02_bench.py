"""Offline bounded normalization/storage sample; no network access."""
from __future__ import annotations

import csv
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "research" / "c02_panel"
REPETITIONS = 200


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from astrabot.data.replay import normalize_agg_trades, normalize_klines

    with (PANEL / "BTCUSDT-1h-2024-10-28.csv").open(newline="") as source:
        candle_rows = list(csv.DictReader(source))
    with (PANEL / "APEUSDT-aggTrades-2024-10-18-first100.csv").open(newline="") as source:
        trade_rows = list(csv.DictReader(source))

    raw_candles = [[int(row["open_time"]), row["open"], row["high"], row["low"],
                    row["close"], row["volume"], int(row["close_time"]),
                    row["quote_volume"], int(row["count"]), row["taker_buy_volume"],
                    row["taker_buy_quote_volume"], row["ignore"]]
                   for row in candle_rows]
    raw_trades = [{
        "a": int(row["agg_trade_id"]), "p": row["price"], "q": row["quantity"],
        "f": int(row["first_trade_id"]), "l": int(row["last_trade_id"]),
        "T": int(row["transact_time"]),
        "m": row["is_buyer_maker"].lower() == "true", "M": True,
    } for row in trade_rows]
    as_of = datetime(2024, 10, 29, tzinfo=timezone.utc)
    candles = normalize_klines(raw_candles, symbol="BTCUSDT", interval="1h", as_of=as_of)
    trades = normalize_agg_trades(raw_trades, symbol="APEUSDT", as_of=as_of)

    normalized_json = json.dumps(
        [item.model_dump(mode="json") for item in (*candles, *trades)],
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    raw_bytes = sum((PANEL / name).stat().st_size for name in (
        "BTCUSDT-1h-2024-10-28.csv", "APEUSDT-aggTrades-2024-10-18-first100.csv"))

    start = time.perf_counter()
    for _ in range(REPETITIONS):
        normalize_klines(raw_candles, symbol="BTCUSDT", interval="1h", as_of=as_of)
        normalize_agg_trades(raw_trades, symbol="APEUSDT", as_of=as_of)
    elapsed = time.perf_counter() - start
    total_records = (len(raw_candles) + len(raw_trades)) * REPETITIONS
    print(json.dumps({
        "python": platform.python_version(),
        "fixture_records": len(candles) + len(trades),
        "repetitions": REPETITIONS,
        "records_processed": total_records,
        "elapsed_seconds": round(elapsed, 6),
        "records_per_second": round(total_records / elapsed, 1),
        "raw_fixture_bytes": raw_bytes,
        "one_normalized_json_panel_bytes": len(normalized_json),
        "scope": "bounded parser/model sample only; no network, archive expansion, storage index, or production extrapolation",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
