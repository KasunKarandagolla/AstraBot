import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pytest
from astrabot.data.binance import BinancePublic, INTERVALS
from astrabot.data.replay import normalize_klines, normalize_agg_trades, checksum, candle_quality, trade_quality

FIXTURE=Path(__file__).parent/"fixtures/c02_binance/klines_synthetic.json"
ASOF=datetime(2026,10,24,0,15,tzinfo=timezone.utc)

def test_synthetic_klines_replay_closed_only_and_stable():
    raw=json.loads(FIXTURE.read_text())["records"]
    provenance=json.loads((FIXTURE.parent/"manifest.json").read_text())
    import hashlib
    assert provenance["synthetic"] is True
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()==provenance["retained_file_sha256"]
    bars=normalize_klines(raw,symbol="BTCUSDT",interval="5m",as_of=ASOF)
    assert len(bars)==2 and all(b.is_closed and b.confirmed_at(ASOF) for b in bars)
    assert bars[0].open.as_tuple().exponent == -1
    assert bars==normalize_klines(raw,symbol="BTCUSDT",interval="5m",as_of=ASOF)
    assert checksum(raw)==checksum(raw)

def test_transport_allowlist_and_input_bounds():
    api=BinancePublic(transport=lambda url,timeout: [])
    with pytest.raises(ValueError): api.get("/fapi/v1/order")
    with pytest.raises(ValueError): api.klines("BTCUSDT","1m")
    with pytest.raises(ValueError): api.agg_trades("BTCUSDT",limit=1001)
    with pytest.raises(ValueError): BinancePublic(max_pages=101)

def test_public_only_surface_exposes_no_signed_or_account_operations():
    from astrabot.data.binance import ENDPOINT_PARAMS
    api = BinancePublic(transport=lambda *_: [])
    assert all(path.startswith("/fapi/v1/") or path.startswith("/futures/data/")
               for path in ENDPOINT_PARAMS)
    assert not any(token in path.lower() for path in ENDPOINT_PARAMS
                   for token in ("/order", "/account", "listenkey", "userdatastream"))
    assert not any(hasattr(api, name) for name in ("sign", "place_order", "account", "user_trades"))
    with pytest.raises(ValueError): api.get("/fapi/v1/order", {"symbol":"BTCUSDT"})
    with pytest.raises(ValueError): api.get("/fapi/v2/account")

def test_agg_trade_buyer_maker_is_sell_aggressor():
    row={"a":7,"p":"10.0","q":"2.0","f":12,"l":13,"T":1792800000000,"m":True}
    captured=datetime.fromtimestamp(row["T"]/1000,timezone.utc)+timedelta(seconds=1)
    api=BinancePublic(transport=lambda url,timeout:[row],clock=lambda:captured)
    trade=api.agg_trades("BTCUSDT",as_of=captured)[0]
    assert trade.buyer_is_maker and trade.aggressor_side=="SELL" and str(trade.quote_quantity)=="20.00"
    assert trade.event_time < trade.available_at == trade.ingested_at

def test_quality_checks_duplicate_and_missing():
    raw=json.loads(FIXTURE.read_text())["records"]
    bars=normalize_klines([raw[0],raw[0],raw[1]],symbol="BTCUSDT",interval="5m",as_of=ASOF)
    # Replay normalization deduplicates nothing; all source records remain visible.
    assert len(bars)==3
    assert any(g.reason=="DUPLICATE" for g in candle_quality(bars))

def test_kline_pagination_uses_next_interval_and_distinct_capture_times():
    raw=json.loads(FIXTURE.read_text())["records"]
    calls=[]
    def transport(url,timeout):
        p=parse_qs(urlparse(url).query); calls.append(p)
        return [raw[0]] if len(calls)==1 else ([raw[1]] if len(calls)==2 else [])
    capture=datetime(2026,10,24,1,tzinfo=timezone.utc)
    api=BinancePublic(transport=transport,max_pages=3,clock=lambda:capture)
    bars=api.klines("BTCUSDT","5m",start_time=datetime.fromtimestamp(raw[0][0]/1000,timezone.utc),
                    limit=1,ingested_at=capture+timedelta(seconds=1))
    assert len(bars)==2 and int(calls[1]["startTime"][0])==raw[1][0]
    assert bars[0].event_time < bars[0].available_at == capture < bars[0].ingested_at

def test_exchange_info_never_backdates_capture_and_preserves_lot_filters():
    payload={"symbols":[{"symbol":"BTCUSDT","baseAsset":"BTC","quoteAsset":"USDT","marginAsset":"USDT","contractType":"PERPETUAL","status":"TRADING","onboardDate":0,"deliveryDate":4133404800000,"filters":[{"filterType":"LOT_SIZE","minQty":"0.001","maxQty":"100","stepSize":"0.001"}]}]}
    capture=datetime(2026,10,24,tzinfo=timezone.utc)
    result=BinancePublic(transport=lambda *_:payload,clock=lambda:capture).exchange_info(as_of=datetime(2020,1,1,tzinfo=timezone.utc))[0]
    assert result.effective_from==capture and result.minimum_quantity==Decimal("0.001")
    assert result.contract_size is None and result.filters[0].max_value==Decimal("100")

def test_open_interest_units_are_unvalidated_but_reported_history_value_preserved():
    def transport(url,timeout):
        if "/openInterestHist" in url: return [{"sumOpenInterest":"10","sumOpenInterestValue":"1234.50","timestamp":1792800000000}]
        return {"openInterest":"10","time":1792800000000}
    api=BinancePublic(transport=transport)
    current=api.open_interest("BTCUSDT"); hist=api.open_interest_history("BTCUSDT")[0]
    assert current.unit_validated is False and current.open_interest_notional_usdt is None
    assert hist.unit_validated is False and hist.open_interest_notional_usdt is None
    assert hist.reported_open_interest_value==Decimal("1234.50")
    assert hist.quantity_unit=="exchange_native_unvalidated"

