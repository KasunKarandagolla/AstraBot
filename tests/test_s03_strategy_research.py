"""S03 causal reducers, independent arithmetic and retained original-source paths."""
from datetime import timedelta
from decimal import Decimal as D
import gzip
import json
from types import SimpleNamespace as N

import pytest

from scripts import s03_strategy_research as s
from test_s01_economic_recovery import bar, context


def setup(name='PC3', side='LONG', **updates):
    return {'candidate': name, 'side': side, 'formed_at': (s.START + timedelta(hours=1)).isoformat(),
        'state': 'ARMED', 'stop': '99', 'transitions': [], 'trigger_boundary': '100.5',
        'entry_cap': '101', 'atr15': '1', 'reclaim_close': '100.3', 'breached_edge': '100',
        'low': '100', 'high': '110', 'formation_vetoes': [],
        'target': {'price': '103'}, **updates}


@pytest.mark.parametrize('name', ['PC3', 'FA3'])
def test_stop_priority_distinct_confirmation_and_terminal_replay(name):
    x = setup(name)
    at = s.dt(x['formed_at'])
    assert s.advance(x, bar(at + timedelta(minutes=5), low='98', close='101'), context())[0] == 'INVALIDATED'
    with pytest.raises(ValueError, match='distinct'):
        s.advance(x, bar(at), context())
    x['state'] = 'CONFIRMED'
    with pytest.raises(ValueError, match='terminal'):
        s.advance(x, bar(at + timedelta(minutes=5)), context())


def test_early_acceptance_is_not_a_whole_formation_or_sweep_break():
    x = setup('FA3')
    at = s.dt(x['formed_at']) + timedelta(minutes=5)
    # This stays far below a hypothetical whole-sweep high of 103.
    assert s.advance(x, bar(at, low='100.1', high='101', close='100.6'), context())[0] == 'CONFIRMED'
    x = setup('PC3')
    assert s.advance(x, bar(at, low='100.1', high='101', close='100.6'), context())[0] == 'CONFIRMED'
    x = setup('FA3')
    assert s.advance(x, bar(at, low='100.1', close='100.2'), context())[0] == 'EXPIRED'


def test_third_pc_bar_confirmation_precedes_expiration_and_gap_is_not_accepted():
    x = setup()
    at = s.dt(x['formed_at'])
    for i in (1, 2):
        b = bar(at + timedelta(minutes=5*i), close='100.4')
        assert s.advance(x, b, context())[0] == 'ARMED'
        x['transitions'].append({'at': b.available_at.isoformat()})
    assert s.advance(x, bar(at + timedelta(minutes=15), close='100.8'), context())[0] == 'CONFIRMED'
    assert s.advance(setup(), bar(at + timedelta(minutes=10)), context()) == ('INVALIDATED', 'MISSING_NEXT_CANDLE')


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_headroom_and_adverse_entry_exact_cost_notionals(side):
    long = side == 'LONG'
    x = setup(side=side, entry_cap='100', stop='99' if long else '101', target={'price': '103' if long else '97'})
    vetoes, actual = s.headroom(x)
    assert not vetoes
    entry, stop, target = D(100), D(x['stop']), D(x['target']['price'])
    win_cost = (entry+target)*D('.0005') + entry*D('.0003')
    loss_cost = (entry+stop)*D('.0005') + entry*D('.0003')
    assert D(actual['scenario_net_rr']) == (3-win_cost)/(1+loss_cost)
    x['target']['price'] = '99' if long else '101'
    assert s.headroom(x)[0] == ['TARGET_BEHIND_FORMATION_ENTRY_CAP']


