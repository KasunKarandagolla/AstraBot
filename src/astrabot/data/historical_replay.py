"""Causal, deterministic research snapshots over streamed source adapters.

This is an opt-in research interface.  The C02 production-facing spread gate
and eligibility policy are intentionally not changed here.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Iterable, Sequence

from astrabot.data.models import (
    DepthLevel,
    DepthSnapshot,
    MarkPriceObservation,
    OpenInterestObservation,
    SpreadSample,
    binance_usdm_instrument_id,
    config_hash,
    stable_id,
)
from astrabot.data.historical_sources import (
    BookObservation,
    DerivativeObservation,
    FeedDiagnostics,
    QuoteObservation,
    SOURCE_VERSION,
)
from astrabot.universe.eligibility import FreshnessPolicy
from astrabot.data.historical_evidence import LoadedEvidence, EvidenceValidation, validate_evidence

SAMPLER_VERSION = "c05g.periodic-spread.v1"
SAMPLER_CONFIG = {
    "version": SAMPLER_VERSION,
    "cadence_seconds": 60,
    "clock_anchor": "UTC minute boundaries; latest endpoint no later than decision_time",
    "window": "(endpoint-60s, endpoint]",
    "selection": "max(event_time, available_at, observation_id)",
    "causal_predicate": "event_time<=endpoint AND available_at<=endpoint",
    "no_forward_fill": True,
    "maximum_source_event_age_seconds": 60,
    "required_distinct_endpoints": 60,
    "maximum_median_spread_fraction": "0.001",
    "production_c02_policy_changed": False,
}
SAMPLER_CONFIG_HASH = config_hash(SAMPLER_CONFIG)
SOURCE_CONFIG_HASH = config_hash({
    "source_version": SOURCE_VERSION,
    "timestamp_fields": "integer_epoch_microseconds_utc",
    "arrival_interpretation": "provider_local_timestamp_arrival_proxy",
    "duplicate_rule": "disk_backed_exact_source_row_id",
    "tie_break": "event_time,available_at,observation_id",
})


_C02_FRESHNESS_DEFAULTS = FreshnessPolicy()


@dataclass(frozen=True)
class FreshnessLimits:
    """Research state freshness, defaulting to the existing C02 policy values."""

    quote: timedelta = _C02_FRESHNESS_DEFAULTS.spread
    depth: timedelta = _C02_FRESHNESS_DEFAULTS.depth
    open_interest_row: timedelta = _C02_FRESHNESS_DEFAULTS.open_interest


@dataclass(frozen=True)
class ResearchSnapshot:
    symbol: str
    decision_time: datetime
    latest_quote: SpreadSample | None
    periodic_spread_samples: tuple[SpreadSample, ...]
    spread_slots_expected: int
    spread_slots_occupied: int
    spread_sample_endpoints_distinct: int
    spread_median_fraction: Decimal | None
    spread_threshold_pass: bool
    spread_source_event_exact_minute_intervals: int
    latest_depth: DepthSnapshot | None
    depth_raw_bid_amount_within_0_20: Decimal | None
    depth_raw_ask_amount_within_0_20: Decimal | None
    depth_missing_bid_levels: int | None
    depth_missing_ask_levels: int | None
    latest_open_interest: OpenInterestObservation | None
    open_interest_raw_quantity: Decimal | None
    open_interest_row_age_seconds: Decimal | None
    open_interest_last_value_change_at: datetime | None
    open_interest_value_change_state: str
    open_interest_equal_value_run_length: int
    open_interest_age_since_value_change_seconds: Decimal | None
    mark_index: MarkPriceObservation | None
    reported_funding_timestamp: datetime | None
    reported_funding_rate: Decimal | None
    predicted_funding_rate: Decimal | None
    funding_settlement_status: str
    quote_event_age_seconds: Decimal | None
    quote_arrival_age_seconds: Decimal | None
    depth_event_age_seconds: Decimal | None
    depth_arrival_age_seconds: Decimal | None
    excluded_late_rows: dict[str, int]
    excluded_future_event_rows: dict[str, int]
    quality_blockers: tuple[str, ...]
    c02_eligibility: str
    economic_qualification: str
    evidence_validation: EvidenceValidation


def _utc(value: datetime, label: str) -> None:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be explicitly UTC")


def _selection_key(observation):
    return observation.event_time, observation.available_at, observation.observation_id


def _causal(observation, at: datetime) -> bool:
    return observation.event_time <= at and observation.available_at <= at


def _age_seconds(at: datetime, source_at: datetime | None) -> Decimal | None:
    if source_at is None:
        return None
    delta = at - source_at
    return Decimal(delta.days * 86_400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(1_000_000)


def _source_common(observation, *, decision_time: datetime, units: str,
                   quality: str = "VALID", readiness: str = "READY", identifier: str | None = None):
    return {
        "symbol": observation.symbol,
        "instrument_id": binance_usdm_instrument_id(observation.symbol),
        "event_time": observation.event_time,
        "available_at": observation.available_at,
        # Tardis local_timestamp is preserved as the only provider arrival proxy;
        # it is not represented as an AstraBot ingestion or execution timestamp.
        "ingested_at": observation.available_at,
        "as_of": decision_time,
        "data_source": f"TARDIS_BINANCE_FUTURES_{observation.source_dataset.upper()}",
        "source_version": SOURCE_VERSION,
        "units": units,
        "fidelity": "UNKNOWN",
        "readiness": readiness,
        "quality": quality,
        "observation_id": identifier or observation.observation_id,
        "config_hash": SOURCE_CONFIG_HASH,
        "source_sha256": observation.source_sha256,
        "source_record_number": observation.row_number,
        "ingestion_time_semantics": "PROVIDER_ARRIVAL_PROXY",
    }


def _spread_sample(observation: QuoteObservation, *, endpoint: datetime,
                   periodic: bool) -> SpreadSample:
    sample_id = stable_id(SAMPLER_VERSION, observation.observation_id, endpoint) if periodic else observation.observation_id
    return SpreadSample(
        **_source_common(
            observation, decision_time=endpoint,
            units="price source-reported; quote amount unit UNVERIFIED",
            identifier=sample_id,
        ),
        sampled_at=endpoint if periodic else None,
        bid_price=observation.bid_price,
        bid_quantity=observation.bid_amount,
        ask_price=observation.ask_price,
        ask_quantity=observation.ask_amount,
    )


def _book_snapshot(observation: BookObservation, *, decision_time: datetime,
                   base_multiplier: Decimal | None = None) -> DepthSnapshot:
    quality = "INCOMPLETE" if observation.quality == "INCOMPLETE" else "VALID"
    multiplier = base_multiplier if base_multiplier is not None else Decimal(1)
    return DepthSnapshot(
        **_source_common(
            observation, decision_time=decision_time,
            units="BASE_ASSET from historical evidence" if base_multiplier is not None else
                  "raw book amount; contract mapping UNVERIFIED",
            quality=quality,
            readiness="DEGRADED",
        ),
        last_update_id=None,
        bids=tuple(DepthLevel(price=level.price, quantity=level.amount * multiplier)
                   for level in observation.bids),
        asks=tuple(DepthLevel(price=level.price, quantity=level.amount * multiplier)
                   for level in observation.asks),
        quantity_unit="BASE_ASSET" if base_multiplier is not None else "UNVERIFIED_RAW_BOOK_AMOUNT",
        unit_validated=base_multiplier is not None,
    )


def _open_interest(observation: DerivativeObservation, *, decision_time: datetime,
                   validation: EvidenceValidation) -> OpenInterestObservation:
    assert observation.open_interest is not None
    return OpenInterestObservation(
        **_source_common(
            observation, decision_time=decision_time,
            units="BASE_ASSET from historical evidence; measurement status in evidence_validation"
                  if validation.oi_base_multiplier is not None else
                  "raw open_interest quantity; unit and measurement time UNVERIFIED",
            quality="UNKNOWN",
            readiness="DEGRADED",
        ),
        open_interest=observation.open_interest * (validation.oi_base_multiplier or Decimal(1)),
        quantity_unit="BASE_ASSET" if validation.oi_base_multiplier is not None else "UNVERIFIED_RAW_OPEN_INTEREST",
        reported_open_interest_value=None,
        open_interest_notional_usdt=validation.oi_notional_usdt,
        unit_validated=validation.oi_base_multiplier is not None,
        interval=None,
    )


def _mark_index(observation: DerivativeObservation, *, decision_time: datetime) -> MarkPriceObservation:
    assert observation.mark_price is not None
    return MarkPriceObservation(
        **_source_common(
            observation, decision_time=decision_time,
            units="source-reported mark/index price; historical contract metadata absent",
        ),
        mark_price=observation.mark_price,
        index_price=observation.index_price,
        funding_rate=observation.funding_rate,
        # funding_timestamp semantics are preserved separately; do not silently
        # label it as the next settlement boundary.
        next_funding_time=None,
    )


def _raw_depth_within(observation: BookObservation, threshold: Decimal) -> tuple[Decimal, Decimal]:
    mid = observation.mid_price
    bid_floor = mid * (Decimal(1) - threshold)
    ask_ceiling = mid * (Decimal(1) + threshold)
    bid_raw = sum((level.amount for level in observation.bids if level.price >= bid_floor), Decimal(0))
    ask_raw = sum((level.amount for level in observation.asks if level.price <= ask_ceiling), Decimal(0))
    return bid_raw, ask_raw


def _sample_endpoints(decisions: Sequence[datetime], count: int = 60) -> tuple[datetime, ...]:
    endpoints = {
        decision.replace(second=0, microsecond=0) - timedelta(minutes=offset)
        for decision in decisions
        for offset in range(count - 1, -1, -1)
    }
    return tuple(sorted(endpoints))


def replay_observations(
    *,
    symbol: str,
    decision_times: Sequence[datetime],
    quotes: Iterable[QuoteObservation],
    books: Iterable[BookObservation],
    derivatives: Iterable[DerivativeObservation],
    quote_diagnostics: FeedDiagnostics,
    book_diagnostics: FeedDiagnostics,
    derivative_diagnostics: FeedDiagnostics,
    freshness: FreshnessLimits | None = None,
    evidence: LoadedEvidence | None = None,
    synthetic: bool = False,
) -> tuple[ResearchSnapshot, ...]:
    """Replay one pass over each source, with output memory bounded by cutoffs.

    Decisions may be unordered; results return in caller order. Source files are
    never sorted, and source-order anomalies remain visible in diagnostics.
    """
    if not symbol or not decision_times:
        raise ValueError("symbol and at least one decision timestamp are required")
    for decision in decision_times:
        _utc(decision, "decision timestamp")
    if len(set(decision_times)) != len(decision_times):
        raise ValueError("decision timestamps must be distinct")
    policy = freshness or FreshnessLimits()
    decisions = tuple(decision_times)
    sorted_decisions = tuple(sorted(decisions))
    endpoints = _sample_endpoints(sorted_decisions)
    endpoint_index = {endpoint: index for index, endpoint in enumerate(endpoints)}
    sample_best: list[QuoteObservation | None] = [None] * len(endpoints)
    quote_best: dict[datetime, QuoteObservation | None] = dict.fromkeys(decisions)
    book_best: dict[datetime, BookObservation | None] = dict.fromkeys(decisions)
    oi_best: dict[datetime, DerivativeObservation | None] = dict.fromkeys(decisions)
    market_best: dict[datetime, DerivativeObservation | None] = dict.fromkeys(decisions)
    funding_best: dict[datetime, DerivativeObservation | None] = dict.fromkeys(decisions)
    late_counts = {decision: {"quotes": 0, "book_snapshot_25": 0, "derivative_ticker": 0} for decision in decisions}
    future_counts = {decision: {"quotes": 0, "book_snapshot_25": 0, "derivative_ticker": 0} for decision in decisions}

    def count_exclusions(observation, feed: str) -> None:
        event_index = bisect_left(sorted_decisions, observation.event_time)
        arrival_index = bisect_left(sorted_decisions, observation.available_at)
        for index in range(0, event_index):
            future_counts[sorted_decisions[index]][feed] += 1
        for index in range(event_index, arrival_index):
            late_counts[sorted_decisions[index]][feed] += 1

    for observation in quotes:
        if observation.symbol != symbol:
            continue
        if observation.quality != "VALID":
            continue
        start = bisect_left(sorted_decisions, max(observation.event_time, observation.available_at))
        count_exclusions(observation, "quotes")
        for index in range(start, len(sorted_decisions)):
            decision = sorted_decisions[index]
            current = quote_best[decision]
            if current is None or _selection_key(observation) > _selection_key(current):
                quote_best[decision] = observation
        # A quote may populate only endpoints in the strict one-minute source
        # age window and only after both event and provider arrival have passed.
        first = max(observation.event_time, observation.available_at)
        start = bisect_left(endpoints, first)
        stop = bisect_left(endpoints, observation.event_time + timedelta(seconds=60))
        for index in range(start, stop):
            endpoint = endpoints[index]
            if endpoint - observation.event_time > timedelta(seconds=60):
                continue
            current = sample_best[index]
            if current is None or _selection_key(observation) > _selection_key(current):
                sample_best[index] = observation

    for observation in books:
        if observation.symbol != symbol or observation.quality not in ("VALID", "INCOMPLETE"):
            continue
        start = bisect_left(sorted_decisions, max(observation.event_time, observation.available_at))
        count_exclusions(observation, "book_snapshot_25")
        for index in range(start, len(sorted_decisions)):
            decision = sorted_decisions[index]
            current = book_best[decision]
            if current is None or _selection_key(observation) > _selection_key(current):
                book_best[decision] = observation

    for observation in derivatives:
        if observation.symbol != symbol:
            continue
        start = bisect_left(sorted_decisions, max(observation.event_time, observation.available_at))
        count_exclusions(observation, "derivative_ticker")
        if observation.quality != "VALID":
            continue
        for index in range(start, len(sorted_decisions)):
            decision = sorted_decisions[index]
            if observation.open_interest is not None:
                current_oi = oi_best[decision]
                if current_oi is None or _selection_key(observation) > _selection_key(current_oi):
                    oi_best[decision] = observation
            if observation.mark_price is not None:
                current_market = market_best[decision]
                if current_market is None or _selection_key(observation) > _selection_key(current_market):
                    market_best[decision] = observation
            if observation.funding_rate is not None or observation.funding_timestamp is not None:
                current_funding = funding_best[decision]
                if current_funding is None or _selection_key(observation) > _selection_key(current_funding):
                    funding_best[decision] = observation

    snapshots: list[ResearchSnapshot] = []
    cutoff = Decimal("0.001")
    for decision in decisions:
        selected_samples = []
        latest_endpoint = decision.replace(second=0, microsecond=0)
        decision_endpoints = tuple(
            latest_endpoint - timedelta(minutes=offset) for offset in range(59, -1, -1)
        )
        for endpoint in decision_endpoints:
            quote = sample_best[endpoint_index[endpoint]]
            if quote is not None:
                # Samples have an independent periodic clock; event_time and
                # available_at remain original source timestamps.
                selected_samples.append(_spread_sample(quote, endpoint=endpoint, periodic=True))
        selected_samples_tuple = tuple(selected_samples)
        median_spread = (
            median([sample.spread_fraction for sample in selected_samples_tuple])
            if len(selected_samples_tuple) == 60
            else None
        )
        exact_intervals = sum(
            right.event_time - left.event_time == timedelta(minutes=1)
            for left, right in zip(selected_samples_tuple, selected_samples_tuple[1:])
        )
        endpoint_count = len({sample.sampled_at for sample in selected_samples_tuple})
        sample_pass = (
            len(selected_samples_tuple) == 60
            and endpoint_count == 60
            and len({sample.observation_id for sample in selected_samples_tuple}) == 60
            and median_spread is not None
            and median_spread <= cutoff
        )
        selected_quote = quote_best[decision]
        quote_sample = _spread_sample(selected_quote, endpoint=decision, periodic=False) if selected_quote else None

        selected_book = book_best[decision]
        selected_oi = oi_best[decision]
        validation = validate_evidence(evidence=evidence, symbol=symbol, decision_time=decision,
                                       synthetic=synthetic, book=selected_book, oi=selected_oi)
        depth = _book_snapshot(selected_book, decision_time=decision,
                               base_multiplier=validation.book_base_multiplier) if selected_book else None
        raw_bid = raw_ask = None
        if selected_book is not None:
            raw_bid, raw_ask = _raw_depth_within(selected_book, Decimal("0.002"))

        oi_contract = _open_interest(selected_oi, decision_time=decision, validation=validation) if selected_oi else None
        selected_market = market_best[decision]
        market_contract = _mark_index(selected_market, decision_time=decision) if selected_market else None
        selected_funding = funding_best[decision]

        quote_age = _age_seconds(decision, selected_quote.event_time if selected_quote else None)
        quote_arrival_age = _age_seconds(decision, selected_quote.available_at if selected_quote else None)
        depth_age = _age_seconds(decision, selected_book.event_time if selected_book else None)
        depth_arrival_age = _age_seconds(decision, selected_book.available_at if selected_book else None)
        oi_age = _age_seconds(decision, selected_oi.event_time if selected_oi else None)
        oi_change_age = _age_seconds(
            decision, selected_oi.last_open_interest_change_at if selected_oi else None
        )
        if selected_oi is None:
            oi_change_state = "MISSING"
        elif selected_oi.open_interest_changed_in_source is True:
            oi_change_state = "VALUE_CHANGED_BUT_REFRESH_TIME_UNVERIFIED"
        elif selected_oi.open_interest_changed_in_source is False:
            oi_change_state = "REPEATED_VALUE_NOT_A_CONFIRMED_REFRESH"
        else:
            oi_change_state = "FIRST_VALUE_NO_PRIOR_COMPARISON"

        blockers = {
            "HISTORICAL_INSTRUMENT_METADATA_MISSING",
            "CANDLE_CONTEXT_MISSING",
            "EVENT_CLEARANCE_UNVERIFIED",
            "OPEN_INTEREST_UNIT_UNVERIFIED",
            "OPEN_INTEREST_REFRESH_TIME_UNVERIFIED",
            "DEPTH_AMOUNT_UNIT_UNVERIFIED",
            "FUNDING_SETTLEMENT_STATUS_UNVERIFIED",
            "FUNDING_TIMESTAMP_SEMANTICS_UNVERIFIED",
            "FEED_COMPLETENESS_AND_CORRECTION_HISTORY_UNVERIFIED",
            "EXECUTABLE_FILL_AND_FEE_EVIDENCE_MISSING",
            "PERIODIC_SPREAD_SAMPLER_IS_RESEARCH_OPT_IN_ONLY",
        }
        evidence_blockers = {
            "historical_metadata": "HISTORICAL_INSTRUMENT_METADATA_MISSING",
            "oi_quantity_unit": "OPEN_INTEREST_UNIT_UNVERIFIED",
            "oi_measurement_time": "OPEN_INTEREST_REFRESH_TIME_UNVERIFIED",
            "book_quantity_unit": "DEPTH_AMOUNT_UNIT_UNVERIFIED",
        }
        for check, blocker in evidence_blockers.items():
            if validation.checks[check].status == "VERIFIED":
                blockers.discard(blocker)
        if validation.checks["oi_notional_conversion"].status != "VERIFIED":
            blockers.add("OPEN_INTEREST_NOTIONAL_UNVERIFIED")
        if validation.checks["book_notional_conversion"].status != "VERIFIED":
            blockers.add("DEPTH_NOTIONAL_UNVERIFIED")
        if selected_quote is None:
            blockers.add("QUOTE_MISSING")
        elif quote_age is not None and quote_age > Decimal(str(policy.quote.total_seconds())):
            blockers.add("QUOTE_STALE")
        if len(selected_samples_tuple) < 60:
            blockers.add("SPREAD_WARMUP_LT_60_PERIODIC_SLOTS")
        elif median_spread is not None and median_spread > cutoff:
            blockers.add("MEDIAN_SPREAD_ABOVE_0_10_PERCENT")
        if selected_book is None:
            blockers.add("DEPTH_MISSING")
        elif depth_age is not None and depth_age > Decimal(str(policy.depth.total_seconds())):
            blockers.add("DEPTH_STALE")
        elif selected_book.quality == "INCOMPLETE":
            blockers.add("DEPTH_LEVELS_INCOMPLETE")
        if selected_oi is None:
            blockers.add("OPEN_INTEREST_MISSING")
        elif oi_age is not None and oi_age > Decimal(str(policy.open_interest_row.total_seconds())):
            blockers.add("OPEN_INTEREST_TICKER_ROW_STALE")
        if quote_diagnostics.out_of_order:
            blockers.add("QUOTES_SOURCE_ORDER_ANOMALY")
        if quote_diagnostics.duplicates:
            blockers.add("QUOTES_DUPLICATE_SOURCE_ROWS_REJECTED")
        if quote_diagnostics.inverted_arrivals:
            blockers.add("QUOTES_INVERTED_ARRIVAL_ROWS_REJECTED")
        if book_diagnostics.out_of_order:
            blockers.add("BOOK_SOURCE_ORDER_ANOMALY")
        if book_diagnostics.duplicates:
            blockers.add("BOOK_DUPLICATE_SOURCE_ROWS_REJECTED")
        if book_diagnostics.inverted_arrivals:
            blockers.add("BOOK_INVERTED_ARRIVAL_ROWS_REJECTED")
        if book_diagnostics.invalid_books:
            blockers.add("INVALID_BOOK_ROWS_REJECTED")
        if book_diagnostics.incomplete_books:
            blockers.add("INCOMPLETE_BOOK_ROWS_OBSERVED")
        if derivative_diagnostics.out_of_order:
            blockers.add("DERIVATIVE_SOURCE_ORDER_ANOMALY")
        if derivative_diagnostics.duplicates:
            blockers.add("DERIVATIVE_DUPLICATE_SOURCE_ROWS_REJECTED")
        if derivative_diagnostics.inverted_arrivals:
            blockers.add("DERIVATIVE_INVERTED_ARRIVAL_ROWS_REJECTED")

        snapshots.append(ResearchSnapshot(
            symbol=symbol,
            decision_time=decision,
            latest_quote=quote_sample,
            periodic_spread_samples=selected_samples_tuple,
            spread_slots_expected=60,
            spread_slots_occupied=len(selected_samples_tuple),
            spread_sample_endpoints_distinct=endpoint_count,
            spread_median_fraction=median_spread,
            spread_threshold_pass=sample_pass,
            spread_source_event_exact_minute_intervals=exact_intervals,
            latest_depth=depth,
            depth_raw_bid_amount_within_0_20=raw_bid,
            depth_raw_ask_amount_within_0_20=raw_ask,
            depth_missing_bid_levels=selected_book.missing_bid_levels if selected_book else None,
            depth_missing_ask_levels=selected_book.missing_ask_levels if selected_book else None,
            latest_open_interest=oi_contract,
            open_interest_raw_quantity=selected_oi.open_interest if selected_oi else None,
            open_interest_row_age_seconds=oi_age,
            open_interest_last_value_change_at=selected_oi.last_open_interest_change_at if selected_oi else None,
            open_interest_value_change_state=oi_change_state,
            open_interest_equal_value_run_length=selected_oi.open_interest_repeat_run if selected_oi else 0,
            open_interest_age_since_value_change_seconds=oi_change_age,
            mark_index=market_contract,
            reported_funding_timestamp=selected_funding.funding_timestamp if selected_funding else None,
            reported_funding_rate=selected_funding.funding_rate if selected_funding else None,
            predicted_funding_rate=selected_funding.predicted_funding_rate if selected_funding else None,
            funding_settlement_status="UNVERIFIED_NOT_REPORTED_AS_SETTLED",
            quote_event_age_seconds=quote_age,
            quote_arrival_age_seconds=quote_arrival_age,
            depth_event_age_seconds=depth_age,
            depth_arrival_age_seconds=depth_arrival_age,
            excluded_late_rows=dict(late_counts[decision]),
            excluded_future_event_rows=dict(future_counts[decision]),
            quality_blockers=tuple(sorted(blockers)),
            c02_eligibility="NOT_READY_FAIL_CLOSED",
            economic_qualification="NOT_ASSESSED_INSUFFICIENT_EVIDENCE",
            evidence_validation=validation,
        ))
    return tuple(snapshots)


def causal_as_of(
    *, symbol: str, decision_time: datetime,
    quotes: Iterable[QuoteObservation], books: Iterable[BookObservation],
    derivatives: Iterable[DerivativeObservation],
    quote_diagnostics: FeedDiagnostics, book_diagnostics: FeedDiagnostics,
    derivative_diagnostics: FeedDiagnostics,
    freshness: FreshnessLimits | None = None,
    evidence: LoadedEvidence | None = None,
    synthetic: bool = False,
) -> ResearchSnapshot:
    """Single-cutoff convenience API over validated, streaming source iterables."""
    return replay_observations(
        symbol=symbol, decision_times=(decision_time,), quotes=quotes, books=books,
        derivatives=derivatives, quote_diagnostics=quote_diagnostics,
        book_diagnostics=book_diagnostics, derivative_diagnostics=derivative_diagnostics,
        freshness=freshness, evidence=evidence, synthetic=synthetic,
    )[0]
