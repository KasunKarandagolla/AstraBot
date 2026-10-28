"""S01 math/causality and exact original-source evidence regressions.

Invented fixtures exercise mechanics only and never enter empirical artifacts.
"""
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace as N

import pytest

from scripts import s01_economic_recovery as study


def context(**updates):
    return N(**{'readiness': 'READY', 'classification': 'TREND_UP', 'bias': 'BULLISH',
        'adx_1h': D(18), 'normalized_slope': D('.1'), 'atr_percentile': D(40),
        'atr_15m': D(1), 'atr_5m': D('.4'), 'rvol_15m': D(1), **updates})


def bar(at, *, high='101', low='99.5', opened='100', close='100.5'):
    return N(symbol='SYNTHETIC', interval='5m', source_record_id='FIXTURE:' + at.isoformat(),
        available_at=at, open_time=at - timedelta(minutes=5),
        open=D(opened), high=D(high), low=D(low), close=D(close))


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_single_structural_target_uses_both_exact_fee_notionals(side):
    stop, target = ('99', '102') if side == 'LONG' else ('101', '98')
    row = {'entry': '100', 'stop': stop, 'stop_distance': '1', 'side': side, 'policy': 'PC2',
        'targets': [{'price': target, 'fraction': '1'}], 'route_feasible': True}
    actual = study.cost_screen(row, study.SCENARIOS['base'])
    win_cost = (D(100) + D(target)) * D('.0005') + D('.02') + D('.01')
    loss_cost = (D(100) + D(stop)) * D('.0005') + D('.02') + D('.01')
    assert D(actual['scenario_net_rr']) == (D(2) - win_cost) / (D(1) + loss_cost)
    assert actual['midpoint_net_rr'] is None
    shifted = study.cost_screen(row, study.SCENARIOS['base'], entry_shift_r=D('.05'))
    assert D(shifted['scenario_net_rr']) < D(actual['scenario_net_rr'])


def test_closest_opposition_is_not_skipped_to_get_a_larger_reward():
    at = study.START
    def level(price, identity):
        return N(kind='SWING_HIGH', invalidated=False, price=D(price), level_id=identity,
            available_at=at, symbol='SYNTHETIC', timeframe='1h', source_ids=(identity,))
    selected = study.select_target('LONG', D(100), [level('101', 'NEAR'), level('104', 'FAR')],
        boundary=D(105), boundary_keys=('BOUNDARY',), boundary_at=at)
    assert selected['price'] == '101'
    assert selected['source_keys'] == [study.source_key('SYNTHETIC', '1h', 'NEAR')]
    setup = {'side': 'LONG', 'candidate': 'PC2', 'stop': '99', 'target': selected}
    result = study.confirmation_geometry(setup, bar(at, close='100'), [])
    assert result['geometry_status'] == 'TARGET_OUTSIDE_1_8_TO_4_R'
    assert result['targets'] == [{'price': '101', 'fraction': '1'}]


def test_stop_touch_in_confirmation_candle_invalidates_even_when_close_confirms():
    at = study.START + timedelta(hours=1)
    setup = {'candidate': 'PC2', 'side': 'LONG', 'formed_at': at.isoformat(),
        'stop': '99', 'trigger_boundary': '101', 'session_id': 'UTC:2024-09-01'}
    update = bar(at + timedelta(minutes=5), high='103', low='98.9', close='102')
    assert study.advance(setup, update, context())[0] == 'INVALIDATED'
    with pytest.raises(ValueError, match='must follow'):
        study.advance(setup, bar(at), context())


def test_fr_first_failed_breach_cannot_wait_for_a_later_pretty_sweep():
    at = study.START
    setup = {'candidate': 'FR2', 'side': 'LONG', 'formed_at': at.isoformat(), 'state': 'ARMED',
        'high': '104', 'low': '100', 'atr15': '1'}
    failed = bar(at + timedelta(minutes=5), high='101', low='99.5', close='99.9')
    assert study.advance(setup, failed, context())[0] == 'INVALIDATED'


def test_fr_bar_three_sweep_allows_only_distinct_bar_four_confirmation():
    at = study.START
    setup = {'candidate': 'FR2', 'side': 'LONG', 'formed_at': at.isoformat(), 'state': 'ARMED',
        'high': '104', 'low': '100', 'atr15': '1'}
    sweep = bar(at + timedelta(minutes=15), high='101', low='99.5', close='100.5')
    state, _ = study.advance(setup, sweep, context())
    assert state == 'SWEPT' and setup['stop'] == '99.25'
    setup['state'] = state
    assert study.advance(setup, bar(at + timedelta(minutes=20), high='102', low='100', close='101.5'), context())[0] == 'CONFIRMED'
    assert study.advance(setup, bar(at + timedelta(minutes=25), high='102', low='100', close='101.5'), context())[0] == 'INVALIDATED'


