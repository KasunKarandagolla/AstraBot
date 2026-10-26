"""September R0 price opportunity/cost census. No eligible trades or returns."""
from __future__ import annotations

import argparse
import csv
import io
from collections import Counter, defaultdict, OrderedDict
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import gzip
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from astrabot.contracts import scenario_net_rr
from astrabot.data.models import binance_usdm_instrument_id, config_hash, stable_id
from astrabot.data.historical_sources import verify_source
from astrabot.research import context as ctx, policies, levels
from astrabot.research.integrated import HISTORY_LIMITS
from astrabot.research.models import VERSIONS
from astrabot.research.replay import _panel_point_in_time, load_public_um_archive_panel

UTC = timezone.utc
START = datetime(2024, 9, 1, tzinfo=UTC)
END = datetime(2024, 10, 1, tzinfo=UTC)
SCENARIOS = {
    'optimistic': {'fee_bps_per_side': '2', 'friction_bps_per_route': '0', 'funding_bps': '0'},
    'base': {'fee_bps_per_side': '5', 'friction_bps_per_route': '2', 'funding_bps': '1'},
    'stress': {'fee_bps_per_side': '10', 'friction_bps_per_route': '5', 'funding_bps': '3'},
}


def _memoize_numeric():
    """Cache identical immutable bar inputs; call the original numeric functions."""
    def wrap(function, limit=4096):
        cache = OrderedDict()
        def cached(rows):
            if not rows:
                return function(rows)
            key = (rows[0].observation_id, rows[-1].observation_id, len(rows))
            if key not in cache:
                cache[key] = function(rows)
                if len(cache) > limit:
                    cache.popitem(last=False)
            return cache[key]
        return cached
    from functools import lru_cache
    ctx._arrays = wrap(ctx._arrays)
    ctx._decimal = lru_cache(maxsize=100000)(ctx._decimal)
    ctx._atr = wrap(ctx._atr)
    ctx._bias = wrap(ctx._bias)
    policies._atr = ctx._atr


def distribution(values):
    values = sorted(D(str(v)) for v in values if v is not None)
    if not values:
        return {'n': 0, 'min': None, 'p10': None, 'median': None, 'p90': None, 'max': None}
    from statistics import median
    return {'n': len(values), 'min': str(values[0]), 'p10': str(values[int((len(values)-1)*.1)]),
        'median': str(median(values)), 'p90': str(values[int((len(values)-1)*.9)]), 'max': str(values[-1])}


def funding_audit(root, symbols):
    """Describe original September funding records; never impute position cash flow."""
    result = {}
    for symbol in sorted(symbols):
        name = f'{symbol}-fundingRate-2024-09.zip'
        path = Path(root)/name
        digest = (Path(root)/(name+'.CHECKSUM')).read_text().split()[0]
        verify_source(path, digest)
        with zipfile.ZipFile(path) as archive:
            with archive.open(name.removesuffix('.zip')+'.csv') as source:
                reader = csv.DictReader(io.TextIOWrapper(source))
                if reader.fieldnames != ['calc_time', 'funding_interval_hours', 'last_funding_rate']:
                    raise ValueError('unexpected original funding columns')
                rows = [(int(r['calc_time']), D(r['last_funding_rate']), int(r['funding_interval_hours'])) for r in reader]
        if not rows or any(b[0] <= a[0] for a,b in zip(rows, rows[1:])):
            raise ValueError('funding records missing or nonchronological')
        left, current, maximum = 0, D(0), D(0)
        for right, (at, rate, _) in enumerate(rows):
            current += abs(rate)*10000
            while at-rows[left][0] >= 12*3600*1000:
                current -= abs(rows[left][1])*10000
                left += 1
            maximum = max(maximum, current)
        result[symbol] = {'url': f'https://data.binance.vision/data/futures/um/monthly/fundingRate/{symbol}/{name}',
            'sha256': digest, 'compressed_bytes': path.stat().st_size, 'rows': len(rows),
            'first_calc_time_ms': rows[0][0], 'last_calc_time_ms': rows[-1][0],
            'interval_hours': dict(Counter(str(r[2]) for r in rows)),
            'rate_bps': distribution(r[1]*10000 for r in rows),
            'negative_rates': sum(r[1]<0 for r in rows),
            'maximum_trailing_12h_absolute_rate_bps': str(maximum)}
    return {'schema_version': 'c05k.reported-funding-audit.v1', 'symbols': result,
        'interpretation': 'Ex-post reported calculation records; no prior entry awareness, mark notional or actual position payment is certified. Trailing12h uses (t-12h,t].',
        'model_comparison': 'Declared funding debit assumptions0/1/3bps are hypotheses, not guaranteed bounds.'}


