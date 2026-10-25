"""Three separate versioned policies over C02 closed observations and C01 setups."""
from datetime import timedelta
from decimal import Decimal as D

from astrabot.contracts import Anchor, SetupSnapshotV15
from astrabot.data.models import Candle, config_hash, stable_id
from astrabot.features.providers import session_vwap
from astrabot.research.context import MarketContext, _atr
from astrabot.research.evidence import EvidenceError, history
from astrabot.research.levels import StructuralLevel, confirmed_swings
from astrabot.research.models import ResearchSetup, VERSIONS
from astrabot.universe.eligibility import SymbolData

BAR = timedelta(minutes=5)
TERMINAL = {"CONSUMED", "INVALIDATED", "EXPIRED"}


def level(*, kind, price, bar, source_ids=None, timeframe="5m", relevance="BOTH"):
    return StructuralLevel(level_id=stable_id("c03.levels.v1", kind, source_ids or (bar.source_record_id,), price),
        symbol=bar.symbol, instrument_id=bar.instrument_id, kind=kind, relevance=relevance,
        source_ids=source_ids or (bar.source_record_id,), timeframe=timeframe,
        event_time=bar.close_time, available_at=bar.available_at, price=price,
        version="c03.levels.v1", fidelity="SYNTHETIC_FIXTURE" if bar.fidelity == "SYNTHETIC_FIXTURE" else "BAR_DERIVED_APPROX", invalidated=False,
        invalidation_policy="FROZEN_SETUP_ANCHOR;TERMINAL_WITH_SETUP")


def historical_vwap(data, bar):
    at = bar.open_time+BAR
    return session_vwap(tuple(c for c in data.candles_5m if c.confirmed_at(at)),
        as_of=at, symbol=bar.symbol, instrument_id=bar.instrument_id)


def verify_setup_sources(setup, data, as_of):
    """Validate saved geometry against raw source records before admission.

    This is a consistency boundary for research replay, not authentication of
    user-supplied market data. Original snapshot hashes remain audit references.
    """
    snap = setup.snapshot
    try:
        five = history(data.candles_5m, interval="5m", symbol=snap.symbol,
            instrument_id=setup.instrument_id, as_of=snap.available_at, minimum=15, fresh=True)
        fifteen = history(data.candles_15m, interval="15m", symbol=snap.symbol,
            instrument_id=setup.instrument_id, as_of=snap.available_at, minimum=15, fresh=True)
        if _atr(five) != snap.frozen_atr or _atr(fifteen) != setup.atr_15m:
            return ("FROZEN_ATR_SOURCE_MISMATCH",)
        if setup.strategy_id == "T1":
            window = five[-3:]
            expected = min(c.low for c in window) if snap.side == "LONG" else max(c.high for c in window)
            if (len(setup.levels) != 1 or setup.levels[0].kind != "PULLBACK_EXTREME"
                    or setup.levels[0].price != expected
                    or setup.levels[0].source_ids != tuple(c.source_record_id for c in window)):
                return ("PULLBACK_ANCHOR_SOURCE_MISMATCH",)
            sign = D(1) if snap.side == "LONG" else D(-1)
            vwap = [historical_vwap(data, b) for b in window]
            if any(v.readiness != "READY" or not isinstance(v.value, D) for v in vwap):
                return ("T1_HISTORICAL_VWAP_UNAVAILABLE",)
            if not any(b.source_record_id == setup.prior_vwap_event_id and sign*(b.close-v.value) <= 0
                       for b, v in zip(window, vwap)):
                return ("T1_PRIOR_VWAP_SOURCE_MISMATCH",)
        elif setup.strategy_id == "R1":
            hourly = history(data.candles_1h, interval="1h", symbol=snap.symbol,
                instrument_id=setup.instrument_id, as_of=snap.available_at, minimum=21, fresh=True)[-21:-1]
            ids = tuple(c.source_record_id for c in hourly)
            high, low = max(c.high for c in hourly), min(c.low for c in hourly)
            expected = {"RANGE_HIGH": high, "RANGE_LOW": low, "RANGE_MIDPOINT": (high+low)/2}
            if (len(setup.levels) != 3 or {x.kind for x in setup.levels} != set(expected)
                    or any(x.source_ids != ids or x.price != expected[x.kind] for x in setup.levels)):
                return ("FROZEN_RANGE_SOURCE_MISMATCH",)
        else:
            rows = history(data.candles_15m, interval="15m", symbol=snap.symbol,
                instrument_id=setup.instrument_id, as_of=snap.available_at, minimum=21, fresh=True)
            boundary = (max(c.high for c in rows[-21:-1]) if snap.side == "LONG"
                        else min(c.low for c in rows[-21:-1]))
            sign = D(1) if snap.side == "LONG" else D(-1)
            if (setup.levels[0].price != boundary or setup.levels[0].kind != "BREAKOUT_BOUNDARY"
                    or sign*(rows[-1].close-boundary) <= 0
                    or snap.tolerance != snap.frozen_atr*D(".20")):
                return ("BREAKOUT_BOUNDARY_SOURCE_MISMATCH",)
        current = history(data.candles_5m, interval="5m", symbol=snap.symbol,
            instrument_id=setup.instrument_id, as_of=as_of, minimum=1)
        by_id = {c.source_record_id: c for c in current}
        for bar in (setup.selected_bar, setup.confirmation_bar):
            if bar and by_id.get(bar.source_record_id) != bar:
                return ("SETUP_EVENT_SOURCE_MISMATCH",)
    except EvidenceError as exc:
        return (exc.code,)
    return ()


