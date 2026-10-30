"""Independent causal/timing/cost adversaries. Fixtures are synthetic mechanics only."""
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace as N

import pytest

from scripts import s04_economic_rescue as s
from test_s01_economic_recovery import bar, context


def setup(**updates):
    return {'state':'ARMED','side':'LONG','formed_at':s.START.isoformat(),
        'edge':'100','atr1_prebreak':'1','stop':'99','candidate':'VT4',
        'entry_cap':'100.5','formation_vetoes':[],
        'target':{'price':'103'},'target_touched_at_formation':False,**updates}


def test_distinct_acceptance_cannot_resurrect_or_ignore_stop_or_gap():
    x=setup();at=s.START+timedelta(minutes=5)
    assert s.advance(x,bar(at,low='98',close='101'))==('INVALIDATED','STOP_BEFORE_ENTRY')
    assert s.advance(x,bar(at,low='99.5',close='100.05'))[0]=='CONFIRMED'
    assert s.advance(x,bar(at,low='99.5',close='100.04'))[0]=='EXPIRED'
    assert s.advance(x,bar(at+timedelta(minutes=5)))[1]=='MISSING_NEXT_CANDLE'
    with pytest.raises(ValueError,match='distinct'):
        s.advance(x,bar(s.START))
    with pytest.raises(ValueError):
        s.advance(setup(state='EXPIRED'),bar(at))


def test_range_excludes_breakout_and_atr_excludes_breakout_hour(monkeypatch):
    at=s.START+timedelta(hours=8)
    prior=[]
    for i in range(25):
        b=bar(at-timedelta(minutes=15*(24-i)),high='100',low='98',close='99')
        b.interval='15m';b.open_time=b.available_at-timedelta(minutes=15)
        prior.append(b)
    prior[-1].close=D('100.2');prior[-1].high=D('101');prior[-1].open=D('99.8')
    hours=tuple(bar(at-timedelta(hours=30-i)) for i in range(31))
    received=[]
    def atr(rows):
        received.append(tuple(rows));return D(1)
    monkeypatch.setattr(s.ctx,'_atr',atr)
    data=N(candles_15m=tuple(prior),candles_1h=hours)
    terms,error=s.raw_terms(data,context(rvol_15m=D('2')),at)
    assert error is None and terms['high']=='100' and terms['width']=='2'
    assert all(b.available_at<=prior[-1].open_time for b in received[-1])
    # A future available hour in the supplied container cannot alter ATR inputs.
    data.candles_1h=hours+(bar(at+timedelta(hours=1),high='9999'),)
    assert s.raw_terms(data,context(rvol_15m=D('2')),at)[0]==terms
    assert terms['stop']=='97.75' and terms['projection']=='104'
    assert len(terms['source_keys'])==24 and len(terms['stop_source_keys'])==12


def test_entry_chase_and_already_touched_target_are_not_retroactive_wins():
    x=setup()
    assert 'ENTRY_CAP_FAILED' in s.geometry(x,bar(s.START,close='100.6'),[],context())['policy_vetoes']
    r=s.geometry(x,bar(s.START,high='103',close='100'),[],context())
    assert 'TARGET_ALREADY_TOUCHED' in r['policy_vetoes'] and not s.is_base(r)
    x['target_touched_at_formation']=True
    assert 'TARGET_ALREADY_TOUCHED' in s.geometry(x,bar(s.START,close='100'),[],context())['policy_vetoes']


@pytest.mark.parametrize('side',['LONG','SHORT'])
def test_cashflow_stop_first_gap_and_actual_fee_notionals(side):
    long=side=='LONG'
    e={'entry':'100','stop':'99' if long else '101','stop_distance':'1','side':side,
       'targets':[{'price':'103' if long else '97','fraction':'1'}]}
    rows=[bar(s.START+timedelta(minutes=5*(i+1)),opened='100',high='104',low='96') for i in range(144)]
    rows[0].open=D('98' if long else '102')
    r=s.cashflow(e,rows,s.SCENARIOS['base'])
    assert r['exit_reason']=='STOP_OR_SAME_BAR_STOP_FIRST' and r['exit_price']==str(rows[0].open)
    expected_pnl=D(-2)-(D(100)+rows[0].open)*D('.0005')-D('.03')
    expected_risk=D(1)+(D(100)+D(e['stop']))*D('.0005')+D('.03')
    assert D(r['modeled_initial_risk_return'])==expected_pnl/expected_risk
    assert s.cashflow(e,rows[:142],s.SCENARIOS['base'])['modeled_initial_risk_return'] is None


def test_time_exit_is_11h55_not_last_available_12h_close():
    e={'entry':'100','stop':'99','stop_distance':'1','side':'LONG','targets':[{'price':'103','fraction':'1'}]}
    rows=[bar(s.START+timedelta(minutes=5*(i+1)),high='101',low='99.5',close='100.2') for i in range(144)]
    rows[-1].close=D('500')
    r=s.cashflow(e,rows,s.SCENARIOS['base'])
    assert r['exit_reason']=='TIME_11H55' and r['exit_source_key']==s.bar_key(rows[142])


def test_matching_is_past_only_same_month_and_outcome_blind():
    at=s.START+timedelta(days=4,hours=1)
    e={'setup_id':'E','candidate':'VT4','symbol':'SYNTHETIC','side':'LONG','terminal_at':at.isoformat(),
       'regime':'UNCLASSIFIED','bias':'BULLISH','atr_percentile':'40'}
    def pool(key,when,**updates):
        return {**e,'window_id':key,'event_time':when.isoformat(),'eligible_nontrigger':True,**updates}
    rows=[pool('PAST',at-timedelta(days=1)),pool('FUTURE',at+timedelta(days=1)),
          pool('JULY',s.START-timedelta(hours=1)),pool('BIAS',at-timedelta(days=1),bias='NEUTRAL'),
          pool('COOLDOWN',at-timedelta(days=1),eligible_nontrigger=False)]
    first=s.select_matches([e],rows)
    assert first[0]['control_id']=='PAST' and first[0]['candidate_count']==1
    for r in rows:r['future_return']='99999'
    assert s.select_matches([e],rows)==first


def test_filters_are_nested_masks_and_cannot_remove_geometry():
    e={'policy_vetoes':['COMPRESSION_FAILED'],'geometry_status':'SCREENABLE',
       'scenarios':{'base':{'passes_with_route':True}}}
    assert not s.is_base(e) and s.is_base(e,ignored={'COMPRESSION_FAILED'})
    e['geometry_status']='STOP_WIDER_THAN_TWO_PERCENT'
    assert not s.is_base(e,ignored=set(s.FILTERS))


def test_month_purge_and_frozen_protocol():
    assert s.month_end(s.START)==s.dt('2024-09-01T00:00:00Z')
    assert s.month_end(s.dt('2024-09-30T23:55:00Z'))==s.END
    s.validate_inputs()