def geometry(setup, data, at):
    """Original unrounded C03 geometry at a declared confirmation-close entry.

    Historical tick, quote/chase bounds, units and minimum quantities are absent;
    this is explicitly a conditional geometry screen, never build_decision admission.
    """
    bar = setup.confirmation_bar
    sign = D(1) if setup.snapshot.side == 'LONG' else D(-1)
    entry = bar.close
    extreme = setup.levels[0] if setup.strategy_id == 'T1' else setup.selected_extreme
    if extreme is None:
        return {'geometry_status': 'FROZEN_STOP_ANCHOR_MISSING'}
    stop = extreme.price-sign*D('.10')*setup.snapshot.frozen_atr
    distance = sign*(entry-stop)
    result = {'entry': str(entry), 'stop': str(stop), 'stop_distance': str(distance),
        'stop_fraction': str(distance/entry), 'stop_price_r': '1', 'confirmation_bar_id': bar.source_record_id,
        'confirmation_available_at': bar.available_at.isoformat(), 'stop_anchor_id': extreme.level_id}
    if stop <= 0:
        return {**result, 'geometry_status': 'STOP_PRICE_INVALID'}
    if distance <= 0:
        return {**result, 'geometry_status': 'STOP_WRONG_SIDE'}
    kind = 'SWING_HIGH' if sign == 1 else 'SWING_LOW'
    opposing = sorted((x for x in setup.opposing_at_formation if x.kind == kind and not x.invalidated
        and x.available_at <= setup.snapshot.available_at and sign*(x.price-entry) > 0),
        key=lambda x: (sign*(x.price-entry), x.available_at, x.level_id))
    if setup.strategy_id == 'T1':
        if not opposing:
            return {**result, 'geometry_status': 'PRECONFIRMED_OPPOSING_TARGET_MISSING'}
        targets = ((entry+sign*distance, D('.4')), (opposing[0].price, D('.6')))
    elif setup.strategy_id == 'R1':
        mid = next(x for x in setup.levels if x.kind == 'RANGE_MIDPOINT')
        far = next(x for x in setup.levels if x.kind == ('RANGE_HIGH' if sign == 1 else 'RANGE_LOW'))
        targets = ((mid.price, D('.5')), (far.price, D('.5')))
    else:
        targets = ((entry+sign*distance, D('.4')), (entry+sign*2*distance, D('.6')))
    if any(sign*(p-entry) <= 0 for p, _ in targets):
        return {**result, 'geometry_status': 'TARGET_WRONG_SIDE'}
    if sign*(targets[1][0]-targets[0][0]) <= 0:
        return {**result, 'geometry_status': 'TARGET_ORDER_INVALID'}
    inventory = levels.confirmed_swings(data.candles_1h, symbol=setup.snapshot.symbol,
        instrument_id=setup.instrument_id, as_of=at)
    obstacles = [x for x in inventory if x.kind == kind and not x.invalidated
        and any(D(0) < sign*(x.price-entry) < sign*(p-entry) for p, _ in targets)]
    gross = sum((f*sign*(p-entry)/distance for p, f in targets), D(0))
    budget = (gross-D('1.5'))/D('2.5')
    if setup.strategy_id == 'R1':
        budget = min(budget, (sign*(targets[0][0]-entry)/distance-D('1.5'))/D('2.5'))
    return {**result, 'geometry_status': 'SCREENABLE', 'targets': [{'price': str(p), 'fraction': str(f)} for p, f in targets],
        'gross_price_r': str(gross), 'symmetric_cost_budget_r': str(budget),
        'max_symmetric_round_trip_bps': str(budget*distance/entry*10000),
        'obstacle_count': len(obstacles), 'nearest_obstacle': str(min(obstacles,
            key=lambda x: sign*(x.price-entry)).price) if obstacles else None,
        'target_level_ids': [x.level_id for x in opposing[:1]] if setup.strategy_id == 'T1' else [],
        'route_feasible': not obstacles}


def cost_screen(row, scenario, *, entry_shift_r=D(0), stop_slippage_r=D(0)):
    entry, stop, distance = (D(row[k]) for k in ('entry', 'stop', 'stop_distance'))
    sign = D(1) if row['side'] == 'LONG' else D(-1)
    entry += sign*distance*entry_shift_r
    distance = sign*(entry-stop)
    fee = D(scenario['fee_bps_per_side'])/10000
    friction = entry*D(scenario['friction_bps_per_route'])/10000
    funding = entry*D(scenario['funding_bps'])/10000
    targets = [(D(t['price']), D(t['fraction'])) for t in row['targets']]
    win = entry*fee+sum((f*p*fee for p, f in targets), D(0))+friction+funding
    loss = entry*fee+stop*fee+friction+funding+D(row['stop_distance'])*stop_slippage_r
    gross = sum((f*sign*(p-entry)/distance for p, f in targets), D(0))
    rr = scenario_net_rr(gross, distance, win, loss)
    midpoint = None
    if row['policy'] == 'R1':
        mid_cost = entry*fee+targets[0][0]*fee+friction+funding
        midpoint = scenario_net_rr(sign*(targets[0][0]-entry)/distance, distance, mid_cost, loss)
    return {'cost_r': str(loss/distance), 'scenario_net_rr': str(rr),
        'midpoint_net_rr': str(midpoint) if midpoint is not None else None,
        'passes_cost_screen': rr >= D('1.5') and (midpoint is None or midpoint >= D('1.5')),
        'passes_with_route': bool(row['route_feasible']) and rr >= D('1.5')
            and (midpoint is None or midpoint >= D('1.5'))}


