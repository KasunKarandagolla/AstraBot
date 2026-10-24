"""Run the retained C02 archive panel through replay, features and scanner offline."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "research" / "c02_panel"


def csv_rows(name: str) -> list[dict[str, str]]:
    with (PANEL / name).open(newline="") as source:
        return list(csv.DictReader(source))


def run() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from astrabot.data.models import binance_usdm_instrument_id
    from astrabot.data.replay import normalize_agg_trades, normalize_klines
    from astrabot.features.providers import cvd, session_vwap, smc_structure
    from astrabot.universe.eligibility import SymbolData, scan_universe

    source_manifest = json.loads((PANEL / "manifest.json").read_text())
    entries = {item["file"]: item for item in source_manifest["records"]}
    for name, item in entries.items():
        actual = hashlib.sha256((PANEL / name).read_bytes()).hexdigest()
        if actual != item["retained_file_sha256"]:
            raise ValueError(f"panel checksum mismatch: {name}")

    btc_rows = csv_rows("BTCUSDT-1h-2024-10-28.csv")
    btc_raw = [[int(row["open_time"]), row["open"], row["high"], row["low"],
                row["close"], row["volume"], int(row["close_time"]),
                row["quote_volume"], int(row["count"]), row["taker_buy_volume"],
                row["taker_buy_quote_volume"], row["ignore"]]
               for row in btc_rows]
    btc_as_of = datetime(2024, 10, 29, 0, 10, 5, tzinfo=timezone.utc)
    btc_candles = normalize_klines(btc_raw, symbol="BTCUSDT", interval="1h", as_of=btc_as_of)

    ape_rows = csv_rows("APEUSDT-aggTrades-2024-10-18-first100.csv")
    ape_raw = [{
        "a": int(row["agg_trade_id"]), "p": row["price"], "q": row["quantity"],
        "f": int(row["first_trade_id"]), "l": int(row["last_trade_id"]),
        "T": int(row["transact_time"]),
        "m": row["is_buyer_maker"].lower() == "true", "M": True,
    } for row in ape_rows]
    ape_last_event = datetime.fromtimestamp(int(ape_rows[-1]["transact_time"]) / 1000,
                                             timezone.utc)
    ape_as_of = ape_last_event + timedelta(milliseconds=1)
    ape_trades = normalize_agg_trades(ape_raw, symbol="APEUSDT", as_of=ape_as_of)
    ape_cvd = cvd(ape_trades, as_of=ape_as_of, coverage_complete=True,
                  symbol="APEUSDT", instrument_id=binance_usdm_instrument_id("APEUSDT"),
                  stream_id="archive:APEUSDT:2024-10-18:first100")

    btc_iid = binance_usdm_instrument_id("BTCUSDT")
    vwap = session_vwap(btc_candles, as_of=btc_as_of, symbol="BTCUSDT",
                        instrument_id=btc_iid)
    structure = smc_structure(btc_candles, as_of=btc_as_of, symbol="BTCUSDT",
                              instrument_id=btc_iid)
    universe = scan_universe({
        "APEUSDT": SymbolData(),
        "BTCUSDT": SymbolData(candles_1h=btc_candles),
    }, btc_as_of, Decimal("10000"))
    def feature_summary(observation, payload_keys: tuple[str, ...]) -> dict:
        result = observation.model_dump(mode="json", exclude={"payload"})
        result["payload"] = {key: observation.payload.get(key) for key in payload_keys}
        return result

    return {
        "workflow": "offline_c02_archive_replay_v1",
        "manifest_version": source_manifest["manifest_version"],
        "normalization_version": source_manifest["normalization_version"],
        "source_records": {name: {
            key: item[key] for key in ("symbol", "feed", "coverage_start", "coverage_end",
                                       "record_count", "retained_file_sha256", "archive_sha256")
        } for name, item in entries.items()},
        "normalized_records": {"BTCUSDT_1h": len(btc_candles), "APEUSDT_aggTrades": len(ape_trades)},
        "features": {
            "A01_APE_CVD": feature_summary(ape_cvd, ("window_id", "reset_policy", "stream_id",
                                                       "first_trade_id", "last_trade_id")),
            "A02_BTC_UTC_VWAP": feature_summary(vwap, ("session_id", "anchor_id",
                                                         "expected_closed_bars", "observed_closed_bars",
                                                         "coverage_complete")),
            "A03_BTC_SMC": feature_summary(structure, ("prefix_causality", "candidate_sources")),
        },
        "universe": universe.model_dump(mode="json"),
        "interpretation": "The retained records reproduce normalization and A01; missing 5M, metadata and eligibility coverage remain explicitly non-ready.",
    }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
