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


def test_exhausted_projection_preserves_missing_target_rejection_and_shadow_path():
    r=s.geometry(setup(target=None),bar(s.START,close='100'),[],context())
    assert r['targets']==[] and 'NO_FORMATION_TARGET' in r['geometry_rejections']
    assert not s.is_base(r) and not any(r['adverse_geometry'].values())


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


def evidence():
    return _evidence()


@__import__('functools').lru_cache(maxsize=1)
def _evidence():
    packet,digest=s.old.checked_json(s.OUT/'S04_EVIDENCE.json.gz',compressed=True)
    census,seal=s.old.checked_json(s.OUT/'S04_CAUSAL_CENSUS.json.gz',compressed=True)
    assert packet['census_sha256']==seal
    return packet,census


def test_original_evidence_and_preregistration_code_bindings():
    from hashlib import sha256
    packet,census=evidence()
    assert packet['verified_source_bars']==266616 and len(packet['source_partitions'])==84
    assert len(census['pool'])==122976
    assert packet['strict_eligible_candidates']==0 and packet['october_outcomes_accessed'] is False
    assert packet['protocol_sha256']==s.PROTOCOL_SHA and packet['policy_version']==s.VERSION
    assert all(r['coverage_start']<'2024-10' for r in packet['source_partitions'])
    for path,digest in packet['research_code_sha256'].items():
        assert sha256((s.ROOT/path).read_bytes()).hexdigest()==digest
    assert packet['benchmarks']['T1']['target_first_lower']==0
    assert packet['benchmarks']['PC2']['target_first_lower']==1
    assert packet['benchmarks']['PC3']['target_first_lower']==1


def test_all_original_formation_ranges_stops_and_atr_availability():
    packet,census=evidence()
    bars={r['source_key']:r for r in packet['source_bars']}
    for f in census['formations']:
        if f['target'] is None:continue
        q=bars[f['formation_source_key']]
        prior=[bars[k] for k in f['source_keys']]
        assert len(prior)==24
        assert all(s.dt(b['available_at'])<=s.dt(q['open_time']) for b in prior)
        assert D(f['high'])==max(D(b['high']) for b in prior)
        assert D(f['low'])==min(D(b['low']) for b in prior)
        sgn=D(1) if f['side']=='LONG' else D(-1)
        assert sgn*(D(q['close'])-D(f['edge']))>0
        stoprows=[bars[k] for k in f['stop_source_keys']]
        anchor=min(D(b['low']) for b in stoprows) if sgn==1 else max(D(b['high']) for b in stoprows)
        assert D(f['stop'])==anchor-sgn*D('.25')*D(f['atr1_prebreak'])
        span=f['prebreak_atr_span']
        assert s.dt(bars[span['last']]['available_at'])<=s.dt(q['open_time'])
        assert f['target']['available_at']<=f['formed_at']
        if f['transitions']:
            assert s.dt(f['transitions'][0]['at'])==s.dt(f['formed_at'])+timedelta(minutes=5)


def test_all_original_paths_and_cashflows_by_independent_touch_arithmetic():
    packet,_=evidence()
    bars={r['source_key']:r for r in packet['source_bars']}
    for e in packet['events']:
        h=e['outcomes']['720'];rows=[bars[k] for k in h['source_keys']]
        assert all(s.dt(b['open_time'])<s.month_end(s.dt(e['terminal_at'])) for b in rows)
        sgn=D(1) if e['side']=='LONG' else D(-1)
        stop=D(e['stop'])
        target=D(e['targets'][0]['price']) if e['targets'] else None
        si=next((i for i,b in enumerate(rows) if (D(b['low'])<=stop if sgn==1 else D(b['high'])>=stop)),None)
        ti=next((i for i,b in enumerate(rows) if target is not None and (D(b['high'])>=target if sgn==1 else D(b['low'])<=target)),None)
        assert h['full_ladder_lower']==(h['ordered_ladder'] and ti is not None and (si is None or ti<si))
        if len(rows)<143 or target is None or sgn*(target-D(e['entry']))<=0:continue
        k=142;exit_price=D(rows[k]['close'])
        for i,b in enumerate(rows[:143]):
            if (D(b['low'])<=stop if sgn==1 else D(b['high'])>=stop):
                k=i;exit_price=min(stop,D(b['open'])) if sgn==1 else max(stop,D(b['open']));break
            if (D(b['high'])>=target if sgn==1 else D(b['low'])<=target):
                k=i;exit_price=target;break
        for name,terms in s.SCENARIOS.items():
            c=e['modeled_cashflows'][name];entry=D(e['entry'])
            fee=D(terms['fee_bps_per_side'])/10000
            other=entry*(D(terms['friction_bps_per_route'])+D(terms['funding_bps']))/10000
            risk=D(e['stop_distance'])+(entry+stop)*fee+other
            pnl=sgn*(exit_price-entry)-(entry+exit_price)*fee-other
            assert c['exit_source_key']==rows[k]['source_key']
            assert D(c['modeled_initial_risk_return'])==pnl/risk


