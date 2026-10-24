"""Read-only public Binance USDⓈ-M market-data adapter.

The narrow transport uses only unauthenticated GET endpoints. It has no API-key
configuration, signing helper, account surface, or order methods. Historical
normalization/replay lives in ``replay.py`` and records its availability
assumptions explicitly.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import (
    Candle,
    DepthLevel,
    DepthSnapshot,
    FundingObservation,
    InstrumentFilter,
    InstrumentMetadata,
    MarkPriceObservation,
    OpenInterestObservation,
    SpreadSample,
    Ticker24h,
    Trade,
    binance_usdm_instrument_id,
    config_hash,
    stable_id,
)

BASE = "https://fapi.binance.com"
SOURCE = "binance_usdm_public_rest"
VERSION = "binance_public_v1"
INTERVALS = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
ENDPOINT_PARAMS = {
    "/fapi/v1/exchangeInfo": {"symbol"},
    "/fapi/v1/klines": {"symbol", "interval", "startTime", "endTime", "limit"},
    "/fapi/v1/aggTrades": {"symbol", "fromId", "startTime", "endTime", "limit"},
    "/fapi/v1/ticker/bookTicker": {"symbol"},
    "/fapi/v1/depth": {"symbol", "limit"},
    "/fapi/v1/ticker/24hr": {"symbol"},
    "/fapi/v1/openInterest": {"symbol"},
    "/futures/data/openInterestHist": {"symbol", "period", "limit", "startTime", "endTime"},
    "/fapi/v1/premiumIndex": {"symbol"},
    "/fapi/v1/fundingRate": {"symbol", "startTime", "endTime", "limit"},
}
SENSITIVE_PARAMS = {"signature", "timestamp", "recvwindow", "apikey", "x-mbx-apikey"}
SOURCE_CONFIG_HASH = config_hash({"transport": "stdlib-get-allowlist-v1"})


def _dt(milliseconds: int | str) -> datetime:
    return datetime.fromtimestamp(int(milliseconds) / 1000, timezone.utc)


def _decimal(value) -> Decimal:
    return Decimal(str(value))


def _interval_ms(value: datetime) -> int:
    if value.utcoffset() != timedelta(0):
        raise ValueError("explicit UTC timestamp required")
    return int(value.timestamp() * 1000)


def _base(symbol: str, contract_type: str = "PERPETUAL", settle_asset: str = "USDT") -> dict:
    return {
        "symbol": symbol,
        "instrument_id": binance_usdm_instrument_id(symbol, contract_type, settle_asset),
        "venue": "BINANCE_USDM",
        "data_source": SOURCE,
        "source_version": VERSION,
        "config_hash": SOURCE_CONFIG_HASH,
        "units": "exchange_native",
        "readiness": "READY",
    }


def _build_observation(
    model,
    fields: dict,
    *,
    event_time: datetime,
    available_at: datetime,
    ingested_at: datetime,
    as_of: datetime,
    fidelity: str = "VENUE_REPORTED",
    units: str = "exchange_native",
) -> object:
    values = _base(
        fields["symbol"],
        fields.get("contract_type", "PERPETUAL"),
        fields.get("settle_asset", "USDT"),
    )
    values.update(
        event_time=event_time,
        available_at=available_at,
        ingested_at=ingested_at,
        as_of=as_of,
        fidelity=fidelity,
        units=units,
        observation_id=stable_id(model.__name__, fields),
    )
    values.update(fields)
    return model(**values)


def _raw_agg_trade(
    row: dict,
    *,
    symbol: str,
    as_of: datetime,
    ingested_at: datetime,
    available_at: datetime | None = None,
) -> Trade:
    quantity = _decimal(row["q"])
    price = _decimal(row["p"])
    maker = row["m"]
    if not isinstance(maker, bool):
        raise ValueError("aggTrade buyer-maker flag must be boolean")
    fields = {
        "symbol": symbol,
        "trade_id": str(row["a"]),
        "aggregate_trade_id": str(row["a"]),
        "first_trade_id": str(row["f"]) if row.get("f") is not None else None,
        "last_trade_id": str(row["l"]) if row.get("l") is not None else None,
        "price": row["p"],
        "base_quantity": row["q"],
        "quote_quantity": str(price * quantity),
        "buyer_is_maker": maker,
        "aggressor_side": "SELL" if maker else "BUY",
    }
    event_time = _dt(row["T"])
    return _build_observation(
        Trade,
        fields,
        event_time=event_time,
        available_at=available_at or event_time,
        ingested_at=ingested_at,
        as_of=as_of,
        fidelity="TRADE_AGG",
        units="price=quote_per_base;quantity=base_asset;quote_quantity=quote_asset",
    )


class BinancePublic:
    """A bounded, unauthenticated public endpoint adapter."""

    def __init__(
        self,
        timeout: float = 10,
        max_pages: int = 20,
        transport=None,
        clock=None,
        sleep=None,
        max_retries: int = 2,
    ):
        if timeout <= 0 or not 1 <= max_pages <= 100:
            raise ValueError("positive timeout and page limit from 1 to 100 required")
        if not 0 <= max_retries <= 5:
            raise ValueError("retry bound must be between zero and five")
        self.timeout = timeout
        self.max_pages = max_pages
        self.transport = transport
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep or time.sleep
        self.max_retries = max_retries

    def get(self, path: str, params: dict | None = None):
        allowed = ENDPOINT_PARAMS.get(path)
        if allowed is None:
            raise ValueError("endpoint is not public allowlisted")
        params = params or {}
        if any(key.lower() in SENSITIVE_PARAMS for key in params):
            raise ValueError("sensitive/authentication parameter forbidden")
        if set(params) - allowed:
            raise ValueError("parameter is not valid for this public endpoint")
        url = BASE + path + ("?" + urlencode(params) if params else "")
        for attempt in range(self.max_retries + 1):
            try:
                if self.transport is not None:
                    payload = self.transport(url, self.timeout)
                else:
                    request = Request(url, headers={"User-Agent": "AstraBot-public-data/1"})
                    with urlopen(request, timeout=self.timeout) as response:
                        payload = json.loads(response.read())
                if isinstance(payload, (bytes, str)):
                    payload = json.loads(payload)
                if not isinstance(payload, (list, dict)):
                    raise ValueError("malformed exchange payload")
                if isinstance(payload, dict):
                    code = payload.get("code", 0)
                    if not isinstance(code, int) or code < 0:
                        raise ValueError("exchange error response")
                return payload
            except HTTPError as error:
                if error.code not in (418, 429) or attempt >= self.max_retries:
                    raise RuntimeError("Binance public request failed") from error
                try:
                    retry_after = float(error.headers.get("Retry-After", "1"))
                except (AttributeError, TypeError, ValueError):
                    retry_after = 1.0
                self.sleep(max(0.0, min(retry_after, 30.0)))
            except (URLError, TimeoutError, OSError, json.JSONDecodeError, TypeError, KeyError, IndexError, ValueError) as error:
                raise RuntimeError("Binance public request failed or returned malformed data") from error
        raise RuntimeError("Binance public retry budget exhausted")

    def exchange_info(self, symbol: str | None = None, *, as_of: datetime | None = None) -> tuple[InstrumentMetadata, ...]:
        capture = self.clock()
        payload = self.get("/fapi/v1/exchangeInfo", {"symbol": symbol} if symbol else {})
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise RuntimeError("malformed exchangeInfo response")
        decision_time = as_of or capture
        observations = []
        for raw in payload["symbols"]:
            if symbol and raw.get("symbol") != symbol:
                continue
            contract_type = raw["contractType"]
            settle_asset = raw["marginAsset"]
            filters = []
            values = {}
            for item in raw.get("filters", []):
                kind = item.get("filterType")
                if kind == "PRICE_FILTER":
                    values["price_tick"] = item.get("tickSize")
                    filters.append(InstrumentFilter(
                        filter_type=kind, min_value=item.get("minPrice"),
                        max_value=item.get("maxPrice"), step_size=item.get("tickSize"),
                    ))
                elif kind in ("LOT_SIZE", "MARKET_LOT_SIZE"):
                    filters.append(InstrumentFilter(
                        filter_type=kind, min_value=item.get("minQty"),
                        max_value=item.get("maxQty"), step_size=item.get("stepSize"),
                    ))
                    if kind == "LOT_SIZE":
                        values["quantity_step"] = item.get("stepSize")
                        values["minimum_quantity"] = item.get("minQty")
                elif kind == "MIN_NOTIONAL":
                    values["minimum_notional"] = item.get("notional")
                    filters.append(InstrumentFilter(filter_type=kind, min_value=item.get("notional")))
            fields = {
                "symbol": raw["symbol"],
                "instrument_id": binance_usdm_instrument_id(raw["symbol"], contract_type, settle_asset),
                "base_asset": raw["baseAsset"],
                "quote_asset": raw["quoteAsset"],
                "settle_asset": settle_asset,
                "contract_type": contract_type,
                "status": raw["status"],
                "onboard_time": _dt(raw["onboardDate"]) if raw.get("onboardDate") else None,
                "delivery_time": _dt(raw["deliveryDate"]) if raw.get("deliveryDate") else None,
                "effective_from": capture,
                "effective_to": None,
                "price_tick": values.get("price_tick"),
                "quantity_step": values.get("quantity_step"),
                "minimum_quantity": values.get("minimum_quantity"),
                "minimum_notional": values.get("minimum_notional"),
                "contract_size": None,
                "filters": tuple(filters),
            }
            observations.append(_build_observation(
                InstrumentMetadata, fields, event_time=capture, available_at=capture,
                ingested_at=capture, as_of=decision_time,
                units="filter_values=exchange_native_decimal",
            ))
        return tuple(observations)

    def klines(
        self,
        symbol: str,
        interval: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
        *,
        as_of: datetime | None = None,
        ingested_at: datetime | None = None,
        availability_mode: Literal["OBSERVED", "EXCHANGE_CLOSE_PROXY"] = "OBSERVED",
    ) -> tuple[Candle, ...]:
        if interval not in INTERVALS or not 1 <= limit <= 1500:
            raise ValueError("unsupported interval or limit")
        if availability_mode not in ("OBSERVED", "EXCHANGE_CLOSE_PROXY"):
            raise ValueError("unknown candle availability mode")
        if start_time and end_time and start_time > end_time:
            raise ValueError("start_time must not follow end_time")
        cursor = _interval_ms(start_time) if start_time else None
        end_ms = _interval_ms(end_time) if end_time else None
        raw_records = []
        for _ in range(self.max_pages):
            params = {"symbol": symbol, "interval": interval, "limit": limit}
            if cursor is not None:
                params["startTime"] = cursor
            if end_ms is not None:
                params["endTime"] = end_ms
            page = self.get("/fapi/v1/klines", params)
            if not isinstance(page, list) or any(not isinstance(row, list) or len(row) < 9 for row in page):
                raise RuntimeError("malformed kline page")
            raw_records.extend(page)
            if len(page) < limit or not page or cursor is None:
                break
            next_cursor = int(page[-1][0]) + INTERVALS[interval]
            if next_cursor <= cursor or (end_ms is not None and next_cursor > end_ms):
                break
            cursor = next_cursor

        capture = self.clock()
        pipeline_ingestion = ingested_at or capture
        if pipeline_ingestion < capture:
            raise ValueError("ingested_at cannot precede endpoint observation time")
        decision_time = as_of or capture
        observations = []
        for row in raw_records:
            close_time = _dt(row[6])
            exchange_close_available = close_time + timedelta(milliseconds=1)
            available_at = (max(exchange_close_available, capture)
                            if availability_mode == "OBSERVED" else exchange_close_available)
            if available_at > decision_time:
                continue
            fields = {
                "symbol": symbol,
                "interval": interval,
                "open_time": _dt(row[0]),
                "close_time": close_time,
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "base_volume": row[5],
                "quote_volume": row[7],
                "trade_count": int(row[8]),
                "is_closed": True,
                "source_record_id": str(row[0]),
            }
            observations.append(_build_observation(
                Candle, fields, event_time=close_time, available_at=available_at,
                ingested_at=pipeline_ingestion, as_of=decision_time,
                units="price=quote_per_base;base_volume=base_asset;quote_volume=quote_asset",
            ))
        return tuple(observations)

    def agg_trades(
        self,
        symbol: str,
        from_id: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
        *,
        as_of: datetime | None = None,
        ingested_at: datetime | None = None,
    ) -> tuple[Trade, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be from 1 to 1000")
        if from_id is not None and start_time is not None:
            raise ValueError("fromId and startTime are mutually exclusive")
        if start_time and end_time and start_time > end_time:
            raise ValueError("start_time must not follow end_time")
        cursor_id = from_id
        cursor_time = _interval_ms(start_time) if start_time else None
        end_ms = _interval_ms(end_time) if end_time else None
        raw_records = []
        for _ in range(self.max_pages):
            params = {"symbol": symbol, "limit": limit}
            if cursor_id is not None:
                params["fromId"] = cursor_id
            elif cursor_time is not None:
                params["startTime"] = cursor_time
            if end_ms is not None:
                params["endTime"] = end_ms
            page = self.get("/fapi/v1/aggTrades", params)
            required = {"a", "p", "q", "f", "l", "T", "m"}
            if not isinstance(page, list) or any(not isinstance(row, dict) or not required <= row.keys() for row in page):
                raise RuntimeError("malformed aggTrades page")
            raw_records.extend(page)
            if len(page) < limit or not page:
                break
            next_id = int(page[-1]["a"]) + 1
            if cursor_id is not None and next_id <= cursor_id:
                raise RuntimeError("aggTrades pagination did not advance")
            if end_ms is not None and int(page[-1]["T"]) >= end_ms:
                break
            cursor_id = next_id
            cursor_time = None

        capture = self.clock()
        pipeline_ingestion = ingested_at or capture
        if pipeline_ingestion < capture:
            raise ValueError("ingested_at cannot precede endpoint observation time")
        decision_time = as_of or capture
        trades = []
        for row in raw_records:
            event_time = _dt(row["T"])
            if capture > decision_time or event_time > capture or event_time > decision_time:
                continue
            trade = _raw_agg_trade(row, symbol=symbol, as_of=decision_time,
                                   ingested_at=pipeline_ingestion, available_at=capture)
            if trade.available_at > decision_time or trade.event_time > decision_time:
                continue
            if end_time is not None and trade.event_time > end_time:
                continue
            trades.append(trade)
        return tuple(trades)

    def book_ticker(self, symbol: str, *, as_of: datetime | None = None) -> SpreadSample:
        capture = self.clock()
        raw = self.get("/fapi/v1/ticker/bookTicker", {"symbol": symbol})
        event_time = _dt(raw["time"]) if isinstance(raw, dict) and raw.get("time") else capture
        fields = {
            "symbol": symbol,
            "bid_price": raw["bidPrice"], "bid_quantity": raw["bidQty"],
            "ask_price": raw["askPrice"], "ask_quantity": raw["askQty"],
        }
        return _build_observation(
            SpreadSample, fields, event_time=event_time, available_at=capture,
            ingested_at=capture, as_of=as_of or capture,
            units="price=quote_per_base;quantity=base_asset",
        )

    def depth(self, symbol: str, limit: int = 100, *, as_of: datetime | None = None) -> DepthSnapshot:
        if limit not in (5, 10, 20, 50, 100, 500, 1000):
            raise ValueError("unsupported depth limit")
        capture = self.clock()
        raw = self.get("/fapi/v1/depth", {"symbol": symbol, "limit": limit})
        fields = {
            "symbol": symbol,
            "last_update_id": raw["lastUpdateId"],
            "bids": tuple(DepthLevel(price=price, quantity=quantity) for price, quantity in raw["bids"]),
            "asks": tuple(DepthLevel(price=price, quantity=quantity) for price, quantity in raw["asks"]),
        }
        return _build_observation(
            DepthSnapshot, fields, event_time=capture, available_at=capture,
            ingested_at=capture, as_of=as_of or capture, fidelity="BOOK_L2",
            units="price=quote_per_base;quantity=base_asset",
        )

    def ticker24h(self, symbol: str, *, as_of: datetime | None = None) -> Ticker24h:
        capture = self.clock()
        raw = self.get("/fapi/v1/ticker/24hr", {"symbol": symbol})
        event_time = _dt(raw["closeTime"])
        fields = {
            "symbol": symbol, "open": raw["openPrice"], "high": raw["highPrice"],
            "low": raw["lowPrice"], "last": raw["lastPrice"],
            "base_volume": raw["volume"], "quote_volume": raw["quoteVolume"],
            "trade_count": int(raw["count"]), "window_start": _dt(raw["openTime"]),
            "window_end": event_time,
        }
        return _build_observation(
            Ticker24h, fields, event_time=event_time, available_at=capture,
            ingested_at=capture, as_of=as_of or capture,
            units="price=quote_per_base;base_volume=base_asset;quote_volume=quote_asset",
        )

    def open_interest(self, symbol: str, *, as_of: datetime | None = None) -> OpenInterestObservation:
        capture = self.clock()
        raw = self.get("/fapi/v1/openInterest", {"symbol": symbol})
        fields = {
            "symbol": symbol, "open_interest": raw["openInterest"],
            "quantity_unit": "exchange_reported_unvalidated",
            "open_interest_notional_usdt": None, "unit_validated": False,
        }
        return _build_observation(
            OpenInterestObservation, fields, event_time=_dt(raw["time"]),
            available_at=capture, ingested_at=capture, as_of=as_of or capture,
            units="open_interest=exchange_native;notional_usdt=unavailable",
        )

    def open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 500,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        *,
        as_of: datetime | None = None,
    ) -> tuple[OpenInterestObservation, ...]:
        if period not in {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}:
            raise ValueError("unsupported OI history period")
        if not 1 <= limit <= 500:
            raise ValueError("OI history limit must be from 1 to 500")
        cursor = _interval_ms(start_time) if start_time else None
        end_ms = _interval_ms(end_time) if end_time else None
        if cursor is not None and end_ms is not None and cursor > end_ms:
            raise ValueError("start_time must not follow end_time")
        rows = []
        for _ in range(self.max_pages):
            params = {"symbol": symbol, "period": period, "limit": limit}
            if cursor is not None:
                params["startTime"] = cursor
            if end_ms is not None:
                params["endTime"] = end_ms
            page = self.get("/futures/data/openInterestHist", params)
            if not isinstance(page, list) or any(not isinstance(row, dict) or "sumOpenInterest" not in row or "timestamp" not in row for row in page):
                raise RuntimeError("malformed open interest history")
            rows.extend(page)
            if len(page) < limit or not page or cursor is None:
                break
            next_cursor = int(page[-1]["timestamp"]) + 1
            if next_cursor <= cursor or (end_ms is not None and next_cursor > end_ms):
                break
            cursor = next_cursor
        capture = self.clock()
        decision_time = as_of or capture
        observations = []
        for row in rows:
            fields = {
                "symbol": symbol,
                "open_interest": row["sumOpenInterest"],
                "quantity_unit": "exchange_native_unvalidated",
                "reported_open_interest_value": row.get("sumOpenInterestValue"),
                "open_interest_notional_usdt": None,
                "unit_validated": False,
                "interval": period,
            }
            observations.append(_build_observation(
                OpenInterestObservation, fields, event_time=_dt(row["timestamp"]),
                available_at=capture, ingested_at=capture, as_of=decision_time,
                units="open_interest=exchange_native;reported_value=venue_native_unit_unspecified",
            ))
        return tuple(observations)

    def mark_price(self, symbol: str, *, as_of: datetime | None = None) -> MarkPriceObservation:
        capture = self.clock()
        raw = self.get("/fapi/v1/premiumIndex", {"symbol": symbol})
        fields = {
            "symbol": symbol, "mark_price": raw["markPrice"],
            "index_price": raw["indexPrice"], "funding_rate": raw["lastFundingRate"],
            "next_funding_time": _dt(raw["nextFundingTime"]),
        }
        return _build_observation(
            MarkPriceObservation, fields, event_time=_dt(raw["time"]),
            available_at=capture, ingested_at=capture, as_of=as_of or capture,
            units="price=quote_per_base;funding_rate=fraction",
        )

    def funding_history(
        self,
        symbol: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
        *,
        as_of: datetime | None = None,
    ) -> tuple[FundingObservation, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("funding history limit must be from 1 to 1000")
        cursor = _interval_ms(start_time) if start_time else None
        end_ms = _interval_ms(end_time) if end_time else None
        rows = []
        for _ in range(self.max_pages):
            params = {"symbol": symbol, "limit": limit}
            if cursor is not None:
                params["startTime"] = cursor
            if end_ms is not None:
                params["endTime"] = end_ms
            page = self.get("/fapi/v1/fundingRate", params)
            if not isinstance(page, list) or any(not isinstance(row, dict) or "fundingTime" not in row or "fundingRate" not in row for row in page):
                raise RuntimeError("malformed funding history")
            rows.extend(page)
            if len(page) < limit or not page or cursor is None:
                break
            next_cursor = int(page[-1]["fundingTime"]) + 1
            if next_cursor <= cursor or (end_ms is not None and next_cursor > end_ms):
                break
            cursor = next_cursor
        capture = self.clock()
        decision_time = as_of or capture
        return tuple(_build_observation(
            FundingObservation,
            {"symbol": symbol, "funding_rate": row["fundingRate"],
             "funding_time": _dt(row["fundingTime"]), "is_settled": True},
            event_time=_dt(row["fundingTime"]), available_at=capture,
            ingested_at=capture, as_of=decision_time, units="funding_rate=fraction",
        ) for row in rows)