def _bars(data, context):
    return history(data.candles_5m, interval="5m", symbol=context.symbol,
        instrument_id=context.instrument_id, as_of=context.as_of, minimum=3, fresh=True)


def _create(strategy, side, context, source_snapshot_id, bars, levels, feature_refs,
            *, event_id=None, formed_at=None, session_id=None, prior_vwap=None,
            atr=None, expiry=None, next_open=None, retest_last=None):
    last = bars[-1]
    atr = atr or context.atr_5m
    terms = {"strategy": VERSIONS[strategy], "stop_atr": ".10", "retest_atr": ".20",
             "failure_atr": ".10", "chase_ticks": 2, "chase_atr": ".10", "chase_price_r": ".05",
             "setup_minutes": 30, "proposal_seconds": 90, "trigger_seconds": 10,
             "session_roll": "SUSPEND_T1_CONFIRMATION", "management": "FIXED_BASELINE_RESEARCH_V1"}
    formed_at = formed_at or last.close_time
    available = context.as_of
    setup_id = stable_id(strategy, VERSIONS[strategy], context.symbol, context.instrument_id,
                         side, event_id or last.source_record_id, tuple(x.level_id for x in levels))
    snapshot = SetupSnapshotV15(setup_id=setup_id, strategy_version=VERSIONS[strategy],
        strategy_policy_hash=config_hash(terms), symbol=context.symbol, side=side,
        source_snapshot_id=source_snapshot_id, formed_event_id=event_id or last.source_record_id,
        anchors=tuple(Anchor(anchor_id=x.level_id, source_event_id=stable_id(*x.source_ids),
                             price=x.price, available_at=x.available_at) for x in levels),
        frozen_atr=atr, tolerance=atr*D(".20") if strategy == "B1" else context.atr_15m*D(".25"),
        original_risk_parameters_hash=config_hash(terms), context_at_formation=context.context_id,
        formed_at=formed_at, available_at=available,
        expires_at=expiry or available+timedelta(minutes=30), state="FORMING").advance("ARMED")
    return ResearchSetup(snapshot=snapshot, strategy_id=strategy, instrument_id=context.instrument_id,
        levels=levels, opposing_at_formation=(),
        feature_refs=tuple(dict.fromkeys((context.context_id, *context.feature_refs, *feature_refs))), atr_15m=context.atr_15m,
        balance_at_formation=context.balance if strategy == "R1" else None,
        session_id=session_id, prior_vwap_event_id=prior_vwap,
        processed_event_ids=tuple(b.source_record_id for b in bars[-3:]),
        last_bar_open=last.open_time, next_bar_open=next_open or last.open_time+BAR,
        retest_last_open=retest_last)