def test_every_control_has_exact_past_covariates_and_never_crosses_month():
    packet,census=evidence()
    pool={r['window_id']:r for r in census['pool']}
    events={e['setup_id']:e for e in packet['events']}
    for link in census['matches']:
        if link['control_id'] is None:continue
        e,c=events[link['event_id']],pool[link['control_id']]
        assert c['eligible_nontrigger'] and not c['exclusions']
        assert c['symbol']==e['symbol'] and c['bias']==e['bias'] and c['regime']==e['regime']
        assert int(D(c['atr_percentile'])//25)==int(D(e['atr_percentile'])//25)
        at,ct=s.dt(e['terminal_at']),s.dt(c['event_time'])
        assert at-timedelta(days=7)<=ct<=at-timedelta(hours=12)
        assert at.month==ct.month and at.hour//4==ct.hour//4
        assert ct+timedelta(hours=12)<=s.month_end(ct)
    for c in packet['months'].values():
        assert c['decision']!='ADVANCE' or all(c['advancement_checks'].values())


def test_supplement_matches_lagged_context_without_future_return_selection():
    from scripts import s04_control_support as supplement
    at=s.START+timedelta(days=4,hours=1)
    e={'setup_id':'E','symbol':'SYNTHETIC','side':'LONG','terminal_at':at.isoformat()}
    def row(key,when,eligible=False,regime='TREND_UP'):
        return {'window_id':key,'symbol':'SYNTHETIC','event_time':when.isoformat(),
                'eligible_nontrigger':eligible,'regime':regime,'bias':'BULLISH','atr_percentile':'40'}
    control=at-timedelta(days=1)
    pool=[row('CASE_LAG',at-timedelta(minutes=20)),
          row('CONTROL_LAG',control-timedelta(minutes=20)),row('CONTROL',control,True,'RANGE')]
    before=supplement.select_matches({'events':[e],'pool':pool})
    assert before[0]['control_id']=='CONTROL'
    # The current control can have a different post-treatment regime; matching
    # binds only the predeclared pre-entry covariates and never future returns.
    for r in pool:r['future_return']='9999'
    assert before==supplement.select_matches({'events':[e],'pool':pool})


def test_supplement_and_session05_never_override_original_rejection():
    import json
    from hashlib import sha256
    packet,_=evidence()
    supplement,digest=s.old.checked_json(s.OUT/'S04_CONTROL_SUPPORT.json.gz',compressed=True)
    assert supplement['original_decision_unchanged']==packet['study_decision']=='REJECT'
    assert supplement['promotion_authority'] is False
    assert supplement['primary_evidence_sha256']==s.old.checked_json(s.OUT/'S04_EVIDENCE.json.gz',compressed=True)[1]
    assert supplement['implementation_sha256']==sha256((s.ROOT/'scripts/s04_control_support.py').read_bytes()).hexdigest()
    contract=json.loads((s.OUT/'S04_SESSION05_CONTRACT.json').read_text())
    assert contract['default_action']=='HOLD_NO_POLICY_INTEGRATION' and contract['approved_policy_ids']==[]
    for item in contract['frozen_inputs'].values():
        assert sha256((s.ROOT/item['path']).read_bytes()).hexdigest()==item['file_sha256']
