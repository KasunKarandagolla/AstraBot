"""C03 S01/S02/S03 and source-wrapper qualification; synthetic price evidence."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import numpy as np
import pytest
import talib

from astrabot.data.models import Candle, SpreadSample, binance_usdm_instrument_id
from astrabot.research.context import (
    BALANCE_TERMS, BalanceEvidence, classify_metrics, evaluate_context, qualify_balance,
)
from astrabot.research.evidence import EvidenceError, INTERVALS, history
from astrabot.research.levels import confirmed_swings
from astrabot.universe.eligibility import SymbolData

T = datetime(2026, 10, 24, 12, 0, 5, tzinfo=timezone.utc)
SYMBOL = "ALTUSDT"
IID = binance_usdm_instrument_id(SYMBOL)


def bar(interval, opened, *, center=D(100), width=D(2), close=None, volume=D(1), suffix=""):
    ended = opened + timedelta(seconds=INTERVALS[interval]) - timedelta(milliseconds=1)
    close = center if close is None else close
    return Candle(
        symbol=SYMBOL, instrument_id=IID, interval=interval, open_time=opened,
        close_time=ended, open=center, high=max(center + width / 2, close),
        low=min(center - width / 2, close), close=close, base_volume=volume,
        trade_count=1, is_closed=True, source_record_id=f"{interval}:{opened.isoformat()}:{suffix}",
        observation_id=f"obs:{interval}:{opened.isoformat()}:{suffix}",
        event_time=ended, available_at=ended + timedelta(milliseconds=1),
        ingested_at=ended + timedelta(milliseconds=1), as_of=ended + timedelta(milliseconds=1),
        data_source="c03.synthetic", source_version="c03.fixture.v1", units="quote_per_base",
        fidelity="SYNTHETIC_FIXTURE", readiness="READY", config_hash="synthetic",
    )


def series(interval, count, *, step=D(0), as_of=T, start=D(100), shrinking=False):
    seconds = INTERVALS[interval]
    end = datetime.fromtimestamp(int(as_of.timestamp()) // seconds * seconds, timezone.utc)
    return tuple(bar(
        interval, end - timedelta(seconds=seconds * (count - i)),
        center=start + step * i,
        width=D(10) - D("0.01") * i if shrinking else D(2),
    ) for i in range(count))


def spread(*, width=D("0.02"), at=T):
    return SpreadSample(
        symbol=SYMBOL, instrument_id=IID, event_time=at, available_at=at,
        ingested_at=at, as_of=at, data_source="c03.synthetic",
        source_version="c03.fixture.v1", units="quote_per_base", fidelity="SYNTHETIC_FIXTURE",
        readiness="READY", observation_id="spread:" + at.isoformat(), config_hash="synthetic",
        bid_price=D(100) - width / 2, ask_price=D(100) + width / 2,
        bid_quantity=D(100), ask_quantity=D(100),
    )


def trend_data(side="LONG"):
    sign = D(1) if side == "LONG" else D(-1)
    start = D(100) if side == "LONG" else D(400)
    return SymbolData(
        candles_1h=series("1h", 735, step=sign * D("0.2"), start=start, shrinking=True),
        candles_4h=series("4h", 53, step=sign * D("0.5"), start=start),
        candles_15m=series("15m", 21), candles_5m=series("5m", 20),
        spread_samples=(spread(),),
    )


def evaluate(data, at=T):
    return evaluate_context(data, symbol=SYMBOL, instrument_id=IID, as_of=at)


@pytest.mark.parametrize("side,label,bias", [
    ("LONG", "TREND_UP", "BULLISH"), ("SHORT", "TREND_DOWN", "BEARISH"),
])
def test_context_real_library_direction_and_five_bar_slope(side, label, bias):
    data = trend_data(side)
    context = evaluate(data)
    assert context.classification == label
    assert context.bias == bias
    assert context.readiness == "READY"
    assert context.adx_1h == D(100)
    assert context.atr_percentile == 0
    assert abs(context.normalized_slope) >= D("0.15")
    sign = 1 if side == "LONG" else -1
    expected_ema = data.candles_1h[-1].close - sign * D("0.2") * D("24.5")
    assert abs(context.ema_1h - expected_ema) < D("0.000000001")
    assert context.source_ids and context.feature_refs
    assert context.threshold_status == "UNVALIDATED"


def test_s01_higher_timeframe_close_or_availability_cannot_advance_early():
    data = trend_data()
    delayed = data.candles_4h[-1].model_copy(update={"available_at": T + timedelta(seconds=1)})
    context = evaluate(data.model_copy(update={"candles_4h": (*data.candles_4h[:-1], delayed)}))
    assert context.classification == "UNKNOWN"
    assert context.reason_codes == ("MISSING_LATEST_CLOSED_4H",)
    forming = data.candles_4h[-1].model_copy(update={"is_closed": False})
    assert evaluate(data.model_copy(update={"candles_4h": (*data.candles_4h[:-1], forming)})).classification == "UNKNOWN"


def test_atr_percentile_needs_720_preceding_finite_observations_not_720_raw_bars():
    data = trend_data()
    context = evaluate(data.model_copy(update={"candles_1h": data.candles_1h[-720:]}))
    assert context.classification == "UNKNOWN"
    assert context.reason_codes == ("INSUFFICIENT_1H_HISTORY_735",)
    # TA-Lib's exercised first finite values establish the actual warm-up.
    high = np.arange(40, dtype=np.float64) + 101
    low, close = high - 2, high - 1
    atr = talib.ATR(high, low, close, timeperiod=14)
    adx = talib.ADX(high, low, close, timeperiod=14)
    assert np.flatnonzero(np.isfinite(atr))[0] == 14
    assert np.flatnonzero(np.isfinite(adx))[0] == 27
    assert atr[-1] == 2 and adx[-1] == 100


def test_s03_context_and_source_ids_are_invariant_to_unavailable_future_inputs():
    data = trend_data()
    future = {}
    for name in ("candles_1h", "candles_4h", "candles_15m", "candles_5m"):
        rows = getattr(data, name)
        next_bar = bar(rows[-1].interval, rows[-1].open_time + timedelta(
            seconds=INTERVALS[rows[-1].interval]), center=D(900))
        next_bar = next_bar.model_copy(update={"readiness": "UNAVAILABLE", "symbol": "FUTUREUSDT"})
        future[name] = (*rows, next_bar)
    assert evaluate(data).model_dump_json() == evaluate(data.model_copy(update=future)).model_dump_json()


@pytest.mark.parametrize("failure,reason", [
    ("gap", "GAP_1H"), ("duplicate", "DUPLICATE_1H"),
    ("order", "OUT_OF_ORDER_1H"), ("readiness", "NON_READY_OR_INVALID_1H"),
    ("identity", "INSTRUMENT_MISMATCH_1H"),
])
def test_available_bad_history_is_rejected_without_sorting_or_interpolation(failure, reason):
    rows = series("1h", 10)
    if failure == "gap":
        rows = (*rows[:4], *rows[5:])
    elif failure == "duplicate":
        rows = (*rows, rows[-1])
    elif failure == "order":
        rows = tuple(reversed(rows))
    elif failure == "readiness":
        rows = (*rows[:-1], rows[-1].model_copy(update={"readiness": "UNAVAILABLE"}))
    else:
        rows = (*rows[:-1], rows[-1].model_copy(update={"instrument_id": "WRONG"}))
    with pytest.raises(EvidenceError) as error:
        history(rows, interval="1h", symbol=SYMBOL, instrument_id=IID, as_of=T)
    assert error.value.code == reason


def test_s02_strict_swings_emit_only_after_third_right_confirmation_and_never_on_ties():
    rows = list(series("1h", 7))
    pivot = rows[3]
    rows[3] = pivot.model_copy(update={"high": D(105), "low": D(95)})
    before = rows[-1].available_at - timedelta(microseconds=1)
    assert confirmed_swings(rows, symbol=SYMBOL, instrument_id=IID, as_of=before) == ()
    levels = confirmed_swings(rows, symbol=SYMBOL, instrument_id=IID, as_of=rows[-1].available_at)
    assert {x.kind for x in levels} == {"SWING_HIGH", "SWING_LOW"}
    assert all(x.event_time == pivot.close_time and x.available_at == rows[-1].available_at for x in levels)
    assert all(x.source_ids == tuple(c.source_record_id for c in rows) for x in levels)
    tied = rows.copy()
    tied[5] = tied[5].model_copy(update={"high": D(105), "low": D(95)})
    assert confirmed_swings(tied, symbol=SYMBOL, instrument_id=IID, as_of=T) == ()


def test_s02_delayed_source_availability_is_not_backdated_to_confirmation_close():
    rows = list(series("1h", 7))
    rows[3] = rows[3].model_copy(update={"high": D(105)})
    delayed = rows[-1].available_at + timedelta(seconds=2)
    rows[-1] = rows[-1].model_copy(update={"available_at": delayed})
    assert confirmed_swings(rows, symbol=SYMBOL, instrument_id=IID, as_of=delayed-timedelta(microseconds=1)) == ()
    level = confirmed_swings(rows, symbol=SYMBOL, instrument_id=IID, as_of=delayed)[0]
    assert level.available_at == delayed
    future = bar("1h", rows[-1].open_time + timedelta(hours=1), center=D(200))
    assert confirmed_swings((*rows, future), symbol=SYMBOL, instrument_id=IID, as_of=delayed) == (level,)


def balance_rows():
    rows = list(series("1h", 21))
    # Two separated tests per edge; intervening closes balance around100.
    for i in (1, 12):
        rows[i] = rows[i].model_copy(update={"high": D(104), "low": D(100), "close": D(101)})
    for i in (5, 16):
        rows[i] = rows[i].model_copy(update={"high": D(100), "low": D(96), "close": D(99)})
    return tuple(rows)


def balance(rows, atr=D(2), spreads=None):
    return qualify_balance(rows, atr=atr, spread_samples=(spread(),) if spreads is None else spreads,
                           symbol=SYMBOL, instrument_id=IID, as_of=T)


def test_s09_balance_is_explicit_separated_edges_bounded_drift_and_width_hypothesis():
    rows = balance_rows()
    result = balance(rows)
    assert result.qualified
    assert result.high == 104 and result.low == 96 and result.midpoint == 100
    assert result.high_test_indices == (1, 12) and result.low_test_indices == (5, 16)
    assert result.width_atr == 4 and result.width_spreads == 400
    assert result.version == "c03.stable-balance.hypothesis.v1"
    assert BALANCE_TERMS["qualification"] == "UNVALIDATED_RESEARCH_HYPOTHESIS"
    # Latest closed hourly bar is deliberately excluded from original range.
    outside = (*rows[:-1], rows[-1].model_copy(update={"high": D(200), "low": D(1)}))
    assert balance(outside).model_dump_json() == result.model_dump_json()


@pytest.mark.parametrize("failure,reason", [
    ("single_edge_test", "BALANCE_SEPARATED_EDGE_TESTS_MISSING"),
    ("adjacent_tests", "BALANCE_SEPARATED_EDGE_TESTS_MISSING"),
    ("narrow", "BALANCE_WIDTH_ATR_OUT_OF_BOUNDS"),
    ("wide", "BALANCE_WIDTH_ATR_OUT_OF_BOUNDS"),
    ("drift", "BALANCE_DRIFT_TOO_LARGE"),
    ("spread", "BALANCE_WIDTH_CANNOT_CLEAR_SPREAD"),
    ("missing_spread", "BALANCE_SPREAD_UNAVAILABLE"),
])
def test_s09_invalid_stable_balance_is_not_a_touch_label(failure, reason):
    rows = list(balance_rows())
    atr, spreads = D(2), (spread(),)
    if failure == "single_edge_test":
        rows[12] = rows[12].model_copy(update={"high": D(101)})
    elif failure == "adjacent_tests":
        rows[2] = rows[2].model_copy(update={"high": D(104), "low": D(100)})
        rows[12] = rows[12].model_copy(update={"high": D(101)})
    elif failure == "narrow":
        atr = D(5)
    elif failure == "wide":
        atr = D("0.5")
    elif failure == "drift":
        for i in range(15, 20):
            rows[i] = rows[i].model_copy(update={"close": D(104), "high": D(104)})
    elif failure == "spread":
        spreads = (spread(width=D(1)),)
    else:
        spreads = ()
    result = balance(tuple(rows), atr, spreads)
    assert result.qualified is False and reason in result.reason_codes


@pytest.mark.parametrize("adx,expected", [(D("19.999"), "RANGE"), (D(20), "UNCLASSIFIED"),
                                         (D(22), "UNCLASSIFIED"), (D("24.999"), "UNCLASSIFIED"),
                                         (D(25), "TREND_UP")])
def test_adx_gap_is_unclassified_not_invented_hysteresis(adx, expected):
    assert classify_metrics(adx=adx, slope=D("0.15"), bias="BULLISH", percentile=D(94),
                            breakout=None, balance=balance(balance_rows())) == expected


def test_breakout_is_closed_event_using_preceding20_volume_and_formation_bias():
    data = trend_data()
    last = data.candles_15m[-1]
    breakout = last.model_copy(update={"high": D(111), "close": D(110), "base_volume": D("1.5")})
    data = data.model_copy(update={"candles_15m": (*data.candles_15m[:-1], breakout)})
    context = evaluate(data)
    assert context.classification == "BREAKOUT_EVENT"
    assert context.rvol_15m == D("1.5")
    assert context.breakout.side == "LONG" and context.breakout.boundary == D(101)
    assert context.breakout.event_time == last.close_time
    assert context.breakout.available_at == last.available_at
    assert context.breakout.atr_5m == D(2)
    assert last.source_record_id in context.breakout.source_ids
    # Wick-only high and volume below threshold do not create an event.
    wick = breakout.model_copy(update={"close": D(100)})
    thin = breakout.model_copy(update={"base_volume": D("1.499")})
    assert evaluate(data.model_copy(update={"candles_15m": (*data.candles_15m[:-1], wick)})).breakout is None
    assert evaluate(data.model_copy(update={"candles_15m": (*data.candles_15m[:-1], thin)})).breakout is None


def test_context_rejects_mutated_global_indicator_configuration_without_changing_it(monkeypatch):
    monkeypatch.setattr(talib, "get_compatibility", lambda: 1)
    context = evaluate(trend_data())
    assert context.classification == "UNKNOWN"
    assert context.reason_codes == ("INDICATOR_VERSION_OR_GLOBAL_CONFIGURATION_MISMATCH",)


def test_three_verified_second_spreads_veto_but_minute_samples_are_not_upsampled():
    data = trend_data()
    seconds = tuple(spread(width=D("0.15"), at=T-timedelta(seconds=i)) for i in (2, 1, 0))
    context = evaluate(data.model_copy(update={"spread_samples": seconds}))
    assert context.classification == "EXTREME_VOLATILITY"
    assert "WIDE_SPREAD_THREE_VERIFIED_SECONDS" in context.reason_codes
    assert all(s.observation_id in context.source_ids for s in seconds)
    minutes = tuple(spread(width=D("0.15"), at=T-timedelta(minutes=i)) for i in (2, 1, 0))
    context = evaluate(data.model_copy(update={"spread_samples": minutes}))
    assert context.classification == "TREND_UP"
    assert "WIDE_SPREAD_THREE_VERIFIED_SECONDS" not in context.reason_codes


def test_range_context_executes_price_balance_and_real_adx_instead_of_touch_label():
    data = trend_data()
    hourly = series("1h", 735)
    cycle = (D(0), D(2), D(2), D(0), D(-2), D(-2))
    hourly = tuple(bar("1h", c.open_time, center=D(100) + cycle[i % len(cycle)],
                       width=D(6) - D("0.005") * i) for i, c in enumerate(hourly))
    context = evaluate(data.model_copy(update={"candles_1h": hourly}))
    assert context.readiness == "READY"
    assert context.adx_1h < 20
    assert context.balance.qualified
    assert context.classification == "RANGE"
    assert context.balance.source_ids[:20] == tuple(c.source_record_id for c in hourly[-21:-1])


def test_short_breakout_is_symmetric_and_unaligned_formation_bias_is_not_promoted():
    data = trend_data("SHORT")
    last = data.candles_15m[-1]
    breakout = last.model_copy(update={"low": D(89), "close": D(90), "base_volume": D("1.5")})
    data = data.model_copy(update={"candles_15m": (*data.candles_15m[:-1], breakout)})
    context = evaluate(data)
    assert context.classification == "BREAKOUT_EVENT"
    assert context.breakout.side == "SHORT" and context.breakout.boundary == D(99)
    unaligned = data.model_copy(update={"candles_4h": trend_data("LONG").candles_4h})
    assert evaluate(unaligned).breakout is None