def test_fixed_levels_cap_and_geometry_rechecked_after_adverse_entry():
    x = setup(entry_cap='100.01', stop='99', target={'price': '102'})
    result = s.final_geometry(x, bar(s.START, close='100'), [])
    assert result['primary_eligible'] and result['adverse_geometry']['0']
    assert not result['adverse_geometry']['0.025']  # cap now crossed
    assert D(result['funding_stress']['10']['scenario_net_rr']) < D(result['scenarios']['base']['scenario_net_rr'])
    assert x['stop'] == '99' and x['target']['price'] == '102'
    assert s.final_geometry(x, bar(s.START, close='102.1'), [])['geometry_status'] != 'SCREENABLE'


def test_visited_levels_only_use_observations_after_confirmation(monkeypatch):
    s.hourly_inventory.cache_clear()
    at = s.START
    rows = tuple(N(available_at=at+timedelta(hours=i), high=D('105') if i == 0 else D('101'), low=D('99')) for i in range(3))
    # Hashable input objects for the memoized wrapper, same attributes as real candles.
    from collections import namedtuple
    B = namedtuple('B', 'available_at high low')
    rows = tuple(B(r.available_at, r.high, r.low) for r in rows)
    level = N(available_at=at+timedelta(hours=1), kind='SWING_HIGH', price=D(102))
    monkeypatch.setattr(s.old, 'opposing_inventory', lambda *args: (level,))
    active, visited = s.hourly_inventory(rows, 'SYNTHETIC')
    assert active == (level,) and not visited  # pivot/source-window high is not later visitation
    future = rows + (B(at+timedelta(hours=3), D(102), D(100)),)
    assert s.hourly_inventory(future, 'SYNTHETIC') == ((), (level,))  # equality visits
    assert s.hourly_inventory(rows, 'SYNTHETIC') == (active, visited)  # old prefix unchanged
    s.hourly_inventory.cache_clear()


def test_previous_day_is_completed_fixed_range_and_missing_hour_refuses():
    midnight = s.START
    rows = tuple(N(symbol='SYNTHETIC', interval='1h', source_record_id=str(i),
        open_time=midnight-timedelta(hours=24-i), available_at=midnight-timedelta(hours=23-i),
        high=D(100+i), low=D(90+i)) for i in range(24))
    a = s.previous_day(N(candles_1h=rows), midnight+timedelta(minutes=5))
    extra = N(open_time=midnight, available_at=midnight+timedelta(hours=1), high=D(999), low=D(1))
    b = s.previous_day(N(candles_1h=rows+(extra,)), midnight+timedelta(hours=2))
    assert a == b and a['high'] == '123' and a['low'] == '90'
    assert s.previous_day(N(candles_1h=rows[1:]), midnight) is None


def test_exact_matching_excludes_future_bias_and_volatility_and_ignores_returns():
    at = s.START+timedelta(days=4, hours=1)
    e = {'setup_id': 'E', 'candidate': 'FA3', 'symbol': 'SYNTHETIC', 'side': 'LONG',
         'terminal_at': at.isoformat(), 'regime': 'UNCLASSIFIED', 'bias': 'BULLISH', 'atr_percentile': '40'}
    def row(key, when, **changes):
        return {**e, 'window_id': key, 'event_time': when.isoformat(), 'eligible_nontrigger': True, **changes}
    rows = [row('PAST', at-timedelta(days=1)), row('FUTURE', at+timedelta(days=1)),
            row('WRONG_BIAS', at-timedelta(days=1), bias='NEUTRAL'),
            row('WRONG_VOL', at-timedelta(days=1), atr_percentile='70'),
            row('TRIGGER', at-timedelta(days=1), eligible_nontrigger=False)]
    before = s.select_matches([e], rows)
    assert before[0]['control_id'] == 'PAST' and before[0]['candidate_count'] == 1
    for r in rows:
        r['outcome'] = '99999'
    assert before == s.select_matches([e], rows)


