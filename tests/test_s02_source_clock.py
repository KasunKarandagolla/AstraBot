"""Independent boundary/oracle tests for the proposed sampler, never policy tests."""
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, localcontext
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

from astrabot.data.historical_sources import verify_source, HistoricalDataError
from astrabot.data.models import SpreadSample
from astrabot.data.source_clock import (
    BBOObservationV2, FieldMeasurement, SampleClockV2, endpoint_reasons, quote_from_cells,
    replay_diagnostic, sample_bbo, scanner_diagnostic,
)
from astrabot.universe.eligibility import scan_universe
from test_c02_universe import eligible_data

ROOT = Path(__file__).resolve().parents[1]
T = datetime(2024, 10, 1, 1, tzinfo=timezone.utc)
DIGEST = "a" * 64


def us(t):
    d = t - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return str((d.days * 86400 + d.seconds) * 1000000 + d.microseconds)


def quote(event, *, arrival=None, number=2, ask="100.01", bid="100", symbol="SOLUSDT", dataset="quotes"):
    return quote_from_cells(("binance-futures", symbol, us(event), us(arrival or event),
                             "10", ask, bid, "11"), source_sha256=DIGEST,
                            row_number=number, scope="SYNTHETIC_ONLY", dataset=dataset)


def run(rows, **kwargs):
    return sample_bbo(rows, symbol="SOLUSDT", source_sha256=DIGEST,
                      source_class="RECONSTRUCTED_L2_QUOTE", scope="SYNTHETIC_ONLY",
                      cutoff=kwargs.pop("cutoff", T), **kwargs)


def irregular():
    return tuple(quote(T-timedelta(minutes=59-i, seconds=1+i % 3),
                       number=i+2) for i in range(60))


def test_irregular_sixty_endpoints_and_independent_expected_identities():
    rows = irregular()
    result = run(rows)
    assert result.selected_count == 60 and result.proposed_spread_diagnostic_pass
    assert not result.strict_v1_spread_diagnostic_pass
    assert result.strict_v1_exact_event_intervals == 0
    assert [s.endpoint for s in result.slots] == [T-timedelta(minutes=59-i) for i in range(60)]
    assert [s.source_row_id for s in result.slots] == [r.source_row_id for r in rows]
    assert len({s.event_identity for s in result.slots}) == 60
    with localcontext() as context:
        context.prec = 28
        value = Decimal("0.01")/Decimal("100.005")
        assert result.median_spread_fraction == (value + value)/2
    assert result.production_c02_eligibility == "NOT_EVALUATED_UNCHANGED"
    assert result.observations == rows


def test_missing_minute_and_stale_event_never_fill():
    rows = irregular()
    result = run(rows[:15]+rows[16:])
    assert result.selected_count == 59 and result.median_spread_fraction is None
    assert result.slots[15].state == "MISSING_EVIDENCE"
    assert dict(result.slots[15].exclusion_counts)["STALE_EVENT"] == 15
    assert not result.proposed_spread_diagnostic_pass


@pytest.mark.parametrize("delta,accepted", [(0, True), (60, True), (60.000001, False), (-0.000001, False)])
def test_inclusive_age_boundaries_and_future(delta, accepted):
    endpoint = T-timedelta(minutes=59)
    row = quote(endpoint-timedelta(seconds=delta))
    result = run([row])
    assert (result.slots[0].state == "SELECTED") == accepted


def test_late_provider_arrival_is_observed_rejection_not_missing():
    endpoint = T-timedelta(minutes=59)
    result = run([quote(endpoint-timedelta(seconds=1), arrival=endpoint+timedelta(microseconds=1))])
    assert result.slots[0].state == "OBSERVED_REJECTED"
    assert dict(result.slots[0].exclusion_counts)["LATE_PROVIDER_ARRIVAL"] == 1
    assert result.selected_count == 0


def test_unknown_owner_clock_is_not_provider_clock():
    rows = irregular()
    result = run(rows, clock=SampleClockV2(availability_clock="OWNER_RECEIPT"))
    assert result.selected_count == 0
    assert all(r.owner_arrival_time is None for r in result.observations)
    assert "OWNER_ARRIVAL_UNKNOWN" in result.rows[0].reasons
    assert run(rows).selected_count == 60


