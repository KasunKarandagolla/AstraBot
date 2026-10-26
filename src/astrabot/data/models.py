"""Shared C02 market and feature contracts.

The shapes extend C01's strict Decimal/UTC conventions. They deliberately model
public observations only and do not carry account or order credentials.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from astrabot.contracts import Contract, ID, Money, Positive, Signed, UTC

Readiness = Literal["COLD", "WARMING", "READY", "DEGRADED", "UNAVAILABLE"]
Fidelity = Literal[
    "TRADE_EXACT",
    "TRADE_AGG",
    "BOOK_L2",
    "BAR_DERIVED_APPROX",
    "VENUE_REPORTED",
    "ESTIMATED",
    "UNKNOWN",
    "SYNTHETIC_FIXTURE",
]
Quality = Literal[
    "VALID",
    "GAP",
    "DUPLICATE",
    "OUT_OF_ORDER",
    "STALE",
    "INCOMPLETE",
    "MALFORMED",
    "CORRECTED",
    "UNKNOWN",
]
FeatureFamily = Annotated[str, Field(pattern=r"^A\d{2,}$")]
Interval = Literal["1m", "5m", "15m", "1h", "4h"]


def stable_id(*parts: object) -> str:
    """Create a deterministic opaque ID from normalized primitive parts."""
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def config_hash(value: dict[str, object]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def binance_usdm_instrument_id(
    symbol: str, contract_type: str = "PERPETUAL", settle_asset: str = "USDT"
) -> str:
    """Retain venue, contract kind, exchange symbol and settlement identity."""
    return f"BINANCE_USDM:{contract_type}:{symbol}:SETTLE:{settle_asset}"


class MarketObservation(Contract):
    """Common provenance and timing fields for normalized source observations."""

    symbol: ID
    instrument_id: ID
    venue: Literal["BINANCE_USDM"] = "BINANCE_USDM"
    event_time: UTC
    available_at: UTC
    ingested_at: UTC
    as_of: UTC
    data_source: ID
    source_version: ID
    units: ID
    fidelity: Fidelity
    readiness: Readiness
    quality: Quality = "VALID"
    observation_id: ID
    config_hash: ID
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    source_record_number: int | None = Field(default=None, ge=1)
    ingestion_time_semantics: Literal["SYSTEM_CAPTURE", "PROVIDER_ARRIVAL_PROXY", "UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def ordered_times(self):
        if self.available_at < self.event_time:
            raise ValueError("available_at cannot precede event_time")
        return self


class InstrumentFilter(Contract):
    filter_type: Literal["PRICE_FILTER", "LOT_SIZE", "MARKET_LOT_SIZE", "MIN_NOTIONAL"]
    min_value: Money | None = None
    max_value: Money | None = None
    step_size: Money | None = None


class InstrumentMetadata(MarketObservation):
    """Point-in-time exchange symbol snapshot, including original filters."""

    base_asset: ID
    quote_asset: ID
    settle_asset: ID
    contract_type: ID
    status: ID
    onboard_time: UTC | None = None
    delivery_time: UTC | None = None
    effective_from: UTC
    effective_to: UTC | None = None
    price_tick: Positive | None = None
    quantity_step: Positive | None = None
    minimum_quantity: Money | None = None
    minimum_notional: Money | None = None
    contract_size: Positive | None = None
    filters: tuple[InstrumentFilter, ...] = ()

    @model_validator(mode="after")
    def valid_interval_and_identity(self):
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("metadata validity interval must be positive")
        if self.instrument_id != binance_usdm_instrument_id(
            self.symbol, self.contract_type, self.settle_asset
        ):
            raise ValueError("instrument_id does not match Binance symbol identity")
        return self

    def valid_at(self, at: datetime) -> bool:
        return (
            self.effective_from <= at
            and (self.effective_to is None or at < self.effective_to)
            and self.available_at <= at
        )


class Candle(MarketObservation):
    interval: Interval
    open_time: UTC
    close_time: UTC
    open: Positive
    high: Positive
    low: Positive
    close: Positive
    base_volume: Money
    quote_volume: Money | None = None
    trade_count: int = Field(ge=0)
    is_closed: bool
    source_record_id: ID

    @model_validator(mode="after")
    def coherent_bar(self):
        if self.event_time != self.close_time:
            raise ValueError("candle event_time must be its exchange close_time")
        if self.close_time < self.open_time:
            raise ValueError("candle close precedes open")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("candle high is inconsistent")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("candle low is inconsistent")
        if self.available_at < self.close_time:
            raise ValueError("a candle cannot be available before its close")
        return self

    def confirmed_at(self, as_of: datetime) -> bool:
        return self.is_closed and self.close_time < as_of and self.available_at <= as_of

    @property
    def typical_price(self):
        return (self.high + self.low + self.close) / 3


class Trade(MarketObservation):
    trade_id: ID
    aggregate_trade_id: ID | None = None
    first_trade_id: ID | None = None
    last_trade_id: ID | None = None
    price: Positive
    base_quantity: Positive
    quote_quantity: Money
    buyer_is_maker: bool
    aggressor_side: Literal["BUY", "SELL"]

    @model_validator(mode="after")
    def maker_mapping(self):
        expected = "SELL" if self.buyer_is_maker else "BUY"
        if self.aggressor_side != expected:
            raise ValueError("Binance buyer-maker flag maps to the opposite aggressor side")
        return self


class Ticker24h(MarketObservation):
    open: Positive
    high: Positive
    low: Positive
    last: Positive
    base_volume: Money
    quote_volume: Money
    trade_count: int = Field(ge=0)
    window_start: UTC
    window_end: UTC

    @model_validator(mode="after")
    def valid_window(self):
        if self.window_start > self.window_end:
            raise ValueError("24-hour ticker window is inverted")
        return self


class SpreadSample(MarketObservation):
    # Populated only by the versioned C05-G periodic research sampler.  C02's
    # production-facing scanner continues to use event_time until separately
    # reviewed; sampled_at does not rewrite or replace that source timestamp.
    sampled_at: UTC | None = None
    bid_price: Positive
    bid_quantity: Money
    ask_price: Positive
    ask_quantity: Money

    @model_validator(mode="after")
    def non_crossed(self):
        if self.ask_price < self.bid_price:
            raise ValueError("crossed best bid/ask snapshot")
        if self.sampled_at is not None and (
            self.event_time > self.sampled_at or self.available_at > self.sampled_at
        ):
            raise ValueError("periodic sample cannot precede its source event or arrival")
        return self

    @property
    def mid_price(self):
        return (self.ask_price + self.bid_price) / 2

    @property
    def spread_fraction(self):
        return (self.ask_price - self.bid_price) / self.mid_price


class DepthLevel(Contract):
    price: Positive
    quantity: Money


class DepthSnapshot(MarketObservation):
    last_update_id: int | None = Field(default=None, ge=0)
    bids: tuple[DepthLevel, ...] = Field(min_length=1)
    asks: tuple[DepthLevel, ...] = Field(min_length=1)
    quantity_unit: ID = "UNKNOWN_RAW"
    unit_validated: bool = False

    @model_validator(mode="after")
    def ordered_sides(self):
        if any(a.price < b.price for a, b in zip(self.bids, self.bids[1:])):
            raise ValueError("bids must be sorted best to worst")
        if any(a.price > b.price for a, b in zip(self.asks, self.asks[1:])):
            raise ValueError("asks must be sorted best to worst")
        if self.asks[0].price < self.bids[0].price:
            raise ValueError("crossed depth snapshot")
        return self


class OpenInterestObservation(MarketObservation):
    open_interest: Positive
    quantity_unit: ID
    reported_open_interest_value: Money | None = None
    open_interest_notional_usdt: Money | None = None
    unit_validated: bool
    interval: str | None = None

    @model_validator(mode="after")
    def notional_requires_valid_unit(self):
        if self.open_interest_notional_usdt is not None and not self.unit_validated:
            raise ValueError("OI notional cannot be populated with unvalidated units")
        return self


class FundingObservation(MarketObservation):
    funding_rate: Signed
    funding_time: UTC
    is_settled: bool


class MarkPriceObservation(MarketObservation):
    mark_price: Positive
    index_price: Positive | None = None
    funding_rate: Signed | None = None
    next_funding_time: UTC | None = None


class DataGap(Contract):
    symbol: ID
    instrument_id: ID
    feed: ID
    start_time: UTC
    end_time: UTC
    reason: Literal["MISSING_INTERVAL", "STALE", "DUPLICATE", "OUT_OF_ORDER", "CORRECTION"]

    @model_validator(mode="after")
    def positive_gap(self):
        if self.end_time < self.start_time:
            raise ValueError("gap interval is inverted")
        return self


class FeedManifest(Contract):
    manifest_version: Literal["c02.feed-manifest.v1"] = "c02.feed-manifest.v1"
    feed: ID
    symbol: ID
    instrument_id: ID
    source: ID
    source_url: str
    archive_id: str | None = None
    source_version: ID
    start_time: UTC
    end_time: UTC
    record_count: int = Field(ge=0)
    checksum_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    missing_periods: tuple[DataGap, ...] = ()
    corrections: tuple[str, ...] = ()
    timestamp_interpretation: ID
    availability_assumption: ID
    original_units: ID
    fidelity: Fidelity
    normalization_version: ID
    synthetic: bool

    @model_validator(mode="after")
    def valid_manifest_range(self):
        if self.end_time < self.start_time:
            raise ValueError("manifest range is inverted")
        if any(g.symbol != self.symbol or g.feed != self.feed for g in self.missing_periods):
            raise ValueError("manifest gaps must belong to this feed and symbol")
        return self


class FeatureObservation(Contract):
    """Unified causal feature output used by later decision/research modules."""

    feature_family: FeatureFamily
    feature_name: ID
    symbol: ID
    instrument_id: ID
    venue: Literal["BINANCE_USDM"] = "BINANCE_USDM"
    event_time: UTC
    available_at: UTC
    ingested_at: UTC
    as_of: UTC
    data_source: ID
    source_version: ID
    feature_version: ID
    units: ID
    fidelity: Fidelity
    readiness: Readiness
    observation_id: ID
    config_hash: ID
    value: Decimal | str | int | float | bool | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None

    @model_validator(mode="after")
    def causal_availability(self):
        if self.available_at < self.event_time:
            raise ValueError("feature cannot be available before its event")
        if self.readiness == "UNAVAILABLE" and self.reason is None:
            raise ValueError("unavailable features require a precise reason")
        return self