def form_t1(data: SymbolData, context: MarketContext, side: str, source_snapshot_id: str):
    expected = "TREND_UP" if side == "LONG" else "TREND_DOWN"
    bias = "BULLISH" if side == "LONG" else "BEARISH"
    if context.classification != expected or context.bias != bias:
        return None, ("T1_CONTEXT_NOT_ALIGNED",)
    bars = _bars(data, context)
    window = bars[-3:]
    if len({b.open_time.date() for b in window}) != 1 or window[-1].open_time.date() != context.as_of.date():
        return None, ("T1_SESSION_ROLLOVER_UNQUALIFIED",)
    observations = [historical_vwap(data, b) for b in window]
    if any(x.readiness != "READY" or not isinstance(x.value, D) for x in observations):
        return None, ("T1_HISTORICAL_VWAP_UNAVAILABLE",)
    sign = D(1) if side == "LONG" else D(-1)
    prior = [b for b, v in zip(window, observations) if sign*(b.close-v.value) <= 0]
    if not prior:
        return None, ("T1_PRIOR_VWAP_CROSS_MISSING",)
    last = window[-1]
    touch_price = last.low if side == "LONG" else last.high
    if abs(touch_price-observations[-1].value) > D(".25")*context.atr_15m:
        return None, ("T1_PULLBACK_OUTSIDE_VWAP_ZONE",)
    extreme = min(b.low for b in window) if side == "LONG" else max(b.high for b in window)
    anchor = level(kind="PULLBACK_EXTREME", price=extreme, bar=last,
                   source_ids=tuple(b.source_record_id for b in window))
    setup = _create("T1", side, context, source_snapshot_id, bars, (anchor,),
        tuple(v.observation_id for v in observations), session_id=observations[-1].payload["session_id"],
        prior_vwap=prior[0].source_record_id)
    return setup, ()


def form_r1(data: SymbolData, context: MarketContext, side: str, source_snapshot_id: str):
    balance = context.balance
    if context.classification != "RANGE" or not balance or not balance.qualified:
        return None, ("R1_STABLE_BALANCE_UNQUALIFIED",)
    bars = _bars(data, context)
    if balance.available_at > context.as_of:
        return None, ("R1_RANGE_NOT_AVAILABLE_BEFORE_SWEEP",)
    hourly = history(data.candles_1h, interval="1h", symbol=context.symbol,
                     instrument_id=context.instrument_id, as_of=context.as_of, minimum=21)
    range_ids = tuple(b.source_record_id for b in hourly[-21:-1])
    anchors = tuple(level(kind=kind, price=price, bar=bars[-1], source_ids=range_ids,
                         timeframe="1h") for kind, price in (
                         ("RANGE_HIGH", balance.high), ("RANGE_LOW", balance.low),
                         ("RANGE_MIDPOINT", balance.midpoint)))
    # Range event identity is stable across repeated scans of the same hourly window.
    setup = _create("R1", side, context, source_snapshot_id, bars, anchors,
                    (balance.terms_hash, *balance.source_ids), event_id=stable_id("range", *range_ids))
    return setup, ()


