from datetime import datetime, timezone, timedelta
from decimal import Decimal

from astrabot.data.models import (
    Candle, DepthLevel, DepthSnapshot, InstrumentFilter, InstrumentMetadata,
    OpenInterestObservation, SpreadSample, Ticker24h, binance_usdm_instrument_id,
)
from astrabot.universe.eligibility import EventClearance, SymbolData, scan_universe

T = datetime(2025, 1, 1, tzinfo=timezone.utc)
SCAN = datetime(2025, 1, 1, 12, 0, 5, tzinfo=timezone.utc)


def metadata(symbol, *, available=T, effective=T, status="TRADING"):
    return InstrumentMetadata(
        symbol=symbol, instrument_id=binance_usdm_instrument_id(symbol), event_time=available,
        available_at=available, ingested_at=available, as_of=available, data_source="exchangeInfo",
        source_version="v1", units="instrument", fidelity="VENUE_REPORTED", readiness="READY",
        observation_id="obs-"+symbol, config_hash="cfg", base_asset=symbol[:-4], quote_asset="USDT",
        settle_asset="USDT", contract_type="PERPETUAL", status=status, effective_from=effective,
        price_tick="0.01", quantity_step="0.001", minimum_quantity="0.001", minimum_notional="5",
        contract_size="1", filters=(
            InstrumentFilter(filter_type="PRICE_FILTER", min_value="0.01", step_size="0.01"),
            InstrumentFilter(filter_type="LOT_SIZE", min_value="0.001", step_size="0.001"),
            InstrumentFilter(filter_type="MIN_NOTIONAL", min_value="5"),
        ))


def test_missing_coverage_is_explicit_and_every_symbol_is_preserved():
    result = scan_universe({"AAAUSDT": SymbolData(metadata=metadata("AAAUSDT")),
                            "BBBUSDT": SymbolData()}, T, Decimal("100"))
    assert [x.symbol for x in result.considered] == ["AAAUSDT", "BBBUSDT"]
    assert result.considered[0].state == "WARMING"
    assert result.considered[1].state == "COLD"
    assert all(x.reasons for x in result.considered)
    assert result.shortlist == ()


def test_metadata_not_known_at_asof_does_not_enter_historical_universe():
    future = datetime(2025, 1, 2, tzinfo=timezone.utc)
    result = scan_universe({"AAAUSDT": SymbolData(metadata=metadata("AAAUSDT", available=future))}, T,
                           Decimal("100"))
    assert result.considered[0].state == "WARMING"
    assert "METADATA_NOT_VALID_OR_NOT_YET_AVAILABLE" in result.considered[0].reasons


def test_nontrading_instrument_is_hard_ineligible():
    result = scan_universe({"AAAUSDT": SymbolData(metadata=metadata("AAAUSDT", status="BREAK"))}, T,
                           Decimal("100"))
    assert result.considered[0].state == "INELIGIBLE"
    assert "INSTRUMENT_IDENTITY_OR_STATUS_INELIGIBLE" in result.considered[0].reasons


def test_wrong_settlement_invalid_filters_and_contract_dates_are_excluded():
    wrong_settlement = metadata("AAAUSDT").model_copy(update={"quote_asset": "USDC"})
    missing_filters = metadata("BBBUSDT").model_copy(update={"filters": ()})
    future_listing = metadata("CCCUSDT").model_copy(update={"onboard_time": T+timedelta(seconds=1)})
    result = scan_universe({
        "AAAUSDT": SymbolData(metadata=wrong_settlement),
        "BBBUSDT": SymbolData(metadata=missing_filters),
        "CCCUSDT": SymbolData(metadata=future_listing),
    }, T, Decimal("100"))
    by_symbol = {item.symbol: item for item in result.considered}
    assert by_symbol["AAAUSDT"].state == "INELIGIBLE"
    assert "INSTRUMENT_IDENTITY_OR_STATUS_INELIGIBLE" in by_symbol["AAAUSDT"].reasons
    assert by_symbol["BBBUSDT"].state == "INELIGIBLE"
    assert "REQUIRED_EXCHANGE_FILTERS_MISSING" in by_symbol["BBBUSDT"].reasons
    assert by_symbol["CCCUSDT"].state == "INELIGIBLE"
    assert "CONTRACT_NOT_YET_ONBOARDED_OR_ALREADY_DELIVERED" in by_symbol["CCCUSDT"].reasons