def test_new_feature_inputs_are_unchanged_by_unavailable_future_bars():
    from astrabot.research.replay import HistoricalPanel
    from test_c03_context_levels import trend_data, T, SYMBOL, bar as make_bar
    data = trend_data()
    future = {f'candles_{interval}': (*getattr(data, f'candles_{interval}'),
        make_bar(interval, T + timedelta(hours=4), center=D(9999))) for interval in study.HISTORY_LIMITS}
    original = study._panel_point_in_time(HistoricalPanel({SYMBOL: data}, (), {}), SYMBOL, T, study.HISTORY_LIMITS)
    appended = study._panel_point_in_time(HistoricalPanel({SYMBOL: data.model_copy(update=future)}, (), {}), SYMBOL, T, study.HISTORY_LIMITS)
    a = study.ctx.evaluate_context(original, symbol=SYMBOL, instrument_id=data.candles_5m[0].instrument_id, as_of=T)
    b = study.ctx.evaluate_context(appended, symbol=SYMBOL, instrument_id=data.candles_5m[0].instrument_id, as_of=T)
    assert study.pc_formation(original, a, 'LONG', T) == study.pc_formation(appended, b, 'LONG', T)
    assert study.range_terms(original, a) == study.range_terms(appended, b)
    assert study.context_record(a, original) == study.context_record(b, appended)


def test_price_balance_requires_separated_tests_not_just_rolling_extrema():
    bars = []
    for i in range(21):
        center = D('101.5') if i % 4 == 0 else D('98.5') if i % 4 == 2 else D(100)
        bars.append(N(symbol='SYNTHETIC', interval='15m', source_record_id=str(i),
            high=center + D('.5'), low=center - D('.5'), close=center, available_at=study.START))
    data = N(candles_15m=bars)
    terms, reasons = study.range_terms(data, context())
    assert not reasons and terms['high'] == '102.0' and terms['low'] == '98.0'
    assert terms['midpoint'] == '100.0' and len(terms['source_keys']) == 20
    # A one-off new high destroys the preexisting high-edge tests.
    bars[-1] = N(**{**vars(bars[-1]), 'high': D(103)})
    terms, reasons = study.range_terms(data, context())
    assert terms is None and 'FR2_SEPARATED_HIGH_TESTS_MISSING' in reasons


def test_pc_positive_formation_freezes_45m_stop_and_closed_session_vwap():
    from test_c03_context_levels import bar as make_bar, SYMBOL
    at = study.START + timedelta(hours=1)
    five = tuple(make_bar('5m', study.START + timedelta(minutes=5 * i)) for i in range(12))
    fifteen = tuple(make_bar('15m', study.START + timedelta(minutes=15 * i),
        center=D('100.2'), width=D('.8'), close=D('100.1')) for i in range(3))
    data = N(candles_5m=five, candles_15m=fifteen)
    terms, reasons = study.pc_formation(data, context(), 'LONG', at)
    assert not reasons and terms['stop_anchor'] == '99.8' and terms['stop'] == '99.55'
    assert len(terms['pullback_source_keys']) == 3 and len(terms['vwap_source_keys']) == 12
    assert D(terms['vwap']) == 100 and terms['session_id'] == 'UTC:2024-09-01'


def test_matching_uses_only_exact_past_causal_metadata():
    at = study.START + timedelta(days=3)
    event = {'candidate': 'FR2', 'setup_id': 'CASE', 'symbol': 'X', 'side': 'LONG',
        'terminal_at': at.isoformat(), 'candidate_regime': 'PRICE_BALANCE', 'atr_percentile': '40'}
    def control(identity, when, **updates):
        return {'candidate': 'FR2', 'window_id': identity, 'symbol': 'X',
            'event_time': when.isoformat(), 'eligible_nontrigger': True,
            'regime': 'PRICE_BALANCE', 'atr_percentile': '40', **updates}
    pool = [control('PAST', at - timedelta(days=1)), control('FUTURE', at + timedelta(days=1)),
        control('OVERLAP', at - timedelta(hours=1)), control('OLD', at - timedelta(days=8)),
        control('WRONG_VOL', at - timedelta(days=1), atr_percentile='60'),
        control('SWEEP', at - timedelta(days=1), eligible_nontrigger=False)]
    before = study.select_matches([event], pool)
    for row in pool:
        row['future_return'] = '999999'
    assert study.select_matches([event], pool) == before
    assert before[0]['control_id'] == 'PAST' and before[0]['candidate_count'] == 1


