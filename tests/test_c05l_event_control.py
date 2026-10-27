"""Method checks only; these invented candles never enter the empirical packet."""
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from scripts import c05_t1_event_control as study


def bars(at, prices):
    return [SimpleNamespace(open_time=at+timedelta(minutes=5*i),
        symbol='SYNTHETIC', interval='5m', available_at=at+timedelta(minutes=5*(i+1)), source_record_id=f'SYNTHETIC_ONLY_{i}',
        high=D(high), low=D(low), close=D(close)) for i, (high, low, close) in enumerate(prices)]


@pytest.mark.parametrize('side', ['LONG', 'SHORT'])
def test_same_bar_stop_and_full_ladder_remains_ambiguous(side):
    at = study.START
    rows = bars(at, [('104', '96', '100')]*3)
    result = study.price_path(rows, at=at, reference=D(100), distance=D(1),
        side=side, target2=D(103) if side == 'LONG' else D(97))['15']
    assert result['complete']
    assert not result['full_ladder_lower'] and result['full_ladder_upper']
    assert result['target2_order']['same_bar_ambiguous']
    assert D(result['mfe_r']) == 4 and D(result['mae_r']) == -4
    assert result['stop_touch']['minutes_lower'] == 0
    assert result['stop_touch']['minutes_upper'] == 5


def test_partial_target_then_stop_does_not_count_distant_structural_target():
    at = study.START
    rows = bars(at, [('101.5', '99.5', '101'), ('102', '98', '99'), ('104', '99', '103')])
    result = study.price_path(rows, at=at, reference=D(100), distance=D(1),
        side='LONG', target2=D(103))['15']
    assert result['target1_order']['strict_before_stop']
    assert not result['full_ladder_upper']
    assert result['structural_target_touch']['minutes_upper'] == 15
    # Full-horizon observational close persists beyond the hypothetical stop.
    assert D(result['signed_close_r']) == 3


def test_split_censoring_never_reads_appended_validation_candle():
    at = study.END-timedelta(minutes=5)
    rows = bars(at, [('101', '99.5', '100.5'), ('9999', '1', '9999'), ('9999', '1', '9999')])
    result = study.price_path(rows, at=at, reference=D(100), distance=D(1), side='LONG', target2=D(103))['15']
    assert not result['complete'] and result['status'] == 'SPLIT_CENSORED'
    assert result['observed_bars'] == 1 and D(result['mfe_r']) == 1
    assert result['signed_close_bps'] is None


def test_missing_forward_candle_is_not_silently_bridged():
    at = study.START
    rows = bars(at, [('101', '99.5', '100.5')]*3)
    with pytest.raises(ValueError, match='missing forward candle'):
        study.price_path([rows[0], rows[2]], at=at, reference=D(100), distance=D(1), side='LONG')


def test_control_matching_ignores_future_outcome_fields_and_obeys_past_embargo():
    at = study.START+timedelta(days=3)
    event = {'setup_id': 'CASE', 'symbol': 'X', 'side': 'LONG', 'terminal_at': at.isoformat(),
             'confirmation_regime': 'TREND_UP', 'confirmation_atr_percentile': '30'}
    def candidate(identity, when, **changes):
        return {'window_id': identity, 'symbol': 'X', 'event_time': when.isoformat(),
            'eligible_nontrigger': True, 'regime': 'TREND_UP', 'atr_percentile': '30', **changes}
    valid = candidate('PAST', at-timedelta(days=1))
    pool = [valid, candidate('FUTURE', at+timedelta(days=1)),
        candidate('OVERLAP', at-timedelta(hours=1)),
        candidate('OLD', at-timedelta(days=8)),
        candidate('ACTIVE', at-timedelta(days=2), eligible_nontrigger=False),
        candidate('OTHER_VOLATILITY', at-timedelta(days=2), atr_percentile='60')]
    first = study.select_matches([event], pool)
    for row in pool:
        row['future_return'] = 'IMPOSSIBLY_FAVORABLE'
    assert first == study.select_matches([event], pool)
    assert first[0]['control_id'] == 'PAST' and first[0]['candidate_count'] == 1


def test_dependence_components_join_symbols_and_midnight_windows():
    t = study.START
    assert study.market_components([(t, t+timedelta(hours=12)),
        (t+timedelta(hours=10), t+timedelta(hours=22)),
        (t+timedelta(days=2), t+timedelta(days=2, hours=12))]) == 2


def test_native_timestamp_collisions_preserve_symbol_and_interval_prices():
    rows = [SimpleNamespace(symbol=symbol, interval=interval,
        source_record_id='1725148800000', close=D(price))
        for symbol, interval, price in [('BTCUSDT', '5m', '58000'),
            ('SOLUSDT', '5m', '135'), ('SOLUSDT', '1h', '136')]]
    retained = {study.bar_key(row): row for row in rows}
    assert len(retained) == 3
    assert [retained[study.bar_key(row)].close for row in rows] == [D(58000), D(135), D(136)]
    assert all(row.source_record_id == '1725148800000' for row in retained.values())