@pytest.mark.parametrize('first_reclaims', [False, True])
def test_full_reducer_first_excursion_and_appended_future_prefix(monkeypatch, first_reclaims):
    from astrabot.research.replay import HistoricalPanel
    from astrabot.universe.eligibility import SymbolData
    from test_c03_context_levels import bar as candle, SYMBOL
    hourly = tuple(candle('1h', s.START-timedelta(hours=24-i), center=D(100), width=D(4)) for i in range(24))
    fifteen = (candle('15m', s.START-timedelta(minutes=15), center=D(100)),)
    one = candle('5m', s.START, center=D('98.2'), width=D('1.4'), close=D('98.4') if first_reclaims else D('97.9'))
    two = candle('5m', s.START+timedelta(minutes=5), center=D('98.3'), width=D('1.0'), close=D('98.6'))
    # Source chronology and previous-day extraction use the real point-in-time adapter.
    data = SymbolData(candles_1h=hourly, candles_15m=fifteen, candles_5m=(one,two))
    monkeypatch.setattr(s.ctx, 'evaluate_context', lambda *a, **k: context())
    monkeypatch.setattr(s.old, 'pc_formation', lambda *a: (None, ['SYNTHETIC_NO_PC3']))
    monkeypatch.setattr(s.old, 'context_record', lambda *a: {'synthetic': True})
    monkeypatch.setattr(s, 'active_inventory', lambda *a: ((), {}))
    a = s.scan(HistoricalPanel({SYMBOL:data},(),{}), end=s.START+timedelta(minutes=11))
    future = candle('5m', s.START+timedelta(minutes=10), center=D(500), width=D(100))
    b = s.scan(HistoricalPanel({SYMBOL:data.model_copy(update={'candles_5m':(one,two,future)})},(),{}),
               end=s.START+timedelta(minutes=11))
    assert a == b and len(a['formations']) == 1
    if first_reclaims:
        assert len(a['events']) == 1
    else:
        assert not a['events'] and 'FIRST_BREACH_NOT_RECLAIMED' in a['formations'][0]['formation_vetoes']


def test_gate_rejects_large_failed_sample_and_never_advances_weak_controls():
    h = {'complete': 20, 'target_before_stop_upper': 4, 'target_before_stop_lower': 4,
         'paired': {'equal_day_difference_bps': None}}
    c = {'confirmations': 100, 'groups': {'base_survivors': {'n': 20, 'symbols': {'A': 5,'B': 5,'C': 5,'D': 5},
        'horizons': {'720': h, '60': h, '240': h}}}}
    assert s.gate(c) == 'REJECT'


@pytest.mark.parametrize('failed', ['n', 'days', 'symbols', 'ratio', 'target', 'matches', 'match_days', 'one', 'four', 'twelve', 'day_delete'])
def test_advancement_requires_every_prespecified_condition(failed):
    def paired(value):
        return {'pairs':10,'event_days':8,'equal_day_difference_bps':value,
                'leave_one_event_day_out_bps':['1','3']}
    h1, h4, h12 = ({'complete':20,'target_before_stop_lower':7,'target_before_stop_upper':8,
                     'paired':paired(v)} for v in ('1','2','0'))
    b = {'n':20,'symbols':dict.fromkeys('ABCD',5),'complete12h_market_days':list(range(8)),
         'complete12h_symbols':list('ABCD'),'horizons':{'60':h1,'240':h4,'720':h12}}
    c = {'confirmations':200,'groups':{'base_survivors':b}}
    assert s.gate(c) == 'ADVANCE_TO_R1_SOURCE_QUALIFICATION'
    if failed == 'n': h12['complete'] = 19
    if failed == 'days': b['complete12h_market_days'].pop()
    if failed == 'symbols': b['complete12h_symbols'].pop()
    if failed == 'ratio': c['confirmations'] = 201
    if failed == 'target': h12['target_before_stop_lower'] = 6
    if failed == 'matches': h12['paired']['pairs'] = 9
    if failed == 'match_days': h12['paired']['event_days'] = 7
    if failed == 'one': h1['paired']['equal_day_difference_bps'] = '0'
    if failed == 'four': h4['paired']['equal_day_difference_bps'] = '0'
    if failed == 'twelve': h12['paired']['equal_day_difference_bps'] = '-.01'
    if failed == 'day_delete': h4['paired']['leave_one_event_day_out_bps'][0] = '0'
    assert s.gate(c) == 'REVISE_BEFORE_R1'
    assert not all(s.gate_checks(c).values())


