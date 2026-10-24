"""Replay the small checksummed Binance archive panel without network access."""
import csv
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from astrabot.data.binance import BinancePublic
from astrabot.data.replay import candle_quality, normalize_agg_trades, normalize_klines
from astrabot.features.providers import cvd
from scripts.c02_replay import run as run_offline_workflow

PANEL = Path(__file__).parents[1] / "research" / "c02_panel"


def _rows(name):
    with (PANEL / name).open(newline="") as source:
        return list(csv.DictReader(source))


def test_actual_archive_manifest_and_replay_are_checksummed_and_deterministic():
    manifest = json.loads((PANEL / "manifest.json").read_text())
    entries = {row["file"]: row for row in manifest["records"]}
    assert entries["BTCUSDT-1h-2024-10-28.csv"]["synthetic"] is False
    assert entries["APEUSDT-aggTrades-2024-10-18-first100.csv"]["fidelity"] == "TRADE_AGG"

    for filename, entry in entries.items():
        actual = hashlib.sha256((PANEL / filename).read_bytes()).hexdigest()
        assert actual == entry["retained_file_sha256"]

    rows = _rows("BTCUSDT-1h-2024-10-28.csv")
    raw = [[
        int(r["open_time"]), r["open"], r["high"], r["low"], r["close"],
        r["volume"], int(r["close_time"]), r["quote_volume"], int(r["count"]),
        r["taker_buy_volume"], r["taker_buy_quote_volume"], r["ignore"],
    ] for r in rows]
    cutoff = datetime(2024, 10, 29, tzinfo=timezone.utc)
    first = normalize_klines(raw, symbol="BTCUSDT", interval="1h", as_of=cutoff)
    again = normalize_klines(raw, symbol="BTCUSDT", interval="1h", as_of=cutoff)
    assert len(first) == 24
    assert first == again
    assert candle_quality(first) == ()
    assert first[-1].available_at == cutoff


def test_real_aggregate_trade_window_has_golden_delta_and_truthful_scope():
    rows = _rows("APEUSDT-aggTrades-2024-10-18-first100.csv")
    raw = [{
        "a": int(r["agg_trade_id"]), "p": r["price"], "q": r["quantity"],
        "f": int(r["first_trade_id"]), "l": int(r["last_trade_id"]),
        "T": int(r["transact_time"]), "m": r["is_buyer_maker"].lower() == "true",
        "M": True,
    } for r in rows]
    event_cutoff = datetime.fromtimestamp(int(rows[-1]["transact_time"]) / 1000,
                                          timezone.utc)
    as_of = event_cutoff + timedelta(milliseconds=1)
    trades = normalize_agg_trades(raw, symbol="APEUSDT", as_of=as_of)
    repeated = normalize_agg_trades(raw, symbol="APEUSDT", as_of=as_of)
    assert len(trades) == 100
    assert trades == repeated
    assert trades[0].aggregate_trade_id == "171927517"
    assert trades[-1].aggregate_trade_id == "171927616"
    assert trades[0].aggressor_side == "BUY"
    assert trades[-1].aggressor_side == "BUY"

    result = cvd(trades, as_of=as_of, coverage_complete=True, symbol="APEUSDT",
                 instrument_id=trades[0].instrument_id)
    assert result.value == -81967
    assert result.fidelity == "TRADE_AGG"
    assert result.readiness == "READY"
    assert result.payload["trade_ids"][0] == "171927517"
    assert result.payload["aggregate_trade_ids"] == [str(i) for i in range(171927517, 171927617)]


def test_complete_offline_replay_reports_missing_coverage_without_fabrication():
    result = run_offline_workflow()
    assert result["normalized_records"] == {"BTCUSDT_1h": 24, "APEUSDT_aggTrades": 100}
    assert result["features"]["A01_APE_CVD"]["value"] == "-81967.0"
    assert result["features"]["A02_BTC_UTC_VWAP"]["readiness"] == "WARMING"
    assert result["features"]["A02_BTC_UTC_VWAP"]["value"] is None
    assert result["features"]["A03_BTC_SMC"]["readiness"] == "UNAVAILABLE"
    assert result["universe"]["shortlist"] == []
    assert [row["symbol"] for row in result["universe"]["considered"]] == ["APEUSDT", "BTCUSDT"]
