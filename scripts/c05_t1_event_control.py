"""Frozen September T1 exploratory price paths and causal matched controls.

No strategy admission, execution simulation, or trade performance statistics.
See C05_L_PREREGISTRATION.md, committed before outcomes were loaded.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal as D
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from c05_r0_market_economics import (START, END, SCENARIOS, _memoize_numeric,
                                    cost_screen, distribution, geometry)
from astrabot.data.models import binance_usdm_instrument_id, config_hash, stable_id
from astrabot.research import context as ctx, policies
from astrabot.research.integrated import HISTORY_LIMITS
from astrabot.research.replay import _panel_point_in_time, load_public_um_archive_panel
from astrabot.research.statistics import effective_sample_size, matched_controls

HORIZONS = (15, 60, 240, 720)
MANIFEST_HASH = '6a34aae6b37ec9b48aa166dda52cd578a86776ef8b36be05aaaa5bf42f51058a'
CENSUS_HASH = 'ac798c084efafeba4ee0bf61e9333fd5e50b077bed6f5de6db68d0c8d676df7f'
SEED = 20261026


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def write_gzip(path, value):
    with path.open('wb') as stream:
        with gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as compressed:
            compressed.write((json.dumps(value, sort_keys=True, indent=2)+'\n').encode())


def source_key(symbol, interval, native_id):
    """Native timestamps are scoped to an instrument AND candle interval."""
    return json.dumps([symbol, interval, native_id], separators=(',', ':'))


def bar_key(bar):
    return source_key(bar.symbol, bar.interval, bar.source_record_id)


def base_survivor(row):
    return (row['geometry_status'] == 'SCREENABLE'
            and row['scenarios']['base']['passes_with_route'] and not row['known_context_veto'])


def atr_bin(value):
    return min(3, int(D(value)//25))


def cohort(side, percentile, at):
    return f'{side}|ATR_QUARTILE_{atr_bin(percentile)}|UTC_SESSION_{at.hour//4}'


def classify(row):
    if row['geometry_status'] != 'SCREENABLE':
        return row['geometry_status']
    if not row['route_feasible']:
        return 'KNOWN_ROUTE_REJECTED'
    if not row['scenarios']['base']['passes_cost_screen']:
        return 'BASE_COST_REJECTED'
    if row['known_context_veto']:
        return 'KNOWN_CONTEXT_REJECTED'
    return 'FROZEN_BASE_SURVIVOR'


def metadata_and_histories(panel, census):
    """Reconstruct frozen histories and causal pool without consulting returns."""
    formations = [r for r in census['formations'] if r['policy'] == 'T1']
    confirmations = [r for r in census['confirmations'] if r['policy'] == 'T1']
    by_id = {r['setup_id']: r for r in confirmations}
    recovered, pool, chronologies = {}, [], {}
    for symbol in sorted(panel.symbols):
        symbol_formations = [r for r in formations if r['symbol'] == symbol]
        starting = defaultdict(list)
        for r in symbol_formations:
            starting[dt(r['formed_at'])].append(r)
        active = {}
        last_day = None
        for bar in panel.symbols[symbol].candles_5m:
            at = bar.available_at
            if not START <= at < END:
                continue
            if at.date() != last_day:
                print(f'metadata {symbol} {at.date()}', flush=True)
                last_day = at.date()
            data = _panel_point_in_time(panel, symbol, at, HISTORY_LIMITS)
            context = ctx.evaluate_context(data, symbol=symbol,
                instrument_id=binance_usdm_instrument_id(symbol), as_of=at)
            terminal_now = []
            # Original active histories are replayed through unchanged C03 functions.
            for sid, setup in list(active.items()):
                advanced = policies.advance_setup(setup, data, context)
                active[sid] = advanced
                chronologies[sid]['transitions'].append({'at': at.isoformat(),
                    'state': advanced.snapshot.state, 'notes': list(advanced.notes),
                    'source_record_id': bar.source_record_id, 'source_key': bar_key(bar)})
                if advanced.snapshot.state in policies.TERMINAL | {'CONFIRMED'}:
                    original = next(r for r in symbol_formations if r['setup_id'] == sid)
                    assert advanced.snapshot.state == original['state'], sid
                    assert at == dt(original['terminal_at']), sid
                    assert (advanced.notes[-1] if advanced.notes else advanced.snapshot.state) == original['reason']
                    chronologies[sid]['terminal_snapshot'] = advanced.snapshot.model_dump(mode='json')
                    terminal_now.append(sid)
                    if sid in by_id:
                        row = by_id[sid]
                        calc = geometry(advanced, data, at)
                        assert all(row[k] == v for k, v in calc.items()), sid
                        assert row['confirmation_regime'] == context.classification
                        assert D(row['confirmation_atr_percentile']) == context.atr_percentile
                        sign = D(1) if row['side'] == 'LONG' else D(-1)
                        opposing = sorted((x for x in advanced.opposing_at_formation
                            if x.kind == ('SWING_HIGH' if sign == 1 else 'SWING_LOW')
                            and not x.invalidated and x.available_at <= advanced.snapshot.available_at
                            and sign*(x.price-D(row['entry'])) > 0),
                            key=lambda x: (sign*(x.price-D(row['entry'])), x.available_at, x.level_id))
                        recovered[sid] = {'snapshot': advanced.snapshot.model_dump(mode='json'),
                            'processed_source_ids': list(advanced.processed_event_ids),
                            'stop_anchor': advanced.levels[0].model_dump(mode='json'),
                            'structural_target': opposing[0].model_dump(mode='json') if opposing else None,
                            'prior_vwap_event_id': advanced.prior_vwap_event_id,
                            'session_id': advanced.session_id,
                            'geometry_matches_c05k': True}
            # Formations come from the fixed census, never future outcomes.
            for original in starting.get(at, []):
                setup, reasons = policies.form_setup('T1', data, context, original['side'],
                    stable_id('c05k.price.v1', symbol, at))
                assert setup is not None, (original['setup_id'], reasons)
                assert setup.snapshot.setup_id == original['setup_id']
                active[original['setup_id']] = setup
                chronologies[original['setup_id']] = {
                    'formation_snapshot': setup.snapshot.model_dump(mode='json'),
                    'formation_source_ids': list(setup.processed_event_ids),
                    'formation_source_keys': [source_key(symbol, '5m', sid) for sid in setup.processed_event_ids],
                    'transitions': [{'at': at.isoformat(), 'state': setup.snapshot.state,
                        'notes': list(setup.notes), 'source_record_id': bar.source_record_id, 'source_key': bar_key(bar)}]}
            reasons = []
            if active:
                reasons.append('T1_ACTIVE_OR_TERMINAL_AT_CUTOFF')
            if at+timedelta(hours=12) > END:
                reasons.append('FULL_12H_CROSSES_DEVELOPMENT_END')
            if context.atr_percentile is None or context.readiness != 'READY':
                reasons.append('CONTEXT_UNAVAILABLE')
            # A valid fresh formation is not a non-trigger, including a previously
            # deduplicated pattern. No later formation is examined for this check.
            if not active and context.readiness == 'READY':
                for side in ('LONG', 'SHORT'):
                    candidate, _ = policies.form_setup('T1', data, context, side,
                        stable_id('c05l.control-screen.v1', symbol, at))
                    if candidate:
                        reasons.append('T1_FORMATION_AT_CUTOFF')
                        break
            pool.append({'window_id': stable_id('c05l.pool.v1', symbol, at),
                'symbol': symbol, 'event_time': at.isoformat(), 'regime': context.classification,
                'atr_percentile': str(context.atr_percentile) if context.atr_percentile is not None else None,
                'session': at.hour//4, 'context_id': context.context_id,
                'source_record_id': bar.source_record_id, 'reference_close': str(bar.close),
                'eligible_nontrigger': not reasons, 'exclusions': reasons})
            for sid in terminal_now:
                del active[sid]
        assert not active, (symbol, 'unexpected end-censored T1 history')
    assert len(formations) == 624 and len(confirmations) == len(recovered) == 434
    assert sum(base_survivor(r) for r in confirmations) == 24
    assert sum(r['geometry_status'] == 'SCREENABLE' for r in confirmations) == 149
    assert len(pool) == 60480
    return formations, confirmations, recovered, pool, chronologies


def select_matches(confirmations, pool):
    index = defaultdict(list)
    for r in pool:
        if r['eligible_nontrigger']:
            for side in ('LONG', 'SHORT'):
                cr = {**r, 'cohort': cohort(side, r['atr_percentile'], dt(r['event_time'])),
                      'is_trigger': False}
                index[r['symbol'], r['regime'], cr['cohort']].append(cr)
    matches = []
    for event in confirmations:
        at = dt(event['terminal_at'])
        trigger = {'window_id': event['setup_id'], 'symbol': event['symbol'],
            'regime': event['confirmation_regime'], 'event_time': at.isoformat(), 'is_trigger': True,
            'cohort': cohort(event['side'], event['confirmation_atr_percentile'], at)}
        candidates = [r for r in index[trigger['symbol'], trigger['regime'], trigger['cohort']]
                      if at-timedelta(days=7) <= dt(r['event_time']) <= at-timedelta(hours=12)]
        mapping = matched_controls([trigger, *candidates], seed=SEED, embargo_hours=12)
        control = mapping.get(event['setup_id'])
        matches.append({'event_id': event['setup_id'], 'control_id': control,
            'candidate_count': len(candidates), 'match_cohort': trigger['cohort'],
            'status': 'MATCHED' if control else 'NO_EXACT_PAST_CONTROL',
            'candidate_ids_sha256': config_hash({'ids': sorted(r['window_id'] for r in candidates)}),
            'candidate_rule': 'same symbol/regime/side/ATR quartile/4h UTC session; past12h..7d; with replacement'})
    return matches


def touch_order(stop_index, target_index):
    if target_index is None:
        return {'strict_before_stop': False, 'possible_before_stop': False, 'same_bar_ambiguous': False}
    return {'strict_before_stop': stop_index is None or target_index < stop_index,
            'possible_before_stop': stop_index is None or target_index <= stop_index,
            'same_bar_ambiguous': stop_index == target_index}


def price_path(bars, *, at, reference, distance, side, target2=None, end=END):
    """Observe candles; touches are not executable prices or trade outcomes."""
    sign = D(1) if side == 'LONG' else D(-1)
    if distance <= 0:
        raise ValueError('nonpositive original price-R')
    stop, target1 = reference-sign*distance, reference+sign*distance
    future = [b for b in bars if b.open_time >= at and b.available_at <= min(at+timedelta(hours=12), end)]
    for i, bar in enumerate(future):
        if bar.open_time != at+timedelta(minutes=5*i):
            raise ValueError('nonchronological or missing forward candle')
    result = {}
    for minutes in HORIZONS:
        endpoint = at+timedelta(minutes=minutes)
        rows = [b for b in future if b.available_at <= endpoint]
        complete = endpoint <= end and len(rows) == minutes//5
        def first_hit(level, favorable):
            if level is None:
                return None
            for i, b in enumerate(rows):
                high, low = (sign*(b.high-level), sign*(b.low-level))
                if (max(high, low) >= 0) if favorable else (min(high, low) <= 0):
                    return i
            return None
        si, t1i, t2i = first_hit(stop, False), first_hit(target1, True), first_hit(target2, True)
        def touch(i):
            return None if i is None else {'source_record_id': rows[i].source_record_id, 'source_key': bar_key(rows[i]),
                'bar_open': rows[i].open_time.isoformat(), 'available_at': rows[i].available_at.isoformat(),
                'minutes_lower': i*5, 'minutes_upper': (i+1)*5}
        favorable = max([D(0), *(sign*((b.high if sign == 1 else b.low)-reference) for b in rows)])
        adverse = min([D(0), *(sign*((b.low if sign == 1 else b.high)-reference) for b in rows)])
        signed = sign*(rows[-1].close-reference) if rows else None
        ordered = target2 is not None and sign*(target2-target1) > 0
        result[str(minutes)] = {'complete': complete, 'status': 'OBSERVED' if complete else 'SPLIT_CENSORED',
            'observed_bars': len(rows), 'requested_endpoint': endpoint.isoformat(),
            'last_available_at': rows[-1].available_at.isoformat() if rows else None,
            'source_record_ids': [b.source_record_id for b in rows],
            'source_keys': [bar_key(b) for b in rows],
            'signed_close_r': str(signed/distance) if complete and signed is not None else None,
            'signed_close_bps': str(signed/reference*10000) if complete and signed is not None else None,
            'mfe_r': str(favorable/distance), 'mae_r': str(adverse/distance),
            'favorable_bps': str(favorable/reference*10000), 'adverse_bps': str(adverse/reference*10000),
            'stop_touch': touch(si), 'target1_touch': touch(t1i), 'structural_target_touch': touch(t2i),
            'target1_order': touch_order(si, t1i), 'target2_order': touch_order(si, t2i),
            'ordered_ladder': ordered,
            'full_ladder_lower': ordered and touch_order(si, t2i)['strict_before_stop'],
            'full_ladder_upper': ordered and touch_order(si, t2i)['possible_before_stop'],
            'target2_not_touched': target2 is not None and t2i is None,
            'time_bound': '12H_OBSERVATION_BOUNDARY' if minutes == 720 and complete else None}
    return result


def market_components(windows):
    """Connected overlapping market-time intervals, including across UTC days."""
    groups, right = 0, None
    for left, end in sorted(windows):
        if right is None or left >= right:
            groups += 1
            right = end
        else:
            right = max(right, end)
    return groups


def paired_summary(events, controls, matches, minutes):
    controls_by_event = {r['matched_event_id']: r for r in controls}
    matches_by_id = {r['event_id']: r for r in matches}
    daily, symbol_diffs, pairs = defaultdict(list), defaultdict(list), []
    matched_events, matched_controls_outcomes = [], []
    for event in events:
        link = matches_by_id[event['setup_id']]
        if not link['control_id']:
            continue
        control = controls_by_event[event['setup_id']]
        a, b = event['outcomes'][str(minutes)], control['outcomes'][str(minutes)]
        if not a['complete'] or not b['complete']:
            continue
        matched_events.append(a)
        matched_controls_outcomes.append(b)
        pair = {'event_id': event['setup_id'], 'control_id': link['control_id'],
            'event_day': event['terminal_at'][:10], 'control_day': control['event_time'][:10],
            'symbol': event['symbol'],
            'signed_close_difference_bps': float(D(a['signed_close_bps'])-D(b['signed_close_bps'])),
            'signed_close_difference_r': float(D(a['signed_close_r'])-D(b['signed_close_r'])),
            'mfe_difference_r': float(D(a['mfe_r'])-D(b['mfe_r'])),
            'mae_difference_r': float(D(a['mae_r'])-D(b['mae_r']))}
        pairs.append(pair)
        daily[pair['event_day']].append(pair)
        symbol_diffs[event['symbol']].append(pair['signed_close_difference_bps'])
    day_means = {day: {metric: mean(p[metric] for p in rows) for metric in (
        'signed_close_difference_bps', 'signed_close_difference_r', 'mfe_difference_r', 'mae_difference_r')}
        for day, rows in sorted(daily.items())}
    means = list(day_means.values())
    leave_one = [mean(v['signed_close_difference_bps'] for j, v in enumerate(means) if i != j)
                 for i in range(len(means))] if len(means) > 1 else []
    return {'pair_count': len(pairs), 'event_day_count': len(daily),
        'matched_event_outcomes': {k: distribution(r[k] for r in matched_events)
            for k in ('signed_close_bps', 'signed_close_r', 'mfe_r', 'mae_r')},
        'matched_control_outcomes': {k: distribution(r[k] for r in matched_controls_outcomes)
            for k in ('signed_close_bps', 'signed_close_r', 'mfe_r', 'mae_r')},
        'equal_day_mean': {k: mean(v[k] for v in means) for k in means[0]} if means else None,
        'leave_one_event_day_out_bps_range': [min(leave_one), max(leave_one)] if leave_one else None,
        'by_event_day': day_means,
        'by_symbol_mean_difference_bps': {k: mean(v) for k, v in sorted(symbol_diffs.items())},
        'ci95': None, 'uncertainty_status': 'LIMITED_CORRELATED_SAMPLE_NO_INFERENTIAL_CI', 'pairs': pairs}


def group_summary(events, controls, matches):
    counts = Counter(r['terminal_at'][:10] for r in events)
    windows = [(dt(r['terminal_at']), min(dt(r['terminal_at'])+timedelta(hours=12), END)) for r in events]
    event_ids = {r['setup_id'] for r in events}
    for control in controls:
        if control['matched_event_id'] in event_ids:
            windows.append((dt(control['event_time']), dt(control['event_time'])+timedelta(hours=12)))
    overlaps = sum(a < d and c < b for i, (a, b) in enumerate(windows) for c, d in windows[i+1:])
    horizons = {}
    for minutes in HORIZONS:
        complete = [r['outcomes'][str(minutes)] for r in events if r['outcomes'][str(minutes)]['complete']]
        horizons[str(minutes)] = {'complete': len(complete), 'censored': len(events)-len(complete),
            'signed_close_bps': distribution(r['signed_close_bps'] for r in complete),
            'signed_close_r': distribution(r['signed_close_r'] for r in complete),
            'mfe_r': distribution(r['mfe_r'] for r in complete), 'mae_r': distribution(r['mae_r'] for r in complete),
            'target1_strict_before_stop': sum(r['target1_order']['strict_before_stop'] for r in complete),
            'target1_possible_before_stop': sum(r['target1_order']['possible_before_stop'] for r in complete),
            'target1_same_bar_ambiguous': sum(r['target1_order']['same_bar_ambiguous'] for r in complete),
            'full_ladder_lower': sum(r['full_ladder_lower'] for r in complete),
            'full_ladder_upper': sum(r['full_ladder_upper'] for r in complete),
            'full_ladder_lower_by_11h55': sum(r['full_ladder_lower']
                and r['structural_target_touch']['minutes_upper'] <= 715 for r in complete),
            'target2_same_bar_ambiguous': sum(r['target2_order']['same_bar_ambiguous'] for r in complete),
            'target2_not_touched': sum(r['target2_not_touched'] for r in complete),
            'stop_touched': sum(r['stop_touch'] is not None for r in complete),
            'comparison': paired_summary(events, controls, matches, minutes)}
    return {'n': len(events), 'market_days': dict(sorted(counts.items())),
        'kish_day_weight_effective_n': effective_sample_size(list(counts.values())),
        'overlapping_case_control_window_pairs': overlaps,
        'connected_case_control_market_time_components': market_components(windows),
        'horizons': horizons}


def decision(summary):
    base = summary['groups']['frozen_base_survivors']['horizons']
    twelve = base['720']
    matched = twelve['comparison']['equal_day_mean']
    if not twelve['complete'] or matched is None:
        return 'T1_INDETERMINATE'
    if (twelve['full_ladder_upper']/twelve['complete'] <= .25
            and matched['signed_close_difference_bps'] <= 0):
        return 'T1_RESEARCH_CASE_WEAK_REVISE'
    comparisons = [base[str(h)]['comparison'] for h in (60, 240, 720)]
    if (twelve['full_ladder_lower']/twelve['complete'] > .25
            and all(c['equal_day_mean'] and c['equal_day_mean']['signed_close_difference_bps'] > 0
                    and c['leave_one_event_day_out_bps_range']
                    and c['leave_one_event_day_out_bps_range'][0] > 0 for c in comparisons)):
        return 'T1_PROSPECTIVE_STUDY_JUSTIFIED_CONDITIONALLY'
    return 'T1_INDETERMINATE'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'research/c05')
    args = parser.parse_args()
    manifest_path = ROOT/'research/c04/historical_manifest.json'
    assert sha256(manifest_path.read_bytes()).hexdigest() == MANIFEST_HASH
    census = json.loads(gzip.decompress((ROOT/'research/c05/C05_K_R0_CENSUS.json.gz').read_bytes()))
    assert census.pop('content_sha256') == CENSUS_HASH and config_hash(census) == CENSUS_HASH
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _memoize_numeric()
    panel = load_public_um_archive_panel(manifest_path, args.data_root, source_end_exclusive=END)
    formations, confirmations, recovered, pool, chronologies = metadata_and_histories(panel, census)
    matches = select_matches(confirmations, pool)
    match_packet = {'schema_version': 'c05l.causal-matching.v1', 'seed': SEED,
        'preregistration_sha256': sha256((ROOT/'research/c05/C05_L_PREREGISTRATION.md').read_bytes()).hexdigest(),
        'census_content_sha256': CENSUS_HASH, 'pool': pool, 'matches': matches}
    match_hash = config_hash(match_packet)
    write_gzip(args.output_dir/'C05_L_MATCHES.json.gz', {**match_packet, 'content_sha256': match_hash})
    print(f'Forward-outcome-blind matches fixed: {match_hash}', flush=True)
    pool_by_id = {r['window_id']: r for r in pool}
    funding_audit_path = ROOT/'research/c05/C05_K_FUNDING_AUDIT.json'
    funding_audit = json.loads(funding_audit_path.read_text())
    outcomes, controls, used_bars = [], [], {}
    for row in confirmations:
        history = recovered[row['setup_id']]
        target = history['structural_target']
        target2 = D(target['price']) if target else None
        at = dt(row['terminal_at'])
        bars = panel.symbols[row['symbol']].candles_5m
        start = bisect_right(bars, at, key=lambda b: b.available_at)
        path = bars[start:start+144]
        used_bars[bar_key(bars[start-1])] = bars[start-1]
        results = price_path(path, at=at, reference=D(row['entry']), distance=D(row['stop_distance']),
            side=row['side'], target2=target2)
        r = {**row, 'confirmation_source_key': bar_key(bars[start-1]), 'classification': classify(row), 'history': history, 'outcomes': results,
             'thesis_management': 'NO_SEPARATE_FROZEN_POST_ENTRY_THESIS_EXIT_IMPLEMENTED; OPTIONAL_MANAGEMENT_DISABLED'}
        r['hypothetical_entry_sensitivity'] = {}
        for shift in (D(0), D('.025'), D('.05')):
            if row['geometry_status'] == 'SCREENABLE':
                r['hypothetical_entry_sensitivity'][str(shift)] = cost_screen(row, SCENARIOS['base'], entry_shift_r=shift)
        r['model_drag_original_r'] = {name: row['scenarios'][name]['cost_r'] for name in SCENARIOS} if 'scenarios' in row else None
        sign = D(1) if row['side'] == 'LONG' else D(-1)
        r['observational_reference_sensitivity'] = {
            'next_bar_open_shift_original_r': str(sign*(path[0].open-D(row['entry']))/D(row['stop_distance'])) if path else None,
            'next_bar_close_5m_shift_original_r': str(sign*(path[0].close-D(row['entry']))/D(row['stop_distance'])) if path else None,
            'interpretation': 'NEXT_OPEN_NOT_PROVEN_POST_CONFIRMATION_QUOTE;5M_CLOSE_EXCEEDS10S_DEADLINE'}
        max_reported = D(funding_audit['symbols'][row['symbol']]['maximum_trailing_12h_absolute_rate_bps'])
        r['ex_post_funding_sensitivity'] = {
            'september_max_reported_trailing12h_absolute_bps': str(max_reported),
            'notional_rate_drag_original_r': str(max_reported/(D(row['stop_fraction'])*10000)),
            'interpretation': 'AGGREGATE_EX_POST_STRESS_ONLY_NOT_EVENT_SPECIFIC_OR_POSITION_CASHFLOW'}
        outcomes.append(r)
        for b in path:
            used_bars[bar_key(b)] = b
    for link in matches:
        if not link['control_id']:
            continue
        event = next(r for r in confirmations if r['setup_id'] == link['event_id'])
        control = pool_by_id[link['control_id']]
        at = dt(control['event_time'])
        bars = panel.symbols[control['symbol']].candles_5m
        start = bisect_right(bars, at, key=lambda b: b.available_at)
        path = bars[start:start+144]
        used_bars[bar_key(bars[start-1])] = bars[start-1]
        reference = D(control['reference_close'])
        # Matched original risk fraction is only a diagnostic normalization.
        distance = reference*D(event['stop_fraction'])
        results = price_path(path, at=at, reference=reference, distance=distance, side=event['side'])
        controls.append({**control, 'reference_source_key': bar_key(bars[start-1]), 'matched_event_id': event['setup_id'], 'control_id': control['window_id'],
            'pool_window_id': control['window_id'],
            'side': event['side'], 'normalization': 'MATCHED_CASE_STOP_FRACTION_NOT_A_CONTROL_STRATEGY',
            'normalization_distance': str(distance), 'outcomes': results})
        for b in path:
            used_bars[bar_key(b)] = b
    # Retain source records by instrument/interval/native ID, including frozen
    # 1h structural-target inputs. Native IDs and policy snapshots stay intact.
    history_keys = {key for h in chronologies.values() for key in h['formation_source_keys']}
    history_keys.update(t['source_key'] for h in chronologies.values() for t in h['transitions'])
    for h in recovered.values():
        symbol = h['snapshot']['symbol']
        h['processed_source_keys'] = [source_key(symbol, '5m', sid) for sid in h['processed_source_ids']]
        history_keys.update(h['processed_source_keys'])
        for name in ('stop_anchor', 'structural_target'):
            level = h[name]
            if level:
                h[name + '_source_keys'] = [source_key(level['symbol'], level['timeframe'], sid)
                    for sid in level['source_ids']]
                history_keys.update(h[name + '_source_keys'])
    for data in panel.symbols.values():
        for interval in ('5m', '1h'):
            for b in getattr(data, 'candles_' + interval):
                if bar_key(b) in history_keys:
                    used_bars[bar_key(b)] = b
    assert history_keys <= used_bars.keys(), 'unresolved original setup source'
    source_bars = []
    for b in sorted(used_bars.values(), key=lambda b: (b.symbol, b.interval, b.open_time)):
        assert b.open_time < END
        archive_id = f'{b.symbol}-{b.interval}-{b.open_time:%Y-%m}.zip'
        minutes = {'5m': 5, '1h': 60}[b.interval]
        source_bars.append({'source_key': bar_key(b), 'interval': b.interval, 'source_record_id': b.source_record_id, 'observation_id': b.observation_id,
            'symbol': b.symbol, 'archive_id': archive_id,
            'csv_record_number_including_header': int(((b.open_time.day-1)*1440+b.open_time.hour*60+b.open_time.minute)//minutes)+2,
            'open_time': b.open_time.isoformat(), 'close_time': b.close_time.isoformat(),
            'available_at': b.available_at.isoformat(), **{k: str(getattr(b,k)) for k in ('open','high','low','close')}})
    selections = {'all_original_confirmations': outcomes,
        'screenable_original_geometry': [r for r in outcomes if r['geometry_status'] == 'SCREENABLE'],
        'frozen_base_survivors': [r for r in outcomes if base_survivor(r)]}
    for reason in sorted({r['classification'] for r in outcomes}):
        selections[f'classification:{reason}'] = [r for r in outcomes if r['classification'] == reason]
    summary = {'schema_version': 'c05l.event-control-summary.v1',
        'census_content_sha256': CENSUS_HASH, 'matching_content_sha256': match_hash,
        'source_manifest_sha256': MANIFEST_HASH, 'source_manifest': panel.source_manifest,
        'funding_audit_sha256': sha256(funding_audit_path.read_bytes()).hexdigest(),
        'verified_source_bars': sum(p['normalized_row_count'] for p in panel.partitions),
        'strict_eligible_candidates': 0, 'economic_verdict': 'INSUFFICIENT_EVIDENCE',
        'policies': 'RESEARCH_ONLY', 'histories_reproduced': len(formations),
        'classification_counts': dict(Counter(r['classification'] for r in outcomes)),
        'control_pool_count': len(pool), 'eligible_nontrigger_pool_count': sum(r['eligible_nontrigger'] for r in pool),
        'pool_exclusion_memberships': dict(Counter(x for r in pool for x in r['exclusions'])),
        'matched_events': len(controls), 'unique_controls': len({r['pool_window_id'] for r in controls}),
        'groups': {name: group_summary(rows, controls, matches) for name, rows in selections.items()}}
    summary['decision'] = decision(summary)
    packet = {'schema_version': 'c05l.event-control-evidence.v2', 'summary': summary,
        'source_partitions': list(panel.partitions), 'formations': formations,
        'setup_histories': chronologies,
        'events': outcomes, 'controls': controls, 'source_bars': source_bars,
        'assumptions': {'entry': 'HYPOTHETICAL_CONFIRMATION_CLOSE_NO_IOC_FILL_PROOF',
            'controls': 'PAST_ONLY_WITH_REPLACEMENT_NO_OUTCOME_MATCHING',
            'ordering': 'LOWER_STRICT_PRIOR_CANDLE;UPPER_SAME_CANDLE_ALLOWED;NO_INTRABAR_PATH_INVENTED',
            'funding': 'PRIOR_AGGREGATE_AUDIT_ONLY;NO_EVENT_LEVEL_RECORDS_OR_POSITION_CASHFLOWS',
            'delay': '0/5/10S_UNRESOLVED_BY_CANDLES;15/60S_MISS_FROZEN10S_DEADLINE',
            'uncertainty': 'DESCRIPTIVE_ONLY;LESS_THAN30_MARKET_DAYS_AND_OVERLAP_COMPONENTS;NO_CI',
            'guardrails': 'C02,STRATEGY,RISK,APPROVAL,EXECUTION_UNCHANGED'}}
    packet['content_sha256'] = config_hash(packet)
    write_gzip(args.output_dir/'C05_L_T1_EVENT_CONTROL_EVIDENCE.json.gz', packet)
    (args.output_dir/'C05_L_T1_EVENT_CONTROL_SUMMARY.json').write_text(json.dumps(summary, sort_keys=True, indent=2)+'\n')
    print(json.dumps({'decision': summary['decision'], 'content_sha256': packet['content_sha256'],
        'matched_events': len(controls), 'base_12h': summary['groups']['frozen_base_survivors']['horizons']['720']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
