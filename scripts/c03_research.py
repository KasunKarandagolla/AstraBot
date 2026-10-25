"""Run the deterministic synthetic T1 vertical slice and an economic rejection."""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from astrabot.research.demo import START, IID, SYMBOL, account, candle, costs, market, roll_market
from astrabot.research.engine import evaluate
from astrabot.research.context import evaluate_context
from astrabot.data.models import config_hash
from astrabot.data.models import binance_usdm_instrument_id
from astrabot.data.replay import normalize_klines
from astrabot.universe.eligibility import SymbolData


def run():
    formed_at = START+timedelta(seconds=5)
    args = dict(symbol=SYMBOL, instrument_id=IID, requested_quantity=Decimal("10"),
                strategies=("T1",), sides=("LONG",))
    original = market(formed_at)
    formation = evaluate(original, as_of=formed_at, account=account(formed_at), profile=costs(), **args)
    confirmed_at = START+timedelta(minutes=5, seconds=5)
    bar = candle(START, open="99.9", high="100.5", low="99.8", close="100.4")
    data = roll_market(original, confirmed_at, extra=(bar,))
    positive = evaluate(data, as_of=confirmed_at, account=account(confirmed_at), profile=costs(),
                        state=formation.state, **args)
    negative = evaluate(data, as_of=confirmed_at, account=account(confirmed_at), profile=costs(expensive=True),
                        state=formation.state, **args)
    return {"evidence_class": "SYNTHETIC_TEST_FIXTURE",
            "input_manifest": {"generator": "astrabot.research.demo:c03.golden.v1",
                "formation_snapshot_sha256": config_hash(original.model_dump(mode="json")),
                "confirmation_snapshot_sha256": config_hash(data.model_dump(mode="json")),
                "positive_cost_assumption": costs().model_dump(mode="json"),
                "negative_cost_assumption": costs(expensive=True).model_dump(mode="json"),
                "formation_bars": [b.model_dump(mode="json") for b in original.candles_5m[-3:]],
                "confirmation_bar": bar.model_dump(mode="json")},
            "context": evaluate_context(original, symbol=SYMBOL, instrument_id=IID, as_of=formed_at).model_dump(mode="json"),
            "formation": formation.model_dump(mode="json"),
            "positive": positive.model_dump(mode="json"), "negative": negative.model_dump(mode="json")}


def summarize(trace):
    ctx = trace["context"]
    return {"evidence_class": trace["evidence_class"], "input_manifest": trace["input_manifest"],
        "context": {k: ctx[k] for k in ("context_id", "version", "as_of", "classification", "bias",
            "adx_1h", "atr_1h", "atr_5m", "atr_15m", "normalized_slope", "atr_percentile", "rvol_15m",
            "indicator_source", "threshold_status")},
        "chronology": [trace[k]["state"]["setups"][0]["snapshot"] for k in ("formation", "positive")],
        "opposing_levels_at_formation": trace["formation"]["state"]["setups"][0]["opposing_at_formation"],
        "positive": trace["positive"]["emitted"][0], "negative": trace["negative"]["emitted"][0]}


def c02_no_trade():
    panel = Path(__file__).resolve().parents[1]/"research/c02_panel"
    manifest = json.loads((panel/"manifest.json").read_text())
    entry = next(x for x in manifest["records"] if x["feed"] == "klines:1h")
    retained = panel/entry["file"]
    checksum = hashlib.sha256(retained.read_bytes()).hexdigest()
    if checksum != entry["retained_file_sha256"]:
        raise ValueError("C02 retained archive checksum mismatch")
    with retained.open(newline="") as source:
        rows = list(csv.DictReader(source))
    raw = [[int(r["open_time"]), r["open"], r["high"], r["low"], r["close"], r["volume"],
            int(r["close_time"]), r["quote_volume"], int(r["count"]), r["taker_buy_volume"],
            r["taker_buy_quote_volume"], r["ignore"]] for r in rows]
    at = datetime(2024, 10, 29, 0, 10, 5, tzinfo=timezone.utc)
    candles = normalize_klines(raw, symbol="BTCUSDT", interval="1h", as_of=at)
    result = evaluate(SymbolData(candles_1h=candles), symbol="BTCUSDT",
        instrument_id=binance_usdm_instrument_id("BTCUSDT"), as_of=at, account=account(at),
        profile=costs(), requested_quantity=Decimal(10), sides=("LONG",))
    return {"evidence_class": "OBSERVED_HISTORICAL_FACT_INPUTS_INCOMPLETE",
        "source_url": entry["source_url"], "retained_file_sha256": checksum,
        "candle_count": len(candles), "availability_assumption": entry["availability_assumption"],
        "overlay": "Explicit synthetic account/cost assumptions; no fabricated missing market feeds",
        "decisions": [d.model_dump(mode="json") for d in result.emitted]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true", help="print the compact inspectable golden trace")
    parser.add_argument("--check", action="store_true", help="compare against the committed frozen trace")
    parser.add_argument("--c02-panel", action="store_true", help="show truthful NO_TRADE on the actual incomplete C02 archive")
    args = parser.parse_args()
    if args.c02_panel:
        result = c02_no_trade()
        if args.check and (result["candle_count"] != 24 or len(result["decisions"]) != 3
                or any(d["decision"] != "NO_TRADE" for d in result["decisions"])):
            raise SystemExit("C03 incomplete archive NO_TRADE gate failed")
        print(json.dumps(result, sort_keys=True, indent=2))
        raise SystemExit(0)
    trace = run()
    summary = summarize(trace)
    if args.check:
        golden = Path(__file__).resolve().parents[1]/"research/c03/golden_trace.json"
        if json.loads(golden.read_text()) != summary:
            raise SystemExit("C03 golden research trace differs; inspect chronology, geometry and costs")
        if summary["positive"]["decision"] != "RESEARCH_CANDIDATE" or summary["negative"]["decision"] != "NO_TRADE":
            raise SystemExit("C03 expected positive/negative decision gate failed")
    print(json.dumps(summary if args.summary else trace, sort_keys=True, indent=2))
