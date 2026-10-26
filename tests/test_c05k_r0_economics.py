"""Protect frozen geometry, cost identities and the research-only speed path."""
from datetime import timedelta
from decimal import Decimal as D

import pytest

from scripts import c05_r0_market_economics as r0
from astrabot.contracts import FixedGeometry, Target
from astrabot.research.demo import START, IID, SYMBOL, account, market, candle
from astrabot.research.economics import evaluate_economics
from astrabot.research.models import CostProfile
from test_c03_policies import t1_case, r1_case, b1_complete


@pytest.mark.parametrize('policy', ['T1', 'R1', 'B1'])
def test_diagnostic_geometry_preserves_original_policy_targets(policy):
    if policy == 'T1':
        _, _, data, at, result = t1_case()
    elif policy == 'R1':
        _, _, _, _, data, at, result = r1_case()
    else:
        _, _, data, at, result = b1_complete()
    setup = result.state.setups[0]
    row = r0.geometry(setup, data, at)
    assert row['geometry_status'] == 'SCREENABLE'
    targets = row['targets']
    if policy == 'T1':
        assert [t['fraction'] for t in targets] == ['0.4', '0.6']
        assert D(targets[1]['price']) in {x.price for x in setup.opposing_at_formation}
    elif policy == 'R1':
        assert [t['fraction'] for t in targets] == ['0.5', '0.5']
        assert [D(t['price']) for t in targets] == [next(x.price for x in setup.levels if x.kind == kind)
            for kind in ('RANGE_MIDPOINT', 'RANGE_HIGH')]
    else:
        assert abs(D(row['gross_price_r'])-D('1.6')) < D('1e-20')
        assert abs(D(row['symmetric_cost_budget_r'])-D('.04')) < D('1e-20')


def test_fee_route_screen_matches_existing_economics_and_midpoint_veto():
    row = {'side': 'LONG', 'policy': 'B1', 'entry': '100', 'stop': '99', 'stop_distance': '1',
        'targets': [{'price': '101', 'fraction': '.4'}, {'price': '102', 'fraction': '.6'}],
        'route_feasible': True}
    scenario = r0.SCENARIOS['base']
    actual = r0.cost_screen(row, scenario)
    profile = CostProfile(version='SYNTHETIC_R0_COMPARISON', evidence_ids=('SYNTHETIC_ONLY',),
        entry_fee_rate='.0005', ordinary_exit_fee_rate='.0005', stop_exit_fee_rate='.0005',
        ordinary_exit_spread_per_unit='.02', ordinary_exit_slippage_per_unit='0',
        stop_spread_per_unit='.02', stop_slippage_per_unit='0', funding_per_unit='.01')
    at = START+timedelta(seconds=5)
    econ, _ = evaluate_economics(side='LONG', entry=D(100),
        geometry=FixedGeometry(original_stop='99', targets=(Target(price='101', fraction='.4'), Target(price='102', fraction='.6'))),
        profile=profile, metadata=market(at).metadata, account=account(at), requested_quantity=D(10))
    assert D(actual['scenario_net_rr']) == econ.scenario_net_rr
    assert D(actual['cost_r']) == econ.cost_r
    row.update(policy='R1', targets=[{'price': '100.9', 'fraction': '.5'}, {'price': '104', 'fraction': '.5'}])
    zero = {'fee_bps_per_side': '0', 'friction_bps_per_route': '0', 'funding_bps': '0'}
    result = r0.cost_screen(row, zero)
    assert D(result['scenario_net_rr']) > D('1.5')
    assert D(result['midpoint_net_rr']) < D('1.5')
    assert not result['passes_cost_screen']


def test_numeric_memoization_keeps_frozen_context_identical(monkeypatch):
    from astrabot.research import context, policies
    at = START+timedelta(seconds=5)
    data = market(at)
    original = context.evaluate_context(data, symbol=SYMBOL, instrument_id=IID, as_of=at)
    later_at = at+timedelta(seconds=1)
    later_original = context.evaluate_context(data, symbol=SYMBOL, instrument_id=IID, as_of=later_at)
    originals = [(context, name, getattr(context, name)) for name in ('_arrays', '_decimal', '_atr', '_bias')]
    originals.append((policies, '_atr', policies._atr))
    for module, name, value in originals:
        monkeypatch.setattr(module, name, value)
    r0._memoize_numeric()
    cached = context.evaluate_context(data, symbol=SYMBOL, instrument_id=IID, as_of=at)
    assert cached.model_dump_json() == original.model_dump_json()
    assert context.evaluate_context(data, symbol=SYMBOL, instrument_id=IID,
        as_of=later_at).model_dump_json() == later_original.model_dump_json()
    future = candle(START+timedelta(minutes=5)).model_copy(update={'readiness': 'UNAVAILABLE'})
    extended = data.model_copy(update={'candles_5m': (*data.candles_5m, future)})
    assert context.evaluate_context(extended, symbol=SYMBOL, instrument_id=IID,
        as_of=later_at).model_dump_json() == later_original.model_dump_json()


def test_funding_audit_preserves_native_clocks_and_does_not_net_unknown_exposure(tmp_path):
    import hashlib
    import zipfile
    name = 'SOLUSDT-fundingRate-2024-09.zip'
    path = tmp_path/name
    with zipfile.ZipFile(path, 'w') as out:
        out.writestr(name.removesuffix('.zip')+'.csv',
            'calc_time,funding_interval_hours,last_funding_rate\n'
            '1725148800000,8,0.0001\n1725177600001,8,-0.00015\n')
    (tmp_path/(name+'.CHECKSUM')).write_text(hashlib.sha256(path.read_bytes()).hexdigest()+' '+name)
    record = r0.funding_audit(tmp_path, ['SOLUSDT'])['symbols']['SOLUSDT']
    assert record['last_calc_time_ms'] == 1725177600001
    assert record['negative_rates'] == 1
    assert record['maximum_trailing_12h_absolute_rate_bps'] == '2.50000'
