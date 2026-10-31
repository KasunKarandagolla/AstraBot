"""Phase 6 M4 S1-S2 regression tests with actual AstraBot Trade contracts.

Only synthetic observations. No market-data retrieval, profitability, S3-S6
confirmation, order simulation or live execution.
"""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from decimal import Decimal as D

import pytest

from astrabot.data.models import Trade, binance_usdm_instrument_id
from astrabot.research.m4_source_clock import PriorDayReference, SourceNotReady
from astrabot.research.m4_funnel import (
    M4StageEvidence,
    SessionCoverage,
    causal_confirmation_timestamp,
    enumerate_m4_penetrations,
)

UTC = timezone.utc
DAY = datetime(2023, 1, 3, tzinfo=UTC)
IID = binance_usdm_instrument_id("BTCUSDT")
CUTOFF = DAY + timedelta(hours=1)
TICK = D("0.1")


def reference(*, available_at=DAY):
    return PriorDayReference(
        symbol="BTCUSDT", instrument_id=IID,
        reference_day=(DAY-timedelta(days=1)).date(),
        as_of=DAY, available_at=available_at,
        high=D("102.0"), low=D("98.0"),
        candle_count=1440, source_digest="b"*64, fidelity="SYNTHETIC_FIXTURE",
    )


def coverage(*, session_start=DAY, complete_through=None, proxy_available_at=None,
             source_digest="a"*64, provenance="SYNTHETIC_FIXTURE", verified_at=None):
    return SessionCoverage(
        session_start=session_start,
        complete_through=complete_through or CUTOFF,
        replay_proxy_available_at=proxy_available_at or CUTOFF,
        source_digest=source_digest, provenance=provenance,
        verified_at=verified_at,
    )


def trade(number, seconds, price, *, buyer_is_maker=True, instrument_id=IID,
          symbol="BTCUSDT", available_at=None, source_sha256=None):
    event = DAY + timedelta(seconds=seconds)
    arrival = event if available_at is None else available_at
    price = D(price)
    return Trade(
        symbol=symbol, instrument_id=instrument_id, event_time=event,
        available_at=arrival, ingested_at=arrival, as_of=arrival,
        data_source="synthetic.m4", source_version="m4.v1",
        units="price-quote-quantity-base", fidelity="SYNTHETIC_FIXTURE",
        readiness="READY", quality="VALID", observation_id=f"event:{number}",
        config_hash="synthetic", source_sha256=source_sha256,
        trade_id=str(number), aggregate_trade_id=str(number),
        first_trade_id=str(number), last_trade_id=str(number),
        price=price, base_quantity=D("1"), quote_quantity=price,
        buyer_is_maker=buyer_is_maker,
        aggressor_side="SELL" if buyer_is_maker else "BUY",
    )


def run(rows, **kwargs):
    return enumerate_m4_penetrations(
        rows, reference=kwargs.pop("reference", reference()),
        coverage=kwargs.pop("coverage", coverage()),
        as_of=kwargs.pop("as_of", CUTOFF),
        tick_size=kwargs.pop("tick_size", TICK),
        **kwargs,
    )


def test_both_sides_and_no_false_confirmation():
    result = run([trade(1, 2, "97.9"), trade(2, 3, "97.8"),
                  trade(3, 60, "102.1", buyer_is_maker=False)])
    assert (result.n1_penetration_prints, result.n2_deduplicated_events) == (3, 2)
    assert [c.side for c in result.candidates] == ["LONG", "SHORT"]
    assert [c.reference_type for c in result.candidates] == ["PDL", "PDH"]
    assert all(c.print_fidelity == c.reference_fidelity == "SYNTHETIC_FIXTURE"
               for c in result.candidates)
    assert all(c.s4_observation_end == c.t1+timedelta(seconds=90)
               for c in result.candidates)
    assert result.candidates[0].penetration_ticks == D("1")
    assert result.n3_participation_pass is result.n6_confirmed_trigger is None
    assert result.status == "RESEARCH_ONLY_S1_S2_NO_CONFIRMATION"
    assert {b.stage for b in result.stage_boundaries} == {
        "S2_REARM", "S3", "S4", "S5", "S6"}
    assert all(b.confirmation_timestamp is None and b.executable is False
               for b in result.stage_boundaries)