def test_owner_requires_receipt_reference_and_checks_lateness():
    endpoint = T-timedelta(minutes=59)
    row = quote(endpoint-timedelta(seconds=1)).model_copy(update={"owner_arrival_time": endpoint})
    clock = SampleClockV2(availability_clock="OWNER_RECEIPT")
    assert run([row], clock=clock).selected_count == 0
    evidenced = row.model_copy(update={"owner_receipt_evidence_id": "reviewed-receipt-hash"})
    assert run([evidenced], clock=clock).selected_count == 1
    late = evidenced.model_copy(update={"owner_arrival_time": endpoint+timedelta(microseconds=1)})
    assert "LATE_OWNER_ARRIVAL" in endpoint_reasons(late, endpoint, clock)


def test_no_reuse_inclusive_age_sixty_cannot_duplicate_one_event():
    endpoint = T-timedelta(minutes=59)
    result = run([quote(endpoint)])
    assert result.selected_count == 1
    assert result.slots[1].state == "OBSERVED_REJECTED"
    assert dict(result.slots[1].exclusion_counts)["EVENT_ALREADY_USED"] == 1


def test_repeated_raw_row_and_same_event_with_different_arrival_are_rejected():
    endpoint = T-timedelta(minutes=59)
    first = quote(endpoint)
    another = quote(endpoint, arrival=endpoint+timedelta(seconds=1), number=3)
    result = run([first, first, another])
    assert result.selected_count == 1 and len(result.observations) == 3
    assert any("DUPLICATE_SOURCE_ROW" in r.reasons for r in result.rows)
    assert "DUPLICATE_EVENT_IDENTITY" in result.rows[-1].reasons


def test_numeric_formatting_does_not_manufacture_distinct_event_identity():
    first = quote(T, number=2)
    second = quote(T, number=3, bid="100.000", ask="100.0100")
    assert first.source_row_id != second.source_row_id
    assert first.event_identity == second.event_identity
    assert run([first, second]).selected_count == 1


def test_native_identity_conflict_quarantines_every_copy():
    rows = [quote(T-timedelta(seconds=2), dataset="book_ticker").model_copy(update={"native_event_id": "venue:123", "exchange_time_semantics": "EXCHANGE_EVENT_RECORDED"}),
            quote(T-timedelta(seconds=1), dataset="book_ticker", number=3, ask="100.02").model_copy(update={"native_event_id": "venue:123", "exchange_time_semantics": "EXCHANGE_EVENT_RECORDED"})]
    result = sample_bbo(rows, symbol="SOLUSDT", source_sha256=DIGEST,
        source_class="NATIVE_BBO", scope="SYNTHETIC_ONLY", cutoff=T)
    assert result.selected_count == 0
    assert all("CONFLICTING_EVENT_IDENTITY" in r.reasons for r in result.rows)


def test_newest_event_then_provider_arrival_then_source_ordinal():
    rows = [quote(T-timedelta(seconds=2), number=2),
            quote(T-timedelta(seconds=1), number=3, ask="100.02"),
            quote(T-timedelta(seconds=1), number=4, ask="100.03")]
    assert run(rows).slots[-1].source_record_number == 4


def test_out_of_order_source_is_quarantined_without_sort_repair():
    rows = [quote(T-timedelta(seconds=1), number=2), quote(T-timedelta(seconds=2), number=3)]
    result = run(rows)
    assert result.slots[-1].source_record_number == 2
    assert "OUT_OF_ORDER_SOURCE_CLOCKS" in result.rows[1].reasons
    assert run(reversed(rows)) == result


def test_provider_clock_regression_is_quarantined():
    rows = [quote(T-timedelta(seconds=4), arrival=T-timedelta(seconds=1), number=2),
            quote(T-timedelta(seconds=3), arrival=T-timedelta(seconds=2), number=3)]
    assert "OUT_OF_ORDER_SOURCE_CLOCKS" in run(rows).rows[1].reasons


def test_inverted_clocks_are_retained_and_excluded():
    row = quote(T-timedelta(seconds=1), arrival=T-timedelta(seconds=2))
    result = run([row])
    assert result.observations == (row,) and result.selected_count == 0
    assert "CONTRADICTORY_CLOCK_CHRONOLOGY" in result.rows[0].reasons


@pytest.mark.parametrize("update", [
    {"bid_price": Decimal("99")}, {"source_row_id": "f"*64},
    {"instrument_id": "another"}, {"scope": "ORIGINAL_SAMPLE_HASH_VERIFIED"},
    {"source_sha256": "b"*64}, {"source_class": "NATIVE_BBO"},
])
def test_tampering_and_cross_source_contamination(update):
    row = irregular()[0].model_copy(update=update)
    result = run([row])
    assert result.selected_count == 0 and result.rows[0].reasons