def scan(panel, start=START, end=END, symbols=None):
    formations, confirmations = [], []
    counters, rejects, regimes, daily, balance = Counter(), Counter(), Counter(), Counter(), Counter()
    for symbol in sorted(symbols or panel.symbols):
        active, seen = {}, set()
        times = [c.available_at for c in panel.symbols[symbol].candles_5m if start <= c.available_at < end]
        last_day = None
        for at in times:
            if at.date() != last_day:
                print(f'{symbol} {at.date()} windows={sum(v for k,v in counters.items() if k[0]==symbol and k[1]=="WINDOW")}', flush=True)
                last_day = at.date()
            data = _panel_point_in_time(panel, symbol, at, HISTORY_LIMITS)
            context = ctx.evaluate_context(data, symbol=symbol, instrument_id=binance_usdm_instrument_id(symbol), as_of=at)
            counters[symbol, 'WINDOW'] += 1
            regimes[symbol, context.classification] += 1
            if context.balance:
                balance.update(context.balance.reason_codes)
            for policy in VERSIONS:
                for side in ('LONG', 'SHORT'):
                    key = (policy, side)
                    setup = active.get(key)
                    if setup is None:
                        setup, reasons = policies.form_setup(policy, data, context, side,
                            stable_id('c05k.price.v1', symbol, at))
                        if setup is None:
                            rejects[symbol, policy, context.classification, '|'.join(reasons)] += 1
                            continue
                        if setup.snapshot.setup_id in seen:
                            rejects[symbol, policy, context.classification, 'SETUP_EVENT_ALREADY_RECORDED'] += 1
                            continue
                        seen.add(setup.snapshot.setup_id)
                        active[key] = setup
                        counters[symbol, policy, 'FORMED'] += 1
                        daily[at.date().isoformat(), policy, 'FORMED'] += 1
                        formations.append({'setup_id': setup.snapshot.setup_id, 'symbol': symbol,
                            'policy': policy, 'side': side, 'formed_at': at.isoformat(),
                            'regime': context.classification, 'atr_percentile': str(context.atr_percentile),
                            'state': 'ARMED', 'terminal_at': None, 'reason': None})
                        continue
                    advanced = policies.advance_setup(setup, data, context)
                    active[key] = advanced
                    state = advanced.snapshot.state
                    if state in policies.TERMINAL or state == 'CONFIRMED':
                        counters[symbol, policy, state] += 1
                        daily[at.date().isoformat(), policy, state] += 1
                        record = next(r for r in reversed(formations) if r['setup_id'] == advanced.snapshot.setup_id)
                        record.update(state=state, terminal_at=at.isoformat(),
                            reason=(advanced.notes[-1] if advanced.notes else state))
                        if state == 'CONFIRMED':
                            row = {**record, 'confirmation_regime': context.classification,
                                'confirmation_atr_percentile': str(context.atr_percentile),
                                'known_context_veto': context.classification == 'EXTREME_VOLATILITY',
                                **geometry(advanced, data, at)}
                            if row['geometry_status'] == 'SCREENABLE':
                                row['scenarios'] = {name: cost_screen(row, s) for name, s in SCENARIOS.items()}
                                row['adverse_entry_sensitivity'] = {str(x): cost_screen(row, SCENARIOS['base'], entry_shift_r=x)
                                    for x in (D(0), D('.025'), D('.05'))}
                                row['stop_slippage_sensitivity'] = {str(x): cost_screen(row, SCENARIOS['base'], stop_slippage_r=x)
                                    for x in (D(0), D('.10'), D('.25'))}
                            confirmations.append(row)
                        active.pop(key)
        for setup in active.values():
            counters[symbol, setup.strategy_id, 'CENSORED_AT_END'] += 1
    def groups(counter):
        return [{'group': list(k) if isinstance(k, tuple) else [k], 'count': v} for k, v in sorted(counter.items())]
    by_policy = {}
    for policy in VERSIONS:
        rows = [r for r in confirmations if r['policy'] == policy]
        screenable = [r for r in rows if r['geometry_status'] == 'SCREENABLE']
        by_policy[policy] = {
            'formations': sum(r['policy'] == policy for r in formations), 'confirmations': len(rows),
            'states': dict(Counter(r['state'] for r in formations if r['policy'] == policy)),
            'geometry_reasons': dict(Counter(r['geometry_status'] for r in rows)),
            'screenable': len(screenable), 'route_feasible': sum(r['route_feasible'] for r in screenable),
            'stop_fraction': distribution(r.get('stop_fraction') for r in rows),
            'symmetric_budget_bps': distribution(r['max_symmetric_round_trip_bps'] for r in screenable),
            'gross_price_r': distribution(r['gross_price_r'] for r in screenable),
            'formation_days': len({r['formed_at'][:10] for r in formations if r['policy'] == policy}),
            'confirmation_days': len({r['terminal_at'][:10] for r in rows}),
            'scenarios': {name: {'confirmed_denominator': len(rows), 'geometry_denominator': len(screenable),
                'cost_pass': sum(r['scenarios'][name]['passes_cost_screen'] for r in screenable),
                'cost_and_route_pass': sum(r['scenarios'][name]['passes_with_route'] for r in screenable),
                'cost_route_context_pass': sum(r['scenarios'][name]['passes_with_route'] and not r['known_context_veto'] for r in screenable),
                'cost_r': distribution(r['scenarios'][name]['cost_r'] for r in screenable)} for name in SCENARIOS}}
    return {'by_policy': by_policy, 'counts': groups(counters), 'context_counts': groups(regimes),
        'price_rejections': groups(rejects), 'balance_reasons': dict(balance), 'daily_counts': groups(daily),
        'formations': formations, 'confirmations': confirmations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=os.environ.get('ASTRABOT_DATA_ROOT'))
    parser.add_argument('--manifest', type=Path, default=ROOT/'research/c04/historical_manifest.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'research/c05')
    parser.add_argument('--end', default=END.isoformat(), help='Bounded development cutoff, never later than Oct1')
    parser.add_argument('--symbols', nargs='+', default=None)
    parser.add_argument('--no-cache', action='store_true', help='Reference path using uncached original numeric functions')
    parser.add_argument('--funding-root', type=Path, help='optional local original September funding ZIPs and venue CHECKSUM files')
    args = parser.parse_args()
    end = datetime.fromisoformat(args.end.replace('Z', '+00:00'))
    if end.utcoffset() != timedelta(0) or not START < end <= END:
        parser.error('study cutoff must be UTC within September development window')
    if not args.data_root:
        parser.error('--data-root or ASTRABOT_DATA_ROOT is required')
    panel = load_public_um_archive_panel(args.manifest, args.data_root)
    if args.symbols and not set(args.symbols) <= set(panel.symbols):
        parser.error('unknown cohort symbol')
    if not args.no_cache:
        _memoize_numeric()
    result = scan(panel, end=end, symbols=args.symbols)
    packet = {'schema_version': 'c05k.r0-census.v1', 'evidence_class': 'INELIGIBLE_PRICE_DIAGNOSTICS',
        'source_manifest_sha256': panel.source_manifest['archive_manifest_sha256'],
        'source_rows_verified': sum(p['normalized_row_count'] for p in panel.partitions),
        'start_inclusive': START.isoformat(), 'end_exclusive': end.isoformat(),
        'symbols': sorted(args.symbols or panel.symbols), 'policy_versions': VERSIONS,
        'history_limits': HISTORY_LIMITS, 'scenarios': SCENARIOS,
        'strict_eligible_trades': 0, 'historical_profit_statistics': None,
        'entry_model': 'Unrounded confirmation close; post-confirmation quote, ticks, chase and quantities unverified',
        'delay_model': '0/5 seconds assume no move; 15/60 seconds exceed frozen10-second deadline. No intrabar prices inferred.',
        'funding_model': 'Declared non-negative max-hold debit in bps, not observed settlements',
        **result}
    packet['content_sha256'] = config_hash(packet)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir/'C05_K_R0_CENSUS.json.gz').open('wb') as out:
        with gzip.GzipFile(fileobj=out, filename='', mode='wb', mtime=0) as compressed:
            compressed.write((json.dumps(packet, sort_keys=True, indent=2)+'\n').encode())
    summary = {k:v for k,v in packet.items() if k not in ('formations', 'confirmations')}
    (args.output_dir/'C05_K_R0_SUMMARY.json').write_text(json.dumps(summary, sort_keys=True, indent=2)+'\n')
    if args.funding_root:
        funding = funding_audit(args.funding_root, args.symbols or panel.symbols)
        (args.output_dir/'C05_K_FUNDING_AUDIT.json').write_text(json.dumps(funding, sort_keys=True, indent=2)+'\n')
    print(json.dumps({'content_sha256': packet['content_sha256'], 'by_policy': packet['by_policy']}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