def test_falsifier_respects_favorable_same_bar_bound_and_small_sample():
    h = {'complete': 20, 'target_before_stop_upper': 4, 'target_before_stop_lower': 3,
         'paired': {'equal_day_difference_bps': None}}
    c = {'confirmations': 100, 'groups': {'base_survivors': {'n': 20, 'horizons': {'720': h}}}}
    assert study.decision(c) == 'REJECT_ECONOMIC_HYPOTHESIS'
    h['complete'] = 19
    base = c['groups']['base_survivors']
    base['horizons'].update({'60': h, '240': h})
    assert study.decision(c) == 'REVISE_BEFORE_IMPLEMENTATION'


def test_saved_ledger_reconstructs_paths_and_source_chronology_without_raw_cache():
    import json
    import gzip
    study.validate_inputs()
    directory = study.ROOT / 'research/p3'
    packet = json.loads(gzip.decompress((directory / 'S01_EVIDENCE.json.gz').read_bytes()))
    assert study.render(packet) == (directory / 'S01_SEPTEMBER_ECONOMIC_SCREEN.md').read_text()
    assert packet.pop('content_sha256') == study.config_hash(packet)
    census, digest = study.checked_json(directory / 'S01_CAUSAL_CENSUS.json.gz', compressed=True)
    assert digest == packet['census_content_sha256']
    assert len(census['pool']) == 120960
    assert study.select_matches(census['events'], census['pool']) == census['matches']
    assert all('outcomes' not in r for r in census['events'] + census['pool'])
    source = {r['source_key']: r for r in packet['source_bars']}
    assert len(source) == len(packet['source_bars'])
    assert len(packet['source_partitions']) == 84
    assert all('2024-10' not in r['archive_id'] for r in packet['source_partitions'])
    formations = {r['setup_id']: r for r in census['formations']}
    for setup in formations.values():
        at = study.dt(setup['formed_at'])
        assert study.dt(source[setup['formation_source_key']]['available_at']) == at
        if setup['target']:
            assert study.dt(setup['target']['available_at']) <= at
            assert all(study.dt(source[k]['available_at']) <= at for k in setup['target']['source_keys'])
        for k in setup.get('pullback_source_keys', []) + setup.get('vwap_source_keys', []) + setup.get('source_keys', []):
            assert study.dt(source[k]['available_at']) <= at
    for row in packet['events'] + packet['controls']:
        is_event = 'setup_id' in row
        at = study.dt(row['terminal_at' if is_event else 'event_time'])
        reference = D(row['entry' if is_event else 'reference_close'])
        ref = source[row['confirmation_source_key' if is_event else 'source_key']]
        assert D(ref['close']) == reference and study.dt(ref['available_at']) == at
        assert ref['symbol'] == row['symbol'] and ref['interval'] == '5m'
        keys = row['outcomes']['720']['source_keys']
        bars = [N(**{**source[k], 'source_record_id': source[k]['native_id'],
            'open_time': study.dt(source[k]['open_time']), 'available_at': study.dt(source[k]['available_at']),
            **{v: D(source[k][v]) for v in ('open', 'high', 'low', 'close')}}) for k in keys]
        target = D(row['targets'][0]['price']) if is_event and row['targets'] else (
            D(row['normalization_target']) if not is_event and row['normalization_target'] else None)
        rebuilt = study.price_path(bars, at=at, reference=reference,
            distance=D(row['stop_distance' if is_event else 'normalization_distance']), side=row['side'], target2=target)
        assert rebuilt == row['outcomes']
        assert all(b.symbol == row['symbol'] and b.open_time >= at and b.available_at <= study.END for b in bars)
        if is_event:
            assert study.dt(formations[row['setup_id']]['formed_at']) < at
    pool = {r['window_id']: r for r in census['pool']}
    events = {r['setup_id']: r for r in packet['events']}
    for link in census['matches']:
        if link['control_id']:
            control, event = pool[link['control_id']], events[link['event_id']]
            assert control['eligible_nontrigger'] and control['symbol'] == event['symbol']
            assert timedelta(hours=12) <= study.dt(event['terminal_at']) - study.dt(control['event_time']) <= timedelta(days=7)
    assert all(study.dt(r['open_time']) < study.END for r in source.values())
    assert packet['strict_eligible_candidates'] == 0 and not packet['october_outcomes_accessed']
