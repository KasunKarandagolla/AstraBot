"""Explicit synthetic golden market, never a historical market/backtest claim."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from astrabot.data.models import (
    Candle, DepthLevel, DepthSnapshot, InstrumentFilter, InstrumentMetadata,
    OpenInterestObservation, SpreadSample, Ticker24h, binance_usdm_instrument_id,
)
from astrabot.research.models import CostProfile, ResearchAccount
from astrabot.universe.eligibility import EventClearance, SymbolData

SYMBOL = "ALTUSDT"
IID = binance_usdm_instrument_id(SYMBOL)
START = datetime(2025, 2, 1, 8, tzinfo=timezone.utc)
STEPS = {"5m": timedelta(minutes=5), "15m": timedelta(minutes=15),
         "1h": timedelta(hours=1), "4h": timedelta(hours=4)}


def observation(model, at, **fields):
    return model(symbol=SYMBOL, instrument_id=IID, event_time=at, available_at=at,
        ingested_at=at, as_of=at, data_source="C03_SYNTHETIC_FIXTURE",
        source_version="c03.golden.v1", units="USDT_PER_BASE", fidelity="SYNTHETIC_FIXTURE",
        readiness="READY", observation_id=f"{model.__name__}:{at.isoformat()}",
        config_hash="c03.golden.v1", **fields)


def candle(at, *, interval="5m", open="100", high="100.2", low="99.8", close="100", volume="100"):
    end = at+STEPS[interval]-timedelta(milliseconds=1)
    return Candle(symbol=SYMBOL, instrument_id=IID, event_time=end,
        available_at=end+timedelta(milliseconds=1), ingested_at=end+timedelta(milliseconds=1),
        as_of=end+timedelta(milliseconds=1), data_source="C03_SYNTHETIC_FIXTURE",
        source_version="c03.golden.v1", units="USDT_PER_BASE", fidelity="SYNTHETIC_FIXTURE",
        readiness="READY", observation_id=f"bar:{interval}:{at.isoformat()}", config_hash="c03.golden.v1",
        interval=interval, open_time=at, close_time=end, open=D(open), high=D(high), low=D(low), close=D(close),
        base_volume=D(volume), quote_volume=D(volume)*D(close), trade_count=10, is_closed=True,
        source_record_id=f"fixture:{interval}:{at.isoformat()}")


def account(at):
    return ResearchAccount(source_id="SYNTHETIC_ACCOUNT_ONLY", as_of=at, equity_usdt="10000",
        pending_open_risk_usdt="0", pending_open_notional_usdt="0", isolated_margin_available_usdt="10000",
        occupied_slots=0, reconciled=True, daily_entry_halt=False)


def costs(*, expensive=False):
    return CostProfile(version="c03.synthetic-cost.v1", evidence_ids=("SYNTHETIC_ASSUMPTION_NOT_VALIDATED",),
        entry_fee_rate=".0001" if not expensive else ".05", ordinary_exit_fee_rate=".0001",
        stop_exit_fee_rate=".0001", ordinary_exit_spread_per_unit=".001",
        ordinary_exit_slippage_per_unit=".001", stop_spread_per_unit=".002",
        stop_slippage_per_unit=".002", funding_per_unit=".001")


def market(at=START+timedelta(seconds=5), *, family="T1", side="LONG", extra=()):
    """Long fixture first; exact price reflection supplies symmetric shorts."""
    boundary = at.replace(second=0, microsecond=0)
    boundary -= timedelta(minutes=boundary.minute % 5)
    hourly_end = boundary.replace(minute=0)
    four_end = hourly_end.replace(hour=(hourly_end.hour//4)*4)
    fifteen_end = boundary-timedelta(minutes=boundary.minute % 15)
    hourly = []
    for i in range(760):
        t = hourly_end-timedelta(hours=760-i)
        center = D("20")+D(".1")*i
        half = D("5")-D(".005")*i
        h = center+half
        if i == 720:
            h = D("108")
        hourly.append(candle(t, interval="1h", open=str(center-D(".01")), close=str(center),
                             high=str(h), low=str(center-half)))
    if family == "R1":
        # Context-neutral bounded oscillations, repeated separated edge tests.
        hourly = []
        for i in range(760):
            t = hourly_end-timedelta(hours=760-i)
            center = D("100")+(D(".1") if i % 2 else D("-.1"))
            half = D("3") if i < 700 else D(".8")
            hi, lo = center+half, center-half
            if i % 6 == 0:
                hi = D("104")
            if i % 6 == 3:
                lo = D("96")
            hourly.append(candle(t, interval="1h", open=str(center), high=str(hi), low=str(lo), close=str(center)))
    four = tuple(candle(four_end-timedelta(hours=4*(200-i)), interval="4h",
        open=str(D("60")+D(".2")*i), high=str(D("61")+D(".2")*i),
        low=str(D("59")+D(".2")*i), close=str(D("60.1")+D(".2")*i)) for i in range(200))
    fifteen = tuple(candle(fifteen_end-timedelta(minutes=15*(40-i)), interval="15m",
        high="101", low="99", close="100") for i in range(40))
    midnight = boundary.replace(hour=0, minute=0)
    five = [candle(midnight+timedelta(minutes=5*i)) for i in range(int((boundary-midnight).total_seconds()/300))]
    if len(five) >= 3:
        five[-3] = candle(five[-3].open_time, open="100", high="100.1", low="99.6", close="99.9")
        five[-1] = candle(five[-1].open_time, open="100", high="100.1", low="99.8", close="99.9")
    by_open = {c.open_time: c for c in five}
    by_open.update({c.open_time: c for c in extra})
    five = tuple(by_open[t] for t in sorted(by_open))
    quote = five[-1].close if extra and five else D("100")
    metadata = observation(InstrumentMetadata, at-timedelta(seconds=5), base_asset="ALT",
        quote_asset="USDT", settle_asset="USDT", contract_type="PERPETUAL", status="TRADING",
        effective_from=at-timedelta(days=100), price_tick=".01", quantity_step=".001",
        minimum_quantity=".001", minimum_notional="5", contract_size="1",
        filters=(InstrumentFilter(filter_type="PRICE_FILTER", min_value=".01", max_value="100000", step_size=".01"),
                 InstrumentFilter(filter_type="LOT_SIZE", min_value=".001", max_value="100000", step_size=".001"),
                 InstrumentFilter(filter_type="MIN_NOTIONAL", min_value="5")))
    ticker = observation(Ticker24h, at, open="90", high="110", low="80", last=str(quote),
        base_volume="300000", quote_volume="30000000", trade_count=1000,
        window_start=at-timedelta(hours=24), window_end=at)
    samples = tuple(observation(SpreadSample, at-timedelta(minutes=59-i),
        bid_price=quote-D(".01"), ask_price=quote+D(".01"), bid_quantity="1000", ask_quantity="1000")
        for i in range(60))
    depth = observation(DepthSnapshot, at, bids=(DepthLevel(price=quote-D(".01"), quantity="100000"),),
        asks=(DepthLevel(price=quote+D(".01"), quantity="100000"),))
    oi = observation(OpenInterestObservation, at, open_interest="100000", quantity_unit="SYNTHETIC_USDT",
        open_interest_notional_usdt="6000000", unit_validated=True)
    result = SymbolData(metadata=metadata, ticker=ticker, candles_5m=five, candles_15m=fifteen,
        candles_1h=tuple(hourly), candles_4h=four, spread_samples=samples, depth=depth, open_interest=oi,
        event_clearance=EventClearance(state="CLEAR", verification_state="VERIFIED", as_of=at,
                                      source_ids=("SYNTHETIC_EVENT_CLEARANCE",)))
    return reflect(result) if side == "SHORT" else result


def roll_market(original, at, *, family="T1", extra=(), side="LONG"):
    """Append fixture observations while retaining every original closed bar."""
    fresh = market(at, family=family, extra=extra, side=side)
    changes = {}
    for name in ("candles_5m", "candles_15m", "candles_1h", "candles_4h"):
        previous = getattr(original, name)
        appended = tuple(c for c in getattr(fresh, name) if c.open_time > previous[-1].open_time)
        changes[name] = (*previous, *appended)
    return fresh.model_copy(update=changes)


def reflect(data):
    def flip_bar(c):
        return c.model_copy(update={"open": D(200)-c.open, "high": D(200)-c.low,
            "low": D(200)-c.high, "close": D(200)-c.close})
    changes = {name: tuple(flip_bar(c) for c in getattr(data, name))
               for name in ("candles_5m", "candles_15m", "candles_1h", "candles_4h")}
    changes["spread_samples"] = tuple(s.model_copy(update={"bid_price": D(200)-s.ask_price,
        "ask_price": D(200)-s.bid_price}) for s in data.spread_samples)
    changes["depth"] = data.depth.model_copy(update={
        "bids": tuple(DepthLevel(price=D(200)-x.price, quantity=x.quantity) for x in data.depth.asks),
        "asks": tuple(DepthLevel(price=D(200)-x.price, quantity=x.quantity) for x in data.depth.bids)})
    return data.model_copy(update=changes)