def test_s03_retained_census_hash_matching_paths_and_native_provenance():
    s.validate_inputs()
    census, digest = s.old.checked_json(s.OUT/'S03_CAUSAL_CENSUS.json.gz', compressed=True)
    p, _ = s.old.checked_json(s.OUT/'S03_EVIDENCE.json.gz', compressed=True)
    assert p['census_content_sha256'] == digest
    p['content_sha256'] = s.config_hash(p)
    assert s.render(p) == (s.OUT/'S03_SEPTEMBER_RESULTS.md').read_text()
    assert len(census['pool']) == 120960
    assert s.select_matches(census['events'], census['pool']) == census['matches']
    assert all('outcomes' not in r for r in census['events']+census['pool'])
    assert len(p['source_partitions']) == 84 and p['verified_source_bars'] == 266616
    assert all('2024-10' not in r['archive_id'] for r in p['source_partitions'])
    source = {r['source_key']: r for r in p['source_bars']}
    assert len(source) == len(p['source_bars'])
    for x in census['formations']:
        at = s.dt(x['formed_at'])
        if x['target']:
            assert s.dt(x['target']['available_at']) <= at
            assert all(s.dt(source[k]['available_at']) <= at for k in x['target']['source_keys'])
        for k in x.get('source_keys', [])+x.get('pullback_source_keys', [])+x.get('vwap_source_keys', []):
            assert s.dt(source[k]['available_at']) <= at
    for e in p['events']+p['controls']:
        event = 'setup_id' in e
        at = s.dt(e['terminal_at' if event else 'event_time'])
        ref = D(e['entry' if event else 'reference_close'])
        key = e['confirmation_source_key' if event else 'source_key']
        assert source[key]['symbol'] == e['symbol'] and D(source[key]['close']) == ref
        target = D(e['targets'][0]['price']) if event and e['targets'] else (
            D(e['normalization_target']) if not event and e['normalization_target'] else None)
        rows = [N(**{**source[k], 'source_record_id': source[k]['native_id'],
            'open_time': s.dt(source[k]['open_time']), 'available_at': s.dt(source[k]['available_at']),
            **{v: D(source[k][v]) for v in ('open','high','low','close')}}) for k in e['outcomes']['720']['source_keys']]
        actual = s.old.price_path(rows, at=at, reference=ref,
            distance=D(e['stop_distance' if event else 'normalization_distance']), side=e['side'], target2=target)
        assert actual == e['outcomes']
    assert s.summarize(census, p['events'], p['controls']) == p['candidates']


@pytest.fixture(scope='module')
def sealed_s03():
    packet, _ = s.old.checked_json(s.OUT/'S03_EVIDENCE.json.gz', compressed=True)
    return packet, {r['source_key']: r for r in packet['source_bars']}


def test_comparator_partitions_and_retained_code_match_exact_sealed_inputs(sealed_s03):
    from hashlib import sha256
    import importlib.metadata
    packet, _ = sealed_s03
    prior, _ = s.old.checked_json(s.OUT/'S01_EVIDENCE.json.gz', compressed=True)
    census, _ = s.old.checked_json(s.OUT/'S03_CAUSAL_CENSUS.json.gz', compressed=True)
    assert packet['source_partitions'] == prior['source_partitions']
    assert census['causal_implementation_sha256'] == s.causal_fingerprint()
    for name, digest in packet['research_code_sha256'].items():
        assert sha256((s.ROOT/name).read_bytes()).hexdigest() == digest
    assert packet['dependencies'] == {name: importlib.metadata.version(name) for name in packet['dependencies']}
    assert packet['strict_eligible_candidates'] == 0
    assert not packet['october_outcomes_accessed']


