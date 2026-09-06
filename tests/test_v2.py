from copy import deepcopy
import json
import pytest
from disaster.v2.data import Database, Observation, RESOURCE_NAMES
from disaster.v2.service import Service
from disaster.v2.planning import plan, validate
from disaster.core import ROOT, read_json

@pytest.fixture
def service(tmp_path):return Service(tmp_path/'test.sqlite')

def test_database_ingestion_is_idempotent_and_rejects_invalid(service):
    row=service.db.observations(0)[0]
    result=service.db.ingest([row,dict(row,station_id='INVALID',value=-10)])
    assert result['duplicates']==1 and result['rejected']==1
    assert result['accepted']==0
    assert all(o['minute']<=0 for o in service.db.observations(0))

def test_forecast_is_causal_and_has_measured_baselines(service):
    observations=service.db.observations(0)
    a=service.forecaster.predict(observations,0)
    b=service.forecaster.predict(observations+[dict(observations[0],minute=100,value=999999)],0)
    for key in a['series']:assert a['series'][key]['forecast']==b['series'][key]['forecast']
    assert len(a['evaluation'])==12
    assert {e['model'] for e in a['evaluation']}=={'AR','Persistence','Gradient Boosting'}
    assert 0<=a['score']<=1

def test_multiresource_plan_and_persistence(service):
    p=service.optimize()
    assert p['status'] in ('OPTIMAL','FEASIBLE')
    assert p['assignments']
    saved=service.db.load()
    assert saved['revision']==service.state['revision']
    assert saved['plan']==p
    before=service.state['minute'];view=service.advance(10)
    assert view['minute']==before+10
    assert service.db.history()[-1]['minute']==10

def test_real_horizon_sequences_one_resource_twice(service):
    s=deepcopy(service.state);s['resources']=[dict(id='ONE',name='one',type='rescue_team',node='N0',capacity=1,status='idle',available_at=0)]
    s['tasks']=[dict(id='A',name='a',node='N3',requirements={'rescue_team':1},priority=1,release=0,deadline=30,duration=5,status='pending'),
                dict(id='B',name='b',node='N4',requirements={'rescue_team':1},priority=1,release=0,deadline=50,duration=5,status='pending')]
    p=plan(s,forecast=False)
    assert len(p['assignments'])==2
    a,b=sorted(p['assignments'],key=lambda a:a['start'])
    assert b['depart']>=a['end']
    assert b['path'][0]==a['node']
    validate(s,p)

def test_cannot_partially_allocate_compound_task(service):
    s=deepcopy(service.state)
    s['resources']=[r for r in s['resources'] if r['type']=='rescue_team']
    s['tasks']=[dict(id='A',name='a',node='N4',requirements={'rescue_team':1,'drone':1},priority=1,release=0,deadline=30,duration=5,status='pending')]
    assert not plan(s,forecast=False)['assignments']

def test_whatif_does_not_mutate_database_or_current_state(service):
    before=deepcopy(service.state);count=len(service.db.history())
    results=service.whatif('RD00',True)
    assert len(results)==3
    assert service.state==before and len(service.db.history())==count

def test_confirm_rejects_stale_and_invalid_before_changes(service):
    candidate=service.extract('N4 失联12人，受伤5人，需要搜救和医疗')
    assert candidate['candidate']['casualties']=={'missing':12,'injured':5}
    assert candidate['candidate']['node']=='N4'
    before=deepcopy(service.state)
    bad=deepcopy(candidate);bad['candidate']['casualties']['missing']=-10
    with pytest.raises(ValueError):service.confirm(bad)
    assert service.state==before
    service.confirm(candidate)
    assert service.state['casualties']['missing']==12
    with pytest.raises(ValueError):service.confirm(candidate)

def test_hybrid_retains_policy_provenance_and_time(service):
    result=service.retrieve('人员搜救 医疗救治')
    assert len(result)==5
    assert all(c['published_at']<'2024-08-03' for c in result)
    assert all('LSA' in c['retrieval'] for c in result)

def test_road_block_persisted_and_infeasible_routes_excluded(service):
    service.optimize();view=service.block('RD00')
    assert view['metrics']['blocked']==1
    assert service.db.load()['roads'][0]['blocked']
    for a in view['plan']['assignments']:
        assert not any({u,v}=={'N0','N1'} for u,v in zip(a['path'],a['path'][1:]))

def test_timeout_fallback_and_total_blockade(service):
    s=deepcopy(service.state)
    p=plan(s,budget=0,forecast=False)
    assert p['degraded'] and p['assignments']
    validate(s,p)
    for road in s['roads']:road['blocked']=True
    s['resources']=[]
    p=plan(s,budget=0,forecast=False)
    assert not p['assignments'] and p['unplanned']

def test_confirm_roads_and_rollback_on_solver_failure(service,monkeypatch):
    candidate=service.extract('N4 道路 RD00 中断，需要工程抢险')
    before=deepcopy(service.state)
    with monkeypatch.context() as m:
        m.setattr('disaster.v2.service.plan',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('solver error')))
        with pytest.raises(RuntimeError):service.confirm(candidate)
    assert service.state==before and service.db.load()==before
    service.confirm(candidate)
    assert service.state['roads'][0]['blocked']
    assert service.state['tasks'][-1]['clause_ids']

def test_model_failure_and_illegal_output_never_changes_state(service,monkeypatch):
    before=deepcopy(service.state)
    for output in [[],{},dict(service.extract('N4 失联12人')['candidate'],confidence=.99)]:
        monkeypatch.setattr('disaster.v2.service.provider_json',lambda *a,**k:output)
        with pytest.raises(ValueError):service.extract('N4 失联12人',live=True)
        assert service.state==before

def test_restart_restore_and_reset_preserve_history(service):
    service.advance(1)
    restored=Service(service.db.path)
    assert restored.state==service.state
    count=len(service.db.history());revision=service.state['revision']
    service.reset()
    assert service.state['minute']==0 and service.state['revision']==revision+1
    assert len(service.db.history())==count+1

def test_road_behind_traveler_does_not_cancel_commitment(service,monkeypatch):
    r=service.state['resources'][0]
    road=service.state['roads'][0]
    r['node']=road['v']
    r['active']=dict(task='V01',path=[road['u'],road['v'],'N4'],start=100,end=120,node='N4')
    service.state['tasks'][0]['status']='committed'
    monkeypatch.setattr('disaster.v2.service.plan',lambda *a,**k:{'assignments':[]})
    service.block(road['id'])
    assert r['active']['task']=='V01'
