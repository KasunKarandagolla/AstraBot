"""Frozen PC3/FA3 September price research; never a production policy registry."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal as D
from functools import lru_cache
from hashlib import sha256
import importlib.metadata
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
import s01_economic_recovery as old
from astrabot.data.models import binance_usdm_instrument_id, config_hash, stable_id
from astrabot.research import context as ctx
from astrabot.research.integrated import HISTORY_LIMITS
from astrabot.research.replay import _panel_point_in_time, load_public_um_archive_panel
from astrabot.research.statistics import matched_controls
from c05_r0_market_economics import START, END, SCENARIOS, _memoize_numeric, cost_screen, distribution
from c05_t1_event_control import MANIFEST_HASH, HORIZONS, bar_key, dt, write_gzip

OUT = ROOT / 'research/p3'
PREREG_SHA = '2e24286cb178f4906f61eba37cc53b704f4ad02a94b405ca6df9b488cc49903e'
PREREG_COMMIT = 'd54dcfc'
CONTRACT = json.loads((OUT / 'S03_CANDIDATES.json').read_text())
CONTRACT_SHA = '0002d9dada9c8006c66082617252ac3b720feab7a756798376f8bb62edb7ca57'
VERSIONS = {k: config_hash({'candidate': v, 'common': CONTRACT['common']})
            for k, v in CONTRACT['candidates'].items()}
SEED = CONTRACT['common']['seed']
sign_for = old.sign_for


def validate_inputs():
    if (sha256((OUT / 'S03_PREREGISTRATION.md').read_bytes()).hexdigest() != PREREG_SHA
            or CONTRACT['common']['protocol_sha256'] != PREREG_SHA
            or sha256((OUT / 'S03_CANDIDATES.json').read_bytes()).hexdigest() != CONTRACT_SHA
            or sha256((ROOT / 'research/c04/historical_manifest.json').read_bytes()).hexdigest() != MANIFEST_HASH):
        raise ValueError('frozen protocol or source manifest changed')


@lru_cache(maxsize=32)
def hourly_inventory(rows, symbol):
    """C03 strict confirmed levels; invalidate only subsequent observed touches."""
    inventory = old.opposing_inventory(type('Data', (), {'candles_1h': rows})(), symbol, rows[-1].available_at)
    # Suffix extrema permit linear-time visitation checks for every known level.
    high, low = [D('-Infinity')] * (len(rows) + 1), [D('Infinity')] * (len(rows) + 1)
    for i in range(len(rows) - 1, -1, -1):
        high[i], low[i] = max(rows[i].high, high[i+1]), min(rows[i].low, low[i+1])
    active, visited = [], []
    for level in inventory:
        i = bisect_right(rows, level.available_at, key=lambda b: b.available_at)
        touched = high[i] >= level.price if level.kind == 'SWING_HIGH' else low[i] <= level.price
        (visited if touched else active).append(level)
    return tuple(active), tuple(visited)


def active_inventory(data, symbol, at):
    active, visited = hourly_inventory(tuple(data.candles_1h), symbol)
    tail = [b for b in data.candles_5m if data.candles_1h[-1].available_at < b.available_at <= at]
    remaining, newly = [], []
    for level in active:
        touched = any(b.high >= level.price if level.kind == 'SWING_HIGH' else b.low <= level.price for b in tail)
        (newly if touched else remaining).append(level)
    return tuple(remaining), {
        'active_ids': [x.level_id for x in remaining],
        'visited_ids': [x.level_id for x in (*visited, *newly)],
        'hourly_span': span(data.candles_1h),
        'partial_hour_keys': [bar_key(b) for b in tail]}


def span(rows):
    return {'first': bar_key(rows[0]), 'last': bar_key(rows[-1]), 'count': len(rows),
            'ordered_keys_sha256': config_hash({'keys': [bar_key(b) for b in rows]})}


def direction_allowed(context, side):
    return context.bias != ('BEARISH' if side == 'LONG' else 'BULLISH')


def previous_day(data, at):
    midnight = at.replace(hour=0, minute=0, second=0, microsecond=0)
    start = midnight - timedelta(days=1)
    rows = [b for b in data.candles_1h if start <= b.open_time < midnight]
    if (len(rows) != 24 or any(b.open_time != start + timedelta(hours=i) for i, b in enumerate(rows))
            or any(b.available_at > at for b in rows)):
        return None
    high, low = max(b.high for b in rows), min(b.low for b in rows)
    return {'high': str(high), 'low': str(low), 'midpoint': str((high + low) / 2),
            'source_keys': [bar_key(b) for b in rows], 'available_at': midnight.isoformat()}


def headroom(setup):
    target, side = setup['target'], setup['side']
    s, entry, stop = sign_for(side), D(setup['entry_cap']), D(setup['stop'])
    if target is None:
        return ['NO_FORMATION_TARGET'], None
    if s * (D(target['price']) - entry) <= 0:
        return ['TARGET_BEHIND_FORMATION_ENTRY_CAP'], None
    if stop <= 0 or s * (entry - stop) <= 0:
        return ['INVALID_FORMATION_STOP'], None
    row = {'entry': str(entry), 'stop': str(stop), 'stop_distance': str(s * (entry-stop)),
           'targets': [{'price': target['price'], 'fraction': '1'}], 'side': side,
           'policy': setup['candidate'], 'route_feasible': True}
    result = cost_screen(row, SCENARIOS['base'])
    return ([] if result['passes_cost_screen'] else ['FORMATION_BASE_HEADROOM_FAILED']), result


def advance(setup, bar, context):
    at, s = bar.available_at, sign_for(setup['side'])
    formed = dt(setup['formed_at'])
    if at <= formed:
        raise ValueError('distinct later confirmation required')
    if setup['state'] != 'ARMED' or (setup['transitions'] and at <= dt(setup['transitions'][-1]['at'])):
        raise ValueError('terminal or repeated setup update')
    age = int((at - formed).total_seconds() // 300)
    if at != formed + timedelta(minutes=age * 5) or age > len(setup['transitions']) + 1:
        return 'INVALIDATED', 'MISSING_NEXT_CANDLE'
    if context.readiness != 'READY' or context.classification == 'EXTREME_VOLATILITY':
        return 'INVALIDATED', 'MISSING_OR_EXTREME_CONTEXT'
    if at.date() != formed.date():
        return 'INVALIDATED', 'UTC_SESSION_ROLLOVER'
    if s * ((bar.low if s == 1 else bar.high) - D(setup['stop'])) <= 0:
        return 'INVALIDATED', 'ORIGINAL_STOP_TOUCHED_BEFORE_CONFIRMATION'
    # FA3 bias is a retained mask so the prespecified no-bias ablation is observable.
    if not direction_allowed(context, setup['side']):
        if setup['candidate'] == 'PC3':
            return 'INVALIDATED', 'OPPOSITE_4H_BIAS'
        setup['bias_veto_at_confirmation'] = True
    directional = s * (bar.close - bar.open) > 0
    if setup['candidate'] == 'PC3':
        confirms = directional and s * (bar.close - D(setup['trigger_boundary'])) > 0
    else:
        confirms = (directional and D(setup['low']) < bar.close < D(setup['high'])
                    and s * (bar.close - D(setup['reclaim_close'])) > 0
                    and s * (bar.close - D(setup['breached_edge'])) >= D('.10') * D(setup['atr15']))
    limit = CONTRACT['candidates'][setup['candidate']]['max_confirmation_bars']
    if age <= limit and confirms:
        return 'CONFIRMED', 'DISTINCT_PRICE_ACCEPTANCE'
    return ('EXPIRED', 'ACCEPTANCE_DEADLINE_FAILED') if age >= limit else ('ARMED', 'WAITING_ACCEPTANCE')


def final_geometry(setup, bar, inventory):
    result = old.confirmation_geometry(setup, bar, inventory)
    s = sign_for(setup['side'])
    result['entry_cap_failed'] = s * (bar.close - D(setup['entry_cap'])) > 0
    result['formation_vetoes'] = setup['formation_vetoes']
    result['bias_veto'] = ('OPPOSITE_4H_BIAS' in setup['formation_vetoes']
                           or setup.get('bias_veto_at_confirmation', False))
    result['primary_eligible'] = not setup['formation_vetoes'] and not result['bias_veto'] and not result['entry_cap_failed']
    result['funding_stress'] = {}
    result['adverse_geometry'] = {}
    if result.get('scenarios'):
        row = {**result, 'side': setup['side'], 'policy': setup['candidate']}
        for bps in ('5', '10'):
            result['funding_stress'][bps] = cost_screen(row, {**SCENARIOS['base'], 'funding_bps': bps})
        for shift in (D(0), D('.025'), D('.05')):
            entry = bar.close + s * D(result['stop_distance']) * shift
            g = s * (D(setup['target']['price']) - entry) / (s * (entry - D(setup['stop'])))
            result['adverse_geometry'][str(shift)] = (D('1.8') <= g <= D(4)
                and s * (entry - D(setup['entry_cap'])) <= 0
                and s * (entry-D(setup['stop'])) / entry <= D('.02'))
    return result


def scan(panel, *, start=START, end=END):
    formations, events, pool, rejections = [], [], [], Counter()
    for symbol in sorted(panel.symbols):
        active, seen, last15, day, band = {}, set(), None, None, None
        for bar in panel.symbols[symbol].candles_5m:
            at = bar.available_at
            if not start <= at < end:
                continue
            data = _panel_point_in_time(panel, symbol, at, HISTORY_LIMITS)
            context = ctx.evaluate_context(data, symbol=symbol,
                instrument_id=binance_usdm_instrument_id(symbol), as_of=at)
            if day != at.date():
                day, seen, band = at.date(), set(), previous_day(data, at)
                print(f'causal census {symbol} {day}', flush=True)
            blocked = {name: False for name in VERSIONS}
            inventory = None
            audit = None
            def get_inventory():
                nonlocal inventory, audit
                if inventory is None:
                    inventory, audit = active_inventory(data, symbol, at)
                return inventory
            for key, setup in list(active.items()):
                blocked[setup['candidate']] = True
                state, reason = advance(setup, bar, context)
                setup['state'] = state
                setup['transitions'].append({'at': at.isoformat(), 'source_key': bar_key(bar), 'state': state, 'reason': reason})
                if state in ('CONFIRMED', 'INVALIDATED', 'EXPIRED'):
                    setup.update(terminal_at=at.isoformat(), terminal_reason=reason)
                    if state == 'CONFIRMED':
                        geometry = final_geometry(setup, bar, get_inventory())
                        events.append({'setup_id': setup['setup_id'], 'candidate': setup['candidate'],
                            'policy': setup['candidate'], 'policy_version': setup['policy_version'],
                            'symbol': symbol, 'side': setup['side'], 'formed_at': setup['formed_at'],
                            'terminal_at': at.isoformat(), 'regime': context.classification,
                            'candidate_regime': context.classification, 'bias': context.bias,
                            'atr_percentile': str(context.atr_percentile),
                            'confirmation_context': old.context_record(context, data),
                            'confirmation_inventory': audit, **geometry})
                    del active[key]
            new15 = data.candles_15m[-1].observation_id != last15
            if new15:
                last15 = data.candles_15m[-1].observation_id
            for name in VERSIONS:
                for side in ('LONG', 'SHORT'):
                    if (name, side) in active:
                        continue
                    s, terms, reasons = sign_for(side), None, []
                    if name == 'PC3':
                        if not new15:
                            continue
                        terms, reasons = old.pc_formation(data, context, side, at)
                        if terms is None:
                            rejections.update((name, r) for r in reasons)
                            continue
                        terms['trigger_boundary'] = str(bar.high if s == 1 else bar.low)
                        hourly = data.candles_1h[-20:]
                        boundary = max(b.high for b in hourly) if s == 1 else min(b.low for b in hourly)
                        bkeys, bat = [bar_key(b) for b in hourly], hourly[-1].available_at
                    else:
                        if band is None:
                            rejections[name, 'PREVIOUS_DAY_SOURCE_UNAVAILABLE'] += 1
                            continue
                        breached = bar.low < D(band['low']) if s == 1 else bar.high > D(band['high'])
                        if side in seen or not breached:
                            continue
                        seen.add(side)
                        blocked[name] = True
                        if context.atr_15m is None or context.atr_5m is None:
                            formations.append({'setup_id': stable_id('s03.setup', VERSIONS[name], symbol, side, at),
                                'candidate': name, 'policy_version': VERSIONS[name], 'symbol': symbol, 'side': side,
                                'formed_at': at.isoformat(), 'formation_source_key': bar_key(bar),
                                'formation_context': old.context_record(context, data), 'target': None,
                                'source_keys': band['source_keys'], 'state': 'REJECTED', 'transitions': [],
                                'formation_vetoes': ['MISSING_FORMATION_ATR'], 'primary_formation_state': 'REJECTED',
                                'terminal_at': at.isoformat(), 'terminal_reason': 'MISSING_FORMATION_ATR'})
                            continue
                        terms = {**band, 'atr15': str(context.atr_15m), 'atr5': str(context.atr_5m),
                            'stop': str((bar.low if s == 1 else bar.high) - s * D('.25') * context.atr_15m),
                            'reclaim_close': str(bar.close), 'breached_edge': band['low' if s == 1 else 'high']}
                        penetration = D(terms['breached_edge']) - bar.low if s == 1 else bar.high - D(terms['breached_edge'])
                        if not D('.10') * context.atr_15m <= penetration <= context.atr_15m:
                            reasons.append('FIRST_BREACH_PENETRATION_FAILED')
                        if not D(band['low']) < bar.close < D(band['high']):
                            reasons.append('FIRST_BREACH_NOT_RECLAIMED')
                        if s * (bar.close - bar.open) <= 0:
                            reasons.append('RECLAIM_DIRECTIONAL_BODY_FAILED')
                        if bar.low < D(band['low']) and bar.high > D(band['high']):
                            reasons.append('TWO_SIDED_RANGE_BREACH')
                        boundary, bkeys, bat = D(band['midpoint']), band['source_keys'], dt(band['available_at'])
                    if context.readiness != 'READY' or context.classification == 'EXTREME_VOLATILITY':
                        reasons.append('MISSING_OR_EXTREME_FORMATION_CONTEXT')
                    if not direction_allowed(context, side):
                        reasons.append('OPPOSITE_4H_BIAS')
                    inv = get_inventory()
                    # PC3 rolling extreme behind reference cannot exclude a valid swing ahead.
                    target = old.select_target(side, bar.close, inv, boundary=boundary,
                        boundary_keys=bkeys, boundary_at=bat)
                    if name == 'PC3' and s * (boundary - bar.close) <= 0:
                        target = old.select_target(side, bar.close, inv)
                    setup = {'setup_id': stable_id('s03.setup', VERSIONS[name], symbol, side, at),
                        'candidate': name, 'policy_version': VERSIONS[name], 'symbol': symbol, 'side': side,
                        'formed_at': at.isoformat(), 'formation_source_key': bar_key(bar),
                        'formation_context': old.context_record(context, data), 'formation_inventory': audit,
                        'target': target, **terms, 'entry_cap': str(bar.close + s * D('.25') * context.atr_15m),
                        'state': 'ARMED', 'transitions': [], 'terminal_at': None}
                    hr, screen = headroom(setup)
                    setup['formation_vetoes'], setup['formation_cap_screen'] = reasons + hr, screen
                    setup['primary_formation_state'] = 'REJECTED' if reasons + hr else 'ARMED'
                    hard = [r for r in reasons if r != 'OPPOSITE_4H_BIAS']
                    if hard:
                        setup.update(state='REJECTED', terminal_at=at.isoformat(), terminal_reason='|'.join(hard))
                    else:
                        active[name, side] = setup
                    # Every formation owns its mutable transition list and frozen anchor copies.
                    formations.append(setup)
                    blocked[name] = True
            for name in VERSIONS:
                reasons = []
                if blocked[name]:
                    reasons.append('ACTIVE_TERMINAL_OR_RAW_FORMATION')
                if context.readiness != 'READY' or context.classification == 'EXTREME_VOLATILITY':
                    reasons.append('CONTEXT_UNAVAILABLE_OR_EXTREME')
                if name == 'PC3' and context.classification not in ('TREND_UP', 'TREND_DOWN'):
                    reasons.append('CANDIDATE_REGIME_NOT_ELIGIBLE')
                if at + timedelta(hours=12) > END:
                    reasons.append('CROSSES_DEVELOPMENT_END')
                pool.append({'window_id': stable_id('s03.pool', name, symbol, at), 'candidate': name,
                    'symbol': symbol, 'event_time': at.isoformat(), 'source_key': bar_key(bar),
                    'reference_close': str(bar.close), 'regime': context.classification, 'bias': context.bias,
                    'atr_percentile': str(context.atr_percentile), 'adx': str(context.adx_1h),
                    'slope': str(context.normalized_slope), 'eligible_nontrigger': not reasons, 'exclusions': reasons})
        for setup in active.values():
            setup.update(state='END_CENSORED', terminal_reason='NO_OCTOBER_CONTINUATION')
    return {'formations': formations, 'events': events, 'pool': pool,
        'formation_rejections': [{'candidate': k[0], 'reason': k[1], 'count': v} for k, v in sorted(rejections.items())]}


def select_matches(events, pool):
    index = defaultdict(list)
    def key(r, side, when):
        return (r['candidate'], r['symbol'], r['regime'], r['bias'], side,
                min(3, int(D(r['atr_percentile']) // 25)), when.hour // 4)
    for row in pool:
        if row['eligible_nontrigger']:
            for side in ('LONG', 'SHORT'):
                if row['bias'] == ('BEARISH' if side == 'LONG' else 'BULLISH'):
                    continue
                if row['candidate'] == 'PC3' and row['regime'] != ('TREND_UP' if side == 'LONG' else 'TREND_DOWN'):
                    continue
                index[key(row, side, dt(row['event_time']))].append(row)
    matches = []
    for e in events:
        at = dt(e['terminal_at'])
        cohort = key(e, e['side'], at)
        candidates = [r for r in index[cohort] if at - timedelta(days=7) <= dt(r['event_time']) <= at - timedelta(hours=12)]
        label = '|'.join(map(str, cohort[3:]))
        trigger = {'window_id': e['setup_id'], 'symbol': e['symbol'], 'regime': e['regime'],
                   'cohort': label, 'event_time': e['terminal_at'], 'is_trigger': True}
        rows = [{**r, 'cohort': label, 'is_trigger': False} for r in candidates]
        selected = matched_controls([trigger, *rows], seed=SEED, embargo_hours=12).get(e['setup_id'])
        matches.append({'event_id': e['setup_id'], 'candidate': e['candidate'], 'control_id': selected,
            'candidate_count': len(candidates), 'cohort': list(cohort),
            'candidate_ids_sha256': config_hash({'ids': sorted(r['window_id'] for r in candidates)}),
            'status': 'MATCHED' if selected else 'NO_EXACT_PAST_CONTROL'})
    return matches


def eligible(row, *, no_headroom=False, no_cap=False, no_bias=False):
    vetoes = row['formation_vetoes']
    ignored = set()
    if no_headroom:
        ignored.update(('NO_FORMATION_TARGET', 'TARGET_BEHIND_FORMATION_ENTRY_CAP', 'FORMATION_BASE_HEADROOM_FAILED'))
    if no_bias:
        ignored.add('OPPOSITE_4H_BIAS')
    return (not (set(vetoes) - ignored) and (no_cap or not row['entry_cap_failed'])
            and (no_bias or not row['bias_veto']))


def is_base(row, scenario='base', **masks):
    return eligible(row, **masks) and old.base_survivor(row, scenario)


def gate(candidate):
    # The inherited decision is deliberately stricter than the user's minimum.
    result = old.decision(candidate)
    if result == 'ADVANCE_TO_SOURCE_QUALIFICATION':
        return 'ADVANCE_TO_R1_SOURCE_QUALIFICATION'
    if result == 'REJECT_ECONOMIC_HYPOTHESIS':
        return 'REJECT'
    base = candidate['groups']['base_survivors']
    return 'REVISE_BEFORE_R1' if base['n'] > 2 and len(base['symbols']) >= 4 else 'REJECT'


def gate_checks(c):
    b = c['groups']['base_survivors']
    h = b['horizons']['720']
    n = h['complete']
    p1, p4, p12 = (b['horizons'][str(t)]['paired'] for t in (60, 240, 720))
    def contrast(p, *, strict=True):
        v = p['equal_day_difference_bps']
        return v is not None and (D(v) > 0 if strict else D(v) >= 0)
    return {'complete_base_at_least20': n >= 20,
        'complete_days_at_least8': len(b['complete12h_market_days']) >= 8,
        'complete_symbols_at_least4': len(b['complete12h_symbols']) >= 4,
        'base_fraction_at_least10pct': c['confirmations'] > 0 and D(b['n']) / c['confirmations'] >= D('.10'),
        'conservative_target_first_at_least35pct': n > 0 and D(h['target_before_stop_lower']) / n >= D('.35'),
        'exact_matched_at_least50pct': n > 0 and p12['pairs'] * 2 >= n,
        'matched_event_days_at_least8': p12['event_days'] >= 8,
        'positive_1h_contrast': contrast(p1), 'positive_4h_contrast': contrast(p4),
        'nonnegative_12h_contrast': contrast(p12, strict=False),
        'positive_4h_day_deletion_lower': p4['leave_one_event_day_out_bps'] is not None and D(p4['leave_one_event_day_out_bps'][0]) > 0}


def summarize(census, events, controls):
    result = {}
    for name in VERSIONS:
        rows = [r for r in events if r['candidate'] == name]
        # A chase rejection is still a confirmation in the qualification denominator.
        primary = [r for r in rows if eligible(r, no_cap=True)]
        formed = [r for r in census['formations'] if r['candidate'] == name]
        base = [r for r in rows if is_base(r)]
        groups = {'all_diagnostic_confirmations': rows, 'all_confirmations': primary,
                  'base_survivors': base, 'rejected_confirmations': [r for r in rows if not is_base(r)]}
        ablations = {'no_headroom': {'no_headroom': True}, 'no_entry_cap': {'no_cap': True},
                     'neither_headroom_nor_cap': {'no_headroom': True, 'no_cap': True}}
        if name == 'FA3':
            ablations['no_4h_bias_veto'] = {'no_bias': True}
        c = {'policy_id': CONTRACT['candidates'][name]['policy_id'], 'version_sha256': VERSIONS[name],
             'raw_formations': len(formed), 'accepted_formation_arms': sum(not f['formation_vetoes'] for f in formed),
             'formation_states': dict(Counter(f['state'] for f in formed)),
             'primary_formation_states': dict(Counter(f['primary_formation_state'] for f in formed)),
             'formation_veto_memberships': dict(Counter(r for f in formed for r in f['formation_vetoes'])),
             'terminal_reason_counts': dict(Counter(f['terminal_reason'] for f in formed)),
             'diagnostic_confirmations': len(rows), 'confirmations': len(primary),
             'confirmation_geometry_rejections': dict(Counter(r for e in rows for r in e['geometry_rejections'])),
             'entry_cap_rejections': sum(e['entry_cap_failed'] for e in rows),
             'scenarios': {s: sum(is_base(e, s) for e in rows) for s in SCENARIOS},
             'adverse_entry_survivors': {s: sum(is_base(e) and e['adverse_geometry'].get(s, False)
                 and e['adverse_entry_sensitivity'][s]['passes_with_route'] for e in rows) for s in ('0', '0.025', '0.05')},
             'funding_stress_survivors': {s: sum(is_base(e) and e['funding_stress'][s]['passes_with_route'] for e in rows) for s in ('5', '10')},
             'groups': {k: old.group_summary(v, controls) for k, v in groups.items()},
             'ablations': {k: old.group_summary([e for e in rows if is_base(e, **m)], controls) for k, m in ablations.items()},
             'control_pool_eligible': sum(r['candidate'] == name and r['eligible_nontrigger'] for r in census['pool']),
             'volatility_quartiles': {str(q): old.group_summary([e for e in base if min(3, int(D(e['atr_percentile']) // 25)) == q], controls) for q in range(4)}}
        # Avoid conditional empty-sample division in the inherited advancement function.
        c['decision'] = gate(c) if c['confirmations'] else 'REJECT'
        c['advancement_checks'] = gate_checks(c)
        c['control_balance'] = {
            field: distribution(D(e['confirmation_context'][source]) - D(r[field])
                for r in controls for e in base if r['matched_event_id'] == e['setup_id'])
            for field, source in (('adx', 'adx_1h'), ('slope', 'normalized_slope'))}
        result[name] = c
    return result


def source_bar(b):
    minutes = {'5m': 5, '15m': 15, '1h': 60, '4h': 240}[b.interval]
    return {'source_key': bar_key(b), 'symbol': b.symbol, 'interval': b.interval,
        'native_id': b.source_record_id, 'observation_id': b.observation_id,
        'archive_id': f'{b.symbol}-{b.interval}-{b.open_time:%Y-%m}.zip',
        'csv_record_number_including_header': int(((b.open_time.day-1)*1440+b.open_time.hour*60+b.open_time.minute)//minutes)+2,
        'open_time': b.open_time.isoformat(), 'available_at': b.available_at.isoformat(),
        **{k: str(getattr(b, k)) for k in ('open', 'high', 'low', 'close', 'base_volume')}}


def benchmarks():
    packet, digest = old.checked_json(OUT / 'S01_EVIDENCE.json.gz', compressed=True)
    return {'source_manifest_sha256': packet['source_manifest_sha256'], 'evidence_sha256': digest,
        'candidates': {k: {f: v[f] for f in ('formations', 'confirmations', 'scenarios', 'groups', 'decision')}
                       for k, v in packet['candidates'].items()}}


def causal_fingerprint():
    functions = (hourly_inventory.__wrapped__, active_inventory, span, direction_allowed, previous_day,
        headroom, advance, final_geometry, scan, select_matches)
    sources = {f.__name__: inspect.getsource(f) for f in functions}
    for name in ('s01_economic_recovery.py', 'c05_r0_market_economics.py', 'c05_t1_event_control.py'):
        sources[name] = sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
    return config_hash(sources)


def render(p):
    lines = ['# S03 — Frozen September strategy test', '',
        '**Exploratory development / original OHLCV / RESEARCH_ONLY.** No executed P&L or net expectancy.', '',
        f"Preregistration `{PREREG_COMMIT}`, protocol `{PREREG_SHA}`. Census `{p['census_content_sha256']}`; evidence `{p['content_sha256']}`.", '',
        f"Verified {p['verified_source_bars']:,} bars in84 pinned July–September archives. October archives/outcomes unopened. "
        'Seven fixed symbols are not a historically qualified universe. Source acceptance remains7 PARTIAL/2 UNVERIFIED/0 accepted.', '',
        '| Candidate | Raw formations / accepted arms | Diagnostic / primary confirmations | Optimistic / base / stress | Decision |',
        '|---|---:|---:|---:|---|']
    for name in p['ranking']:
        c = p['candidates'][name]
        lines.append(f"| {name} | {c['raw_formations']} / {c['accepted_formation_arms']} | {c['diagnostic_confirmations']} / {c['confirmations']} | {' / '.join(str(c['scenarios'][s]) for s in SCENARIOS)} | {c['decision']} |")
    lines += ['', 'PC3 instantiates the lead reference with early acceptance, causal unvisited objectives and explicit formation headroom. '
        'FA3 tests a distinct previous-day failed-auction mechanism. A verbal benchmark has no independent third-policy results.', '',
        'PC2/FR2 use the identical84 archives, manifest, split and C05 cost/path formulas:392/70/2 and361/3/0 formations/confirmations/base survivors. '
        'PC2 conservative target-first1/2, exact controls0/2; FR2 has no surviving paths. Entry/management differ by frozen version.', '']
    for name in p['ranking']:
        c = p['candidates'][name]
        b = c['groups']['base_survivors']
        h = b['horizons']['720']
        lines += [f"## {name}: {c['decision']}", '', f"`{c['policy_id']}` / `{c['version_sha256']}`.", '',
            f"Base population {b['n']}; complete12h {h['complete']}, censored {h['censored']}; "
            f"{len(b['complete12h_market_days'])} complete UTC days, {len(b['complete12h_symbols'])} symbols. "
            f"Target first conservative–optimistic {h['target_before_stop_lower']}–{h['target_before_stop_upper']}; "
            f"stop first {h['stop_first']}, same candle {h['same_bar_ambiguous']}.", '',
            f"Symbols `{json.dumps(b['symbols'], sort_keys=True)}`; sides `{json.dumps(b['side'], sort_keys=True)}`; "
            f"regimes `{json.dumps(b['regimes'], sort_keys=True)}`; UTC4h sessions `{json.dumps(b['sessions_utc_4h'], sort_keys=True)}`. "
            f"Days `{json.dumps(b['market_days'], sort_keys=True)}`.", '',
            f"Median stop fraction {b['stop_fraction']['median']}, target price-R {b['target_price_r']['median']}, base loss cost-R {b['base_loss_cost_r']['median']}. "
            f"Adverse0/.025/.05R survivors `{json.dumps(c['adverse_entry_survivors'], sort_keys=True)}`; funding5/10bps survivors `{json.dumps(c['funding_stress_survivors'], sort_keys=True)}`. "
            'These are planned successful-target scenarios, not returns.', '',
            '| Horizon | Complete/censored | Target lower/upper | Stop first | Median signed bps | Paired N/days | Equal-day contrast bps | Day-deletion range |',
            '|---|---:|---:|---:|---:|---:|---:|---|']
        for horizon in HORIZONS:
            r = b['horizons'][str(horizon)]
            pair = r['paired']
            lines.append(f"| {horizon}m | {r['complete']}/{r['censored']} | {r['target_before_stop_lower']}/{r['target_before_stop_upper']} | {r['stop_first']} | {r['signed_close_bps']['median']} | {pair['pairs']}/{pair['event_days']} | {pair['equal_day_difference_bps']} | {pair['leave_one_event_day_out_bps']} |")
        lines += ['', f"Original stop by5m/15m/1h: {b['first_forward_bar_stop_touches']}/{b['stop_by15m']}/{b['stop_by1h']}; "
            f"target first by11h55: {h['target_before_stop_by_11h55_lower']}. "
            f"Kish day concentration {b['kish_day_concentration']:.3f}; {b['overlapping_case_control_window_pairs']} overlapping intervals, "
            f"{b['connected_market_time_components']} connected market-time components. No independent-trade or significance claim.", '',
            f"Formation vetoes `{json.dumps(c['formation_veto_memberships'], sort_keys=True)}`; "
            f"terminal reasons `{json.dumps(c['terminal_reason_counts'], sort_keys=True)}`; "
            f"confirmation geometry vetoes `{json.dumps(c['confirmation_geometry_rejections'], sort_keys=True)}`; cap vetoes {c['entry_cap_rejections']}.", '',
            '| Frozen population / ablation | N | Complete12h | Target lower/upper | 4h equal-day contrast bps |',
            '|---|---:|---:|---:|---:|']
        labels = ['all_diagnostic_confirmations', 'all_confirmations', 'base_survivors', 'rejected_confirmations',
                  'no_headroom', 'no_entry_cap', 'neither_headroom_nor_cap']
        if name == 'FA3':
            labels.append('no_4h_bias_veto')
        for label in labels:
            g = (c['groups'] if label in c['groups'] else c['ablations'])[label]
            hh = g['horizons']['720']
            lines.append(f"| {label} | {g['n']} | {hh['complete']} | {hh['target_before_stop_lower']}/{hh['target_before_stop_upper']} | {g['horizons']['240']['paired']['equal_day_difference_bps']} |")
        lines += ['', 'Ablations are descriptive masks, not candidates eligible for advancement; no policy is replaced after observing these results. '
            'All rejected confirmations retain signed paths. Invalid geometry target touches are context, not admissible trades. '
            'Full MFE/MAE, volatility strata, per-day contrasts, matched pool hashes and source CSV locators are in the evidence.', '']
    lines += ['## Reproduction and scope', '', '```sh',
        'python scripts/s03_strategy_research.py --data-root /workspace/work/c04-data', '```', '',
        'Use requirements-test.txt in an isolated environment. No command downloads data or opens October. '
        '`--output-dir` writes a comparison copy; `--census-only` stops before outcomes; '
        '`--reuse-census` validates and reopens the frozen causal census. '
        'Census is written and sealed before any new path call. Candidate/contract/source/code/dependency hashes are retained.', '',
        'See S03_OWNER_DECISION.md for the falsification examples, complete gate checklist and S04/S05 handoff. '
        'No strict C02 eligibility, actual fees/funding/fills, approval/IOC feasibility or full-policy net_R is established. '
        'P3 INSUFFICIENT_EVIDENCE; formal qualification remains45%/55% unqualified.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=OUT)
    parser.add_argument('--reuse-census', type=Path)
    parser.add_argument('--census-only', action='store_true')
    args = parser.parse_args()
    validate_inputs()
    _memoize_numeric()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    panel = load_public_um_archive_panel(ROOT / 'research/c04/historical_manifest.json', args.data_root, source_end_exclusive=END)
    identity = config_hash({'partitions': list(panel.partitions)})
    if args.reuse_census:
        census, digest = old.checked_json(args.reuse_census, compressed=True)
        if (census['protocol_sha256'] != PREREG_SHA or census['contract_sha256'] != CONTRACT_SHA
                or census['source_identity_sha256'] != identity or census['versions'] != VERSIONS
                or census.get('causal_implementation_sha256') != causal_fingerprint()):
            raise ValueError('census is not this frozen study')
    else:
        census = {'schema_version': 's03.outcome-blind-census.v1', 'protocol_sha256': PREREG_SHA,
            'contract_sha256': CONTRACT_SHA, 'source_identity_sha256': identity, 'versions': VERSIONS,
            'causal_implementation_sha256': causal_fingerprint(), **scan(panel)}
        if len(census['pool']) != 120960:
            raise ValueError('incomplete frozen September population')
        census['matches'] = select_matches(census['events'], census['pool'])
        digest = config_hash(census)
    write_gzip(args.output_dir / 'S03_CAUSAL_CENSUS.json.gz', {**census, 'content_sha256': digest})
    print(f'Outcome-blind census sealed: {digest}', flush=True)
    if args.census_only:
        return
    events, controls, source_bars = old.calculate_paths(panel, census)
    retained = {r['source_key']: r for r in source_bars}
    # Preserve all hourly source history so unvisited-level claims can be independently rebuilt.
    for data in panel.symbols.values():
        for interval in ('1h', '4h'):
            for b in getattr(data, 'candles_' + interval):
                retained[bar_key(b)] = source_bar(b)
    candidates = summarize(census, events, controls)
    order = {'ADVANCE_TO_R1_SOURCE_QUALIFICATION': 0, 'REVISE_BEFORE_R1': 1, 'SOURCE_DEPENDENT': 2, 'REJECT': 3}
    def rank(k):
        c = candidates[k]
        contrast = c['groups']['base_survivors']['horizons']['240']['paired']['equal_day_difference_bps']
        return (order[c['decision']], -D(contrast) if contrast is not None else D('Infinity'),
                -c['groups']['base_survivors']['horizons']['720']['complete'], k != 'PC3')
    code_files = [Path(__file__), ROOT/'scripts/s01_economic_recovery.py', ROOT/'scripts/c05_r0_market_economics.py',
        ROOT/'scripts/c05_t1_event_control.py', ROOT/'src/astrabot/research/context.py', ROOT/'src/astrabot/research/levels.py',
        ROOT/'src/astrabot/research/replay.py', ROOT/'src/astrabot/research/statistics.py', ROOT/'src/astrabot/features/providers.py']
    packet = {'schema_version': 's03.exploratory-evidence.v1', 'census_content_sha256': digest,
        'protocol_sha256': PREREG_SHA, 'contract_sha256': CONTRACT_SHA, 'preregistration_commit': PREREG_COMMIT,
        'source_manifest_sha256': MANIFEST_HASH, 'source_partitions': list(panel.partitions),
        'verified_source_bars': sum(x['normalized_row_count'] for x in panel.partitions),
        'research_code_sha256': {str(f.relative_to(ROOT)): sha256(f.read_bytes()).hexdigest() for f in code_files},
        'dependencies': {k: importlib.metadata.version(k) for k in ('numpy', 'TA-Lib', 'pydantic')},
        'strict_eligible_candidates': 0, 'october_outcomes_accessed': False,
        'economic_qualification': 'INSUFFICIENT_EVIDENCE', 'policy_status': 'PROPOSED_RESEARCH_ONLY',
        'candidates': candidates, 'ranking': sorted(candidates, key=rank), 'benchmarks': benchmarks(),
        'joint_candidates': old.group_summary(events, controls), 'events': events, 'controls': controls,
        'source_bars': sorted(retained.values(), key=lambda r: (r['symbol'], r['interval'], r['open_time']))}
    packet['content_sha256'] = config_hash(packet)
    write_gzip(args.output_dir/'S03_EVIDENCE.json.gz', packet)
    (args.output_dir/'S03_SEPTEMBER_RESULTS.md').write_text(render(packet))
    print(json.dumps({'evidence_sha256': packet['content_sha256'], 'ranking': packet['ranking'],
        'candidates': {k: {f: v[f] for f in ('raw_formations', 'confirmations', 'scenarios', 'decision')} for k, v in candidates.items()}}, indent=2), flush=True)


if __name__ == '__main__':
    main()