def test_stale_metadata_is_rejected_at_scan_time():
    from datetime import timedelta
    from astrabot.universe.eligibility import FreshnessPolicy

    old = T - timedelta(seconds=3601)
    result = scan_universe({"AAAUSDT": SymbolData(metadata=metadata("AAAUSDT", available=old,
                                                                       effective=old))}, T,
                           Decimal("100"))
    assert result.considered[0].state == "WARMING"
    assert "METADATA_STALE" in result.considered[0].reasons
    # A caller can tighten cutoffs for its research run and preserve the same reason.
    tighter = FreshnessPolicy(metadata=timedelta(seconds=30))
    assert "METADATA_STALE" in scan_universe(
        {"AAAUSDT": SymbolData(metadata=metadata("AAAUSDT", available=T-timedelta(seconds=31),
                                                     effective=T-timedelta(seconds=31)))},
        T, Decimal("100"),
        freshness=tighter).considered[0].reasons


def test_stale_well_formed_ticker_fails_turnover_gate():
    from datetime import timedelta
    from astrabot.data.models import Ticker24h

    old = T - timedelta(seconds=61)
    ticker = Ticker24h(
        symbol="AAAUSDT", instrument_id=binance_usdm_instrument_id("AAAUSDT"),
        event_time=old, available_at=old, ingested_at=old, as_of=old, data_source="ticker",
        source_version="v1", units="USDT", fidelity="VENUE_REPORTED", readiness="READY",
        observation_id="ticker-old", config_hash="cfg", open="1", high="2", low="1",
        last="1", base_volume="1", quote_volume="30000000", trade_count=1,
        window_start=old-timedelta(hours=24), window_end=old)
    result = scan_universe({"AAAUSDT": SymbolData(metadata=metadata("AAAUSDT"), ticker=ticker)}, T,
                           Decimal("100"))
    assert result.considered[0].turnover_usdt is None
    assert "TICKER_24H_STALE" in result.considered[0].reasons


def _obs(model, symbol, instrument_id, event_time, **fields):
    return model(
        symbol=symbol, instrument_id=instrument_id, event_time=event_time,
        available_at=fields.pop("available_at", event_time),
        ingested_at=fields.pop("ingested_at", event_time), as_of=fields.pop("as_of", T),
        data_source="fixture", source_version="fixture-v1", units="fixture units",
        fidelity=fields.pop("fidelity", "VENUE_REPORTED"), readiness="READY",
        observation_id=fields.pop("observation_id", f"{model.__name__}-{symbol}-{event_time.isoformat()}"),
        config_hash="fixture", **fields)


def _candle_series(symbol, interval, count, final_open, step, as_of, *, near_edge=False):
    instrument_id = binance_usdm_instrument_id(symbol)
    rows = []
    for index in range(count):
        open_time = final_open - step * (count - index - 1)
        close_time = open_time + step - timedelta(milliseconds=1)
        close = Decimal("101.8") if near_edge else Decimal("100")
        rows.append(_obs(
            Candle, symbol, instrument_id, close_time, interval=interval, open_time=open_time,
            close_time=close_time, open=Decimal("100"), high=Decimal("102"), low=Decimal("98"),
            close=close, base_volume=Decimal("10"), quote_volume=Decimal("1000"),
            trade_count=10, is_closed=True, source_record_id=f"{symbol}-{interval}-{index}",
            available_at=close_time + timedelta(milliseconds=1), as_of=as_of,
            fidelity="BAR_DERIVED_APPROX"))
    return tuple(rows)