def form_b1(data: SymbolData, context: MarketContext, side: str, source_snapshot_id: str):
    event = context.breakout
    if (context.classification == "EXTREME_VOLATILITY" or not event or event.side != side
            or not event.atr_5m):
        return None, ("B1_ALIGNED_BREAKOUT_EVENT_MISSING",)
    # Require event-time formation. A scanner that missed the breakout cannot
    # freeze a later ATR/context and pretend it was present at the event.
    if context.as_of-event.available_at > timedelta(seconds=10):
        return None, ("B1_FORMATION_EVENT_STALE",)
    bars = _bars(data, context)
    anchor = level(kind="BREAKOUT_BOUNDARY", price=event.boundary, bar=bars[-1],
                   source_ids=event.source_ids, timeframe="15m")
    next_open = bars[-1].open_time+BAR
    setup = _create("B1", side, context, source_snapshot_id, bars, (anchor,),
        (event.event_id,), event_id=event.event_id, formed_at=event.event_time,
        atr=event.atr_5m, expiry=next_open+BAR*7+timedelta(seconds=10),
        next_open=next_open, retest_last=next_open+BAR*5)
    return setup, ()


FORMERS = {"T1": form_t1, "R1": form_r1, "B1": form_b1}


def form_setup(strategy, data, context, side, source_snapshot_id):
    if context.readiness != "READY" or context.atr_5m is None or context.atr_15m is None:
        return None, ("MANDATORY_CONTEXT_UNAVAILABLE", *context.reason_codes)
    try:
        result, reasons = FORMERS[strategy](data, context, side, source_snapshot_id)
        if result:
            inventory = confirmed_swings(data.candles_1h, symbol=context.symbol,
                                         instrument_id=context.instrument_id, as_of=context.as_of)
            result = result.model_copy(update={"opposing_at_formation": inventory})
        return result, reasons
    except EvidenceError as exc:
        return None, (exc.code,)


def _update(setup, **changes):
    return ResearchSetup.model_validate_json(setup.model_copy(update=changes).model_dump_json())


def _terminal(setup, state, reason):
    evidence = {"invalidation_reason": reason} if state == "INVALIDATED" else {}
    return _update(setup, snapshot=setup.snapshot.advance(state, **evidence), notes=(*setup.notes, reason))


def _confirm(setup, bar):
    return _update(setup, confirmation_bar=bar,
        snapshot=setup.snapshot.advance("CONFIRMED", confirmed_at=bar.available_at,
                                       confirmed_event_id=bar.source_record_id))


def advance_t1(setup, bar, data):
    sign = D(1) if setup.snapshot.side == "LONG" else D(-1)
    anchor = setup.levels[0].price
    if sign*(bar.close-anchor) < 0:
        return _terminal(setup, "INVALIDATED", "T1_ORIGINAL_STRUCTURE_BROKEN")
    if (f"UTC:{bar.open_time.date().isoformat()}" != setup.session_id
            or (bar.open_time+BAR).date() != bar.open_time.date()):
        # No invented acceptance or thesis invalidation on an anchor reset.
        return _update(setup, notes=tuple(dict.fromkeys((*setup.notes, "T1_ROLLOVER_CONFIRMATION_SUSPENDED"))))
    vwap = historical_vwap(data, bar)
    if vwap.readiness != "READY" or not isinstance(vwap.value, D):
        return _terminal(setup, "INVALIDATED", "T1_VWAP_UNAVAILABLE_AT_CONFIRMATION")
    if (setup.prior_vwap_event_id and sign*(bar.close-vwap.value) > 0
            and sign*(bar.close-bar.open) > 0):
        return _confirm(setup, bar)
    return setup


def advance_r1(setup, bar, data):
    side = setup.snapshot.side
    low = next(x.price for x in setup.levels if x.kind == "RANGE_LOW")
    high = next(x.price for x in setup.levels if x.kind == "RANGE_HIGH")
    if bar.low < low and bar.high > high:
        return _terminal(setup, "INVALIDATED", "R1_TWO_SIDED_RANGE_VIOLATION")
    if setup.selected_bar:
        adverse = bar.close <= low if side == "LONG" else bar.close >= high
        if adverse:
            return _terminal(setup, "INVALIDATED", "R1_FROZEN_EDGE_RECLAIM_FAILED")
        if bar.open_time != setup.confirmation_due_open:
            return _terminal(setup, "EXPIRED", "R1_NEXT_DISTINCT_CONFIRMATION_MISSING")
        passed = bar.close > setup.selected_bar.high if side == "LONG" else bar.close < setup.selected_bar.low
        return _confirm(setup, bar) if passed else _terminal(setup, "EXPIRED", "R1_CONFIRMATION_FAILED")
    inside = low < bar.close < high
    swept = bar.low < low if side == "LONG" else bar.high > high
    if inside and swept:
        extreme = bar.low if side == "LONG" else bar.high
        return _update(setup, selected_bar=bar,
            selected_extreme=level(kind="SWEEP_EXTREME", price=extreme, bar=bar),
            confirmation_due_open=bar.open_time+BAR)
    if (bar.close <= low if side == "LONG" else bar.close >= high):
        return _terminal(setup, "INVALIDATED", "R1_RANGE_BREACH_WITHOUT_RECLAIM")
    return setup


