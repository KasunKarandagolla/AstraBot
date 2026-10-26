"""Integrated research regressions: evidence boundaries, causality and denominators."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from astrabot.data.models import binance_usdm_instrument_id
from astrabot.research.replay import (
    HistoricalPanel, _panel_point_in_time, load_c02_panel, synthetic_eligible_panel,
)
from astrabot.universe.eligibility import SymbolData
from scripts import c05_historical_research as historical_cli

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
AT = datetime(2024, 10, 1, 1, tzinfo=UTC)


def _snapshots(*, evidence_manifest=None, decisions=(AT,)):
    args = historical_cli.build_parser().parse_args([
        '--data-root', str(ROOT / 'tests/fixtures/c05g'),
        '--source-manifest', str(ROOT / 'tests/fixtures/c05g/manifest.json'),
        '--symbol', 'SOLUSDT', '--date', '2024-10-01',
        *[arg for at in decisions for arg in ('--decision-time', at.isoformat())],
        *(['--evidence-manifest', str(evidence_manifest)] if evidence_manifest else []),
    ])
    manifest, synthetic, hashes, times, diagnostics, evidence, freshness, snapshots = historical_cli.load_snapshots(args)
    return snapshots, {
        'synthetic': synthetic, 'source_manifest': manifest,
        'source_sha256': hashes,
        'evidence_manifest_sha256': evidence.manifest_sha256 if evidence else None,
    }


def _empty_feed_panel():
    return HistoricalPanel(
        symbols={'SOLUSDT': SymbolData()},
        partitions=(),
        source_manifest={'evidence_class': 'SYNTHETIC_C05_G_H_TEST_ONLY'},
    )


def test_authentic_incomplete_panel_has_honest_zero_admission_denominators():
    from astrabot.research.integrated import build_packet, render_packet

    packet = build_packet(
        load_c02_panel(ROOT / 'research/c02_panel'),
        replay_start=datetime(2024, 10, 28, tzinfo=UTC),
        replay_end=datetime(2024, 10, 29, 1, tzinfo=UTC),
        evaluation_interval='1h',
    )
    replay = packet['replay']
    assert replay['funnel']['symbol_evaluation_windows'] == 48
    assert replay['funnel']['eligible_symbol_windows'] == 0
    assert replay['funnel']['strict_candidate_decisions'] == 0
    assert replay['funnel']['diagnostic_no_trade_decisions'] == 288
    assert replay['strict_decisions'] == []
    assert replay['scenario_outcomes'] == {'E0': [], 'E1': [], 'E2': []}
    assert replay['statistics']['outcomes']['mean_net_r'] is None
    assert replay['statistics']['market_time_block_bootstrap']['ci95'] is None
    # The authentic APE partition has trades but no candle. Its rejected case
    # must still produce a complete human decision packet.
    assert 'INSUFFICIENT_EVIDENCE' in render_packet(packet)


def test_future_candle_append_cannot_change_an_earlier_decision_funnel():
    from astrabot.research.integrated import build_packet

    panel = load_c02_panel(ROOT / 'research/c02_panel')
    data = panel.symbols['BTCUSDT']
    last = data.candles_1h[-1]
    advance = timedelta(days=1)
    future = last.model_copy(update={
        'open_time': last.open_time + advance,
        'close_time': last.close_time + advance,
        'event_time': last.event_time + advance,
        'available_at': last.available_at + advance,
        'ingested_at': last.ingested_at + advance,
        'as_of': last.as_of + advance,
        'source_record_id': 'future-poisoned-row',
        'observation_id': 'future-poisoned-observation',
        'readiness': 'UNAVAILABLE',
    })
    extended = replace(panel, symbols={
        **panel.symbols,
        'BTCUSDT': data.model_copy(update={'candles_1h': (*data.candles_1h, future)}),
    })
    scope = dict(
        replay_start=datetime(2024, 10, 28, 6, tzinfo=UTC),
        replay_end=datetime(2024, 10, 28, 8, tzinfo=UTC),
        evaluation_interval='1h',
    )
    original_packet = build_packet(panel, **scope)
    extended_packet = build_packet(extended, **scope)
    for key in ('strict_decisions', 'diagnostic_summary', 'funnel_events', 'scenario_outcomes'):
        assert original_packet['replay'][key] == extended_packet['replay'][key]


def test_verified_feed_units_are_cutoff_scoped_and_remain_nonexecutable():
    from astrabot.research.integrated import attach_snapshots

    snapshots, provenance = _snapshots(evidence_manifest=ROOT / 'tests/fixtures/c05h/manifest.json')
    joined = attach_snapshots(_empty_feed_panel(), snapshots, feed_provenance=provenance)
    exact = _panel_point_in_time(joined, 'SOLUSDT', AT)
    later = _panel_point_in_time(joined, 'SOLUSDT', AT + timedelta(seconds=1))
    assert exact.metadata is not None
    assert exact.open_interest is not None and exact.open_interest.unit_validated
    assert str(exact.open_interest.open_interest_notional_usdt) == '10050.00'
    assert exact.depth is not None and exact.depth.unit_validated
    assert exact.depth.readiness == exact.open_interest.readiness == 'DEGRADED'
    # A normalized verification at t cannot certify a different replay cutoff.
    assert later.metadata is later.depth is later.open_interest is None
    assert later.spread_samples == ()
    # Quote/book/OI evidence does not invent the remaining mandatory inputs.
    assert exact.ticker is exact.event_clearance is None
    assert all(sample.sampled_at is not None and sample.event_time <= sample.sampled_at
               for sample in exact.spread_samples)


def test_snapshot_join_rejects_hash_instrument_and_synthetic_scope_mismatch():
    from astrabot.research.integrated import attach_snapshots

    snapshots, provenance = _snapshots(evidence_manifest=ROOT / 'tests/fixtures/c05h/manifest.json')
    snapshot = snapshots[0]
    assert snapshot.latest_depth is not None
    bad_hash = replace(snapshot, latest_depth=snapshot.latest_depth.model_copy(update={'source_sha256': '0' * 64}))
    with pytest.raises(ValueError, match='identity/hash'):
        attach_snapshots(_empty_feed_panel(), (bad_hash,), feed_provenance=provenance)
    bad_instrument = replace(snapshot, latest_depth=snapshot.latest_depth.model_copy(update={
        'instrument_id': binance_usdm_instrument_id('BTCUSDT'),
    }))
    with pytest.raises(ValueError, match='identity/hash'):
        attach_snapshots(_empty_feed_panel(), (bad_instrument,), feed_provenance=provenance)
    wrong_periodic = snapshot.periodic_spread_samples[0].model_copy(update={'source_sha256': '0' * 64})
    bad_periodic = replace(snapshot, periodic_spread_samples=(wrong_periodic, *snapshot.periodic_spread_samples[1:]))
    with pytest.raises(ValueError, match='identity/hash'):
        attach_snapshots(_empty_feed_panel(), (bad_periodic,), feed_provenance=provenance)
    authentic_panel = replace(_empty_feed_panel(), source_manifest={'evidence_class': 'OBSERVED_HISTORICAL_INPUTS'})
    with pytest.raises(ValueError, match='synthetic feed/panel scope mismatch'):
        attach_snapshots(authentic_panel, snapshots, feed_provenance=provenance)


@pytest.mark.parametrize('metadata_source', ('base', 'history', 'exact_snapshot'))
def test_synthetic_strict_opportunity_runs_existing_execution_without_qualification(metadata_source):
    from astrabot.research.integrated import build_packet

    panel = synthetic_eligible_panel()
    if metadata_source != 'base':
        data = panel.symbols['ALTUSDT'].model_copy(update={'metadata': None})
        # Admission can use causal metadata without a copy on the raw outcome
        # panel. Execution must retain those same decision-time filters.
        updates = {'symbols': {'ALTUSDT': data}}
        if metadata_source == 'exact_snapshot':
            from astrabot.research.integrated import evaluation_times
            times = evaluation_times(panel, start=None, end=None, interval=None)
            updates['research_snapshots'] = {
                at: {'ALTUSDT': _panel_point_in_time(panel, 'ALTUSDT', at)} for at in times
            }
            updates['observation_history'] = {'ALTUSDT': {
                **panel.observation_history['ALTUSDT'], 'metadata': (),
            }}
        panel = replace(panel, **updates)
        assert panel.symbols['ALTUSDT'].metadata is None
    packet = build_packet(panel, evaluation_interval=None)
    assert packet['decision'] == 'INSUFFICIENT_EVIDENCE'
    assert packet['policy_status'] == 'RESEARCH_ONLY'
    assert packet['funnel']['strict_candidate_decisions'] == 1
    assert packet['funnel']['historical_executable_trades'] == 0
    assessments = packet['policy_assessments']
    assert set(assessments) == {'T1', 'R1', 'B1'}
    t1 = assessments['T1']
    assert t1['strict_candidates'] == 1
    assert t1['scenarios']['E0']['status_counts'] == {'UNFILLED': 1}
    assert t1['scenarios']['E1']['status_counts'] == {'FLAT': 1}
    assert t1['scenarios']['E2']['status_counts'] == {'FLAT': 1}
    assert t1['scenarios']['E1']['evidence_class'].startswith('SYNTHETIC_')
    assert t1['scenarios']['E1']['uncertainty']['ci95'] is None
    assert t1['scenarios']['E1']['uncertainty']['warning'] == 'FEWER_THAN_TWO_MARKET_TIME_BLOCKS'
    assert all(row['decision'] == 'INSUFFICIENT_EVIDENCE' and row['historical_executable_trades'] == 0
               for row in assessments.values())
    assert packet['price_diagnostics']['admitted_to_execution'] is False
    assert all(row['eligible_trade'] is False for row in packet['price_diagnostics']['setups'])
