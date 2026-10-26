"""Versioned, offline evidence checks; verification is scoped to supplied artifacts.

Pinned structured extracts are review inputs, not automatic authentication of a
publisher. No URL is fetched. Missing/unsupported evidence never implies a unit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from astrabot.contracts import Contract, ID, Positive, UTC
from astrabot.data.historical_sources import (
    BookObservation, DerivativeObservation, EXCHANGE, SOURCE_VERSION,
    HistoricalDataError, verify_source, sha256_file,
)
from astrabot.data.models import InstrumentMetadata, binance_usdm_instrument_id, config_hash

EVIDENCE_VERSION = "c05h.historical-evidence.v1"
CHECKS = ("historical_metadata", "oi_quantity_unit", "oi_measurement_time",
          "oi_notional_conversion", "book_quantity_unit", "book_notional_conversion")
Kind = Literal["metadata", "oi_unit", "oi_time", "book_unit"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class EvidenceReference(Contract):
    evidence_id: ID
    kind: Kind
    artifact: ID
    sha256: Digest
    pointer: str  # RFC 6901 JSON pointer to a structured extract in the artifact
    source_uri: ID
    source_locator: ID
    authority: Literal["VENUE", "PROVIDER", "SYNTHETIC_FIXTURE"]
    available_at: UTC  # when the supported claim was knowable, NOT retrieval time
    captured_at: UTC
    effective_from: UTC
    effective_to: UTC  # finite, half-open; no extrapolation from today's metadata
    exchange: Literal["binance-futures"]
    symbol: ID
    source_version: Literal["tardis-binance-futures-csv.v1"]
    dataset_sha256: Digest | None = None  # required for feed-specific claims

    @model_validator(mode="after")
    def times(self):
        if self.effective_to <= self.effective_from or self.captured_at < self.available_at:
            raise ValueError("invalid effective interval or capture before availability")
        return self


class EvidenceManifest(Contract):
    manifest_version: Literal["c05h.historical-evidence.v1"]
    synthetic: bool
    records: tuple[EvidenceReference, ...]

    @model_validator(mode="after")
    def unique_ids(self):
        if len({record.evidence_id for record in self.records}) != len(self.records):
            raise ValueError("duplicate evidence_id")
        return self


class QuantityEvidence(Contract):
    raw_unit: Literal["BASE_ASSET", "CONTRACTS"]
    base_asset: ID
    price_unit: Literal["USDT_PER_BASE_ASSET"]
    base_per_contract: Positive | None = None

    @model_validator(mode="after")
    def multiplier(self):
        if (self.raw_unit == "CONTRACTS") != (self.base_per_contract is not None):
            raise ValueError("only CONTRACTS requires base_per_contract")
        return self


class MeasurementEvidence(Contract):
    semantics: Literal["ROW_TIMESTAMP_IS_OI_MEASUREMENT"]
    # Carried-forward values, poll cadence and value changes do not satisfy this.
    timestamp_field: Literal["timestamp"]
    mark_price_semantics: Literal["ROW_TIMESTAMP_IS_MARK_MEASUREMENT"] | None = None


@dataclass(frozen=True)
class EvidenceCheck:
    status: str
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()


def _unverified(reason: str, ids=()) -> EvidenceCheck:
    return EvidenceCheck("UNVERIFIED", (reason,), tuple(sorted(ids)))


@dataclass(frozen=True)
class LoadedEvidence:
    manifest: EvidenceManifest
    manifest_sha256: str
    payloads: dict[str, object]
    errors: dict[str, str]


def _pointer(document, pointer: str):
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("pointer must be RFC 6901 JSON pointer")
    for part in pointer[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


def _json_without_duplicate_keys(value: str):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result
    return json.loads(value, object_pairs_hook=unique)


def load_evidence(path: Path) -> LoadedEvidence:
    """Invalid manifests abort; unusable individual artifacts remain UNVERIFIED."""
    try:
        source = path.read_text(encoding="utf-8")
        _json_without_duplicate_keys(source)
        manifest = EvidenceManifest.model_validate_json(source)
    except (OSError, ValueError) as exc:
        raise HistoricalDataError(f"invalid evidence manifest: {exc}") from exc
    payloads, errors = {}, {}
    root = path.resolve().parent
    for ref in manifest.records:
        try:
            artifact = (root / ref.artifact).resolve()
            if not artifact.is_relative_to(root):
                raise ValueError("artifact must stay inside evidence manifest directory")
            verify_source(artifact, ref.sha256)
            payloads[ref.evidence_id] = _pointer(_json_without_duplicate_keys(artifact.read_text(encoding="utf-8")), ref.pointer)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            errors[ref.evidence_id] = str(exc)
    return LoadedEvidence(manifest, sha256_file(path), payloads, errors)


@dataclass(frozen=True)
class EvidenceValidation:
    version: str
    manifest_sha256: str | None
    checks: dict[str, EvidenceCheck]
    metadata: InstrumentMetadata | None = None
    oi_base_multiplier: Decimal | None = None
    book_base_multiplier: Decimal | None = None
    oi_measurement_at: datetime | None = None
    oi_notional_usdt: Decimal | None = None
    book_bid_notional_usdt_within_0_20: Decimal | None = None
    book_ask_notional_usdt_within_0_20: Decimal | None = None


def validate_evidence(*, evidence: LoadedEvidence | None, symbol: str,
                      decision_time: datetime, synthetic: bool,
                      book: BookObservation | None = None,
                      oi: DerivativeObservation | None = None) -> EvidenceValidation:
    """Only the supported linear USDT-perpetual conversion is implemented."""
    if decision_time.utcoffset() != timedelta(0):
        raise ValueError("decision_time must be explicitly UTC")
    checks = {name: _unverified("EVIDENCE_NOT_SUPPLIED") for name in CHECKS}
    metadata = None

    def resolve(kind: str, at: datetime, digest: str | None, schema):
        if evidence is None:
            return None, _unverified("EVIDENCE_NOT_SUPPLIED")
        if evidence.manifest.synthetic != synthetic:
            return None, _unverified("SYNTHETIC_SCOPE_MISMATCH")
        refs = [ref for ref in evidence.manifest.records if ref.kind == kind
                and ref.symbol == symbol and ref.exchange == EXCHANGE
                and ref.source_version == SOURCE_VERSION
                and ref.effective_from <= at < ref.effective_to]
        if not refs:
            return None, _unverified("NO_EFFECTIVE_EVIDENCE")
        known_refs = [ref for ref in refs if ref.available_at <= decision_time]
        if not known_refs:
            return None, _unverified("EVIDENCE_NOT_KNOWN_AT_DECISION",
                                     (ref.evidence_id for ref in refs))
        ids = tuple(sorted(ref.evidence_id for ref in known_refs))
        values = []
        for ref in known_refs:
            expected_authority = "VENUE" if kind == "metadata" else "PROVIDER"
            if ref.authority != ("SYNTHETIC_FIXTURE" if synthetic else expected_authority):
                return None, _unverified("UNSUPPORTED_AUTHORITY", ids)
            if kind != "metadata" and (digest is None or ref.dataset_sha256 != digest):
                return None, _unverified("DATASET_HASH_MISMATCH", ids)
            if ref.evidence_id in evidence.errors:
                return None, _unverified("ARTIFACT_UNAVAILABLE_OR_INVALID", ids)
            try:
                values.append(schema.model_validate_json(json.dumps(evidence.payloads[ref.evidence_id])))
            except (ValidationError, ValueError, TypeError):
                return None, _unverified("UNSUPPORTED_OR_INCOMPLETE_CLAIM", ids)
        if len({config_hash(value.model_dump(mode="json")) for value in values}) != 1:
            return None, _unverified("CONTRADICTORY_EVIDENCE", ids)
        return values[0], EvidenceCheck("VERIFIED", (), ids)

    metadata, checks["historical_metadata"] = resolve("metadata", decision_time, None, InstrumentMetadata)
    if metadata is not None:
        required = (metadata.onboard_time, metadata.price_tick, metadata.quantity_step,
                    metadata.minimum_quantity, metadata.minimum_notional, metadata.contract_size)
        filters = {item.filter_type: item for item in metadata.filters}
        price, lot, market, notional = (filters.get(name) for name in
                                      ("PRICE_FILTER", "LOT_SIZE", "MARKET_LOT_SIZE", "MIN_NOTIONAL"))
        valid = (metadata.symbol == symbol
                 and metadata.instrument_id == binance_usdm_instrument_id(symbol)
                 and metadata.quote_asset == metadata.settle_asset == "USDT"
                 and symbol == metadata.base_asset + metadata.quote_asset
                 and metadata.contract_type == "PERPETUAL" and metadata.status == "TRADING"
                 and metadata.quality == "VALID" and metadata.readiness == "READY"
                 and metadata.fidelity == ("SYNTHETIC_FIXTURE" if synthetic else "VENUE_REPORTED")
                 and metadata.valid_at(decision_time) and metadata.event_time <= decision_time
                 and all(value is not None for value in required)
                 and metadata.onboard_time <= decision_time
                 and (metadata.delivery_time is None or decision_time < metadata.delivery_time)
                 and len(filters) == len(metadata.filters)
                 and all(item is not None for item in (price, lot, market, notional)))
        if valid:
            valid = (price.step_size == metadata.price_tick and lot.step_size == metadata.quantity_step
                     and lot.min_value == metadata.minimum_quantity and metadata.minimum_quantity > 0
                     and notional.min_value == metadata.minimum_notional
                     and market.min_value is not None and market.min_value > 0
                     and market.step_size is not None and market.step_size > 0
                     and all(item.min_value is not None and item.max_value is not None
                             and item.max_value >= item.min_value
                             for item in (price, lot, market)))
        if not valid:
            checks["historical_metadata"] = _unverified("METADATA_INCOMPLETE_OR_INCONSISTENT",
                                                        checks["historical_metadata"].evidence_ids)
            metadata = None

    def usable(observation):
        return (observation is not None and observation.symbol == symbol
                and observation.exchange == EXCHANGE
                and observation.event_time <= observation.available_at <= decision_time
                and observation.quality in ("VALID", "INCOMPLETE"))

    def unit(kind, observation):
        name = "oi_quantity_unit" if kind == "oi_unit" else "book_quantity_unit"
        if not usable(observation):
            checks[name] = _unverified("OBSERVATION_MISSING_OR_INVALID")
            return None
        value, checks[name] = resolve(kind, observation.event_time, observation.source_sha256, QuantityEvidence)
        if value is None:
            return None
        # Metadata must apply to the observed quantity as well as the decision.
        observed_metadata, observed_check = resolve("metadata", observation.event_time, None, InstrumentMetadata)
        if (metadata is None or observed_check.status != "VERIFIED" or observed_metadata != metadata
                or not metadata.valid_at(observation.event_time)
                or value.base_asset != metadata.base_asset
                or (value.raw_unit == "CONTRACTS" and value.base_per_contract != metadata.contract_size)):
            checks[name] = _unverified("HISTORICAL_METADATA_OR_MULTIPLIER_UNSUPPORTED", checks[name].evidence_ids)
            return None
        checks[name] = EvidenceCheck("VERIFIED", (), tuple(sorted(set(
            checks[name].evidence_ids + observed_check.evidence_ids))))
        return value.base_per_contract if value.raw_unit == "CONTRACTS" else Decimal(1)

    oi_factor = unit("oi_unit", oi)
    book_factor = unit("book_unit", book)
    measurement_at = oi_notional = bid_notional = ask_notional = None
    time_claim = None
    if not usable(oi) or oi.open_interest is None or oi.quality != "VALID":
        checks["oi_measurement_time"] = _unverified("OBSERVATION_MISSING")
    else:
        time_claim, checks["oi_measurement_time"] = resolve(
            "oi_time", oi.event_time, oi.source_sha256, MeasurementEvidence)
        if time_claim is not None:
            measurement_at = oi.event_time
    if (oi_factor is not None and measurement_at is not None and oi is not None
            and oi.open_interest is not None and oi.mark_price is not None and oi.mark_price > 0
            and time_claim.mark_price_semantics == "ROW_TIMESTAMP_IS_MARK_MEASUREMENT"):
        oi_notional = oi.open_interest * oi_factor * oi.mark_price
        checks["oi_notional_conversion"] = EvidenceCheck("VERIFIED", (), tuple(sorted(set(
            checks["oi_quantity_unit"].evidence_ids + checks["oi_measurement_time"].evidence_ids))))
    else:
        checks["oi_notional_conversion"] = _unverified("UNIT_MEASUREMENT_OR_SAME_ROW_MARK_UNSUPPORTED")
    if book_factor is not None and book is not None and book.quality == "VALID" and not (
            book.missing_bid_levels or book.missing_ask_levels):
        mid = book.mid_price
        bid_notional = sum((level.price * level.amount * book_factor for level in book.bids
                            if level.price >= mid * Decimal("0.998")), Decimal(0))
        ask_notional = sum((level.price * level.amount * book_factor for level in book.asks
                            if level.price <= mid * Decimal("1.002")), Decimal(0))
        checks["book_notional_conversion"] = EvidenceCheck(
            "VERIFIED", (), checks["book_quantity_unit"].evidence_ids)
    else:
        checks["book_notional_conversion"] = _unverified("UNIT_OR_COMPLETE_VALID_BOOK_UNSUPPORTED")
    return EvidenceValidation(EVIDENCE_VERSION, evidence.manifest_sha256 if evidence else None,
                              checks, metadata, oi_factor, book_factor, measurement_at,
                              oi_notional, bid_notional, ask_notional)
