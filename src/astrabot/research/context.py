"""Versioned C03 closed-bar context using a thin pinned TA-Lib wrapper.

Thresholds and the balance metric are explicit UNVALIDATED research hypotheses.
Breakout is a source-timestamped event; these labels are not a setup lifecycle.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal, Sequence

import numpy as np
import talib
from pydantic import Field

from astrabot.contracts import Contract, ID, Money, Positive, Signed, Side, UTC
from astrabot.data.models import Candle, Readiness, SpreadSample, config_hash, stable_id
from astrabot.research.evidence import EvidenceError, history
from astrabot.universe.eligibility import SymbolData

VERSION = "c03.context.v1"
INDICATOR_SOURCE = "TA-Lib-python:0.6.8;TA-Lib-C:0.6.4;compatibility:0;unstable:0"
BALANCE_VERSION = "c03.stable-balance.hypothesis.v1"
BALANCE_TERMS = {
    "history": "preceding20closed1h_excluding_latest",
    "edge_tolerance_atr": "0.15", "tests_per_edge": 2,
    "minimum_same_edge_test_separation_bars": 3,
    "maximum_first5_last5_mean_close_drift_width": "0.20",
    "minimum_width_atr": "2", "maximum_width_atr": "8",
    "minimum_width_median_absolute_spread": "10",
    "maximum_touch_bar_fraction_of_width": "0.75",
    "disqualifying_latest_15m_breakout_rvol": "1.5",
    "qualification": "UNVALIDATED_RESEARCH_HYPOTHESIS",
}


class BreakoutEvent(Contract):
    version: ID = VERSION
    event_id: ID
    side: Side
    boundary: Positive
    event_time: UTC
    available_at: UTC
    source_ids: tuple[ID, ...] = Field(min_length=1)
    atr_5m: Positive | None = None


class BalanceEvidence(Contract):
    qualified: bool
    high: Positive
    low: Positive
    midpoint: Positive
    available_at: UTC
    source_ids: tuple[ID, ...] = Field(min_length=1)
    version: ID = BALANCE_VERSION
    terms_hash: ID
    high_test_indices: tuple[int, ...] = ()
    low_test_indices: tuple[int, ...] = ()
    width_atr: Money
    drift_fraction: Money
    width_spreads: Money | None = None
    reason_codes: tuple[ID, ...] = ()


class MarketContext(Contract):
    context_id: ID
    symbol: ID
    instrument_id: ID
    as_of: UTC
    version: ID = VERSION
    classification: Literal[
        "TREND_UP", "TREND_DOWN", "RANGE", "BREAKOUT_EVENT",
        "EXTREME_VOLATILITY", "UNKNOWN", "UNCLASSIFIED",
    ]
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN"]
    readiness: Readiness
    reason_codes: tuple[ID, ...] = ()
    source_ids: tuple[ID, ...] = ()
    feature_refs: tuple[ID, ...] = ()
    adx_1h: Money | None = None
    atr_1h: Money | None = None
    atr_5m: Money | None = None
    atr_15m: Money | None = None
    ema_1h: Positive | None = None
    normalized_slope: Signed | None = None
    atr_percentile: Money | None = None
    rvol_15m: Money | None = None
    breakout: BreakoutEvent | None = None
    balance: BalanceEvidence | None = None
    threshold_status: Literal["UNVALIDATED"] = "UNVALIDATED"
    indicator_source: Literal[
        "TA-Lib-python:0.6.8;TA-Lib-C:0.6.4;compatibility:0;unstable:0"
    ] = INDICATOR_SOURCE


def _library_guard() -> None:
    if (talib.__version__ != "0.6.8" or not talib.__ta_version__.startswith(b"0.6.4")
            or talib.get_compatibility() != 0
            or any(talib.get_unstable_period(name) != 0 for name in ("ATR", "ADX", "EMA"))):
        raise EvidenceError("INDICATOR_VERSION_OR_GLOBAL_CONFIGURATION_MISMATCH")


def _arrays(rows: Sequence[Candle]):
    arrays = tuple(np.asarray([float(getattr(c, name)) for c in rows], dtype=np.float64)
                   for name in ("high", "low", "close"))
    if any(not np.all(np.isfinite(values)) for values in arrays):
        raise EvidenceError("INDICATOR_INPUT_OUTSIDE_FLOAT64_RANGE")
    return arrays


def _decimal(value) -> Decimal:
    if not np.isfinite(value):
        raise EvidenceError("INDICATOR_NOT_FINITE")
    return Decimal(str(float(value)))


def _atr(rows: Sequence[Candle]) -> Decimal:
    high, low, close = _arrays(rows)
    value = _decimal(talib.ATR(high, low, close, timeperiod=14)[-1])
    if value <= 0:
        raise EvidenceError("ZERO_ATR")
    return value


def _bias(rows: Sequence[Candle]) -> str:
    values = talib.EMA(_arrays(rows)[2], timeperiod=50)
    current, previous = _decimal(values[-1]), _decimal(values[-4])
    if rows[-1].close > current and current > previous:
        return "BULLISH"
    if rows[-1].close < current and current < previous:
        return "BEARISH"
    return "NEUTRAL"


def _separated(indices: tuple[int, ...]) -> bool:
    return any(b - a >= 3 for a in indices for b in indices)


def qualify_balance(
    rows: Sequence[Candle], *, atr: Decimal,
    spread_samples: Sequence[SpreadSample], symbol: str,
    instrument_id: str, as_of: datetime,
) -> BalanceEvidence:
    """Freeze only the preceding 20 hourly bars, never the current closed bar.

    The metric uses price geometry and currently available transaction width;
    it never applies a current RVOL to historical hourly candles. Its chosen
    constants are testable research assumptions, not empirical qualification.
    """
    prior = tuple(rows[-21:-1])
    if len(prior) != 20 or atr <= 0:
        raise EvidenceError("INSUFFICIENT_BALANCE_EVIDENCE")
    high, low = max(c.high for c in prior), min(c.low for c in prior)
    width = high - low
    if width <= 0:
        raise EvidenceError("ZERO_RANGE_WIDTH")
    tolerance = Decimal("0.15") * atr
    high_tests = tuple(i for i, c in enumerate(prior)
                       if c.high >= high - tolerance
                       and c.high - c.low <= Decimal("0.75") * width)
    low_tests = tuple(i for i, c in enumerate(prior)
                      if c.low <= low + tolerance
                      and c.high - c.low <= Decimal("0.75") * width)
    early = sum((c.close for c in prior[:5]), Decimal(0)) / 5
    late = sum((c.close for c in prior[-5:]), Decimal(0)) / 5
    drift = abs(late - early) / width
    spreads = tuple(s for s in spread_samples
                    if s.available_at <= as_of and s.event_time <= as_of
                    and as_of - s.event_time <= timedelta(hours=1))
    good_spreads = (spreads and all(
        s.symbol == symbol and s.instrument_id == instrument_id
        and s.readiness == "READY" and s.quality == "VALID" for s in spreads
    ) and max(s.event_time for s in spreads) >= as_of - timedelta(seconds=60))
    spread = median(s.ask_price - s.bid_price for s in spreads) if good_spreads else None
    width_spreads = width / spread if spread and spread > 0 else None
    reasons = []
    if not _separated(high_tests) or not _separated(low_tests):
        reasons.append("BALANCE_SEPARATED_EDGE_TESTS_MISSING")
    if drift > Decimal("0.20"):
        reasons.append("BALANCE_DRIFT_TOO_LARGE")
    if not Decimal(2) <= width / atr <= Decimal(8):
        reasons.append("BALANCE_WIDTH_ATR_OUT_OF_BOUNDS")
    if spread is None:
        reasons.append("BALANCE_SPREAD_UNAVAILABLE")
    elif width_spreads is not None and width_spreads < 10:
        reasons.append("BALANCE_WIDTH_CANNOT_CLEAR_SPREAD")
    source_ids = tuple(c.source_record_id for c in prior) + tuple(
        s.observation_id for s in spreads if good_spreads
    )
    return BalanceEvidence(
        qualified=not reasons, high=high, low=low, midpoint=(high + low) / 2,
        available_at=max((*[c.available_at for c in prior],
                          *[s.available_at for s in spreads if good_spreads])),
        source_ids=source_ids, terms_hash=config_hash(BALANCE_TERMS),
        high_test_indices=high_tests, low_test_indices=low_tests,
        width_atr=width / atr, drift_fraction=drift,
        width_spreads=width_spreads, reason_codes=tuple(reasons),
    )


def classify_metrics(*, adx: Decimal, slope: Decimal, bias: str,
                     percentile: Decimal, breakout: BreakoutEvent | None,
                     balance: BalanceEvidence, liquidity_veto: bool = False) -> str:
    """The exact v1.5 priority; 20–25 ADX is an unclassified band."""
    if percentile >= 95 or liquidity_veto:
        return "EXTREME_VOLATILITY"
    if breakout is not None:
        return "BREAKOUT_EVENT"
    if adx >= 25 and slope >= Decimal("0.15") and bias == "BULLISH":
        return "TREND_UP"
    if adx >= 25 and slope <= Decimal("-0.15") and bias == "BEARISH":
        return "TREND_DOWN"
    if adx < 20 and balance.qualified:
        return "RANGE"
    return "UNCLASSIFIED"


def _wide_spread_seconds(samples: Sequence[SpreadSample], *, symbol: str,
                         instrument_id: str, as_of: datetime) -> tuple[SpreadSample, ...]:
    """Only three actual consecutive 1-second observations prove this veto.

    C02's minute samples cannot be upsampled into evidence. One second after
    the most recent observation is the explicit C03 freshness assumption.
    """
    available = tuple(s for s in samples if s.available_at <= as_of and s.event_time <= as_of)
    selected = available[-3:]
    if (len(selected) != 3 or as_of - selected[-1].event_time > timedelta(seconds=1)
            or any(b.event_time - a.event_time != timedelta(seconds=1)
                   for a, b in zip(selected, selected[1:]))
            or len({s.observation_id for s in selected}) != 3):
        return ()
    if all(s.symbol == symbol and s.instrument_id == instrument_id
           and s.readiness == "READY" and s.quality == "VALID"
           and s.fidelity in ("BOOK_L2", "VENUE_REPORTED", "SYNTHETIC_FIXTURE")
           and s.spread_fraction >= Decimal("0.0015") for s in selected):
        return selected
    return ()


def evaluate_context(data: SymbolData, *, symbol: str, instrument_id: str,
                     as_of: datetime) -> MarketContext:
    """Evaluate available C02 observations with no network or setup mutation."""
    source_ids: tuple[str, ...] = ()
    try:
        _library_guard()
        hourly = history(data.candles_1h, interval="1h", symbol=symbol,
                         instrument_id=instrument_id, as_of=as_of, minimum=735, fresh=True)
        four = history(data.candles_4h, interval="4h", symbol=symbol,
                       instrument_id=instrument_id, as_of=as_of, minimum=53, fresh=True)
        fifteen = history(data.candles_15m, interval="15m", symbol=symbol,
                          instrument_id=instrument_id, as_of=as_of, minimum=21, fresh=True)
        five = history(data.candles_5m, interval="5m", symbol=symbol,
                       instrument_id=instrument_id, as_of=as_of, minimum=15, fresh=True)
        source_ids = tuple(c.source_record_id for c in (*hourly, *four, *fifteen, *five))
        high, low, close = _arrays(hourly)
        atr_values = talib.ATR(high, low, close, timeperiod=14)
        atr, atr5, atr15 = _decimal(atr_values[-1]), _atr(five), _atr(fifteen)
        if atr <= 0:
            raise EvidenceError("ZERO_ATR")
        ema = talib.EMA(close, timeperiod=50)
        slope = (_decimal(ema[-1]) - _decimal(ema[-6])) / atr
        adx = _decimal(talib.ADX(high, low, close, timeperiod=14)[-1])
        percentages = tuple(_decimal(a) / c.close
                            for a, c in zip(atr_values[-721:], hourly[-721:]))
        percentile = Decimal(sum(x <= percentages[-1] for x in percentages[:-1])) / 720 * 100
        bias = _bias(four)
        volume_median = median(c.base_volume for c in fifteen[-21:-1])
        if volume_median <= 0:
            raise EvidenceError("ZERO_RVOL_BASE_VOLUME")
        rvol = fifteen[-1].base_volume / volume_median
        balance = qualify_balance(hourly, atr=atr, spread_samples=data.spread_samples,
                                  symbol=symbol, instrument_id=instrument_id, as_of=as_of)
        breakout = None
        last = fifteen[-1]
        preceding = fifteen[-21:-1]
        up, down = max(c.high for c in preceding), min(c.low for c in preceding)
        direction = "LONG" if last.close > up else "SHORT" if last.close < down else None
        if direction is not None and rvol >= Decimal("1.5"):
            # An unaligned price/volume breakout cannot arm B1, but still
            # disqualifies new balance formation. Bias is not proof of safety.
            balance = balance.model_copy(update={"qualified": False,
                "reason_codes": (*balance.reason_codes, "BALANCE_DISQUALIFYING_VOLUME_BREAKOUT"),
                "source_ids": (*balance.source_ids, *(c.source_record_id for c in fifteen[-21:]))})
            # Formation bias/ATR are taken from the breakout's own available
            # prefix, never a later 4H observation at the scanner timestamp.
            at_event_four = history(data.candles_4h, interval="4h", symbol=symbol,
                                    instrument_id=instrument_id, as_of=last.available_at,
                                    minimum=53, fresh=True)
            at_event_five = history(data.candles_5m, interval="5m", symbol=symbol,
                                    instrument_id=instrument_id, as_of=last.available_at,
                                    minimum=15, fresh=True)
            event_bias = _bias(at_event_four)
            if (direction == "LONG" and event_bias == "BULLISH"
                    or direction == "SHORT" and event_bias == "BEARISH"):
                event_sources = tuple(c.source_record_id for c in (
                    *preceding, last, *at_event_four, *at_event_five
                ))
                breakout = BreakoutEvent(
                    event_id=stable_id(VERSION, "BREAKOUT", instrument_id, direction, *event_sources),
                    side=direction, boundary=up if direction == "LONG" else down,
                    event_time=last.close_time, available_at=last.available_at,
                    source_ids=event_sources, atr_5m=_atr(at_event_five),
                )
        wide = _wide_spread_seconds(data.spread_samples, symbol=symbol,
                                   instrument_id=instrument_id, as_of=as_of)
        label = classify_metrics(adx=adx, slope=slope, bias=bias,
                                 percentile=percentile, breakout=breakout, balance=balance,
                                 liquidity_veto=bool(wide))
        sources = tuple(dict.fromkeys((*source_ids, *balance.source_ids,
                                       *(s.observation_id for s in wide))))
        feature_refs = tuple(stable_id(VERSION, INDICATOR_SOURCE, name, *source_ids)
                             for name in ("ATR14", "ADX14", "EMA50", "ATR_PERCENTILE720", "RVOL20"))
        return MarketContext(
            context_id=stable_id(VERSION, instrument_id, as_of, label, *sources),
            symbol=symbol, instrument_id=instrument_id, as_of=as_of,
            classification=label, bias=bias, readiness="READY",
            reason_codes=("UNVALIDATED_RESEARCH_THRESHOLDS",) + (
                ("WIDE_SPREAD_THREE_VERIFIED_SECONDS",) if wide else ()
            ), source_ids=sources,
            feature_refs=feature_refs, adx_1h=adx, atr_1h=atr, atr_5m=atr5,
            atr_15m=atr15, ema_1h=_decimal(ema[-1]), normalized_slope=slope,
            atr_percentile=percentile, rvol_15m=rvol, breakout=breakout, balance=balance,
        )
    except EvidenceError as exc:
        return MarketContext(
            context_id=stable_id(VERSION, instrument_id, as_of, exc.code, *source_ids),
            symbol=symbol, instrument_id=instrument_id, as_of=as_of,
            classification="UNKNOWN", bias="UNKNOWN", readiness="WARMING",
            reason_codes=(exc.code,), source_ids=source_ids,
        )
