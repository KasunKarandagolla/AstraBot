"""S02 proposed research clocks. No scanner, strategy, network or order imports.

Hashes establish replay integrity against a separately pinned source, not vendor
authenticity, data rights, completeness, or a historical owner receipt.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Context, Decimal, localcontext
from itertools import islice
from statistics import median
from typing import Annotated, Iterable, Literal

from pydantic import Field

from astrabot.contracts import Contract, ID, Signed, UTC
from astrabot.data.models import binance_usdm_instrument_id, config_hash, stable_id
from astrabot.data.historical_sources import (
    EXCHANGE, QUOTE_HEADER, _source_row_id, epoch_microseconds, strict_decimal,
)

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SourceClass = Literal["NATIVE_BBO", "RECONSTRUCTED_L2_QUOTE"]
Scope = Literal["SYNTHETIC_ONLY", "ORIGINAL_SAMPLE_HASH_VERIFIED"]
Clock = Literal["PROVIDER_HISTORY", "OWNER_RECEIPT"]
VERSION = "proposed.c02.sample-clock.v2.0.0"
RESULT = "PROPOSED_C02_SAMPLE_CLOCK_V2_DIAGNOSTIC"


def _decimal_identity(value: Decimal):
    """Numeric identity independent of lexical zeros and caller precision."""
    if value == 0:
        return (0, (0,), 0)
    sign, digits, exponent = value.as_tuple()
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    return sign, tuple(digits), exponent


class FieldMeasurement(Contract):
    field: ID
    value: str | None = None
    unit: ID
    measured_at: UTC | None
    available_at: UTC | None
    evidence_id: ID | None


class MarketObservationV2(Contract):
    """Wire envelope; unknown field clocks stay null, never inherit row clocks."""

    schema_version: Literal["proposed.market-observation.v2.0.0"] = "proposed.market-observation.v2.0.0"
    symbol: ID
    instrument_id: ID
    venue: Literal["BINANCE_USDM"] = "BINANCE_USDM"
    source_class: Literal[
        "NATIVE_BBO", "RECONSTRUCTED_L2_QUOTE", "NATIVE_DEPTH_SEQUENCE",
        "PROVIDER_DERIVATIVE_TICKER", "VENUE_METADATA", "NATIVE_TICKER",
        "NEWS_EVENT", "FUNDING_SETTLEMENT", "ACCOUNT_EXECUTION", "NATIVE_CANDLE",
    ]
    scope: Scope
    source_sha256: Digest
    source_record_number: int = Field(ge=1)
    source_row_id: Digest
    exchange_event_time: UTC | None
    provider_arrival_time: UTC | None
    exchange_time_semantics: Literal["EXCHANGE_EVENT_RECORDED", "PROVIDER_FALLBACK", "UNVERIFIED"] = "UNVERIFIED"
    owner_arrival_time: UTC | None = None
    owner_receipt_evidence_id: ID | None = None
    field_measurements: tuple[FieldMeasurement, ...] = ()


class BBOObservationV2(MarketObservationV2):
    source_record_number: int = Field(ge=2)
    source_class: SourceClass
    source_dataset: Literal["quotes", "book_ticker"]
    # Native IDs must be independently mapped from an original venue payload.
    # Normalized CSV lacks them; the supplied CSV adapter never asserts one.
    native_event_id: ID | None = None
    raw_cells: tuple[str, ...] = Field(min_length=8, max_length=8)
    bid_price: Signed
    bid_quantity: Signed
    ask_price: Signed
    ask_quantity: Signed

    @property
    def event_identity(self) -> str:
        # Arrival/file/record are deliberately excluded: replaying the same event
        # under another arrival/row cannot manufacture a distinct observation.
        return stable_id(self.instrument_id, self.source_class,
                         self.native_event_id if self.native_event_id else (
                             self.exchange_event_time,
                             *(_decimal_identity(v) for v in (self.bid_price, self.bid_quantity,
                                                             self.ask_price, self.ask_quantity))))


class SampleClockV2(Contract):
    version: Literal["proposed.c02.sample-clock.v2.0.0"] = VERSION
    availability_clock: Clock = "PROVIDER_HISTORY"
    endpoint_count: Literal[60] = 60
    cadence_seconds: Literal[60] = 60
    maximum_event_age_seconds: Literal[60] = 60
    no_event_reuse: Literal[True] = True
    maximum_median_spread_fraction: Literal["0.001"] = "0.001"
    maximum_input_rows: Literal[100000] = 100000


class RowAudit(Contract):
    source_record_number: int
    source_row_id: str
    event_identity: str
    selected_endpoint: UTC | None
    reasons: tuple[str, ...]


class Slot(Contract):
    endpoint: UTC
    source_row_id: str | None
    source_record_number: int | None
    event_identity: str | None
    exchange_event_time: UTC | None
    provider_arrival_time: UTC | None
    owner_arrival_time: UTC | None
    bid_price: Signed | None
    ask_price: Signed | None
    event_age_microseconds: int | None
    state: Literal["SELECTED", "MISSING_EVIDENCE", "OBSERVED_REJECTED"]
    exclusion_counts: tuple[tuple[str, int], ...]


class SamplingDiagnostic(Contract):
    result: Literal["PROPOSED_C02_SAMPLE_CLOCK_V2_DIAGNOSTIC"] = RESULT
    clock: SampleClockV2
    config_sha256: Digest
    symbol: str
    instrument_id: str
    source_sha256: Digest
    source_class: SourceClass
    scope: Scope
    cutoff: UTC
    observations: tuple[BBOObservationV2, ...]
    rows: tuple[RowAudit, ...]
    slots: tuple[Slot, ...]
    selected_count: int
    median_spread_fraction: Signed | None
    proposed_spread_diagnostic_pass: bool
    latest_sample_fresh_at_cutoff: bool
    strict_v1_exact_event_intervals: int
    strict_v1_spread_diagnostic_pass: bool
    production_c02_eligibility: Literal["NOT_EVALUATED_UNCHANGED"] = "NOT_EVALUATED_UNCHANGED"


def quote_from_cells(cells: tuple[str, ...], *, source_sha256: str,
                     row_number: int, scope: Scope,
                     dataset: Literal["quotes", "book_ticker"] = "quotes") -> BBOObservationV2:
    """Small C05-G normalization wrapper; retains invalid chronology for audit."""
    if len(cells) != len(QUOTE_HEADER) or cells[0] != EXCHANGE:
        raise ValueError("invalid quote schema or exchange")
    return BBOObservationV2(
        symbol=cells[1], instrument_id=binance_usdm_instrument_id(cells[1]),
        source_class="RECONSTRUCTED_L2_QUOTE" if dataset == "quotes" else "NATIVE_BBO",
        scope=scope, source_sha256=source_sha256, source_record_number=row_number,
        source_row_id=_source_row_id(dataset, source_sha256, cells),
        source_dataset=dataset, raw_cells=cells,
        exchange_time_semantics="EXCHANGE_EVENT_RECORDED" if dataset == "quotes" else "UNVERIFIED",
        exchange_event_time=epoch_microseconds(cells[2], field_name="timestamp"),
        provider_arrival_time=epoch_microseconds(cells[3], field_name="local_timestamp"),
        bid_price=strict_decimal(cells[6], field_name="bid_price"),
        bid_quantity=strict_decimal(cells[7], field_name="bid_amount"),
        ask_price=strict_decimal(cells[5], field_name="ask_price"),
        ask_quantity=strict_decimal(cells[4], field_name="ask_amount"),
    )


def _static_reasons(row: BBOObservationV2, *, symbol, digest, source_class, scope):
    reasons = []
    if row.symbol != symbol or row.instrument_id != binance_usdm_instrument_id(symbol):
        reasons.append("SYMBOL_OR_INSTRUMENT_MISMATCH")
    if row.source_sha256 != digest or row.source_class != source_class or row.scope != scope:
        reasons.append("CROSS_SOURCE_OR_SCOPE_MISMATCH")
    try:
        original = quote_from_cells(row.raw_cells, source_sha256=row.source_sha256,
                                    row_number=row.source_record_number,
                                    scope=row.scope, dataset=row.source_dataset)
        fields = ("source_row_id", "symbol", "instrument_id", "exchange_event_time",
                  "provider_arrival_time", "bid_price", "bid_quantity", "ask_price",
                  "ask_quantity", "source_class")
        if any(getattr(original, key) != getattr(row, key) for key in fields):
            reasons.append("TAMPERED_NORMALIZATION_OR_ROW")
    except ValueError:
        reasons.append("TAMPERED_NORMALIZATION_OR_ROW")
    e, p, o = row.exchange_event_time, row.provider_arrival_time, row.owner_arrival_time
    if e is None:
        reasons.append("EXCHANGE_EVENT_TIME_UNKNOWN")
    if row.exchange_time_semantics != "EXCHANGE_EVENT_RECORDED":
        reasons.append("EXCHANGE_TIMESTAMP_ORIGIN_UNVERIFIED")
    if e and p and p < e or e and o and o < e or p and o and o < p:
        reasons.append("CONTRADICTORY_CLOCK_CHRONOLOGY")
    if row.bid_price <= 0 or row.ask_price <= row.bid_price or min(row.bid_quantity, row.ask_quantity) < 0:
        reasons.append("INVALID_OR_LOCKED_BBO")
    return tuple(reasons)


def endpoint_reasons(row: BBOObservationV2, endpoint: datetime, clock: SampleClockV2) -> tuple[str, ...]:
    """Temporal exclusions are public and independently reproducible per row/slot."""
    reasons = []
    e, p, o = row.exchange_event_time, row.provider_arrival_time, row.owner_arrival_time
    if e is None:
        reasons.append("EXCHANGE_EVENT_TIME_UNKNOWN")
    elif e > endpoint:
        reasons.append("FUTURE_EXCHANGE_EVENT")
    elif endpoint - e > timedelta(seconds=60):
        reasons.append("STALE_EVENT")
    if clock.availability_clock == "PROVIDER_HISTORY":
        if p is None:
            reasons.append("PROVIDER_ARRIVAL_UNKNOWN")
        elif p > endpoint:
            reasons.append("LATE_PROVIDER_ARRIVAL")
    else:
        if o is None or row.owner_receipt_evidence_id is None:
            reasons.append("OWNER_ARRIVAL_UNKNOWN")
        elif o > endpoint:
            reasons.append("LATE_OWNER_ARRIVAL")
        if p is not None and p > endpoint:
            reasons.append("LATE_PROVIDER_ARRIVAL")
    return tuple(reasons)


def _known_source_context(rows, static, identities, endpoint, clock):
    """Quarantine only contradictions actually knowable by this endpoint."""
    context = [list(s) for s in static]
    seen_rows, events, locators = set(), defaultdict(list), defaultdict(list)
    high_event = high_arrival = None
    for i, row in enumerate(rows):
        e, p, o = row.exchange_event_time, row.provider_arrival_time, row.owner_arrival_time
        available = p if clock.availability_clock == "PROVIDER_HISTORY" else (
            o if row.owner_receipt_evidence_id else None)
        if available is None or available > endpoint or e is None or e > endpoint:
            continue
        if static[i]:
            continue
        locators[(row.source_sha256, row.source_record_number)].append(i)
        if row.source_row_id in seen_rows:
            context[i].append("DUPLICATE_SOURCE_ROW")
        seen_rows.add(row.source_row_id)
        if high_event and e < high_event or high_arrival and p and p < high_arrival:
            context[i].append("OUT_OF_ORDER_SOURCE_CLOCKS")
        high_event = max(high_event, e) if high_event else e
        high_arrival = max(high_arrival, p) if high_arrival and p else p or high_arrival
        events[identities[i]].append(i)
    for indices in locators.values():
        if len({rows[i].source_row_id for i in indices}) > 1:
            for i in indices:
                context[i].append("CONFLICTING_SOURCE_LOCATOR")
    for indices in events.values():
        payloads = {(rows[i].exchange_event_time, rows[i].bid_price, rows[i].ask_price,
                     rows[i].bid_quantity, rows[i].ask_quantity) for i in indices}
        if len(payloads) > 1:
            for i in indices:
                context[i].append("CONFLICTING_EVENT_IDENTITY")
        else:
            for i in indices[1:]:
                context[i].append("DUPLICATE_EVENT_IDENTITY")
    return context


def sample_bbo(observations: Iterable[BBOObservationV2], *, symbol: str,
               source_sha256: str, source_class: SourceClass, scope: Scope,
               cutoff: datetime, clock: SampleClockV2 = SampleClockV2()) -> SamplingDiagnostic:
    """Pure bounded batch reduction. Ascending slots; never backtrack/reassign.

    Stable file ordinals, not Python iteration order, define source chronology.
    All offered rows and their exclusions remain in the returned evidence.
    """
    if cutoff.utcoffset() != timedelta(0):
        raise ValueError("cutoff must be explicitly UTC")
    rows = tuple(islice(observations, clock.maximum_input_rows + 1))
    if len(rows) > clock.maximum_input_rows:
        raise ValueError("bounded sampler input exceeds 100000 rows; partition input")
    rows = tuple(sorted(rows, key=lambda r: (r.source_record_number, r.source_row_id,
                                            r.model_dump_json())))
    static = [list(_static_reasons(r, symbol=symbol, digest=source_sha256,
                                  source_class=source_class, scope=scope)) for r in rows]
    identities = [r.event_identity for r in rows]
    final = cutoff.replace(second=0, microsecond=0)
    endpoints = tuple(final - timedelta(minutes=59-i) for i in range(60))
    used, selected, slots, row_reasons = set(), {}, [], [set(s) for s in static]
    for endpoint in endpoints:
        context = _known_source_context(rows, static, identities, endpoint, clock)
        eligible, counts = [], Counter()
        observed_near_slot = False
        for i, row in enumerate(rows):
            temporal = endpoint_reasons(row, endpoint, clock)
            exclusions = tuple(context[i]) + temporal
            if identities[i] in used:
                exclusions += ("EVENT_ALREADY_USED",)
            counts.update(set(exclusions))
            # Invalid rows in the slot are evidence, distinct from absent rows.
            if context[i] != static[i]:
                row_reasons[i].update(context[i])
            if row.exchange_event_time and endpoint - timedelta(seconds=60) <= row.exchange_event_time <= endpoint:
                observed_near_slot = True
                row_reasons[i].update(exclusions)
            if not exclusions:
                eligible.append(i)
        if eligible:
            # Equal exchange timestamps: provider/source order, then stable ID.
            index = max(eligible, key=lambda i: (rows[i].exchange_event_time,
                        rows[i].provider_arrival_time or rows[i].exchange_event_time,
                        rows[i].source_record_number, rows[i].source_row_id))
            row = rows[index]
            used.add(identities[index])
            selected[index] = endpoint
            age = endpoint - row.exchange_event_time
            slots.append(Slot(endpoint=endpoint, source_row_id=row.source_row_id,
                source_record_number=row.source_record_number, event_identity=identities[index],
                exchange_event_time=row.exchange_event_time, provider_arrival_time=row.provider_arrival_time,
                owner_arrival_time=row.owner_arrival_time, bid_price=row.bid_price, ask_price=row.ask_price,
                event_age_microseconds=(age.days*86400+age.seconds)*1000000+age.microseconds,
                state="SELECTED", exclusion_counts=tuple(sorted(counts.items()))))
        else:
            slots.append(Slot(endpoint=endpoint, source_row_id=None, source_record_number=None,
                event_identity=None, exchange_event_time=None, provider_arrival_time=None,
                owner_arrival_time=None, bid_price=None, ask_price=None, event_age_microseconds=None,
                state="OBSERVED_REJECTED" if observed_near_slot else "MISSING_EVIDENCE",
                exclusion_counts=tuple(sorted(counts.items()))))
    audits = []
    for i, row in enumerate(rows):
        if i not in selected:
            invalid = static[i] or any(r in row_reasons[i] for r in (
                "DUPLICATE_SOURCE_ROW", "DUPLICATE_EVENT_IDENTITY", "CONFLICTING_EVENT_IDENTITY",
                "CONFLICTING_SOURCE_LOCATOR", "OUT_OF_ORDER_SOURCE_CLOCKS"))
            row_reasons[i].add("NOT_SELECTED_NEWER_EVENT" if not invalid else "REJECTED_INVALID_OBSERVATION")
            if row.exchange_event_time and row.exchange_event_time > final:
                row_reasons[i].add("FUTURE_EXCHANGE_EVENT")
            elif row.exchange_event_time and row.exchange_event_time < endpoints[0] - timedelta(seconds=60):
                row_reasons[i].add("OUTSIDE_WINDOW_STALE_EVENT")
        audits.append(RowAudit(source_record_number=row.source_record_number,
            source_row_id=row.source_row_id, event_identity=identities[i],
            selected_endpoint=selected.get(i), reasons=tuple(sorted(row_reasons[i]))))
    chosen = [rows[i] for i in sorted(selected, key=selected.get)]
    exact = sum(r.exchange_event_time-l.exchange_event_time == timedelta(minutes=1)
                for l, r in zip(chosen, chosen[1:]))
    with localcontext(Context(prec=28)):
        statistic = median([(r.ask_price-r.bid_price)/((r.ask_price+r.bid_price)/2)
                            for r in chosen]) if len(chosen) == 60 else None
    fresh = bool(chosen) and cutoff - chosen[-1].exchange_event_time <= timedelta(seconds=60)
    passed = statistic is not None and statistic <= Decimal("0.001") and fresh
    return SamplingDiagnostic(clock=clock, config_sha256=config_hash(clock.model_dump(mode="json")),
        symbol=symbol, instrument_id=binance_usdm_instrument_id(symbol), source_sha256=source_sha256,
        source_class=source_class, scope=scope, cutoff=cutoff, observations=rows, rows=tuple(audits),
        slots=tuple(slots), selected_count=len(chosen), median_spread_fraction=statistic,
        proposed_spread_diagnostic_pass=passed, strict_v1_exact_event_intervals=exact,
        latest_sample_fresh_at_cutoff=fresh,
        strict_v1_spread_diagnostic_pass=passed and exact == 59)


# Both research callers use this exact reducer; no second selection algorithm.
scanner_diagnostic = sample_bbo
replay_diagnostic = sample_bbo