def test_public_quote_depth_mark_index_and_funding_observations_keep_units():
    capture=datetime(2026,10,24,0,10,tzinfo=timezone.utc)
    payloads={
        "/fapi/v1/ticker/bookTicker":{"symbol":"ETHUSDT","bidPrice":"1999.5","bidQty":"2",
                                      "askPrice":"2000.5","askQty":"3","time":1792800000000},
        "/fapi/v1/depth":{"lastUpdateId":99,"bids":[["1999.5","2"]],"asks":[["2000.5","3"]]},
        "/fapi/v1/ticker/24hr":{"symbol":"ETHUSDT","openTime":1792713600000,
            "closeTime":1792800000000,"openPrice":"1900","highPrice":"2050","lowPrice":"1850",
            "lastPrice":"2000","volume":"100","quoteVolume":"200000","count":50},
        "/fapi/v1/premiumIndex":{"symbol":"ETHUSDT","time":1792800000000,"markPrice":"2000.1",
            "indexPrice":"1999.9","lastFundingRate":"0.0001","nextFundingTime":1792828800000},
        "/fapi/v1/fundingRate":[{"symbol":"ETHUSDT","fundingTime":1792771200000,"fundingRate":"0.0002"}],
    }
    queries=[]
    def transport(url, timeout):
        path=urlparse(url).path; queries.append((path,parse_qs(urlparse(url).query)))
        return payloads[path]
    api=BinancePublic(transport=transport,clock=lambda:capture)
    spread=api.book_ticker("ETHUSDT",as_of=capture)
    depth=api.depth("ETHUSDT",as_of=capture)
    ticker=api.ticker24h("ETHUSDT",as_of=capture)
    mark=api.mark_price("ETHUSDT",as_of=capture)
    funding=api.funding_history("ETHUSDT",start_time=capture-timedelta(hours=8),
                                end_time=capture,limit=100,as_of=capture)[0]
    assert spread.bid_price==Decimal("1999.5") and spread.ask_quantity==Decimal("3")
    assert depth.fidelity=="BOOK_L2" and depth.asks[0].quantity==Decimal("3")
    assert ticker.quote_volume==Decimal("200000")
    assert mark.mark_price==Decimal("2000.1") and mark.index_price==Decimal("1999.9")
    assert funding.funding_rate==Decimal("0.0002") and funding.is_settled
    query=dict(queries)["/fapi/v1/fundingRate"]
    assert query=={"symbol":["ETHUSDT"],"startTime":[str(int((capture-timedelta(hours=8)).timestamp()*1000))],
                   "endTime":[str(int(capture.timestamp()*1000))],"limit":["100"]}

def test_sensitive_params_rejected_and_rate_limits_retry_bounded():
    with pytest.raises(ValueError): BinancePublic().get("/fapi/v1/klines",{"timestamp":1})
    from urllib.error import HTTPError
    attempts=[]; delays=[]
    def transport(url,timeout):
        attempts.append(url)
        if len(attempts)==1: raise HTTPError(url,429,"rate limited",{"Retry-After":"2"},None)
        return []
    got=BinancePublic(transport=transport,sleep=delays.append).get("/fapi/v1/klines")
    assert got==[] and len(attempts)==2 and delays==[2.0]

def test_malformed_payload_fails_closed():
    api=BinancePublic(transport=lambda *_:"<html>not json")
    with pytest.raises(RuntimeError): api.klines("BTCUSDT","5m")
    timeout=BinancePublic(transport=lambda *_: (_ for _ in ()).throw(TimeoutError("offline")))
    with pytest.raises(RuntimeError): timeout.get("/fapi/v1/klines",{"symbol":"BTCUSDT"})

@pytest.mark.parametrize("interval,duration", INTERVALS.items())
def test_forming_candles_never_enter_confirmed_history(interval, duration):
    open_ms = 1792800000000
    row=[open_ms,"100","102","99","101","2.5",open_ms+duration-1,
         "251",12,"1","100","0"]
    close_boundary = datetime.fromtimestamp((open_ms+duration)/1000,timezone.utc)
    cutoff = close_boundary-timedelta(milliseconds=1)
    assert normalize_klines([row],symbol="BTCUSDT",interval=interval,as_of=cutoff) == ()
    complete = normalize_klines([row],symbol="BTCUSDT",interval=interval,as_of=close_boundary)
    assert len(complete)==1 and complete[0].confirmed_at(close_boundary)

def test_trade_quality_detects_duplicate_gap_and_out_of_order_records():
    row0={"a":10,"p":"10","q":"1","f":20,"l":20,"T":1792800000000,"m":False}
    row1={"a":11,"p":"10","q":"1","f":21,"l":21,"T":1792800001000,"m":False}
    as_of=datetime(2026,10,24,0,1,tzinfo=timezone.utc)
    two=normalize_agg_trades([row0,row1],symbol="BTCUSDT",as_of=as_of)
    dup=normalize_agg_trades([row0,row0],symbol="BTCUSDT",as_of=as_of)
    out=normalize_agg_trades([row1,row0],symbol="BTCUSDT",as_of=as_of)
    gap=normalize_agg_trades([row0,{**row1,"a":12}],symbol="BTCUSDT",as_of=as_of)
    assert trade_quality(two)==()
    assert any(x.reason=="DUPLICATE" for x in trade_quality(dup))
    assert any(x.reason=="OUT_OF_ORDER" for x in trade_quality(out))
    assert any(x.reason=="MISSING_INTERVAL" for x in trade_quality(gap))