def test_15m_dedup_boundary_uses_first_accepted_per_side():
    result = run([trade(11, 10, "97.8"), trade(12, 15, "97.7"),
                  trade(13, 910, "97.9")])
    assert (result.n1_penetration_prints, result.n2_deduplicated_events) == (3, 2)
    assert [c.aggregate_trade_id for c in result.candidates] == ["11", "13"]


def test_identical_input_is_deterministic_and_future_print_is_ignored():
    rows = [trade(1, 10, "97.9"), trade(2, 25, "100.0")]
    a = run(rows)
    b = run([*rows, trade(3, 4200, "102.3", buyer_is_maker=False)])
    assert a == b == run(rows)


def test_event_id_binds_print_values_even_when_source_id_is_unchanged():
    original = trade(1, 10, "97.9")
    revised = original.model_copy(update={"price": D("97.8")})
    first = run([original]).candidates[0]
    second = run([revised]).candidates[0]
    assert first.aggregate_trade_id == second.aggregate_trade_id
    assert first.source_digest == second.source_digest
    assert first.event_id != second.event_id


def test_forged_reference_with_incomplete_or_impossible_clock_fails_closed():
    bad_count = replace(reference(), candle_count=1439)
    with pytest.raises(SourceNotReady, match="1440"):
        run([], reference=bad_count)

    impossible_clock = replace(
        reference(available_at=DAY - timedelta(microseconds=1)),
        as_of=DAY-timedelta(seconds=1))
    with pytest.raises(SourceNotReady, match="available|chronology"):
        run([], reference=impossible_clock)


def test_s6_timestamp_waits_for_all_inputs_and_rejects_lookahead():
    s4_end = DAY + timedelta(seconds=90)
    inputs = (
        M4StageEvidence("S2_REARM", DAY+timedelta(seconds=20), DAY+timedelta(seconds=21)),
        M4StageEvidence("S3", DAY+timedelta(seconds=30), DAY+timedelta(seconds=32)),
        M4StageEvidence("S4", s4_end, DAY+timedelta(seconds=91)),
        M4StageEvidence("S5", DAY+timedelta(seconds=40), DAY+timedelta(seconds=95)),
    )
    cutoff = DAY + timedelta(seconds=100)
    assert causal_confirmation_timestamp(inputs, t1=DAY, as_of=cutoff) == DAY+timedelta(seconds=95)

    with pytest.raises(SourceNotReady, match="causally unavailable"):
        causal_confirmation_timestamp(
            (*inputs[:-1], replace(inputs[-1], available_at=cutoff+timedelta(microseconds=1))),
            t1=DAY, as_of=cutoff)
    with pytest.raises(SourceNotReady, match="90-second clock"):
        causal_confirmation_timestamp(
            (*inputs[:-2], replace(inputs[-2], evaluated_through=DAY+timedelta(seconds=89)), inputs[-1]),
            t1=DAY, as_of=cutoff)
    with pytest.raises(SourceNotReady, match="qualified S2 re-arm and S3-S5"):
        causal_confirmation_timestamp(inputs[:-1], t1=DAY, as_of=cutoff)
    with pytest.raises(SourceNotReady, match="duplicated"):
        causal_confirmation_timestamp((*inputs, inputs[0]), t1=DAY, as_of=cutoff)
    with pytest.raises(SourceNotReady, match="failed upstream"):
        causal_confirmation_timestamp(
            (*inputs[:-1], replace(inputs[-1], passed=False)), t1=DAY, as_of=cutoff)