def test_foreign_symbol_cannot_poison_valid_source_locator_or_selection():
    valid = irregular()
    foreign = quote(valid[0].exchange_event_time, symbol="BTCUSDT")
    result = run((*valid, foreign))
    assert result.selected_count == 60
    assert [s.source_row_id for s in result.slots] == [r.source_row_id for r in valid]


def test_spread_threshold_is_preserved_above_and_exactly_at_boundary():
    rows = tuple(quote(T-timedelta(minutes=59-i), number=i+2, bid="99.95", ask="100.05") for i in range(60))
    assert run(rows).median_spread_fraction == Decimal("0.001")
    assert run(rows).proposed_spread_diagnostic_pass
    wider = tuple(quote(r.exchange_event_time, number=r.source_record_number,
                        bid="99.94", ask="100.06") for r in rows)
    assert not run(wider).proposed_spread_diagnostic_pass


def test_conflicting_source_ordinal_is_not_tie_broken_into_false_evidence():
    rows = [quote(T-timedelta(seconds=2)), quote(T-timedelta(seconds=1), ask="100.02")]
    assert all("CONFLICTING_SOURCE_LOCATOR" in r.reasons for r in run(rows).rows)


def test_round_only_endpoint_and_actual_cutoff_freshness_is_preserved():
    rows = irregular()
    result = run(rows, cutoff=T+timedelta(seconds=59, microseconds=999999))
    assert result.slots[-1].endpoint == T
    assert result.observations[-1].exchange_event_time == rows[-1].exchange_event_time
    assert not result.latest_sample_fresh_at_cutoff
    assert not result.proposed_spread_diagnostic_pass


def test_appended_future_events_cannot_change_selected_identities_or_statistic():
    rows = irregular()
    before = run(rows)
    after = run((*rows, quote(T+timedelta(microseconds=1), number=62)))
    assert [s.source_row_id for s in before.slots] == [s.source_row_id for s in after.slots]
    assert before.median_spread_fraction == after.median_spread_fraction


def test_later_conflicting_native_id_cannot_rewrite_earlier_endpoint():
    endpoint = T-timedelta(minutes=59)
    rows = [quote(endpoint, dataset="book_ticker").model_copy(update={
        "native_event_id": "venue:123", "exchange_time_semantics": "EXCHANGE_EVENT_RECORDED"}),
        quote(endpoint+timedelta(seconds=1), number=3, dataset="book_ticker", ask="100.02").model_copy(update={
        "native_event_id": "venue:123", "exchange_time_semantics": "EXCHANGE_EVENT_RECORDED"})]
    result = sample_bbo(rows, symbol="SOLUSDT", source_sha256=DIGEST,
        source_class="NATIVE_BBO", scope="SYNTHETIC_ONLY", cutoff=T)
    assert result.slots[0].source_row_id == rows[0].source_row_id
    assert result.selected_count == 1


def test_native_csv_timestamp_fallback_is_not_assumed_exchange_time():
    row = quote(T, dataset="book_ticker")
    result = sample_bbo([row], symbol="SOLUSDT", source_sha256=DIGEST,
        source_class="NATIVE_BBO", scope="SYNTHETIC_ONLY", cutoff=T)
    assert result.selected_count == 0
    assert "EXCHANGE_TIMESTAMP_ORIGIN_UNVERIFIED" in result.rows[0].reasons


def test_scanner_replay_share_reducer_and_exact_selection_with_serialized_replay():
    rows = irregular()
    kwargs = dict(symbol="SOLUSDT", source_sha256=DIGEST, source_class="RECONSTRUCTED_L2_QUOTE",
                  scope="SYNTHETIC_ONLY", cutoff=T)
    restored = [BBOObservationV2.model_validate_json(r.model_dump_json()) for r in reversed(rows)]
    assert scanner_diagnostic is replay_diagnostic
    assert scanner_diagnostic(rows, **kwargs) == replay_diagnostic(restored, **kwargs)


def test_pure_input_bound_and_naive_clock_fail_before_claiming_result():
    with pytest.raises(ValueError, match="100000"):
        run(iter([irregular()[0]]*100001))
    with pytest.raises(ValueError, match="UTC"):
        run([], cutoff=T.replace(tzinfo=None))


def test_decimal_statistic_does_not_depend_on_caller_context():
    with localcontext() as context:
        context.prec = 8
        context.rounding = ROUND_DOWN
        changed = run(irregular())
    assert changed.median_spread_fraction == run(irregular()).median_spread_fraction


