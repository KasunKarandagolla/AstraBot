"""Analyst-blind preregistered lag-context sensitivity. Cannot advance a policy."""
from bisect import bisect_right
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal as D
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace as N
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import s04_economic_rescue as s
from astrabot.research.statistics import matched_controls


def select_matches(census):
    lag={(r['symbol'],r['event_time']):r for r in census['pool']}
    def key(row,at,side):
        previous=lag.get((row['symbol'],(at-timedelta(minutes=20)).isoformat()))
        if previous is None or previous['event_time'][:7]!=at.strftime('%Y-%m'):
            return None
        if previous['bias']==('BEARISH' if side=='LONG' else 'BULLISH'):
            return None
        if previous['atr_percentile']=='None':return None
        return (row['symbol'],side,previous['regime'],previous['bias'],
                min(3,int(D(previous['atr_percentile'])//25)),at.hour//4,at.strftime('%Y-%m'))
    index=defaultdict(list)
    for r in census['pool']:
        if r['eligible_nontrigger']:
            for side in ('LONG','SHORT'):
                k=key(r,s.dt(r['event_time']),side)
                if k is not None:index[k].append(r)
    result=[]
    for e in census['events']:
        at=s.dt(e['terminal_at']);k=key(e,at,e['side'])
        candidates=[r for r in index[k] if at-timedelta(days=7)<=s.dt(r['event_time'])<=at-timedelta(hours=12)] if k else []
        label='|'.join(map(str,k)) if k else 'MISSING_OR_DISALLOWED_LAG'
        trigger={'window_id':e['setup_id'],'symbol':e['symbol'],'event_time':e['terminal_at'],
                 'regime':label,'cohort':label,'is_trigger':True}
        rows=[{**r,'regime':label,'cohort':label,'is_trigger':False} for r in candidates]
        chosen=matched_controls([trigger,*rows],seed=s.SEED,embargo_hours=12).get(e['setup_id'])
        result.append({'event_id':e['setup_id'],'control_id':chosen,'cohort':k,'candidate_count':len(candidates),
                       'candidate_ids_sha256':s.config_hash({'ids':sorted(r['window_id'] for r in candidates)})})
    return result


def run():
    protocol=s.OUT/'S04_CONTROL_SUPPORT_PREREGISTRATION.md'
    if sha256(protocol.read_bytes()).hexdigest()!='89e207ff5aa8b4ed87f1aba5a631c13068807dc23b9691cd6bdece99ceb74668':
        raise ValueError('supplement preregistration changed')
    census,seal=s.old.checked_json(s.OUT/'S04_CAUSAL_CENSUS.json.gz',compressed=True)
    matches=select_matches(census)
    binding={'schema_version':'s04.lag-context-supplement.v1','census_sha256':seal,
             'protocol_sha256':sha256(protocol.read_bytes()).hexdigest(),
             'implementation_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    match_packet={**binding,'matches':matches,'promotion_authority':False}
    match_packet['content_sha256']=s.config_hash(match_packet)
    s.write_gzip(s.OUT/'S04_SUPPLEMENT_MATCHES.json.gz',match_packet)
    print('SUPPLEMENT OUTCOME BLIND MATCH SEAL',match_packet['content_sha256'],flush=True)
    packet,digest=s.old.checked_json(s.OUT/'S04_EVIDENCE.json.gz',compressed=True)
    source={r['source_key']:r for r in packet['source_bars']}
    streams=defaultdict(list)
    for r in packet['source_bars']:
        if r['interval']=='5m':
            streams[r['symbol']].append(N(symbol=r['symbol'],interval=r['interval'],
                source_record_id=r['native_id'],open_time=s.dt(r['open_time']),available_at=s.dt(r['available_at']),
                **{k:D(r[k]) for k in ('open','high','low','close')}))
    pools={r['window_id']:r for r in census['pool']};events={e['setup_id']:e for e in packet['events']}
    controls=[]
    for link in matches:
        if not link['control_id']:continue
        e,c=events[link['event_id']],pools[link['control_id']]
        b=streams[c['symbol']];at=s.dt(c['event_time']);entry=D(c['reference_close'])
        assert entry==D(source[c['source_key']]['close'])
        i=bisect_right(b,at,key=lambda x:x.available_at)
        distance=entry*D(e['stop_fraction'])
        target=entry+s.sign_for(e['side'])*entry*D(e['target_fraction']) if e.get('target_fraction') is not None else None
        outcomes=s.price_path(b[i:i+144],at=at,reference=entry,distance=distance,side=e['side'],target2=target,end=s.month_end(at))
        controls.append({**c,'control_id':c['window_id'],'matched_event_id':e['setup_id'],'side':e['side'],
                         'outcomes':outcomes,'normalization_distance':str(distance),'normalization_target':str(target)})
    summaries={}
    for month in ('2024-08','2024-09'):
        rows=[e for e in packet['events'] if e['terminal_at'].startswith(month)]
        groups={name:s.summarize_group(selected,controls) for name,selected in (
            ('all_diagnostic',rows),('primary',[e for e in rows if not e['formation_vetoes']]),
            ('base',[e for e in rows if s.is_base(e)]),('rejected',[e for e in rows if not s.is_base(e)]))}
        b=groups['base'];p4=b['horizons']['240']['paired'];p12=b['horizons']['720']['paired']
        a,b12=p4['equal_day_difference_bps'],p12['equal_day_difference_bps']
        verdict='INCONCLUSIVE'
        if a is not None and b12 is not None:
            if min(p4['event_days'],p12['event_days'])>=8 and D(a)<0 and D(b12)<0:
                verdict='NEGATIVE_4H_AND_12H_FALSIFICATION'
            elif D(a)>0 and D(b12)>0 and p4['leave_one_event_day_out_bps'] and D(p4['leave_one_event_day_out_bps'][0])>0:
                verdict='SUPPORTIVE_EXPLORATORY_ONLY'
        summaries[month]={'groups':groups,'interpretation':verdict}
    output={**binding,'primary_evidence_sha256':digest,'match_content_sha256':match_packet['content_sha256'],
            'original_decision_unchanged':packet['study_decision'],'promotion_authority':False,
            'months':summaries,'controls':controls}
    output['content_sha256']=s.config_hash(output)
    s.write_gzip(s.OUT/'S04_CONTROL_SUPPORT.json.gz',output)
    print(json.dumps({'sha256':output['content_sha256'],'months':{m:{'verdict':v['interpretation'],
        'pairs':v['groups']['base']['horizons']['720']['paired']['pairs']} for m,v in summaries.items()}},indent=2))


if __name__=='__main__':run()
