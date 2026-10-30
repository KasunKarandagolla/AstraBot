"""Preregistered VT4 causal research. No registry, authenticated API or trading path."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal as D
from hashlib import sha256
import importlib.metadata
import inspect
import json
from pathlib import Path
from statistics import mean, stdev
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
import s01_economic_recovery as old
import s03_strategy_research as s03
from astrabot.data.models import binance_usdm_instrument_id, config_hash, stable_id
from astrabot.research import context as ctx
from astrabot.research.replay import _panel_point_in_time, load_public_um_archive_panel
from c05_r0_market_economics import SCENARIOS, _memoize_numeric, cost_screen, distribution
from c05_t1_event_control import MANIFEST_HASH, bar_key, dt, price_path, write_gzip, market_components

OUT = ROOT/'research/p3'
PROTOCOL_SHA = sha256((OUT/'S04_PREREGISTRATION.md').read_bytes()).hexdigest()
CONTRACT = json.loads((OUT/'S04_CANDIDATES.json').read_text())
CONTRACT_SHA = sha256((OUT/'S04_CANDIDATES.json').read_bytes()).hexdigest()
VERSION = config_hash({'contract': CONTRACT, 'protocol_sha256': PROTOCOL_SHA})
LIMITS = {**s03.HISTORY_LIMITS, '15m': 25}
START, END = dt('2024-08-01T00:00:00Z'), dt('2024-10-01T00:00:00Z')
SEED = CONTRACT['seed']
sign_for = old.sign_for
FILTERS = ('COMPRESSION_FAILED', 'VOLUME_FAILED', 'OPPOSITE_4H_BIAS')
ABLATIONS = {'no_compression': {FILTERS[0]}, 'no_volume': {FILTERS[1]},
             'no_bias': {FILTERS[2]}, 'no_three_filters': set(FILTERS)}


def month_end(at):
    return dt('2024-09-01T00:00:00Z') if at.month == 8 else END


def validate_inputs():
    # Literal byte hashes from preregistration commit93adad5; also works in a
    # shallow Actions checkout without that ancestor object or Git installed.
    if (PROTOCOL_SHA != 'c64c81cad1963d16fa66054d9c327483af311320cb16ed717aa41c98a2b68938'
            or CONTRACT_SHA != '3dd0d38c1187c8d75e141f7dc4c1d76bdcde183accd7e22365a7dd0f50222792'):
        raise ValueError('preregistered contract changed')
    if sha256((ROOT/'research/c04/historical_manifest.json').read_bytes()).hexdigest() != MANIFEST_HASH:
        raise ValueError('source manifest changed')


def raw_terms(data, context, at):
    """A past-only range; return raw breakout even when a primary mask fails."""
    rows = data.candles_15m
    if len(rows) < 25:
        return None, 'INSUFFICIENT_RANGE_HISTORY'
    q, prior = rows[-1], rows[-25:-1]
    if any(b.open_time != q.open_time-timedelta(minutes=15*(24-i)) for i, b in enumerate(prior)):
        return None, 'NONCONTIGUOUS_RANGE'
    high, low = max(b.high for b in prior), min(b.low for b in prior)
    if not low <= prior[-1].close <= high:
        return None, 'PREVIOUS_CLOSE_OUTSIDE_RANGE'
    side = 'LONG' if q.close > high else 'SHORT' if q.close < low else None
    if side is None:
        return None, 'NO_CLOSED_RANGE_BREAKOUT'
    history = tuple(b for b in data.candles_1h if b.available_at <= q.open_time)
    if len(history) < 15:
        return {'side': side, 'source_keys': [bar_key(b) for b in prior]}, 'MISSING_PREBREAK_ATR'
    a, s = ctx._atr(history), sign_for(side)
    edge, width = (high if s == 1 else low), high-low
    stop_rows = rows[-12:]
    anchor = min(b.low for b in stop_rows) if s == 1 else max(b.high for b in stop_rows)
    vetoes = []
    if context.readiness != 'READY' or context.classification == 'EXTREME_VOLATILITY':
        vetoes.append('MISSING_OR_EXTREME_CONTEXT')
    if not s03.direction_allowed(context, side):
        vetoes.append('OPPOSITE_4H_BIAS')
    if width/a > D(CONTRACT['compression_max_atr']):
        vetoes.append('COMPRESSION_FAILED')
    if context.rvol_15m is None or context.rvol_15m < D(CONTRACT['minimum_rvol']):
        vetoes.append('VOLUME_FAILED')
    if s*(q.close-q.open) <= 0:
        vetoes.append('DIRECTIONAL_BODY_FAILED')
    if not D('.05')*a <= s*(q.close-edge) <= D('.50')*a:
        vetoes.append('BREAKOUT_DISTANCE_FAILED')
    return {'side': side, 'edge': str(edge), 'high': str(high), 'low': str(low),
        'width': str(width), 'atr1_prebreak': str(a), 'atr5': str(context.atr_5m),
        'atr15': str(context.atr_15m), 'stop': str(anchor-s*D('.25')*a),
        'stop_anchor': str(anchor), 'entry_cap': str(edge+s*D('.50')*a),
        'projection': str(edge+s*2*width), 'formation_vetoes': vetoes,
        'source_keys': [bar_key(b) for b in prior],
        'stop_source_keys': [bar_key(b) for b in stop_rows],
        'prebreak_atr_span': s03.span(history)}, None


def advance(setup, bar):
    if setup['state'] != 'ARMED' or bar.available_at <= dt(setup['formed_at']):
        raise ValueError('distinct later bar and armed state required')
    if bar.available_at != dt(setup['formed_at'])+timedelta(minutes=5):
        return 'INVALIDATED', 'MISSING_NEXT_CANDLE'
    s = sign_for(setup['side'])
    if s*((bar.low if s == 1 else bar.high)-D(setup['stop'])) <= 0:
        return 'INVALIDATED', 'STOP_BEFORE_ENTRY'
    if s*(bar.close-D(setup['edge'])) >= D('.05')*D(setup['atr1_prebreak']):
        return 'CONFIRMED', 'DISTINCT_RANGE_ACCEPTANCE'
    return 'EXPIRED', 'NEXT_BAR_ACCEPTANCE_FAILED'


def geometry(setup, bar, inventory, context):
    result = old.confirmation_geometry(setup, bar, inventory)
    s = sign_for(setup['side'])
    target = D(setup['target']['price']) if setup['target'] else None
    vetoes = list(setup['formation_vetoes'])
    if context.readiness != 'READY' or context.classification == 'EXTREME_VOLATILITY':
        vetoes.append('MISSING_OR_EXTREME_CONFIRMATION_CONTEXT')
    if s*(bar.close-D(setup['entry_cap'])) > 0:
        vetoes.append('ENTRY_CAP_FAILED')
    if target is not None and ((bar.high >= target if s == 1 else bar.low <= target) or setup['target_touched_at_formation']):
        vetoes.append('TARGET_ALREADY_TOUCHED')
    result['formation_vetoes'] = list(setup['formation_vetoes'])
    result['policy_vetoes'] = sorted(set(vetoes))
    row = {**result, 'policy': 'VT4', 'side': setup['side']}
    result['funding_stress'] = {bps: cost_screen(row, {**SCENARIOS['base'], 'funding_bps': bps})
                              for bps in ('5', '10')} if result.get('scenarios') else {}
    result['stop_slippage_stress'] = cost_screen(row, SCENARIOS['base'], stop_slippage_r=D('.10')) if result.get('scenarios') else None
    result['adverse_geometry'] = {}
    for shift in ('0', '0.025', '0.05'):
        e = bar.close+s*D(result['stop_distance'])*D(shift)
        d = s*(e-D(setup['stop']))
        g = s*(target-e)/d if d > 0 and target is not None else D(-1)
        result['adverse_geometry'][shift] = (d > 0 and D('1.8') <= g <= D(4)
            and d/e <= D('.02') and s*(e-D(setup['entry_cap'])) <= 0)
    return result


def scan(panel):
    formations, events, pool, counters = [], [], [], Counter()
    for symbol in sorted(panel.symbols):
        active, cooldown, last15, lastday = None, START, None, None
        for bar in panel.symbols[symbol].candles_5m:
            at = bar.available_at
            if not START <= at < END:
                continue
            if at.date() != lastday:
                lastday = at.date()
                print(f'census {symbol} {lastday}', flush=True)
            data = _panel_point_in_time(panel, symbol, at, LIMITS)
            context = ctx.evaluate_context(data, symbol=symbol,
                instrument_id=binance_usdm_instrument_id(symbol), as_of=at)
            terminal = False
            if active is not None:
                state, reason = advance(active, bar)
                active['state'] = state
                active['transitions'].append({'source_key': bar_key(bar), 'at': at.isoformat(), 'state': state, 'reason': reason})
                active.update(terminal_at=at.isoformat(), terminal_reason=reason)
                if state == 'CONFIRMED':
                    inventory, audit = s03.active_inventory(data, symbol, at)
                    events.append({'setup_id': active['setup_id'], 'candidate': 'VT4', 'policy': 'VT4',
                        'policy_version': VERSION, 'symbol': symbol, 'side': active['side'],
                        'formed_at': active['formed_at'], 'terminal_at': at.isoformat(),
                        'regime': context.classification, 'bias': context.bias,
                        'atr_percentile': str(context.atr_percentile),
                        'confirmation_context': old.context_record(context, data),
                        'confirmation_inventory': audit, 'entry_cap': active['entry_cap'],
                        **geometry(active, bar, inventory, context)})
                active, terminal = None, True
            q = data.candles_15m[-1]
            if q.observation_id != last15:
                last15 = q.observation_id
                if at < cooldown:
                    counters[symbol, 'COOLDOWN_15M'] += 1
                else:
                    terms, reason = raw_terms(data, context, at)
                    if terms is None:
                        counters[symbol, reason] += 1
                    else:
                        cooldown = at+timedelta(hours=6)
                        setup = {'setup_id': stable_id('s04.setup', VERSION, symbol, at, terms['side']),
                            'candidate': 'VT4', 'policy_version': VERSION, 'symbol': symbol,
                            'formed_at': at.isoformat(), 'formation_source_key': bar_key(q),
                            'formation_context': old.context_record(context, data),
                            'state': 'ARMED', 'transitions': [], **terms}
                        if reason:
                            setup.update(state='REJECTED', terminal_at=at.isoformat(), terminal_reason=reason,
                                         formation_vetoes=[reason], target=None)
                        else:
                            inventory, audit = s03.active_inventory(data, symbol, at)
                            target = old.select_target(terms['side'], q.close, inventory,
                                boundary=D(terms['projection']), boundary_keys=terms['source_keys'], boundary_at=at)
                            # Breakout projection is ahead by construction; nearest eligible opposition wins.
                            setup.update(target=target, formation_inventory=audit,
                                target_touched_at_formation=bool(target and (q.high >= D(target['price']) if terms['side']=='LONG'
                                                             else q.low <= D(target['price']))))
                            active = setup
                        formations.append(setup)
            exclusions = []
            if at < cooldown or terminal or active:
                exclusions.append('RAW_ACTIVE_TERMINAL_OR_COOLDOWN')
            if context.readiness != 'READY' or context.classification == 'EXTREME_VOLATILITY':
                exclusions.append('CONTEXT_UNAVAILABLE_OR_EXTREME')
            if at+timedelta(hours=12) > month_end(at):
                exclusions.append('CROSSES_MONTH_END')
            pool.append({'window_id': stable_id('s04.pool', VERSION, symbol, at), 'candidate': 'VT4',
                'symbol': symbol, 'event_time': at.isoformat(), 'source_key': bar_key(bar),
                'reference_close': str(bar.close), 'regime': context.classification, 'bias': context.bias,
                'atr_percentile': str(context.atr_percentile), 'adx': str(context.adx_1h),
                'slope': str(context.normalized_slope), 'eligible_nontrigger': not exclusions,
                'exclusions': exclusions})
        if active is not None:
            active.update(state='END_CENSORED', terminal_at=None, terminal_reason='NO_OCTOBER_CONTINUATION')
    return {'formations': formations, 'events': events, 'pool': pool,
            'scan_rejections': [{'symbol': k[0], 'reason': k[1], 'count': v} for k,v in sorted(counters.items())]}


def select_matches(events, pool):
    # Reuse S03 exact covariate + original past-only matching, separately per month.
    result = []
    previous_seed = s03.SEED
    try:
        s03.SEED = SEED
        for month in ('2024-08', '2024-09'):
            result.extend(s03.select_matches([e for e in events if e['terminal_at'].startswith(month)],
                [r for r in pool if r['event_time'].startswith(month)]))
    finally:
        s03.SEED = previous_seed
    return result


_WORKER_PANEL = None


def _scan_symbol(symbol):
    from dataclasses import replace
    return scan(replace(_WORKER_PANEL,symbols={symbol:_WORKER_PANEL.symbols[symbol]}))


def run_census(panel, workers):
    """Two independent symbol reducers; deterministic merge, no outcome access."""
    if workers==1:
        return scan(panel)
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    global _WORKER_PANEL
    _WORKER_PANEL=panel
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('fork')) as executor:
        fragments=list(executor.map(_scan_symbol,sorted(panel.symbols)))
    return {key:[row for f in fragments for row in f[key]]
            for key in ('formations','events','pool','scan_rejections')}


def is_base(e, scenario='base', ignored=frozenset()):
    return not (set(e['policy_vetoes'])-set(ignored)) and old.base_survivor(e, scenario)


def paths(panel, census):
    used, events, controls = {}, [], []
    lookup = {e['setup_id']:e for e in census['events']}
    pool = {r['window_id']:r for r in census['pool']}
    def calculate(symbol, at, entry, distance, side, target):
        bars = panel.symbols[symbol].candles_5m
        index = bisect_right(bars, at, key=lambda b:b.available_at)
        if not index or bars[index-1].available_at != at:
            raise ValueError('reference missing native bar')
        rows = tuple(b for b in bars[index:index+144] if b.available_at <= month_end(at))
        for b in (bars[index-1], *rows):
            used[bar_key(b)] = s03.source_bar(b)
        return price_path(rows, at=at, reference=entry, distance=distance, side=side,
                          target2=target, end=month_end(at)), rows
    for e in census['events']:
        outcomes, rows = calculate(e['symbol'], dt(e['terminal_at']), D(e['entry']),
            D(e['stop_distance']), e['side'], D(e['targets'][0]['price']) if e['targets'] else None)
        timing = []
        for offset in (0, 1):
            if len(rows) <= offset:
                continue
            b, s = rows[offset], sign_for(e['side'])
            entry = b.open
            distance = s*(entry-D(e['stop']))
            g = s*(D(e['targets'][0]['price'])-entry)/distance if distance > 0 and e['targets'] else D(-1)
            geometry_ok = distance > 0 and D('1.8') <= g <= D(4) and distance/entry <= D('.02') and s*(entry-D(e['entry_cap'])) <= 0
            shifted = {**e, 'entry': str(entry), 'stop_distance':str(distance)}
            timing.append({'delay_seconds':offset*300, 'source_key':bar_key(b), 'reference_open':str(entry),
                'within_geometry_cap_and_base_cost':geometry_ok and cost_screen(shifted, SCENARIOS['base'])['passes_with_route'],
                'actual_approval_or_fill_proven':False})
        events.append({**e, 'outcomes':outcomes, 'entry_timing_diagnostics':timing,
            'modeled_cashflows': {name: cashflow(e, rows, terms) for name,terms in SCENARIOS.items()}})
    for link in census['matches']:
        if not link['control_id']:
            continue
        e, c = lookup[link['event_id']], pool[link['control_id']]
        reference, s = D(c['reference_close']), sign_for(e['side'])
        distance = reference*D(e['stop_fraction'])
        target = reference+s*reference*D(e['target_fraction']) if e.get('target_fraction') is not None else None
        outcomes, _ = calculate(c['symbol'],dt(c['event_time']),reference,distance,e['side'],target)
        controls.append({**c,'control_id':c['window_id'],'matched_event_id':e['setup_id'],
            'side':e['side'],'normalization_distance':str(distance),
            'normalization_target':str(target) if target else None,'outcomes':outcomes})
    # Retain every normalized pre-October bar so all indicators, range/stop/target
    # inventories, scan rejections and full paths can be rebuilt independently.
    for data in panel.symbols.values():
        for interval in LIMITS:
            for b in getattr(data,'candles_'+interval):
                used[bar_key(b)] = s03.source_bar(b)
    return events, controls, sorted(used.values(),key=lambda b:(b['symbol'],b['interval'],b['open_time']))


def cashflow(e, rows, scenario):
    """Conditional full-position SL/TP or 11h55 cashflow; never actual net_R."""
    if len(rows) < 143 or not e['targets'] or D(e['stop_distance']) <= 0:
        return {'status':'CENSORED_OR_INVALID','modeled_initial_risk_return':None}
    entry, stop, target = D(e['entry']), D(e['stop']), D(e['targets'][0]['price'])
    s, fee = sign_for(e['side']), D(scenario['fee_bps_per_side'])/10000
    reason, exit_price, chosen = 'TIME_11H55',rows[142].close,rows[142]
    for b in rows[:143]:
        if (b.low <= stop if s == 1 else b.high >= stop):
            exit_price = min(stop,b.open) if s == 1 else max(stop,b.open)
            reason,chosen = 'STOP_OR_SAME_BAR_STOP_FIRST',b
            break
        if (b.high >= target if s == 1 else b.low <= target):
            exit_price,reason,chosen = target,'TARGET',b
            break
    friction_funding = entry*(D(scenario['friction_bps_per_route'])+D(scenario['funding_bps']))/10000
    loss_budget = D(e['stop_distance'])+(entry+stop)*fee+friction_funding
    pnl = s*(exit_price-entry)-(entry+exit_price)*fee-friction_funding
    return {'status':'OHLC_CONDITIONAL_NOT_FILL_EVIDENCE','exit_reason':reason,
        'exit_source_key':bar_key(chosen),'exit_price':str(exit_price),'cashflow_per_base_unit':str(pnl),
        'initial_modeled_loss_per_unit':str(loss_budget),'modeled_initial_risk_return':str(pnl/loss_budget)}


def summarize_group(events, controls):
    result = old.group_summary(events,controls)
    ids={e['setup_id'] for e in events}
    intervals=[(dt(e['terminal_at']),min(dt(e['terminal_at'])+timedelta(hours=12),month_end(dt(e['terminal_at'])))) for e in events]
    intervals.extend((dt(c['event_time']),dt(c['event_time'])+timedelta(hours=12))
                     for c in controls if c['matched_event_id'] in ids)
    result['connected_market_time_components']=market_components(intervals)
    result['overlapping_case_control_window_pairs']=sum(a<d and c<b for i,(a,b) in enumerate(intervals) for c,d in intervals[i+1:])
    result['cashflow_scenarios'] = {name:distribution(e['modeled_cashflows'][name]['modeled_initial_risk_return']
                                                    for e in events) for name in SCENARIOS}
    result['cashflow_mean'] = {name:str(mean(values)) if (values:=[D(e['modeled_cashflows'][name]['modeled_initial_risk_return'])
        for e in events if e['modeled_cashflows'][name]['modeled_initial_risk_return'] is not None]) else None for name in SCENARIOS}
    result['cashflow_exit_reasons'] = dict(Counter(e['modeled_cashflows']['base'].get('exit_reason','CENSORED') for e in events))
    result['side_reversed_equal_day_close_bps'] = {}
    for h in (60,240,720):
        days = defaultdict(list)
        for e in events:
            r=e['outcomes'][str(h)]
            if r['complete']:
                days[e['terminal_at'][:10]].append(-D(r['signed_close_bps']))
        result['side_reversed_equal_day_close_bps'][str(h)] = str(mean(mean(v) for v in days.values())) if days else None
    result['joint_day_4h_sensitivity'] = bootstrap_sensitivity(result['horizons']['240']['paired']['day_means_bps'])
    return result


def bootstrap_sensitivity(day_means):
    import numpy as np
    values = np.asarray([float(v) for v in day_means.values()])
    if len(values)<2:
        return {'status':'INSUFFICIENT_DAYS','days':len(values),'interval':None}
    rng=np.random.default_rng(SEED)
    draws=values[rng.integers(0,len(values),(4000,len(values)))].mean(axis=1)
    return {'status':'DESCRIPTIVE_JOINT_EVENT_DAY_RESAMPLING_NOT_SELECTION_VALID_CI',
            'days':len(values),'resamples':4000,'percentiles_2_5_97_5':[float(x) for x in np.quantile(draws,[.025,.975])]}


def summarize(census, events, controls):
    result={}
    for month in ('2024-08','2024-09'):
        rows=[e for e in events if e['terminal_at'].startswith(month)]
        primary=[e for e in rows if not e['formation_vetoes']]
        base=[e for e in rows if is_base(e)]
        formed=[e for e in census['formations'] if e['formed_at'].startswith(month)]
        c={'policy_id':CONTRACT['policy_id'],'raw_formations':len(formed),
            'diagnostic_confirmations':len(rows),'confirmations':len(primary),
            'formation_states':dict(Counter(f['state'] for f in formed)),
            'formation_vetoes':dict(Counter(r for f in formed for r in f['formation_vetoes'])),
            'terminal_reasons':dict(Counter(f['terminal_reason'] for f in formed)),
            'geometry_rejections':dict(Counter(r for e in rows for r in e['geometry_rejections'])),
            'policy_vetoes':dict(Counter(r for e in rows for r in e['policy_vetoes'])),
            'scenarios':{name:sum(is_base(e,name) for e in rows) for name in SCENARIOS},
            'adverse_entry_survivors':{shift:sum(is_base(e) and e['adverse_geometry'][shift]
                and e['adverse_entry_sensitivity'][shift]['passes_with_route'] for e in rows) for shift in ('0','0.025','0.05')},
            'funding_stress_survivors':{bps:sum(is_base(e) and e['funding_stress'].get(bps,{}).get('passes_with_route',False)
                for e in rows) for bps in ('5','10')},
            'stop_slippage_stress_survivors':sum(is_base(e) and e['stop_slippage_stress']['passes_with_route'] for e in rows),
            'groups':{name:summarize_group(selected,controls) for name,selected in (
                ('all_diagnostic_confirmations',rows),('all_confirmations',primary),('base_survivors',base),
                ('rejected_confirmations',[e for e in rows if not is_base(e)]))},
            'ablations':{name:summarize_group([e for e in rows if is_base(e,ignored=ignored)],controls)
                         for name,ignored in ABLATIONS.items()},
            'ablation_added_cases':{name:summarize_group([e for e in rows if is_base(e,ignored=ignored)
                and not is_base(e)],controls) for name,ignored in ABLATIONS.items()},
            'volatility_quartiles':{str(q):summarize_group([e for e in base if min(3,int(D(e['atr_percentile'])//25))==q],controls)
                                   for q in range(4)},
            'portfolio':portfolio(base)}
        c['advancement_checks']=s03.gate_checks(c)
        h=c['groups']['base_survivors']['horizons']['720']
        rejected=(len(primary)>=20 and not base) or (h['complete']>=20 and D(h['target_before_stop_upper'])/h['complete']<=D('.20'))
        c['hard_reject']=rejected
        c['decision']='REJECT' if rejected else ('ADVANCE' if all(c['advancement_checks'].values()) else
            'REVISE' if h['complete']>9 and len(c['groups']['base_survivors']['symbols'])>=4
                and D(h['target_before_stop_lower'])/h['complete']>D(1)/9 else 'REJECT')
        c['control_balance']={field:distribution(D(e['confirmation_context'][source])-D(r[field])
            for e in base for r in controls if r['matched_event_id']==e['setup_id'])
            for field,source in (('adx','adx_1h'),('slope','normalized_slope'))}
        days=c['groups']['base_survivors']['horizons']['240']['paired']['day_means_bps']
        sigma=stdev(float(v) for v in days.values()) if len(days)>1 else None
        c['planning_power']={'status':'APPROXIMATE_PLANNING_ONLY_NOT_A_GATE_OR_GUARANTEE',
            'matched_4h_event_day_sd_bps':sigma,
            'required_independent_joint_days_by_true_effect_bps':{
                str(effect):max(30,__import__('math').ceil(((1.96+.84)*sigma/effect)**2)) if sigma is not None else None
                for effect in (10,20,40)},
            'observed_primary_confirmations_per_calendar_day':str(D(len(primary))/(31 if month=='2024-08' else 30)),
            'observed_base_cases_per_calendar_day':str(D(len(base))/(31 if month=='2024-08' else 30)),
            'minimum_calendar_days_for100_at_observed_base_rate':__import__('math').ceil(100*(31 if month=='2024-08' else 30)/len(base)) if base else None,
            'source_eligible_rate_known':False}
        examples={}
        for label,predicate in (
            ('first_base',lambda e:is_base(e)),('first_target',lambda e:is_base(e) and e['outcomes']['720']['full_ladder_lower']),
            ('first_loss',lambda e:is_base(e) and e['modeled_cashflows']['base'].get('modeled_initial_risk_return') is not None
             and D(e['modeled_cashflows']['base']['modeled_initial_risk_return'])<0),
            ('first_time_exit',lambda e:is_base(e) and e['modeled_cashflows']['base'].get('exit_reason')=='TIME_11H55'),
            ('first_rejected_confirmation',lambda e:not is_base(e)),
            ('first_ambiguity',lambda e:is_base(e) and e['outcomes']['720']['target2_order']['same_bar_ambiguous'])):
            examples[label]=next((e['setup_id'] for e in sorted(rows,key=lambda x:(x['terminal_at'],x['symbol'])) if predicate(e)),None)
        c['examples']=examples
        result[month]=c
    august=result['2024-08']['groups']['base_survivors']
    h=august['horizons']['720']
    contrasts=[august['horizons'][str(t)]['paired']['equal_day_difference_bps'] for t in (240,720)]
    contradiction=h['complete']>=20 and (D(h['target_before_stop_upper'])/h['complete']<=D('.20')
        or all(x is not None and D(x)<0 for x in contrasts))
    result['2024-09']['august_contradiction']=contradiction
    if contradiction and result['2024-09']['decision']=='ADVANCE':
        result['2024-09']['decision']='REVISE'
    return result


def portfolio(events):
    equity, pending, ledger, day, baseline = D(1),[],[],None,D(1)
    for e in sorted(events,key=lambda e:(e['terminal_at'],e['symbol'],e['setup_id'])):
        at=dt(e['terminal_at'])
        for p in list(pending):
            if p['release']<=at:
                equity+=p['pnl']; pending.remove(p)
        if day!=at.date():
            day,baseline=at.date(),equity
        cf=e['modeled_cashflows']['base']
        reason=None
        if cf['modeled_initial_risk_return'] is None: reason='CENSORED'
        elif len(pending)>=2: reason='TWO_SLOTS'
        elif any(p['symbol']==e['symbol'] for p in pending): reason='SYMBOL_RESERVED'
        elif equity<=baseline*D('.99'): reason='REALIZED_PROXY_DAILY_HALT'
        risk=min(equity*D('.0025'),max(D(0),equity*D('.005')-sum((p['risk'] for p in pending),D(0))))
        actualrisk,notional=D(0),D(0)
        if reason is None:
            available=max(D(0),2*equity-sum((p['notional'] for p in pending),D(0)))
            notional=min(risk/D(cf['initial_modeled_loss_per_unit'])*D(e['entry']),available)
            actualrisk=notional/D(e['entry'])*D(cf['initial_modeled_loss_per_unit'])
            if notional<=0: reason='AGGREGATE_RISK_OR_TWO_X_NOTIONAL'
            else: pending.append({'symbol':e['symbol'],'release':at+timedelta(hours=12),'notional':notional,
                                  'risk':actualrisk,'pnl':actualrisk*D(cf['modeled_initial_risk_return'])})
        ledger.append({'event_id':e['setup_id'],'status':reason or 'CONDITIONALLY_ALLOCATED',
                       'equity_before':str(equity),'modeled_risk':str(actualrisk),'entry_notional':str(notional),
                       'source_eligibility':False})
    for p in pending: equity+=p['pnl']
    return {'status':'OHLC_ONLY_FIXED_12H_RESERVATION_CAPACITY_DIAGNOSTIC',
        'counts':dict(Counter(r['status'] for r in ledger)),'conditional_terminal_equity_multiple':str(equity),
        'strict_eligible_allocations':0,'unrealized_daily_halt_and_tick_rounding_proven':False,'ledger':ledger}


def causal_fingerprint():
    sources={f.__name__:inspect.getsource(f) for f in (raw_terms,advance,geometry,scan,select_matches,is_base,
                                                     _scan_symbol,run_census)}
    for name in ('s01_economic_recovery.py','s03_strategy_research.py','c05_r0_market_economics.py',
                 'c05_t1_event_control.py'):
        sources[name]=sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
    return config_hash(sources)


def benchmarks(panel):
    """Recheck previous paths and source OHLC against the identical archives."""
    raw={bar_key(b):b for data in panel.symbols.values() for interval in LIMITS
         for b in getattr(data,'candles_'+interval)}
    result={}
    for label,name,predicate in (
        ('T1','../c05/C05_L_T1_EVENT_CONTROL_EVIDENCE.json.gz',lambda e:e['classification']=='FROZEN_BASE_SURVIVOR'),
        ('PC2','S01_EVIDENCE.json.gz',lambda e:e['candidate']=='PC2' and old.base_survivor(e)),
        ('PC3','S03_EVIDENCE.json.gz',lambda e:e['candidate']=='PC3' and s03.is_base(e))):
        packet,digest=old.checked_json(OUT/name,compressed=True)
        for r in packet['source_bars']:
            b=raw[r['source_key']]
            if any(D(r[k])!=getattr(b,k) for k in ('open','high','low','close')):
                raise ValueError('benchmark original OHLC mismatch')
        selected=[e for e in packet['events'] if predicate(e)]
        for e in packet['events']:
            at=dt(e['terminal_at']);b=panel.symbols[e['symbol']].candles_5m
            i=bisect_right(b,at,key=lambda x:x.available_at)
            if label=='T1':
                original=e['history']['structural_target']
                target=D(original['price']) if original else None
            else:
                target=D(e['targets'][-1]['price']) if e['targets'] else None
            rebuilt=price_path(b[i:i+144],at=at,reference=D(e['entry']),distance=D(e['stop_distance']),
                               side=e['side'],target2=target,end=END)
            if rebuilt!=e['outcomes']:raise ValueError('benchmark path reproduction mismatch')
        result[label]={'evidence_sha256':digest,'source_ohlc_rechecked':len(packet['source_bars']),
            'all_diagnostic_paths_reproduced':len(packet['events']),'base_n':len(selected),
            'complete12h':sum(e['outcomes']['720']['complete'] for e in selected),
            'target_first_lower':sum(e['outcomes']['720']['complete'] and e['outcomes']['720']['full_ladder_lower'] for e in selected),
            'stop_first':sum(e['outcomes']['720']['complete'] and e['outcomes']['720']['stop_touch'] is not None
                and (e['outcomes']['720']['structural_target_touch'] is None or
                e['outcomes']['720']['stop_touch']['bar_open']<e['outcomes']['720']['structural_target_touch']['bar_open']) for e in selected),
            'management_comparison':'PATH_TO_ORIGINAL_FINAL_TARGET_NOT_REPLACED_WITH_VT4_CASHFLOW'}
    return result


def render(packet):
    lines=['# S04 VT4 empirical development result','','Exploratory genuine OHLCV. No fills, C02 admission or independent profitability.',
        '',f"Census `{packet['census_sha256']}`; evidence `{packet['content_sha256']}`.",'',
        '| Month | Raw / diagnostic / primary | Base complete / days / symbols | Target / stop first | Exact pairs / days | Decision |',
        '|---|---:|---:|---:|---:|---|']
    for month,c in packet['months'].items():
        b=c['groups']['base_survivors'];h=b['horizons']['720'];p=h['paired']
        lines.append(f"| {month} | {c['raw_formations']}/{c['diagnostic_confirmations']}/{c['confirmations']} | {h['complete']}/{len(b['complete12h_market_days'])}/{len(b['complete12h_symbols'])} | {h['target_before_stop_lower']}/{h['stop_first']} | {p['pairs']}/{p['event_days']} | {c['decision']} |")
        lines += ['',f"## {month}",'',f"Scenarios optimistic/base/stress: {c['scenarios']}. Gate checks: `{json.dumps(c['advancement_checks'],sort_keys=True)}`.",'',
            '| Horizon | Paired equal-day bps | Delete-one-day range |','|---|---:|---|']
        for t in (60,240,720):
            p=b['horizons'][str(t)]['paired']
            lines.append(f"| {t}m | {p['equal_day_difference_bps']} | {p['leave_one_event_day_out_bps']} |")
        lines += ['',f"Modeled cashflow mean, ideal close reference (not actual net_R): `{b['cashflow_mean']}`.",
            f"Adverse entry survivors `{c['adverse_entry_survivors']}`; funding5/10bps `{c['funding_stress_survivors']}`; extra stop0.10R {c['stop_slippage_stress_survivors']}.",'',
            '| Arm | Complete | Target-first | 4h paired bps | Base cashflow mean |','|---|---:|---:|---:|---:|']
        for name,g in [('base',b),('rejected',c['groups']['rejected_confirmations']),*c['ablations'].items()]:
            h=g['horizons']['720']
            lines.append(f"| {name} | {h['complete']} | {h['target_before_stop_lower']} | {g['horizons']['240']['paired']['equal_day_difference_bps']} | {g['cashflow_mean']['base']} |")
    lines += ['','See S04_OWNER_DECISION.md and S04_SESSION05_CONTRACT.json for decision, source and implementation gates.','',
        '```sh','python scripts/s04_economic_rescue.py --data-root /workspace/work/c04-data --output-dir work/s04-reproduction','```']
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--census-only',action='store_true')
    parser.add_argument('--reuse-census',type=Path)
    parser.add_argument('--workers',type=int,choices=(1,2),default=1,
                        help='Two Linux fork workers independently scan symbols; deterministic merge')
    args=parser.parse_args()
    validate_inputs(); _memoize_numeric();args.output_dir.mkdir(parents=True,exist_ok=True)
    panel=load_public_um_archive_panel(ROOT/'research/c04/historical_manifest.json',args.data_root,source_end_exclusive=END)
    identity=config_hash({'partitions':list(panel.partitions)})
    binding={'schema_version':'s04.outcome-blind-census.v1','protocol_sha256':PROTOCOL_SHA,
        'contract_sha256':CONTRACT_SHA,'policy_version':VERSION,'source_identity_sha256':identity,
        'causal_implementation_sha256':causal_fingerprint()}
    if args.reuse_census:
        census,digest=old.checked_json(args.reuse_census,compressed=True)
        if any(census.get(k)!=v for k,v in binding.items()): raise ValueError('census binding mismatch')
    else:
        census={**binding,**run_census(panel,args.workers)}
        if len(census['pool'])!=122976: raise ValueError('incomplete two-month window census')
        census['matches']=select_matches(census['events'],census['pool']);digest=config_hash(census)
    write_gzip(args.output_dir/'S04_CAUSAL_CENSUS.json.gz',{**census,'content_sha256':digest})
    print('OUTCOME BLIND SEAL',digest,flush=True)
    if args.census_only:return
    events,controls,bars=paths(panel,census)
    months=summarize(census,events,controls)
    study_decision='REJECT' if any(c['hard_reject'] for c in months.values()) else months['2024-09']['decision']
    packet={'schema_version':'s04.exploratory-evidence.v1','census_sha256':digest,**binding,
        'preregistration_commit':'93adad5','source_manifest_sha256':MANIFEST_HASH,
        'source_partitions':list(panel.partitions),'verified_source_bars':len(bars),
        'october_outcomes_accessed':False,'strict_eligible_candidates':0,'economic_qualification':'INSUFFICIENT_EVIDENCE',
        'months':months,'study_decision':study_decision,'benchmarks':benchmarks(panel),
        'events':events,'controls':controls,'source_bars':bars,
        'dependencies':{name:importlib.metadata.version(name) for name in ('numpy','TA-Lib','pydantic')},
        'research_code_sha256':{str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__),ROOT/'scripts/s01_economic_recovery.py',ROOT/'scripts/s03_strategy_research.py',
             ROOT/'scripts/c05_r0_market_economics.py',ROOT/'scripts/c05_t1_event_control.py',
             *sorted((ROOT/'src/astrabot').rglob('*.py'))]}}
    packet['content_sha256']=config_hash(packet)
    write_gzip(args.output_dir/'S04_EVIDENCE.json.gz',packet)
    (args.output_dir/'S04_RESULTS.md').write_text(render(packet))
    print(json.dumps({'sha256':packet['content_sha256'],'months':{m:{k:c[k] for k in ('raw_formations','diagnostic_confirmations','confirmations','scenarios','decision')} for m,c in packet['months'].items()}},indent=2),flush=True)


if __name__=='__main__':main()