def advance_b1(setup, bar, data):
    sign = D(1) if setup.snapshot.side == "LONG" else D(-1)
    boundary = setup.levels[0].price
    extreme = bar.low if sign == 1 else bar.high
    failure = setup.snapshot.frozen_atr*D(".10")
    if sign*(extreme-boundary) < -failure or sign*(bar.close-boundary) < -failure:
        return _terminal(setup, "INVALIDATED", "B1_SAVED_PENETRATION_FAILURE")
    if setup.selected_bar:
        if bar.open_time != setup.confirmation_due_open:
            return _terminal(setup, "EXPIRED", "B1_NEXT_DISTINCT_CONFIRMATION_MISSING")
        passed = bar.close > setup.selected_bar.high if sign == 1 else bar.close < setup.selected_bar.low
        return _confirm(setup, bar) if passed else _terminal(setup, "EXPIRED", "B1_CONFIRMATION_FAILED")
    if bar.open_time > setup.retest_last_open:
        return _terminal(setup, "EXPIRED", "B1_SIX_BAR_RETEST_DEADLINE")
    if abs(extreme-boundary) <= setup.snapshot.tolerance:
        return _update(setup, selected_bar=bar,
            selected_extreme=level(kind="RETEST_EXTREME", price=extreme, bar=bar),
            confirmation_due_open=bar.open_time+BAR)
    return setup


ADVANCERS = {"T1": advance_t1, "R1": advance_r1, "B1": advance_b1}


def advance_setup(setup: ResearchSetup, data: SymbolData, context: MarketContext):
    """Consume each closed event once, preserving state across scanner calls."""
    if setup.snapshot.state in TERMINAL or setup.snapshot.state == "CONFIRMED":
        return setup
    # Process available event chronology first; late detection is rejected at
    # the separate trigger deadline by the decision mapper, never retro-entered.
    try:
        bars = _bars(data, context)
    except EvidenceError as exc:
        return _terminal(setup, "INVALIDATED", exc.code)
    for bar in bars:
        if bar.open_time <= setup.last_bar_open:
            continue
        if bar.source_record_id in setup.processed_event_ids:
            continue
        if bar.open_time != setup.last_bar_open+BAR:
            return _terminal(setup, "INVALIDATED", "SETUP_EVENT_GAP")
        if bar.available_at >= setup.snapshot.expires_at:
            return _terminal(setup, "EXPIRED", "SETUP_ORIGINAL_EXPIRY")
        setup = _update(setup, last_bar_open=bar.open_time,
                        processed_event_ids=(*setup.processed_event_ids, bar.source_record_id))
        setup = ADVANCERS[setup.strategy_id](setup, bar, data)
        if setup.snapshot.state in TERMINAL or setup.snapshot.state == "CONFIRMED":
            return setup
        if setup.strategy_id == "B1" and not setup.selected_bar and bar.open_time == setup.retest_last_open:
            return _terminal(setup, "EXPIRED", "B1_SIX_BAR_RETEST_DEADLINE")
    if context.as_of >= setup.snapshot.expires_at:
        return _terminal(setup, "EXPIRED", "SETUP_ORIGINAL_EXPIRY")
    return setup