def test_empty_session_requires_explicit_source_coverage():
    result = run([])
    assert result.n1_penetration_prints == result.n2_deduplicated_events == 0
    assert not result.candidates
    with pytest.raises(SourceNotReady):
        run([], coverage=coverage(complete_through=DAY+timedelta(minutes=10)))


def test_all_unavailable_or_unsafe_candles_trades_fail_closed():
    with pytest.raises(SourceNotReady, match="trade input required"):
        run([object()])
    late = trade(1, 20, "97.9", available_at=CUTOFF+timedelta(seconds=1))
    with pytest.raises(SourceNotReady, match="chronology"):
        run([late])


def test_price_grid_and_reference_availability_are_strict():
    with pytest.raises(SourceNotReady, match="tick aligned"):
        run([trade(1, 20, "97.95")])
    with pytest.raises(SourceNotReady, match="reference unavailable"):
        run([], reference=reference(available_at=DAY+timedelta(microseconds=1)))


def test_id_gap_and_regressed_time_fail_closed():
    with pytest.raises(SourceNotReady, match="continuity gap"):
        run([trade(1, 1, "97.9"), trade(3, 2, "97.8")])
    with pytest.raises(SourceNotReady, match="continuity gap"):
        run([trade(1, 2, "97.9"), trade(2, 1, "97.8")])


def test_mixed_symbol_fails_even_if_price_does_not_penetrate():
    with pytest.raises(SourceNotReady, match="identity"):
        run([trade(1, 2, "100.0", symbol="ETHUSDT")])


def test_original_source_hash_must_match_retrospective_archive_claim():
    valid = trade(1, 2, "97.9", source_sha256="a"*64)
    stamp = datetime(2026, 10, 31, tzinfo=UTC)
    c = coverage(provenance="HASH_VERIFIED_ARCHIVE_REPLAY", verified_at=stamp)
    assert run([valid], coverage=c).n2_deduplicated_events == 1
    with pytest.raises(SourceNotReady, match="provenance"):
        run([trade(1, 2, "97.9")], coverage=c)
    with pytest.raises(SourceNotReady, match="verification timestamp"):
        run([valid], coverage=coverage(provenance="HASH_VERIFIED_ARCHIVE_REPLAY"))


def test_sealed_and_evaluation_periods_are_rejected():
    bad = datetime(2024, 10, 1, tzinfo=UTC)
    with pytest.raises(SourceNotReady, match="development window"):
        run([], coverage=coverage(session_start=bad))


def test_unverified_source_clock_and_float_ticks_rejected():
    with pytest.raises(SourceNotReady, match="not causally available"):
        run([], coverage=coverage(proxy_available_at=CUTOFF+timedelta(seconds=1)))
    with pytest.raises(SourceNotReady, match="Decimal tick"):
        run([], tick_size=0.1)


def test_threshold_is_one_tick_not_a_wick_or_any_touch():
    result = run([trade(1, 1, "98.0"), trade(2, 2, "102.0"),
                  trade(3, 3, "98.1"), trade(4, 4, "101.9")])
    assert result.n1_penetration_prints == 0


def test_source_coverage_is_bounded_by_development_and_utc_day():
    with pytest.raises(SourceNotReady, match="coverage"):
        run([], coverage=coverage(session_start=DAY+timedelta(minutes=1)))
    with pytest.raises(SourceNotReady, match="incomplete session coverage"):
        run([], coverage=coverage(complete_through=DAY+timedelta(days=2)))


def test_print_after_cutoff_never_repaints_t1():
    first = trade(1, 1, "97.9")
    cutoff = DAY + timedelta(minutes=5)
    proof = coverage(complete_through=cutoff, proxy_available_at=cutoff)
    original = run([first], as_of=cutoff, coverage=proof)
    later = trade(2, 600, "102.1", buyer_is_maker=False)
    assert original == run([first, later], as_of=cutoff, coverage=proof)
