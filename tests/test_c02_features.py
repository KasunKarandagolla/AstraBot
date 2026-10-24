from datetime import date, datetime, timezone, timedelta
from decimal import Decimal as D

from astrabot.data.models import Trade, Candle, binance_usdm_instrument_id
from astrabot.features.providers import cvd, session_vwap, smc_structure

UTC = timezone.utc

def trade(i, maker, qty, minute=1):
    t = datetime(2026, 1, 1, 0, minute, tzinfo=UTC)
    return Trade(symbol="BTCUSDT", instrument_id=binance_usdm_instrument_id("BTCUSDT"),
        event_time=t, available_at=t, ingested_at=t, as_of=t, data_source="fixture",
        source_version="fixture-v1", units="base", fidelity="TRADE_AGG", readiness="READY",
        observation_id=f"trade-{i}", config_hash="fixture", trade_id=str(i),
        aggregate_trade_id=str(i), first_trade_id=str(i), last_trade_id=str(i),
        price=D("100"), base_quantity=D(qty), quote_quantity=D("100")*D(qty),
        buyer_is_maker=maker, aggressor_side="SELL" if maker else "BUY")

def candle(i, minute, h, l, close, vol, day=date(2026, 1, 1)):
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(minutes=minute)
    close_time = start + timedelta(minutes=5) - timedelta(milliseconds=1)
    available = close_time + timedelta(milliseconds=1)
    return Candle(symbol="BTCUSDT", instrument_id=binance_usdm_instrument_id("BTCUSDT"),
        event_time=close_time, available_at=available, ingested_at=available, as_of=available, data_source="fixture",
        source_version="fixture-v1", units="base", fidelity="BAR_DERIVED_APPROX", readiness="READY",
        observation_id=f"candle-{i}", config_hash="fixture", interval="5m", open_time=start,
        close_time=close_time, open=max(D(l), min(D("100"), D(h))), high=D(h), low=D(l), close=D(close),
        base_volume=D(vol), trade_count=10, is_closed=True, source_record_id=f"k{i}")

def test_cvd_aggressor_side_signed_and_missing_coverage_not_zero():
    ts = [trade(10, False, "2"), trade(11, True, "0.5")]
    as_of = datetime(2026, 1, 1, 1, tzinfo=UTC)
    out = cvd(ts, as_of=as_of, coverage_complete=True, symbol="BTCUSDT",
              instrument_id=ts[0].instrument_id)
    assert out.value == D("1.5")
    assert out.readiness == "READY"
    assert out.fidelity == "TRADE_AGG"
    assert out.payload["trade_ids"] == ["10", "11"]
    assert out.payload["aggregate_trade_ids"] == ["10", "11"]
    assert cvd(ts, as_of=as_of, coverage_complete=False, symbol="BTCUSDT",
               instrument_id=ts[0].instrument_id).value is None
    empty = cvd([], as_of=as_of, coverage_complete=False, symbol="BTCUSDT",
                instrument_id=ts[0].instrument_id)
    assert empty.readiness == "WARMING" and empty.value is None
    gap = cvd([ts[0], trade(12, True, "1")], as_of=as_of, coverage_complete=True,
              symbol="BTCUSDT", instrument_id=ts[0].instrument_id)
    assert gap.readiness == "DEGRADED"
    assert "gap" in gap.reason.lower()
    out_of_order = cvd([ts[1], ts[0]], as_of=as_of, coverage_complete=True,
                       symbol="BTCUSDT", instrument_id=ts[0].instrument_id)
    assert out_of_order.readiness == "DEGRADED"
    duplicate = cvd([ts[0], ts[0]], as_of=as_of, coverage_complete=True,
                    symbol="BTCUSDT", instrument_id=ts[0].instrument_id)
    assert duplicate.readiness == "DEGRADED"

def test_vwap_numerical_closed_only_and_append_does_not_rewrite_prior_value():
    k1 = candle(1, 0, "110", "90", "100", "2")  # TP=100
    k2 = candle(2, 5, "130", "110", "120", "1") # TP=120
    future = candle(3, 10, "500", "400", "450", "100")
    as_of = datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
    old = session_vwap([k1, k2], as_of=as_of, symbol="BTCUSDT", instrument_id=k1.instrument_id)
    extended = session_vwap([k1, k2, future], as_of=as_of, symbol="BTCUSDT", instrument_id=k1.instrument_id)
    assert old.value == D(320) / D(3)
    assert extended.value == old.value
    assert old.fidelity == "BAR_DERIVED_APPROX"
    assert old.payload["anchor_id"] == "UTC:2026-01-01"
    gap = session_vwap([k1], as_of=as_of, symbol="BTCUSDT", instrument_id=k1.instrument_id)
    assert gap.readiness == "DEGRADED" and gap.value is None
    zero1 = candle(4, 0, "110", "90", "100", "0")
    zero2 = candle(5, 5, "130", "110", "120", "0")
    zero = session_vwap([zero1, zero2], as_of=as_of, symbol="BTCUSDT", instrument_id=k1.instrument_id)
    assert zero.readiness == "UNAVAILABLE" and zero.value is None

def test_vwap_rolls_at_utc_midnight_and_keeps_session_id():
    prior = candle(10, 1435, "900", "800", "850", "1000")
    current = candle(11, 0, "110", "90", "100", "2", day=date(2026, 1, 2))
    as_of = datetime(2026, 1, 2, 0, 5, tzinfo=UTC)
    out = session_vwap([prior, current], as_of=as_of, symbol="BTCUSDT",
                       instrument_id=current.instrument_id)
    assert out.value == D("100")
    assert out.payload["session_id"] == "UTC:2026-01-02"
    assert out.payload["candle_ids"] == ["k11"]

def test_smc_gate_is_explicitly_unavailable_with_qualification_path():
    k = candle(1, 0, "110", "90", "100", "2")
    as_of = datetime(2026, 1, 1, 1, tzinfo=UTC)
    out = smc_structure([k], as_of=as_of, symbol="BTCUSDT", instrument_id=k.instrument_id)
    assert out.readiness == "UNAVAILABLE"
    assert out.value is None
    assert "shift(-1)" in out.reason and "future mitigation" in out.reason
    assert "1b62fd6c41e1f508e7ed76831a039fa4c82d42f6" in out.source_version
    assert "55008a6dce09e0e36691d2e34150f0f499ac4f4b" in out.source_version
    assert out.payload["qualification_path"]
    future = candle(2, 5, "500", "400", "450", "100")
    extended = smc_structure([k, future], as_of=as_of, symbol="BTCUSDT", instrument_id=k.instrument_id)
    assert extended.readiness == "UNAVAILABLE" and extended.value is None
    assert out.reason == extended.reason