def test_all_event_control_paths_and_frozen_sources_resolve_exactly():
    import gzip
    import json
    packet = json.loads(gzip.decompress((study.ROOT /
        'research/c05/C05_L_T1_EVENT_CONTROL_EVIDENCE.json.gz').read_bytes()))
    source = {r['source_key']: r for r in packet['source_bars']}
    native = {}
    for key, row in source.items():
        assert key == study.source_key(row['symbol'], row['interval'], row['source_record_id'])
        native.setdefault((row['interval'], row['source_record_id']), []).append(row)
    assert any(len({r['symbol'] for r in rows}) > 1 and len({r['close'] for r in rows}) > 1
        for rows in native.values())
    for history in packet['setup_histories'].values():
        symbol = history['formation_snapshot']['symbol']
        for key in history['formation_source_keys'] + [t['source_key'] for t in history['transitions']]:
            assert source[key]['symbol'] == symbol and source[key]['interval'] == '5m'
    for row in packet['events'] + packet['controls']:
        event = 'setup_id' in row
        reference = source[row['confirmation_source_key' if event else 'reference_source_key']]
        assert reference['symbol'] == row['symbol'] and reference['interval'] == '5m'
        assert reference['close'] == row['entry' if event else 'reference_close']
        at = study.dt(row['terminal_at' if event else 'event_time'])
        keys = row['outcomes']['720']['source_keys']
        bars = [SimpleNamespace(**{**source[key],
            'open_time': study.dt(source[key]['open_time']),
            'available_at': study.dt(source[key]['available_at']),
            **{name: D(source[key][name]) for name in ('open', 'high', 'low', 'close')}}) for key in keys]
        assert all(b.symbol == row['symbol'] and b.interval == '5m' for b in bars)
        target = row['history']['structural_target'] if event else None
        rebuilt = study.price_path(bars, at=at,
            reference=D(row['entry' if event else 'reference_close']),
            distance=D(row['stop_distance' if event else 'normalization_distance']),
            side=row['side'], target2=D(target['price']) if target else None)
        assert rebuilt == row['outcomes']
        if event:
            for name in ('stop_anchor', 'structural_target'):
                level = row['history'][name]
                if level:
                    for sid, key in zip(level['source_ids'], row['history'][name + '_source_keys'], strict=True):
                        original = source[key]
                        assert (original['symbol'], original['interval'], original['source_record_id']) == (
                            level['symbol'], level['timeframe'], sid)


def test_authentic_packet_keeps_original_membership_and_all_paths_in_development():
    import gzip
    import json
    from astrabot.data.models import config_hash
    directory = study.ROOT/'research/c05'
    packet = json.loads(gzip.decompress((directory/'C05_L_T1_EVENT_CONTROL_EVIDENCE.json.gz').read_bytes()))
    digest = packet.pop('content_sha256')
    assert config_hash(packet) == digest
    matching = json.loads(gzip.decompress((directory/'C05_L_MATCHES.json.gz').read_bytes()))
    assert config_hash({k: v for k, v in matching.items() if k != 'content_sha256'}) == matching['content_sha256']
    assert packet['summary']['matching_content_sha256'] == matching['content_sha256']
    original = json.loads(gzip.decompress((directory/'C05_K_R0_CENSUS.json.gz').read_bytes()))
    original_events = {r['setup_id']: r for r in original['confirmations'] if r['policy'] == 'T1'}
    assert {r['setup_id'] for r in packet['events']} == set(original_events)
    assert len(original_events) == 434
    assert {r['setup_id'] for r in packet['events'] if study.base_survivor(r)} == {
        k for k, r in original_events.items() if study.base_survivor(r)}
    assert len(packet['setup_histories']) == 624
    source = {r['source_key']: r for r in packet['source_bars']}
    assert len(source) == len(packet['source_bars'])
    for event in packet['events']:
        frozen = original_events[event['setup_id']]
        assert all(event[k] == v for k, v in frozen.items())
        at = study.dt(event['terminal_at'])
        assert study.START <= at < study.END
        for horizon, outcome in event['outcomes'].items():
            assert outcome['complete'] == (at+timedelta(minutes=int(horizon)) <= study.END)
            for native_id, identity in zip(outcome['source_record_ids'], outcome['source_keys'], strict=True):
                bar = source[identity]
                assert (bar['symbol'], bar['interval'], bar['source_record_id']) == (event['symbol'], '5m', native_id)
                assert study.dt(bar['open_time']) >= at
                assert study.dt(bar['available_at']) <= min(at+timedelta(minutes=int(horizon)), study.END)
    pool = {r['window_id']: r for r in matching['pool']}
    for link in matching['matches']:
        if link['control_id']:
            control = pool[link['control_id']]
            assert control['eligible_nontrigger']
            lag = study.dt(original_events[link['event_id']]['terminal_at'])-study.dt(control['event_time'])
            assert timedelta(hours=12) <= lag <= timedelta(days=7)
    assert all(study.dt(r['open_time']) < study.END for r in source.values())
    assert packet['summary']['strict_eligible_candidates'] == 0
    assert len(packet['summary']['source_manifest']['unopened_archive_ids']) == 28
