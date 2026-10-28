"""Bounded September exploratory PC2/FR2 diagnostic; no policy registration.

Reuses C04 sources, C03 context/levels, C02 VWAP and C05-K/L costs/paths/matching.
The immutable S01 preregistration precedes all new forward-path calculations.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import timedelta
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

from astrabot.data.models import binance_usdm_instrument_id, config_hash, stable_id
from astrabot.features.providers import session_vwap
from astrabot.research import context as ctx, levels
from astrabot.research.integrated import HISTORY_LIMITS
from astrabot.research.replay import _panel_point_in_time, load_public_um_archive_panel
from astrabot.research.statistics import effective_sample_size, matched_controls
from c05_r0_market_economics import START, END, SCENARIOS, _memoize_numeric, cost_screen, distribution
from c05_t1_event_control import (MANIFEST_HASH, HORIZONS, bar_key, source_key, dt,
                                  write_gzip, price_path, market_components)

PREREG_SHA = '114e951b111b4dd55b90dd91e53eb82bac1d13815dfd7bcda7251a80bcc7f7d9'
CONTRACT_SHA = 'e89dfe169ddc9eb43a55fbbae9e1394ebc2e3367310a27166b61bddc4e4c8280'
PREREG_COMMIT = '1bd2a3729fc7ef49a1a47744f380e14973d29d3a'
SEED = 20261027
OUT = ROOT / 'research/p3'
CONTRACT = json.loads((OUT / 'S01_CANDIDATES.json').read_text())
VERSIONS = {name: config_hash({'candidate': terms, 'common': CONTRACT['common']})
            for name, terms in CONTRACT['candidates'].items()}


def checked_json(path, *, compressed=False):
    raw = path.read_bytes()
    value = json.loads(gzip.decompress(raw) if compressed else raw)
    digest = value.pop('content_sha256')
    if config_hash(value) != digest:
        raise ValueError(f'evidence content hash mismatch: {path.name}')
    return value, digest


def validate_inputs():
    for path, expected in ((OUT / 'S01_NEW_POLICY_PREREGISTRATION.md', PREREG_SHA),
                           (OUT / 'S01_CANDIDATES.json', CONTRACT_SHA),
                           (ROOT / 'research/c04/historical_manifest.json', MANIFEST_HASH)):
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'frozen input changed: {path.name}')


def sign_for(side):
    return D(1) if side == 'LONG' else D(-1)


def opposing_inventory(data, symbol, at):
    return levels.confirmed_swings(data.candles_1h, symbol=symbol,
        instrument_id=binance_usdm_instrument_id(symbol), as_of=at)


def select_target(side, reference, inventory, *, boundary=None, boundary_keys=(), boundary_at=None):
    """Select closest causal obstacle; never search farther for a better ratio."""
    s = sign_for(side)
    kind = 'SWING_HIGH' if s == 1 else 'SWING_LOW'
    choices = [{'price': str(x.price), 'level_id': x.level_id,
                'available_at': x.available_at.isoformat(), 'kind': x.kind,
                'source_keys': [source_key(x.symbol, x.timeframe, sid) for sid in x.source_ids]}
               for x in inventory if x.kind == kind and not x.invalidated
               and s * (x.price - reference) > 0
               and (boundary is None or s * (x.price - boundary) <= 0)]
    if boundary is not None and s * (boundary - reference) > 0:
        choices.append({'price': str(boundary), 'level_id': stable_id('s01.boundary', *boundary_keys, side, boundary),
            'available_at': boundary_at.isoformat(), 'kind': 'FROZEN_RANGE_OBJECTIVE',
            'source_keys': list(boundary_keys)})
    return min(choices, key=lambda x: (s * (D(x['price']) - reference), x['level_id'])) if choices else None


def context_record(context, data):
    result = {k: context.model_dump(mode='json')[k] for k in (
        'context_id', 'as_of', 'classification', 'bias', 'readiness', 'adx_1h',
        'atr_1h', 'atr_5m', 'atr_15m', 'normalized_slope', 'atr_percentile', 'rvol_15m')}
    result['source_spans'] = {interval: {'first': bar_key(rows[0]), 'last': bar_key(rows[-1]),
        'count': len(rows), 'ordered_keys_sha256': config_hash({'keys': [bar_key(b) for b in rows]})}
        for interval in HISTORY_LIMITS if (rows := getattr(data, 'candles_' + interval))}
    return result


def range_terms(data, context):
    """FR2 price-only balance, distinct from frozen R1 spread qualification."""
    reasons = []
    if (context.readiness != 'READY' or context.adx_1h is None or context.adx_1h >= 25
            or abs(context.normalized_slope) > D('.30') or context.atr_percentile >= 95):
        return None, ['FR2_REGIME_NOT_PRICE_BALANCE']
    prior, latest = data.candles_15m[-21:-1], data.candles_15m[-1]
    if (context.rvol_15m >= D('1.5') and
            (latest.close > max(b.high for b in prior) or latest.close < min(b.low for b in prior))):
        return None, ['FR2_CURRENT_VOLUME_BREAKOUT']
    bars = data.candles_15m[-20:]
    a = context.atr_15m
    high, low = max(b.high for b in bars), min(b.low for b in bars)
    width = high - low
    if width <= 0:
        return None, ['FR2_ZERO_RANGE']
    tests = {}
    for name in ('high', 'low'):
        indices = [i for i, b in enumerate(bars) if b.high - b.low <= D('.75') * width
                   and (b.high >= high - D('.25') * a if name == 'high' else b.low <= low + D('.25') * a)]
        tests[name] = indices
        if not any(j - i >= 3 for i in indices for j in indices):
            reasons.append('FR2_SEPARATED_' + name.upper() + '_TESTS_MISSING')
    drift = abs(sum((b.close for b in bars[:5]), D(0)) / 5
                - sum((b.close for b in bars[-5:]), D(0)) / 5) / width
    if not D(2) <= width / a <= D(8):
        reasons.append('FR2_WIDTH_ATR_INVALID')
    if drift > D('.20'):
        reasons.append('FR2_DRIFT_TOO_LARGE')
    terms = {'high': str(high), 'low': str(low), 'midpoint': str((high + low) / 2),
        'atr15': str(a), 'width_atr': str(width / a), 'drift_fraction': str(drift),
        'edge_test_indices': tests, 'source_keys': [bar_key(b) for b in bars],
        'available_at': bars[-1].available_at.isoformat()}
    return (None, reasons) if reasons else (terms, [])


def pc_formation(data, context, side, at):
    s = sign_for(side)
    if context.readiness != 'READY' or context.classification != ('TREND_UP' if s == 1 else 'TREND_DOWN'):
        return None, ['PC2_TREND_REGIME_MISSING']
    q = data.candles_15m[-1]
    if s * (q.close - q.open) >= 0:
        return None, ['PC2_COUNTER_DIRECTION_BODY_MISSING']
    vwap = session_vwap(data.candles_5m, as_of=at, symbol=q.symbol, instrument_id=q.instrument_id)
    if vwap.readiness != 'READY':
        return None, ['PC2_SESSION_VWAP_UNAVAILABLE']
    bars, a = data.candles_15m[-3:], context.atr_15m
    extreme = min(b.low for b in bars) if s == 1 else max(b.high for b in bars)
    if abs(extreme - vwap.value) > D('.50') * a:
        return None, ['PC2_PULLBACK_LOCATION_FAILED']
    if not 0 <= s * (q.close - vwap.value) <= a:
        return None, ['PC2_CLOSE_LOCATION_FAILED']
    return {'atr15': str(a), 'atr5': str(context.atr_5m), 'stop': str(extreme - s * D('.25') * a),
        'stop_anchor': str(extreme), 'trigger_boundary': str(q.high if s == 1 else q.low),
        'pullback_source_keys': [bar_key(b) for b in bars],
        'vwap': str(vwap.value), 'session_id': vwap.payload['session_id'],
        'vwap_source_keys': [source_key(q.symbol, '5m', sid) for sid in vwap.payload['candle_ids']]}, []


def advance(setup, bar, context):
    """One causal closed5m update. No future path or alternate retry search."""
    s, at = sign_for(setup['side']), bar.available_at
    if at <= dt(setup['formed_at']):
        raise ValueError('confirmation/sweep must follow formation')
    if context.readiness != 'READY' or context.classification == 'EXTREME_VOLATILITY':
        return 'INVALIDATED', 'MISSING_OR_EXTREME_CONTEXT'
    age = int((at - dt(setup['formed_at'])).total_seconds() // 300)
    if setup['candidate'] == 'PC2':
        if ('UTC:' + at.date().isoformat() != setup['session_id']
                or context.bias == ('BEARISH' if s == 1 else 'BULLISH')):
            return 'INVALIDATED', 'SESSION_ROLLOVER_OR_OPPOSITE_BIAS'
        if s * ((bar.low if s == 1 else bar.high) - D(setup['stop'])) <= 0:
            return 'INVALIDATED', 'ORIGINAL_STOP_TOUCHED_BEFORE_CONFIRMATION'
        if age <= 3 and s * (bar.close - D(setup['trigger_boundary'])) > 0 and s * (bar.close - bar.open) > 0:
            return 'CONFIRMED', 'FIRST_DIRECTIONAL_BREAK_OF_FORMATION_BAR'
        return ('EXPIRED', 'NO_CONFIRMATION_IN_THREE_BARS') if age >= 3 else ('ARMED', 'WAITING_CONFIRMATION')
    low, high, a = D(setup['low']), D(setup['high']), D(setup['atr15'])
    if setup['state'] == 'SWEPT':
        if at != dt(setup['sweep_at']) + timedelta(minutes=5):
            return 'INVALIDATED', 'MISSING_DISTINCT_NEXT_CONFIRMATION'
        if s * ((bar.low if s == 1 else bar.high) - D(setup['stop'])) <= 0:
            return 'INVALIDATED', 'ORIGINAL_STOP_TOUCHED_BEFORE_CONFIRMATION'
        boundary = D(setup['sweep_high' if s == 1 else 'sweep_low'])
        if low < bar.close < high and s * (bar.close - boundary) > 0 and s * (bar.close - bar.open) > 0:
            return 'CONFIRMED', 'DISTINCT_ACCEPTANCE_AFTER_FAILED_BREAK'
        return 'INVALIDATED', 'NEXT_BAR_CONFIRMATION_FAILED'
    if bar.low < low and bar.high > high:
        return 'INVALIDATED', 'TWO_SIDED_RANGE_VIOLATION'
    breached = bar.low < low if s == 1 else bar.high > high
    if breached and age <= 3:
        penetration = low - bar.low if s == 1 else bar.high - high
        if not D('.10') * a <= penetration <= D('.75') * a or not low < bar.close < high:
            return 'INVALIDATED', 'FIRST_BREACH_NOT_QUALIFIED_REJECTION'
        setup.update(sweep_at=at.isoformat(), sweep_source_key=bar_key(bar),
            sweep_low=str(bar.low), sweep_high=str(bar.high),
            stop=str((bar.low if s == 1 else bar.high) - s * D('.25') * a))
        return 'SWEPT', 'FIRST_QUALIFIED_RANGE_REJECTION'
    return ('EXPIRED', 'NO_SWEEP_IN_THREE_BARS') if age >= 3 else ('ARMED', 'WAITING_FIRST_BREACH')


def confirmation_geometry(setup, bar, inventory):
    s, entry, stop = sign_for(setup['side']), bar.close, D(setup['stop'])
    distance = s * (entry - stop)
    target = setup['target']
    row = {'entry': str(entry), 'stop': str(stop), 'stop_distance': str(distance),
        'stop_fraction': str(distance / entry), 'targets': [], 'route_feasible': False,
        'geometry_rejections': [], 'confirmation_source_key': bar_key(bar)}
    reasons = row['geometry_rejections']
    if stop <= 0 or distance <= 0:
        reasons.append('INVALID_STOP')
    if distance / entry > D('.02'):
        reasons.append('STOP_WIDER_THAN_TWO_PERCENT')
    if target is None:
        reasons.append('NO_FORMATION_TARGET')
    else:
        t = D(target['price'])
        row['targets'] = [{'price': str(t), 'fraction': '1'}]
        row['target_fraction'] = str(s * (t - entry) / entry)
        g = s * (t - entry) / distance if distance > 0 else None
        row['gross_price_r'] = str(g) if g is not None else None
        if s * (t - entry) <= 0:
            reasons.append('TARGET_NOT_AHEAD_AT_CONFIRMATION')
        if g is not None and not D('1.8') <= g <= D(4):
            reasons.append('TARGET_OUTSIDE_1_8_TO_4_R')
        obstacles = [x for x in inventory if x.kind == ('SWING_HIGH' if s == 1 else 'SWING_LOW')
                     and not x.invalidated and 0 < s * (x.price - entry) < s * (t - entry)]
        row['new_obstacles'] = [x.level_id for x in obstacles]
        if obstacles:
            reasons.append('NEW_NEARER_OPPOSITION')
        row['route_feasible'] = not obstacles
    row['geometry_status'] = 'SCREENABLE' if not reasons else '|'.join(reasons)
    if distance > 0 and stop > 0 and target and s * (D(target['price']) - entry) > 0:
        cost_input = {**row, 'side': setup['side'], 'policy': setup['candidate']}
        row['scenarios'] = {name: cost_screen(cost_input, terms) for name, terms in SCENARIOS.items()}
        row['adverse_entry_sensitivity'] = {str(x): cost_screen(cost_input, SCENARIOS['base'], entry_shift_r=x)
                                           for x in (D(0), D('.025'), D('.05'))}
    return row


def scan(panel):
    formations, events, pool, counters = [], [], [], Counter()
    for symbol in sorted(panel.symbols):
        active, last_fifteen = {}, None
        last_day = None
        for bar in panel.symbols[symbol].candles_5m:
            at = bar.available_at
            if not START <= at < END:
                continue
            if last_day != at.date():
                print(f'causal census {symbol} {at.date()}', flush=True)
                last_day = at.date()
            data = _panel_point_in_time(panel, symbol, at, HISTORY_LIMITS)
            context = ctx.evaluate_context(data, symbol=symbol,
                instrument_id=binance_usdm_instrument_id(symbol), as_of=at)
            new_fifteen = data.candles_15m[-1].observation_id != last_fifteen
            fr_terms, fr_reasons = range_terms(data, context)
            blocked = {name: False for name in VERSIONS}
            inventory = None
            for key, setup in list(active.items()):
                # PC2 armed state excludes controls; FR2 unswept range does not.
                if setup['candidate'] == 'PC2' or setup['state'] == 'SWEPT':
                    blocked[setup['candidate']] = True
                state, reason = advance(setup, bar, context)
                setup['state'] = state
                setup['transitions'].append({'at': at.isoformat(), 'source_key': bar_key(bar), 'state': state, 'reason': reason})
                if state == 'SWEPT' or (setup['candidate'] == 'FR2' and state == 'INVALIDATED'):
                    blocked['FR2'] = True
                if state in ('CONFIRMED', 'INVALIDATED', 'EXPIRED'):
                    setup.update(terminal_at=at.isoformat(), terminal_reason=reason)
                    if state == 'CONFIRMED':
                        blocked[setup['candidate']] = True
                        if inventory is None:
                            inventory = opposing_inventory(data, symbol, at)
                        events.append({'setup_id': setup['setup_id'], 'candidate': setup['candidate'],
                            'policy': setup['candidate'], 'policy_version': setup['policy_version'],
                            'symbol': symbol, 'side': setup['side'], 'formed_at': setup['formed_at'],
                            'terminal_at': at.isoformat(), 'regime': context.classification,
                            'candidate_regime': ('TREND_UP' if setup['side'] == 'LONG' else 'TREND_DOWN')
                                if setup['candidate'] == 'PC2' else 'PRICE_BALANCE',
                            'atr_percentile': str(context.atr_percentile),
                            'confirmation_context': context_record(context, data),
                            **confirmation_geometry(setup, bar, inventory)})
                    del active[key]
            if new_fifteen:
                last_fifteen = data.candles_15m[-1].observation_id
                for name in VERSIONS:
                    for side in ('LONG', 'SHORT'):
                        if (name, side) in active:
                            counters[name, 'ACTIVE_FORMATION_SLOT_SKIPPED'] += 1
                            continue
                        terms, reasons = pc_formation(data, context, side, at) if name == 'PC2' else (fr_terms, fr_reasons)
                        if terms is None:
                            counters.update((name, r) for r in reasons)
                            continue
                        if inventory is None:
                            inventory = opposing_inventory(data, symbol, at)
                        s = sign_for(side)
                        if name == 'PC2':
                            hourly = data.candles_1h[-20:]
                            boundary = max(b.high for b in hourly) if s == 1 else min(b.low for b in hourly)
                            boundary_keys = [bar_key(b) for b in hourly]
                            boundary_at = hourly[-1].available_at
                        else:
                            boundary = D(terms['midpoint'])
                            boundary_keys, boundary_at = terms['source_keys'], dt(terms['available_at'])
                        target = select_target(side, bar.close, inventory, boundary=boundary,
                            boundary_keys=boundary_keys, boundary_at=boundary_at)
                        # PC2 may target a closer swing even if the rolling extreme is behind.
                        if name == 'PC2' and s * (boundary - bar.close) <= 0:
                            target = select_target(side, bar.close, inventory)
                        setup = {'setup_id': stable_id('s01.setup', VERSIONS[name], symbol, side, at),
                            'candidate': name, 'policy_version': VERSIONS[name], 'symbol': symbol, 'side': side,
                            'formed_at': at.isoformat(), 'formation_source_key': bar_key(bar),
                            'formation_context': context_record(context, data), 'target': target,
                            **terms, 'state': 'ARMED', 'transitions': [], 'terminal_at': None}
                        # Each side owns an independent immutable range/transition list.
                        setup = json.loads(json.dumps(setup))
                        formations.append(setup)
                        active[name, side] = setup
                        if name == 'PC2':
                            blocked[name] = True
            for name in VERSIONS:
                eligible_regime = context.classification in ('TREND_UP', 'TREND_DOWN') if name == 'PC2' else fr_terms is not None
                reasons = []
                if blocked[name]:
                    reasons.append('ACTIVE_OR_CURRENT_TRIGGER')
                if not eligible_regime or context.readiness != 'READY':
                    reasons.append('CANDIDATE_REGIME_NOT_ELIGIBLE')
                if at + timedelta(hours=12) > END:
                    reasons.append('CROSSES_DEVELOPMENT_END')
                pool.append({'window_id': stable_id('s01.pool', name, symbol, at), 'candidate': name,
                    'symbol': symbol, 'event_time': at.isoformat(), 'source_key': bar_key(bar),
                    'reference_close': str(bar.close), 'regime': context.classification if name == 'PC2' else 'PRICE_BALANCE',
                    'atr_percentile': str(context.atr_percentile) if context.atr_percentile is not None else None,
                    'eligible_nontrigger': not reasons, 'exclusions': reasons})
        for setup in active.values():
            setup['state'], setup['terminal_reason'] = 'END_CENSORED', 'NO_OCTOBER_CONTINUATION'
    if len(pool) != 120960:
        raise ValueError('unexpected frozen seven-symbol September census size')
    return {'formations': formations, 'events': events, 'pool': pool,
        'formation_rejections': [{'candidate': k[0], 'reason': k[1], 'count': v} for k, v in sorted(counters.items())]}


def select_matches(events, pool):
    index = defaultdict(list)
    for row in pool:
        if row['eligible_nontrigger']:
            for side in ('LONG', 'SHORT'):
                if row['candidate'] == 'PC2' and row['regime'] != ('TREND_UP' if side == 'LONG' else 'TREND_DOWN'):
                    continue
                key = (row['candidate'], row['symbol'], row['regime'], side,
                       min(3, int(D(row['atr_percentile']) // 25)), dt(row['event_time']).hour // 4)
                index[key].append(row)
    matches = []
    for event in events:
        at = dt(event['terminal_at'])
        key = (event['candidate'], event['symbol'], event['candidate_regime'], event['side'],
               min(3, int(D(event['atr_percentile']) // 25)), at.hour // 4)
        candidates = [r for r in index[key] if at - timedelta(days=7) <= dt(r['event_time']) <= at - timedelta(hours=12)]
        cohort = '|'.join(map(str, key[3:]))
        trigger = {'window_id': event['setup_id'], 'symbol': event['symbol'], 'regime': key[2],
            'cohort': cohort, 'event_time': at.isoformat(), 'is_trigger': True}
        rows = [{**r, 'cohort': cohort, 'is_trigger': False} for r in candidates]
        control = matched_controls([trigger, *rows], seed=SEED, embargo_hours=12).get(event['setup_id'])
        matches.append({'event_id': event['setup_id'], 'candidate': event['candidate'], 'control_id': control,
            'candidate_count': len(candidates), 'cohort': list(key),
            'candidate_ids_sha256': config_hash({'ids': sorted(r['window_id'] for r in candidates)}),
            'status': 'MATCHED' if control else 'NO_EXACT_PAST_CONTROL'})
    return matches


def base_survivor(row, scenario='base'):
    return row['geometry_status'] == 'SCREENABLE' and row['scenarios'][scenario]['passes_with_route']


def paired(events, controls, minutes):
    lookup = {r['matched_event_id']: r for r in controls}
    pairs, daily = [], defaultdict(list)
    for event in events:
        control = lookup.get(event['setup_id'])
        if control is None:
            continue
        a, b = event['outcomes'][str(minutes)], control['outcomes'][str(minutes)]
        if not a['complete'] or not b['complete']:
            continue
        delta = D(a['signed_close_bps']) - D(b['signed_close_bps'])
        day = event['terminal_at'][:10]
        daily[day].append(delta)
        pairs.append({'event_id': event['setup_id'], 'control_id': control['control_id'], 'event_day': day,
            'control_day': control['event_time'][:10], 'symbol': event['symbol'], 'difference_bps': str(delta)})
    means = {k: mean(v) for k, v in sorted(daily.items())}
    values = list(means.values())
    delete = [mean(v for j, v in enumerate(values) if i != j) for i in range(len(values))] if len(values) > 1 else []
    return {'pairs': len(pairs), 'event_days': len(daily), 'unique_controls': len({p['control_id'] for p in pairs}),
        'equal_day_difference_bps': str(mean(values)) if values else None,
        'leave_one_event_day_out_bps': [str(min(delete)), str(max(delete))] if delete else None,
        'day_means_bps': {k: str(v) for k, v in means.items()}, 'pair_ledger': pairs,
        'ci95': None, 'uncertainty': 'DESCRIPTIVE_CORRELATED_DEVELOPMENT_SAMPLE'}


def group_summary(events, controls):
    days = Counter(r['terminal_at'][:10] for r in events)
    intervals = [(dt(r['terminal_at']), min(dt(r['terminal_at']) + timedelta(hours=12), END)) for r in events]
    event_ids = {r['setup_id'] for r in events}
    intervals.extend((dt(r['event_time']), dt(r['event_time']) + timedelta(hours=12))
                     for r in controls if r['matched_event_id'] in event_ids)
    horizons = {}
    for h in HORIZONS:
        observed = [r['outcomes'][str(h)] for r in events if r['outcomes'][str(h)]['complete']]
        horizons[str(h)] = {'complete': len(observed), 'censored': len(events) - len(observed),
            **{k: distribution(r[k] for r in observed) for k in ('signed_close_bps', 'mfe_r', 'mae_r')},
            'target_before_stop_lower': sum(r['full_ladder_lower'] for r in observed),
            'target_before_stop_upper': sum(r['full_ladder_upper'] for r in observed),
            'same_bar_ambiguous': sum(r['ordered_ladder'] and r['target2_order']['same_bar_ambiguous'] for r in observed),
            'stop_first': sum(r['ordered_ladder'] and r['stop_touch'] is not None and
                              (r['structural_target_touch'] is None or r['stop_touch']['bar_open'] < r['structural_target_touch']['bar_open'])
                              for r in observed),
            'target_never_touched': sum(r['ordered_ladder'] and r['target2_not_touched'] for r in observed),
            'stop_touched': sum(r['stop_touch'] is not None for r in observed),
            'target_before_stop_by_11h55_lower': sum(r['full_ladder_lower'] and
                r['structural_target_touch']['minutes_upper'] <= 715 for r in observed),
            'paired': paired(events, controls, h)}
    complete = [r['outcomes']['720'] for r in events if r['outcomes']['720']['complete']]
    full_events = [r for r in events if r['outcomes']['720']['complete']]
    return {'n': len(events), 'symbols': dict(sorted(Counter(r['symbol'] for r in events).items())),
        'complete12h_market_days': sorted({r['terminal_at'][:10] for r in full_events}),
        'complete12h_symbols': sorted({r['symbol'] for r in full_events}),
        'market_days': dict(sorted(days.items())), 'kish_day_concentration': effective_sample_size(list(days.values())),
        'regimes': dict(sorted(Counter(r['regime'] for r in events).items())),
        'sessions_utc_4h': dict(sorted(Counter(str(dt(r['terminal_at']).hour // 4) for r in events).items())),
        'side': dict(Counter(r['side'] for r in events)),
        'overlapping_case_control_window_pairs': sum(a < d and c < b for i, (a, b) in enumerate(intervals) for c, d in intervals[i+1:]),
        'connected_market_time_components': market_components(intervals),
        'first_forward_bar_stop_touches': sum(r['stop_touch'] is not None and r['stop_touch']['minutes_upper'] == 5 for r in complete),
        'stop_by15m': sum(r['stop_touch'] is not None and r['stop_touch']['minutes_upper'] <= 15 for r in complete),
        'stop_by1h': sum(r['stop_touch'] is not None and r['stop_touch']['minutes_upper'] <= 60 for r in complete),
        'target_price_r': distribution(r.get('gross_price_r') for r in events),
        'stop_fraction': distribution(r['stop_fraction'] for r in events),
        'base_loss_cost_r': distribution(r.get('scenarios', {}).get('base', {}).get('cost_r') for r in events),
        'horizons': horizons}


def decision(candidate):
    base = candidate['groups']['base_survivors']
    twelve = base['horizons']['720']
    n = twelve['complete']
    if (candidate['confirmations'] >= 20 and base['n'] == 0
            or n >= 20 and D(twelve['target_before_stop_upper']) / n <= D('.20')):
        return 'REJECT_ECONOMIC_HYPOTHESIS'
    p1, p4, p12 = (base['horizons'][str(h)]['paired'] for h in (60, 240, 720))
    def positive(p):
        return p['equal_day_difference_bps'] is not None and D(p['equal_day_difference_bps']) > 0
    if (n >= 20 and len(base['complete12h_market_days']) >= 8 and len(base['complete12h_symbols']) >= 4
            and D(base['n']) / candidate['confirmations'] >= D('.10')
            and D(twelve['target_before_stop_lower']) / n >= D('.35')
            and p12['pairs'] * 2 >= n and p12['event_days'] >= 8
            and positive(p1) and positive(p4)
            and p12['equal_day_difference_bps'] is not None and D(p12['equal_day_difference_bps']) >= 0
            and p4['leave_one_event_day_out_bps'] is not None and D(p4['leave_one_event_day_out_bps'][0]) > 0):
        return 'ADVANCE_TO_SOURCE_QUALIFICATION'
    return 'REVISE_BEFORE_IMPLEMENTATION'


def diagnose_original(panel):
    """Recheck old T1 paths against raw inputs; describe failures, never retune."""
    directory = ROOT / 'research/c05'
    old, old_hash = checked_json(directory / 'C05_L_T1_EVENT_CONTROL_EVIDENCE.json.gz', compressed=True)
    census, census_hash = checked_json(directory / 'C05_K_R0_CENSUS.json.gz', compressed=True)
    source = {r['source_key']: r for r in old['source_bars']}
    raw = {bar_key(b): b for data in panel.symbols.values() for interval in HISTORY_LIMITS
           for b in getattr(data, 'candles_' + interval)}
    for key, row in source.items():
        b = raw[key]
        if any(D(row[k]) != getattr(b, k) for k in ('open', 'high', 'low', 'close')):
            raise ValueError('old evidence OHLC does not match original archive')
    base = [r for r in old['events'] if r['classification'] == 'FROZEN_BASE_SURVIVOR']
    for row in old['events']:
        target = row['history']['structural_target']
        rebuilt = price_path([raw[k] for k in row['outcomes']['720']['source_keys']],
            at=dt(row['terminal_at']), reference=D(row['entry']), distance=D(row['stop_distance']),
            side=row['side'], target2=D(target['price']) if target else None)
        if rebuilt != row['outcomes']:
            raise ValueError('old original T1 paths changed')
    groups = {}
    for name, rows in (('all_confirmations', old['events']), ('base_survivors', base)):
        before_stop = []
        for e in rows:
            s, reference, distance = sign_for(e['side']), D(e['entry']), D(e['stop_distance'])
            stop = e['outcomes']['720']['stop_touch']
            eligible = [source[k] for k in e['outcomes']['720']['source_keys']
                        if stop is None or source[k]['open_time'] < stop['bar_open']]
            before_stop.append(max([D(0), *(s * (D(b['high' if s == 1 else 'low']) - reference) / distance for b in eligible)]))
        groups[name] = {'n': len(rows), 'stop_fraction': distribution(r['stop_fraction'] for r in rows),
            'formation_to_confirmation_minutes': distribution((dt(r['terminal_at']) - dt(r['formed_at'])).total_seconds() / 60 for r in rows),
            'mfe_strictly_before_stop_candle_r': distribution(before_stop),
            'stop_touch_elapsed_upper_minutes': distribution(r['outcomes']['720']['stop_touch']['minutes_upper'] for r in rows if r['outcomes']['720']['stop_touch']),
            'stop_by5m': sum(r['outcomes']['720']['stop_touch'] is not None and r['outcomes']['720']['stop_touch']['minutes_upper'] <= 5 for r in rows),
            'stop_by15m': sum(r['outcomes']['720']['stop_touch'] is not None and r['outcomes']['720']['stop_touch']['minutes_upper'] <= 15 for r in rows),
            'stop_by1h': sum(r['outcomes']['720']['stop_touch'] is not None and r['outcomes']['720']['stop_touch']['minutes_upper'] <= 60 for r in rows),
            'regimes': dict(Counter(r['confirmation_regime'] for r in rows)),
            'sessions_utc_4h': dict(Counter(str(dt(r['terminal_at']).hour // 4) for r in rows)),
            'atr_percentile': distribution(r['confirmation_atr_percentile'] for r in rows)}
    groups['base_survivors']['original_target2_price_r'] = distribution(
        sign_for(r['side']) * (D(r['targets'][1]['price']) - D(r['entry'])) / D(r['stop_distance']) for r in base)
    b1 = []
    for row in (r for r in census['confirmations'] if r['policy'] == 'B1'):
        bars, at = panel.symbols[row['symbol']].candles_5m, dt(row['terminal_at'])
        index = bisect_right(bars, at, key=lambda b: b.available_at)
        path = price_path(bars[index:index + 144], at=at, reference=D(row['entry']),
            distance=D(row['stop_distance']), side=row['side'], target2=D(row['targets'][1]['price']))
        b1.append({**row, 'outcomes': path})
    return {'c05l_content_sha256': old_hash, 'c05k_content_sha256': census_hash,
        'old_source_bars_independently_rechecked': len(source), 'original_t1_paths_reproduced': len(old['events']),
        't1': groups, 't1_classifications': old['summary']['classification_counts'],
        'b1_census': census['by_policy']['B1'], 'b1_original_price_paths': group_summary(b1, []),
        'b1_events': b1,
        'r1_balance_rejection_memberships': census['balance_reasons']}


def rank_candidates(candidates):
    order = {'ADVANCE_TO_SOURCE_QUALIFICATION': 0, 'REVISE_BEFORE_IMPLEMENTATION': 1,
             'SOURCE_DEPENDENT_NOT_YET_DISCRIMINATED': 2, 'REJECT_ECONOMIC_HYPOTHESIS': 3}
    def key(name):
        c = candidates[name]
        base = c['groups']['base_survivors']
        delta = base['horizons']['240']['paired']['equal_day_difference_bps']
        cost = base['base_loss_cost_r']['median']
        return (order[c['decision']], -D(delta) if delta is not None else D('Infinity'),
                D(cost) if cost is not None else D('Infinity'), 0 if name == 'PC2' else 1)
    return sorted(candidates, key=key)


def source_contract():
    from astrabot.universe.eligibility import FreshnessPolicy
    return {
        'status': 'MISSING_STRICT_EVIDENCE_NOT_RELAXED_BY_PRICE_R0',
        'c02_policy': 'c02-universe-v1',
        'freshness_seconds': {name: int(value.total_seconds()) for name, value in FreshnessPolicy().model_dump().items()},
        'instrument': {'dated_lifecycle_filters_and_linear_usdt_units': 'REQUIRED_UNVERIFIED',
                       'historical_not_current_metadata': True},
        'ticker_24h_min_turnover_usdt': '20000000',
        'spread': {'samples': 60, 'max_median_fraction': '0.001',
                   'clock': 'FROZEN_C02_RAW_EVENT_60S_UNCHANGED; S02_ISSUE22_REVIEW_AND_OWNER_APPROVAL_REQUIRED'},
        'depth': {'within_mid_fraction': '0.002', 'min_each_side_times_max_order_notional': '5',
                  'units_sequence_and_coverage': 'REQUIRED_UNVERIFIED'},
        'oi': {'min_notional_usdt': '5000000', 'dated_units_measurement_clock_contemporaneous_mark': 'REQUIRED_UNVERIFIED'},
        'events': 'VERIFIED_ORIGINAL_PUBLISHED_AT_COVERAGE_BLACKOUTS_REQUIRED_UNAVAILABLE',
        'costs': SCENARIOS,
        'funding': 'ORIGINAL_CALC_OR_SETTLEMENT_CLOCK_PLUS_ACTUAL_QUANTITY_MARK_EXPOSURE_REQUIRED;0_1_3BPS_NOT_A_BOUND',
        'approval_and_execution': 'ONE_USE_OWNER_NONCE;DATED_FILTERS;IOC_WITHIN10S;ADVERSE_BOUND_DEPTH_PARTIAL_STOP_AND_TIME_EVIDENCE_REQUIRED',
        'evidence_interfaces': ['c05g.historical-source-manifest.v1', 'c05h.historical-evidence.v1',
                               'astrabot.universe.eligibility.SymbolData'],
        'a01_a10': {
            'A01': 'RECORD_ONLY_UNAVAILABLE_ORIGINAL_AGGRESSOR_TRADES',
            'A02': 'PC2_MANDATORY_READY_BAR_APPROX;FR2_RECORD_ONLY',
            'A03': 'MANDATORY_NARROW_CAUSAL_C03_SWINGS_RANGES_READY;ADVANCED_UNAVAILABLE',
            'A04': 'C02_DEPTH_VETO_UNAVAILABLE;LIQUIDATION_RECORD_ONLY_UNAVAILABLE',
            'A05': 'RECORD_ONLY_UNAVAILABLE', 'A06': 'C02_OI_VETO_UNAVAILABLE;FUNDING_QUALIFICATION_MISSING',
            'A07': 'MANDATORY_CLOSED_BAR_PRICE_ACTION_READY_WITH_AVAILABILITY_PROXY',
            'A08': 'RECORD_ONLY_UNAVAILABLE_ORIGINAL_TRADE_BUCKETS',
            'A09': 'MANDATORY_EXISTING_C03_TALIB_READY', 'A10': 'MANDATORY_EXISTING_ATR_AND_NEW_FR2_PRICE_BALANCE_READY'},
        'candidate_contract_byte_sha256': CONTRACT_SHA,
        'future_qualification_contract_byte_sha256': PREREG_SHA,
        'future_liquidity_cohort_annex': {
            'version': 's01.future-source-cohorts.proposed.v1',
            'timing': 'HANDOFF_DEFINED_AFTER_SEPTEMBER_SCREEN;NOT_USED_IN_S01;BEFORE_RESERVED_OUTCOMES',
            'owner_acceptance': 'REQUIRED_WITH_S02_SOURCE_CONTRACT_BEFORE_STRICT_R1_R2',
            'assignment': 'AFTER_ALL_C02_GATES_PASS_AT_DECISION;FRESH_ORIGINAL_TICKER_QUOTE_VOLUME_USDT',
            'Q20_100': {'turnover_min_inclusive_usdt': '20000000', 'turnover_max_exclusive_usdt': '100000000'},
            'Q100_PLUS': {'turnover_min_inclusive_usdt': '100000000', 'turnover_max_exclusive_usdt': None},
            'unknown_source': 'UNVERIFIED_NO_COHORT;NEVER_INFER_FROM_SYMBOL_OR_DAILY_BAR_VOLUME',
            'minimum_each_cohort': {'admissible_intended_signals': 25, 'utc_market_days': 8},
            'future_controls': 'ADD_EXACT_POINT_IN_TIME_LIQUIDITY_COHORT_TO_FROZEN_SYMBOL_SIDE_REGIME_VOL_SESSION_MATCH;NO_RELAXED_FALLBACK',
            'effect': 'STRATIFICATION_AND_ADEQUACY_ONLY;NO_RELAXED_C02_GATE_OR_EDGE_CLAIM'},
        'registry_or_activation_authority': False}


def calculate_paths(panel, census):
    events, controls, used = [], [], {}
    pool = {r['window_id']: r for r in census['pool']}
    event_lookup = {r['setup_id']: r for r in census['events']}
    def path(symbol, at, reference, distance, side, target):
        bars = panel.symbols[symbol].candles_5m
        index = bisect_right(bars, at, key=lambda b: b.available_at)
        forward = bars[index:index + 144]
        if bars[index - 1].available_at != at:
            raise ValueError('reference does not resolve to native confirmation bar')
        for b in (bars[index - 1], *forward):
            if b.open_time < END:
                used[bar_key(b)] = b
        return price_path(forward, at=at, reference=reference, distance=distance, side=side, target2=target)
    for event in census['events']:
        target = D(event['targets'][0]['price']) if event['targets'] else None
        at, distance = dt(event['terminal_at']), D(event['stop_distance'])
        if distance <= 0:
            raise ValueError('unexpected nonpositive risk after pre-entry stop veto')
        outcomes = path(event['symbol'], at, D(event['entry']), distance, event['side'], target)
        events.append({**event, 'outcomes': outcomes})
    for link in census['matches']:
        if not link['control_id']:
            continue
        event, control = event_lookup[link['event_id']], pool[link['control_id']]
        reference, s = D(control['reference_close']), sign_for(event['side'])
        distance = reference * D(event['stop_fraction'])
        target = reference + s * reference * D(event['target_fraction']) if event.get('target_fraction') is not None else None
        controls.append({**control, 'control_id': link['control_id'], 'matched_event_id': link['event_id'],
            'side': event['side'], 'normalization_distance': str(distance),
            'normalization_target': str(target) if target is not None else None,
            'outcomes': path(control['symbol'], dt(control['event_time']), reference, distance, event['side'], target)})
    keys = set()
    for setup in census['formations']:
        keys.add(setup['formation_source_key'])
        keys.update(t['source_key'] for t in setup['transitions'])
        for name in ('pullback_source_keys', 'vwap_source_keys', 'source_keys'):
            keys.update(setup.get(name, []))
        if setup['target']:
            keys.update(setup['target']['source_keys'])
    keys.update(r['source_key'] for r in census['pool'])
    for data in panel.symbols.values():
        for interval in HISTORY_LIMITS:
            for b in getattr(data, 'candles_' + interval):
                if bar_key(b) in keys:
                    used[bar_key(b)] = b
    if not keys <= used.keys():
        raise ValueError('unresolved formation/pool source key')
    source_bars = []
    for b in sorted(used.values(), key=lambda b: (b.symbol, b.interval, b.open_time)):
        minutes = {'5m': 5, '15m': 15, '1h': 60, '4h': 240}[b.interval]
        source_bars.append({'source_key': bar_key(b), 'symbol': b.symbol, 'interval': b.interval,
            'native_id': b.source_record_id, 'observation_id': b.observation_id,
            'archive_id': f'{b.symbol}-{b.interval}-{b.open_time:%Y-%m}.zip',
            'csv_record_number_including_header': int(((b.open_time.day - 1) * 1440 + b.open_time.hour * 60 + b.open_time.minute) // minutes) + 2,
            'open_time': b.open_time.isoformat(), 'available_at': b.available_at.isoformat(),
            **{k: str(getattr(b, k)) for k in ('open', 'high', 'low', 'close', 'base_volume')}})
    return events, controls, source_bars


def summarize(census, events, controls):
    result = {}
    for name in VERSIONS:
        rows = [r for r in events if r['candidate'] == name]
        formations = [r for r in census['formations'] if r['candidate'] == name]
        formation_lookup = {r['setup_id']: r for r in formations}
        incompatible = [r for r in formations if name == 'PC2' and r['target']
            and sign_for(r['side']) * (D(r['target']['price']) - D(r['trigger_boundary'])) <= 0]
        incompatible_ids = {r['setup_id'] for r in incompatible}
        groups = {'all_confirmations': rows, 'geometry_pass': [r for r in rows if r['geometry_status'] == 'SCREENABLE'],
            'base_survivors': [r for r in rows if base_survivor(r)],
            'rejected_confirmations': [r for r in rows if not base_survivor(r)]}
        candidate = {'policy_id': CONTRACT['candidates'][name]['policy_id'], 'version_sha256': VERSIONS[name],
            'formations': len(formations), 'formation_states': dict(Counter(r['state'] for r in formations)),
            'sweeps': sum(any(t['state'] == 'SWEPT' for t in r['transitions']) for r in formations),
            'confirmations': len(rows),
            'terminal_reason_counts': dict(Counter(r['terminal_reason'] for r in formations)),
            'formation_target_kinds': dict(Counter(r['target']['kind'] if r['target'] else 'MISSING' for r in formations)),
            'formation_target_at_or_behind_required_trigger': len(incompatible),
            'confirmed_with_known_trigger_target_incompatibility': sum(r['setup_id'] in incompatible_ids for r in rows),
            'formation_to_confirmation_minutes': distribution((dt(r['terminal_at']) - dt(r['formed_at'])).total_seconds() / 60 for r in rows),
            'target_age_at_confirmation_hours': distribution((dt(r['terminal_at']) - dt(formation_lookup[r['setup_id']]['target']['available_at'])).total_seconds() / 3600
                for r in rows if formation_lookup[r['setup_id']]['target']),
            'formation_rejections': [r for r in census['formation_rejections'] if r['candidate'] == name],
            'geometry_rejection_memberships': dict(Counter(reason for r in rows for reason in r['geometry_rejections'])),
            'scenarios': {scenario: {'cost_only_pass': sum(r.get('scenarios', {}).get(scenario, {}).get('passes_cost_screen', False) for r in rows),
                'geometry_cost_route_pass': sum(base_survivor(r, scenario) for r in rows)} for scenario in SCENARIOS},
            'entry_shift_base_survivors': {str(x): sum(base_survivor(r) and
                r['adverse_entry_sensitivity'][str(x)]['passes_with_route'] for r in rows) for x in (D(0), D('.025'), D('.05'))},
            'eligible_control_pool': sum(r['candidate'] == name and r['eligible_nontrigger'] for r in census['pool']),
            'control_exclusion_memberships': dict(Counter(reason for r in census['pool'] if r['candidate'] == name for reason in r['exclusions'])),
            'matched_all_confirmations': sum(r['candidate'] == name for r in controls),
            'groups': {group: group_summary(selected, controls) for group, selected in groups.items()}}
        candidate['decision'] = decision(candidate)
        result[name] = candidate
    return result


def render(packet):
    """Single empirical report generated from the exact machine evidence."""
    summary = {name: packet['candidates'][name] for name in packet['ranking']}
    lines = ['# S01 — Authentic September economic screen', '',
        '**Exploratory development evidence / price-only / RESEARCH_ONLY.**', '',
        'No executable fills, realized P&L, true win rate or strategy expectancy are estimated. '
        'September informed design; October archives and outcomes were not accessed. '
        'The fixed seven-symbol panel is not a point-in-time eligible universe.', '',
        f"**Frozen ranking: {' > '.join(packet['ranking'])}.** "
        'Ranking does not authorize implementation. The exact verdict follows the preregistered rules, '
        'including small-sample and matching requirements.', '',
        f"Across both candidates, all confirmation/control12h windows have "
        f"{packet['joint_candidates']['overlapping_case_control_window_pairs']} overlapping pairs in "
        f"{packet['joint_candidates']['connected_market_time_components']} connected market-time components. "
        'Pooling symbols or strategies does not create independent observations.', '',
        f"Base `{CONTRACT['base_commit']}`; preregistration commit `{PREREG_COMMIT}`. "
        f"Preregistration SHA-256 `{PREREG_SHA}`; machine contract `{CONTRACT_SHA}`. "
        f"Evidence content hash `{packet['content_sha256']}`; outcome-blind census/matches `{packet['census_content_sha256']}`.", '',
        f"C04 verified {packet['verified_source_bars']:,} native bars from84 July–September ZIPs "
        '(11,566,262 compressed bytes), using the existing ZIP/member/schema/continuity checks. '
        f'Manifest SHA-256 `{MANIFEST_HASH}`. All84 archive/member hashes are in the ledger. '
        'The28 October archives are excluded by the loader before file access.', '',
        '## Frozen opportunity census', '',
        '| Candidate | Formed | Confirmed | Invalidated / expired / end-censored | Geometry pass | Optimistic / base / stress survivors |',
        '|---|---:|---:|---|---:|---|']
    for name, c in summary.items():
        states = c['formation_states']
        counts = '/'.join(str(c['scenarios'][s]['geometry_cost_route_pass']) for s in SCENARIOS)
        lines.append(f"| {name} | {c['formations']} | {c['confirmations']} | {states.get('INVALIDATED',0)} / {states.get('EXPIRED',0)} / {states.get('END_CENSORED',0)} | {c['groups']['geometry_pass']['n']} | {counts} |")
    lines += ['', 'Each candidate receives60,480 symbol-windows; formation attempts occur only on new15m closes. '
        'FR2 formations count armed ranges, not observed sweeps. PC2 uses a45m pullback stop; FR2 uses first range rejection. '
        'All confirmations, including geometry/cost rejections, receive paths. Counts are outside strict C02 admission.', '']
    for name, c in summary.items():
        base = c['groups']['base_survivors']
        lines += [f"## {name}: {c['decision']}", '',
            f"Policy `{c['policy_id']}`, version `{c['version_sha256']}`. "
            f"{c['sweeps']} observed sweep transitions. Geometry rejection memberships: "
            f"`{json.dumps(c['geometry_rejection_memberships'], sort_keys=True)}`.", '',
            f"Formation terminal reasons `{json.dumps(c['terminal_reason_counts'], sort_keys=True)}`. "
            f"Target types `{json.dumps(c['formation_target_kinds'], sort_keys=True)}`. "
            f"Median formation-to-confirmation latency {c['formation_to_confirmation_minutes']['median']} minutes; "
            f"median target confirmation age {c['target_age_at_confirmation_hours']['median']} hours. "
            f"PC2-style target-at/behind-required-trigger incompatibility was already present at formation in "
            f"{c['formation_target_at_or_behind_required_trigger']} setups, including "
            f"{c['confirmed_with_known_trigger_target_incompatibility']} later confirmations. "
            'These are causal geometry diagnostics, not a hypothetical earlier-entry performance test.', '',
            f"Base survivors: {base['n']} on {len(base['market_days'])} UTC days / {len(base['symbols'])} symbols. "
            f"Symbols `{json.dumps(base['symbols'], sort_keys=True)}`; sides `{json.dumps(base['side'], sort_keys=True)}`. "
            f"Regimes `{json.dumps(base['regimes'], sort_keys=True)}`; UTC4h sessions0..5 `{json.dumps(base['sessions_utc_4h'], sort_keys=True)}`. "
            f"Market-day counts `{json.dumps(base['market_days'], sort_keys=True)}`.", '',
            f"Median original stop fraction {base['stop_fraction']['median']}; target distance {base['target_price_r']['median']}R; "
            f"base modeled loss-route drag {base['base_loss_cost_r']['median']}R. "
            f"Fixed-level adverse-entry0/.025/.05R cost survivors `{json.dumps(c['entry_shift_base_survivors'], sort_keys=True)}`. "
            'These are successful-target scenario screens, not probabilities or net performance.', '',
            '| Horizon | Complete / censored | Median signed bps | Median MFE / MAE R | Target before stop lower–upper | Stop first | Same-bar ambiguous |',
            '|---|---|---:|---|---|---:|---:|']
        for h in HORIZONS:
            r = base['horizons'][str(h)]
            lines.append(f"| {h}m | {r['complete']} / {r['censored']} | {r['signed_close_bps']['median']} | {r['mfe_r']['median']} / {r['mae_r']['median']} | {r['target_before_stop_lower']}–{r['target_before_stop_upper']} | {r['stop_first']} | {r['same_bar_ambiguous']} |")
        lines += ['', f"Among complete12h cases, {base['first_forward_bar_stop_touches']} touch the original stop in the first forward5m bar, "
            f"{base['stop_by15m']} by15m and {base['stop_by1h']} by1h. "
            f"Target-before-stop by11h55 lower={base['horizons']['720']['target_before_stop_by_11h55_lower']}. "
            'Whole-horizon MFE/MAE can occur after a stop; later favorable movement is not a setup success.', '',
            '| Fixed population | N | Complete12h | Target lower–upper | Median12h bps |',
            '|---|---:|---:|---|---:|']
        for group in ('all_confirmations', 'geometry_pass', 'base_survivors', 'rejected_confirmations'):
            g = c['groups'][group]
            h = g['horizons']['720']
            lines.append(f"| {group} | {g['n']} | {h['complete']} | {h['target_before_stop_lower']}–{h['target_before_stop_upper']} | {h['signed_close_bps']['median']} |")
        lines += ['', 'Targets of invalid geometry are contextual touches only; full-target counts require ordered target>1R, '
            'and do not rehabilitate rejected geometry. Missing or behind targets remain failed geometry.', '',
            '| All confirmations: price-path context | Complete / censored | Median signed bps | Median MFE / MAE R | Matched pairs / days | Equal-day contrast bps |',
            '|---|---|---:|---|---|---:|']
        for h in (60, 240, 720):
            r = c['groups']['all_confirmations']['horizons'][str(h)]
            p = r['paired']
            lines.append(f"| {h}m | {r['complete']} / {r['censored']} | {r['signed_close_bps']['median']} | "
                f"{r['mfe_r']['median']} / {r['mae_r']['median']} | {p['pairs']} / {p['event_days']} | {p['equal_day_difference_bps']} |")
        lines += ['', 'These broad contrasts include rejected geometry. They cannot substitute for the declared cost/geometry population. '
            'All day-deletion ranges, per-day pair values and rejected-population contrasts are retained in machine evidence.', '',
            f"Outcome-blind eligible control pool={c['eligible_control_pool']:,}; all-confirmation matched={c['matched_all_confirmations']}. "
            f"Pool exclusion memberships `{json.dumps(c['control_exclusion_memberships'], sort_keys=True)}`.", '',
            '| Base matched contrast | Pairs / event days / unique controls | Equal-day case−control bps | Day-deletion range bps |',
            '|---|---|---:|---|']
        for h in (60, 240, 720):
            p = base['horizons'][str(h)]['paired']
            lines.append(f"| {h}m | {p['pairs']} / {p['event_days']} / {p['unique_controls']} | {p['equal_day_difference_bps']} | {p['leave_one_event_day_out_bps']} |")
        lines += ['', f"Day-count Kish concentration={base['kish_day_concentration']:.3f}; "
            f"{base['overlapping_case_control_window_pairs']} overlapping case/control12h interval pairs and "
            f"{base['connected_market_time_components']} connected market-time components. "
            'These are descriptive concentration/dependence counts, not certified independent observations. '
            'Missing controls and shared market shocks can confound contrasts; no CI/p-value is issued.', '',
            '### Source-linked cases', '']
        rows = sorted((r for r in packet['events'] if r['candidate'] == name), key=lambda r: (r['terminal_at'], r['symbol'], r['setup_id']))
        selections = {
            'first base survivor': next((r for r in rows if base_survivor(r)), None),
            'first base stop-first': next((r for r in rows if base_survivor(r) and r['outcomes']['720']['complete']
                and r['outcomes']['720']['stop_touch'] and not r['outcomes']['720']['full_ladder_upper']), None),
            'first base target-first': next((r for r in rows if base_survivor(r) and r['outcomes']['720']['full_ladder_lower']), None),
            'first rejected confirmation': next((r for r in rows if not base_survivor(r)), None)}
        for label, row in selections.items():
            if row is None:
                lines.append(f'- {label}: none in frozen population.')
                continue
            h = row['outcomes']['720']
            touch = lambda r: r['bar_open'] if r else 'not touched'
            lines.append(f"- {label}: `{row['setup_id']}` {row['symbol']} {row['side']}, confirmation {row['terminal_at']}; "
                f"E={row['entry']}, S={row['stop']}, T={row['targets'][0]['price'] if row['targets'] else None}, "
                f"g={row.get('gross_price_r')}R; stop candle {touch(h['stop_touch'])}, target candle {touch(h['structural_target_touch'])}; "
                f"12h signed={h['signed_close_bps']}bps, MFE/MAE={h['mfe_r']}/{h['mae_r']}R. "
                f"Geometry `{row['geometry_status']}`. Reference key `{row['confirmation_source_key']}`; "
                'formation, target-source window, transition, forward-bar and CSV locators are in the ledger.')
        lines.append('')
    lines += ['## Reproduction, source gaps and handoff', '',
        '```sh', 'python scripts/s01_economic_recovery.py --data-root /path/to/c04-data', '```', '',
        'Uses existing pinned requirements. No network operation, raw archive in Git or October source required. '
        'Optional `--output-dir` writes a verification copy. The command first writes a deterministic outcome-blind census/matching '
        'artifact, then calculates paths and generates this report plus the compressed evidence. '
        'The ledger includes every formation/transition, confirmation/geometry/cost rejection, control, '
        'source key, archive/member hash and uncertainty record. Native IDs are scoped by symbol and interval.', '',
        'No strict eligible candidates: dated metadata/filters/units, ticker, accepted source-clock/#22 and BBO history, '
        'validated OI units/measurement time, depth notional and event/news clearance remain missing. '
        'A01 flow, A04 liquidation, A05 ICT and A08 profile cannot be inferred from these bars. '
        'Funding0/1/3bps is hypothetical: C05-K reported up to4.3136bps trailing12h absolute funding on BNB, '
        'an ex-post aggregate stress, not a settlement forecast or actual cash flow. '
        'Candles do not resolve approval/IOC within10s, depth/partial fills, stop execution or exact11h55 liquidation.', '',
        'Candidate ranking, original-policy root-cause diagnosis, upstream reuse comparison and the explicit owner decision '
        'are in `docs/adr/ADR-P3-ECONOMIC-RECOVERY-S01.md`; the complete frozen source/formula/qualification handoff is '
        'in `S01_NEW_POLICY_PREREGISTRATION.md` and `S01_CANDIDATES.json`. '
        'No production policy/registry/C02/risk/execution change, collector, paid access or account action occurred. '
        'P3 remains INSUFFICIENT_EVIDENCE and formal phase credit45%/55% unqualified.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=OUT)
    parser.add_argument('--reuse-census', type=Path, help='reuse an exact hashed outcome-blind census from this preregistration')
    args = parser.parse_args()
    validate_inputs()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _memoize_numeric()
    panel = load_public_um_archive_panel(ROOT / 'research/c04/historical_manifest.json', args.data_root,
                                       source_end_exclusive=END)
    source_identity = config_hash({'partitions': list(panel.partitions)})
    if args.reuse_census:
        census, census_hash = checked_json(args.reuse_census, compressed=True)
        if (census['preregistration_sha256'] != PREREG_SHA or census['contract_sha256'] != CONTRACT_SHA
                or census['source_identity_sha256'] != source_identity):
            raise ValueError('reused census is not this frozen original-source study')
    else:
        census = {'schema_version': 's01.outcome-blind-census.v1', 'preregistration_sha256': PREREG_SHA,
            'contract_sha256': CONTRACT_SHA, 'source_identity_sha256': source_identity, **scan(panel)}
        census['matches'] = select_matches(census['events'], census['pool'])
        census_hash = config_hash(census)
    write_gzip(args.output_dir / 'S01_CAUSAL_CENSUS.json.gz', {**census, 'content_sha256': census_hash})
    print(f'Outcome-blind census/matches fixed: {census_hash}', flush=True)
    events, controls, source_bars = calculate_paths(panel, census)
    candidates = summarize(census, events, controls)
    packet = {'schema_version': 's01.exploratory-evidence.v1',
        'evidence_class': 'EXPLORATORY_DEVELOPMENT_PRICE_ONLY_NOT_EXECUTABLE',
        'census_content_sha256': census_hash, 'preregistration_sha256': PREREG_SHA,
        'contract_sha256': CONTRACT_SHA, 'preregistration_commit': PREREG_COMMIT,
        'source_manifest_sha256': MANIFEST_HASH, 'source_partitions': list(panel.partitions),
        'source_scope': panel.source_manifest, 'source_acceptance_contract': source_contract(),
        'research_code_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'verified_source_bars': sum(p['normalized_row_count'] for p in panel.partitions),
        'strict_eligible_candidates': 0, 'economic_qualification': 'INSUFFICIENT_EVIDENCE',
        'october_outcomes_accessed': False, 'policy_status': 'PROPOSED_RESEARCH_ONLY',
        'candidates': candidates, 'ranking': rank_candidates(candidates),
        'joint_candidates': group_summary(events, controls),
        'original_policy_diagnosis': diagnose_original(panel),
        'events': events, 'controls': controls, 'source_bars': source_bars}
    packet['content_sha256'] = config_hash(packet)
    write_gzip(args.output_dir / 'S01_EVIDENCE.json.gz', packet)
    (args.output_dir / 'S01_SEPTEMBER_ECONOMIC_SCREEN.md').write_text(render(packet))
    print(json.dumps({'evidence_sha256': packet['content_sha256'], 'census_sha256': census_hash,
        'candidates': {k: {f: v[f] for f in ('formations', 'confirmations', 'scenarios', 'decision')} for k, v in packet['candidates'].items()}}, indent=2), flush=True)


if __name__ == '__main__':
    main()