def test_v1_production_rejects_irregular_even_with_proposed_sampled_at():
    rows = irregular()
    sampled = run(rows)
    data = eligible_data("SOLUSDT", as_of=T)
    converted = tuple(SpreadSample(
        symbol=r.symbol, instrument_id=r.instrument_id, event_time=r.exchange_event_time,
        available_at=r.provider_arrival_time, ingested_at=r.provider_arrival_time,
        as_of=T, data_source="SYNTHETIC_ONLY", source_version="s02-test",
        units="unvalidated", fidelity="SYNTHETIC_FIXTURE", readiness="READY",
        observation_id=r.source_row_id, config_hash="test", sampled_at=s.endpoint,
        bid_price=r.bid_price, ask_price=r.ask_price, bid_quantity=r.bid_quantity,
        ask_quantity=r.ask_quantity) for r, s in zip(rows, sampled.slots))
    production = scan_universe({"SOLUSDT": data.model_copy(update={"spread_samples": converted})}, T, Decimal("100000"))
    assert "SPREAD_SAMPLE_GAP_DUPLICATE_OR_ORDER" in production.considered[0].reasons
    assert not production.considered[0].eligible
    assert sampled.proposed_spread_diagnostic_pass


def cli_module():
    spec = importlib.util.spec_from_file_location("s02_cli", ROOT / "scripts/s02_source_diagnostic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_machine_contract_matches_executable_schema_and_nine_acceptance_rows():
    cli = cli_module()
    assert json.loads((ROOT / "research/p3/S02_SOURCE_CONTRACT.json").read_text()) == cli.schema_contract()
    matrix = json.loads((ROOT / "research/p3/S02_SOURCE_ACCEPTANCE.json").read_text())
    assert [r["id"] for r in matrix["requirements"]] == list("ABCDEFGHI")
    assert Counter(r["status"] for r in matrix["requirements"]) == {"PARTIAL": 7, "UNVERIFIED": 2}
    assert {r["family"] for r in matrix["feature_readiness"]} == {f"A{i:02}" for i in range(1, 11)}
    for requirement in matrix["requirements"]:
        for key in ("required_native_fields", "units", "timestamp_contract", "provenance_contract",
                    "historical_coverage", "supporting_evidence", "unaccepted_facts",
                    "acceptance_test", "missingness_behavior", "adapter"):
            assert requirement[key]


def test_financial_wire_and_field_specific_unknown_measurement_clock():
    row = irregular()[0]
    with pytest.raises(ValueError, match="decimal strings"):
        BBOObservationV2.model_validate({**row.model_dump(), "bid_price": 100.0})
    oi = FieldMeasurement(field="openInterest", value="123", unit="UNVERIFIED_RAW_OPEN_INTEREST",
                          measured_at=None, available_at=None, evidence_id=None)
    envelope = row.model_copy(update={"field_measurements": (oi,)})
    assert envelope.provider_arrival_time is not None
    assert envelope.field_measurements[0].measured_at is None
    assert envelope.field_measurements[0].available_at is None
    assert cli_module().deterministic_gzip(b"test")[9] == 255


def test_cli_fixture_reproduction_and_original_mode_rejects_synthetic_bytes(tmp_path):
    cli = cli_module()
    fixture = ROOT / "tests/fixtures/c05g"
    first = cli.run(fixture, tmp_path / "one", synthetic=True)
    second = cli.run(fixture, tmp_path / "two", synthetic=True)
    assert first == second
    assert first == json.loads((ROOT / "research/p3/s02-synthetic/S02_DIAGNOSTIC.json").read_text())
    assert first["scope"] == "SYNTHETIC_ONLY"
    assert first["original_one_day_empirical_acceptance"] == "PENDING_OWNER_RUN"
    assert first["quote_counts"]["raw_quote_rows"] == 63
    assert first["quote_counts"]["duplicate_source_rows"] == 1
    assert first["quote_counts"]["inverted_arrivals"] == 0
    with pytest.raises(ValueError, match="fresh directory"):
        cli.run(fixture, tmp_path / "one", synthetic=True)
    assert all(r["owner_receipt_selected_count"] == 0 for r in first["cutoffs"])
    for path in (tmp_path / "one").glob("*.gz"):
        assert path.read_bytes() == (tmp_path / "two" / path.name).read_bytes()
    with pytest.raises(HistoricalDataError, match="SHA-256 mismatch"):
        cli.run(fixture, tmp_path / "original", synthetic=False)
    assert not (tmp_path / "original").exists()


def test_original_pin_tamper_rejected_before_parser(tmp_path):
    path = tmp_path / "bytes.gz"
    path.write_bytes(b"tampered")
    with pytest.raises(HistoricalDataError, match="SHA-256 mismatch"):
        verify_source(path, DIGEST)