def test_original_price_ordering_independent_of_shared_path_function(sealed_s03):
    packet, source = sealed_s03
    counts = {'PC3': [0, 0, 0], 'FA3': [0, 0, 0]}
    for e in packet['events']:
        if not s.is_base(e):
            continue
        h = e['outcomes']['720']
        assert h['complete']
        rows = [source[k] for k in h['source_keys']]
        stop, target = D(e['stop']), D(e['targets'][0]['price'])
        long = e['side'] == 'LONG'
        stop_index = next((i for i, r in enumerate(rows) if
            (D(r['low']) <= stop if long else D(r['high']) >= stop)), None)
        target_index = next((i for i, r in enumerate(rows) if
            (D(r['high']) >= target if long else D(r['low']) <= target)), None)
        lower = target_index is not None and (stop_index is None or target_index < stop_index)
        upper = target_index is not None and (stop_index is None or target_index <= stop_index)
        assert h['full_ladder_lower'] == lower
        assert h['full_ladder_upper'] == upper
        assert (h['stop_touch']['source_key'] if h['stop_touch'] else None) == (
            rows[stop_index]['source_key'] if stop_index is not None else None)
        assert (h['structural_target_touch']['source_key'] if h['structural_target_touch'] else None) == (
            rows[target_index]['source_key'] if target_index is not None else None)
        counts[e['candidate']][0] += 1
        counts[e['candidate']][1] += lower
        counts[e['candidate']][2] += stop_index is not None and (target_index is None or stop_index < target_index)
    assert counts == {'PC3': [9, 1, 8], 'FA3': [1, 0, 1]}


def test_original_entry_economics_independently_checks_both_fee_notionals(sealed_s03):
    packet, _ = sealed_s03
    for e in packet['events']:
        if not e.get('scenarios'):
            continue
        entry, stop, target, distance = D(e['entry']), D(e['stop']), D(e['targets'][0]['price']), D(e['stop_distance'])
        direction = D(1) if e['side'] == 'LONG' else D(-1)
        for name, terms in s.SCENARIOS.items():
            fee = D(terms['fee_bps_per_side'])/10000
            other = entry*(D(terms['friction_bps_per_route'])+D(terms['funding_bps']))/10000
            win = (entry+target)*fee+other
            loss = (entry+stop)*fee+other
            actual = e['scenarios'][name]
            assert D(actual['cost_r']) == loss/distance
            # Match the declared finite-Decimal order of operations, with a
            # tight tolerance for equivalent unnormalized arithmetic.
            expected = (direction*(target-entry)-win)/(distance+loss)
            assert abs(D(actual['scenario_net_rr'])-expected) < D('1e-24')
            assert actual['passes_cost_screen'] == (expected >= D('1.5'))


def test_native_ids_csv_locators_and_clock_are_original_september_or_history(sealed_s03):
    from datetime import datetime, timezone
    packet, source = sealed_s03
    minutes = {'5m':5, '15m':15, '1h':60, '4h':240}
    epoch = datetime(1970,1,1,tzinfo=timezone.utc)
    partition_ids = {r['archive_id'] for r in packet['source_partitions']}
    for r in source.values():
        at, available = s.dt(r['open_time']), s.dt(r['available_at'])
        assert at < s.END and available <= s.END
        assert r['archive_id'] in partition_ids
        assert int(r['native_id']) == int((at-epoch).total_seconds()*1000)
        assert available-at == timedelta(minutes=minutes[r['interval']])
        assert json.loads(r['source_key']) == [r['symbol'],r['interval'],r['native_id']]
        assert r['csv_record_number_including_header'] == (
            ((at.day-1)*1440+at.hour*60+at.minute)//minutes[r['interval']])+2