def eligible_data(symbol="ALTUSDT", *, as_of=T, turnover="30000000", spread="0.0005",
                  depth_qty="100000", oi_notional="6000000", event="CLEAR"):
    iid = binance_usdm_instrument_id(symbol)
    # Last completed 5m bar became available five seconds before this scan.
    five_final = as_of.replace(minute=(as_of.minute // 5) * 5, second=0, microsecond=0) - timedelta(minutes=5)
    fifteen_final = as_of.replace(minute=(as_of.minute // 15) * 15, second=0, microsecond=0) - timedelta(minutes=15)
    one_hour_final = as_of.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    four_hour_hour = (as_of.hour // 4) * 4
    four_hour_final = as_of.replace(hour=four_hour_hour, minute=0, second=0, microsecond=0) - timedelta(hours=4)
    metadata_time = as_of - timedelta(seconds=5)
    metadata_observation = metadata(symbol, available=metadata_time, effective=as_of-timedelta(days=30))
    ticker_event = as_of - timedelta(seconds=5)
    ticker = _obs(Ticker24h, symbol, iid, ticker_event, open="90", high="110", low="80",
                  last="100", base_volume="300000", quote_volume=turnover, trade_count=1000,
                  window_start=ticker_event-timedelta(hours=24), window_end=ticker_event,
                  available_at=as_of)
    samples = []
    for index in range(60):
        at = as_of - timedelta(minutes=59-index)
        samples.append(_obs(SpreadSample, symbol, iid, at,
                            bid_price=Decimal("100")*(Decimal(1)-Decimal(spread)/2),
                            bid_quantity="1000",
                            ask_price=Decimal("100")*(Decimal(1)+Decimal(spread)/2),
                            ask_quantity="1000", available_at=at))
    depth = _obs(DepthSnapshot, symbol, iid, as_of, last_update_id=10,
                 bids=(DepthLevel(price="99.99", quantity=depth_qty),),
                 asks=(DepthLevel(price="100.01", quantity=depth_qty),), fidelity="BOOK_L2")
    oi = _obs(OpenInterestObservation, symbol, iid, as_of-timedelta(seconds=2),
              open_interest="100000", quantity_unit="USDT_notional", unit_validated=True,
              open_interest_notional_usdt=oi_notional, available_at=as_of)
    clearance = None if event == "MISSING" else EventClearance(
        state=event, verification_state="UNVERIFIED" if event == "UNKNOWN" else "VERIFIED",
        as_of=as_of, source_ids=("event-source-1",),
        reason="verified policy event" if event == "VETO" else None)
    return SymbolData(
        metadata=metadata_observation, ticker=ticker,
        candles_5m=_candle_series(symbol, "5m", 20, five_final, timedelta(minutes=5), as_of, near_edge=True),
        candles_15m=_candle_series(symbol, "15m", 21, fifteen_final, timedelta(minutes=15), as_of),
        candles_1h=_candle_series(symbol, "1h", 720, one_hour_final, timedelta(hours=1), as_of),
        candles_4h=_candle_series(symbol, "4h", 200, four_hour_final, timedelta(hours=4), as_of),
        spread_samples=tuple(samples), depth=depth, open_interest=oi, event_clearance=clearance)


def test_complete_altcoin_eligibility_uses_every_research_gate():
    result = scan_universe({"ALTUSDT": eligible_data(as_of=SCAN)}, SCAN, Decimal("100000"))
    item = result.considered[0]
    assert item.state == "READY" and item.eligible
    assert item.turnover_usdt == Decimal("30000000")
    assert item.median_spread_fraction <= Decimal("0.001")
    assert item.bid_depth_usdt >= Decimal("500000")
    assert item.ask_depth_usdt >= Decimal("500000")
    assert item.oi_notional_usdt == Decimal("6000000")
    assert result.shortlist == ("ALTUSDT",)
    assert result.purpose == "RESEARCH_WATCHLIST" and result.executable is False


def test_contiguous_closed_history_and_fresh_5m_are_mandatory():
    data = eligible_data(as_of=SCAN)
    # A currently forming bar cannot count as the last completed 5m evidence.
    forming = data.candles_5m[-1].model_copy(update={"is_closed": False})
    incomplete = data.model_copy(update={"candles_5m": (*data.candles_5m[:-1], forming)})
    result = scan_universe({"ALTUSDT": incomplete}, SCAN, Decimal("100000"))
    assert result.considered[0].state == "WARMING"
    assert "LATEST_5M_CANDLE_STALE_OR_LATE" in result.considered[0].reasons
    # Remove a middle 1h bar while retaining the total warmup count.
    expanded = _candle_series("ALTUSDT", "1h", 721,
                              SCAN.replace(minute=0, second=0, microsecond=0)-timedelta(hours=1),
                              timedelta(hours=1), SCAN)
    gap = expanded[:350] + expanded[351:]
    result = scan_universe({"ALTUSDT": data.model_copy(update={"candles_1h": gap})},
                           SCAN, Decimal("100000"))
    assert result.considered[0].state == "DEGRADED"
    assert "GAP_OR_ORDER_1H_WARMUP" in result.considered[0].reasons


def test_spread_depth_oi_and_event_veto_fail_closed():
    cases = [
        (eligible_data(as_of=SCAN, spread="0.002"), "MEDIAN_SPREAD_ABOVE_0_10_PERCENT", "INELIGIBLE"),
        (eligible_data(as_of=SCAN, depth_qty="100"), "SIDE_AWARE_DEPTH_BELOW_5X_WITHIN_0_20_PERCENT", "INELIGIBLE"),
        (eligible_data(as_of=SCAN, oi_notional="4000000"), "OPEN_INTEREST_BELOW_5M_USDT", "INELIGIBLE"),
        (eligible_data(as_of=SCAN, oi_notional="6000000").model_copy(update={
            "open_interest": eligible_data(as_of=SCAN).open_interest.model_copy(update={"unit_validated": False,
                                                                                 "open_interest_notional_usdt": None})}),
         "OPEN_INTEREST_UNIT_UNVALIDATED", "WARMING"),
        (eligible_data(as_of=SCAN, event="VETO"), "VERIFIED_EVENT_VETO", "INELIGIBLE"),
        (eligible_data(as_of=SCAN, event="MISSING"), "EVENT_CLEARANCE_MISSING_OR_FUTURE", "WARMING"),
    ]
    for data, reason, state in cases:
        item = scan_universe({"ALTUSDT": data}, SCAN, Decimal("100000")).considered[0]
        assert item.state == state
        assert reason in item.reasons

    data = eligible_data(as_of=SCAN)
    thin_asks = data.depth.model_copy(update={"asks": (DepthLevel(price="100.01", quantity="100"),)})
    item = scan_universe({"ALTUSDT": data.model_copy(update={"depth": thin_asks})},
                         SCAN, Decimal("100000")).considered[0]
    assert item.state == "INELIGIBLE"
    assert item.ask_depth_usdt < Decimal("500000")
    assert item.bid_depth_usdt >= Decimal("500000")


def test_explicitly_unavailable_mandatory_feed_cannot_be_ready():
    data = eligible_data(as_of=SCAN)
    unavailable_ticker = data.ticker.model_copy(update={"readiness": "UNAVAILABLE"})
    item = scan_universe({"ALTUSDT": data.model_copy(update={"ticker": unavailable_ticker})},
                         SCAN, Decimal("100000")).considered[0]
    assert item.state == "UNAVAILABLE"
    assert item.eligible is False


def test_same_exchange_symbol_data_with_wrong_instrument_identity_is_degraded():
    data = eligible_data(as_of=SCAN)
    wrong_ticker = data.ticker.model_copy(update={
        "instrument_id": binance_usdm_instrument_id("ALTUSDT", "CURRENT_QUARTER", "USDT")
    })
    item = scan_universe({"ALTUSDT": data.model_copy(update={"ticker": wrong_ticker})},
                         SCAN, Decimal("100000")).considered[0]
    assert item.state == "DEGRADED"
    assert "OBSERVATION_INSTRUMENT_ID_MISMATCH" in item.reasons
    assert "TICKER_INSTRUMENT_ID_MISMATCH" in item.reasons
    assert item.turnover_usdt is None


def test_stale_event_clearance_does_not_count_as_verified_current_clearance():
    data = eligible_data(as_of=SCAN)
    stale = data.event_clearance.model_copy(update={"as_of": SCAN-timedelta(hours=2)})
    item = scan_universe({"ALTUSDT": data.model_copy(update={"event_clearance": stale})},
                         SCAN, Decimal("100000")).considered[0]
    assert item.state == "WARMING"
    assert "EVENT_CLEARANCE_STALE" in item.reasons


def test_out_of_order_spread_history_is_degraded_even_when_sorted_timestamps_cover():
    data = eligible_data(as_of=SCAN)
    item = scan_universe({"ALTUSDT": data.model_copy(update={
        "spread_samples": tuple(reversed(data.spread_samples))
    })}, SCAN, Decimal("100000")).considered[0]
    assert item.state == "DEGRADED"
    assert "SPREAD_SAMPLE_GAP_DUPLICATE_OR_ORDER" in item.reasons


def test_dynamic_shortlist_caps_at_15_and_records_exclusions_deterministically():
    symbols = {f"A{index:02d}USDT": eligible_data(f"A{index:02d}USDT", as_of=SCAN) for index in range(16)}
    symbols["BADUSDT"] = SymbolData(metadata=metadata("BADUSDT", status="BREAK"))
    first = scan_universe(symbols, SCAN, Decimal("100000"), limit=30)
    second = scan_universe(dict(reversed(list(symbols.items()))), SCAN, Decimal("100000"), limit=30)
    assert len(first.shortlist) == 15
    assert first.shortlist == second.shortlist
    assert "BADUSDT" not in first.shortlist
    statuses = {item.symbol: item.shortlist_status for item in first.considered}
    assert list(statuses.values()).count("SELECTED") == 15
    assert list(statuses.values()).count("RANKED_OUT_LIMIT") == 1
    assert statuses["BADUSDT"] == "NOT_ELIGIBLE"
    assert next(item for item in first.considered if item.symbol == "BADUSDT").reasons
