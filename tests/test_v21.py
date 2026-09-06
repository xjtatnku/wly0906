from copy import deepcopy
from datetime import datetime
import json
import sqlite3
import numpy as np
import pytest
from sklearn.linear_model import Ridge
from disaster.core import ROOT,read_json
from disaster.v2.data import Database
from disaster.v2.forecast import Forecaster
from disaster.v2.service import Service
from disaster.v2.osm import build,load_scenario
from disaster.v2.planning import plan,graph,validate

@pytest.fixture
def service(tmp_path):return Service(tmp_path/'v21.sqlite')

def test_observed_received_clocks_freshness_and_heartbeat(service):
    row=deepcopy(service.db.observations(0)[0]);row.update(station_id='TEST',received_at='1900-01-01T00:00:00Z')
    report=service.db.ingest([row],received_minute=10)
    assert report['accepted']==1
    assert not any(r['station_id']=='TEST' for r in service.db.observations(0,10000))
    stored=next(r for r in service.db.observations(10,10000) if r['station_id']=='TEST')
    assert stored['received_at']!=row['received_at'] and len(stored['checksum'])==64
    health=next(h for h in service.db.source_health(10) if h['source_id'].startswith('import:TEST:'))
    assert health['source_status']=='STALE' and health['heartbeat_age_seconds']==0
    assert next(h for h in service.db.source_health(41) if h['source_id'].startswith('import:TEST:'))['source_status']=='OFFLINE'
    replay=next(h for h in service.db.source_health(0) if h['source_id']=='replay:S01:rainfall')
    assert replay['source_status']=='FRESH' and replay['missing_rate']==0

def test_legacy_database_migration_preserves_observation(tmp_path):
    path=tmp_path/'legacy.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sensor_observations (id INTEGER PRIMARY KEY,station_id TEXT,minute INTEGER,timestamp TEXT,type TEXT,value FLOAT,unit TEXT,quality TEXT,lat FLOAT,lon FLOAT,provenance TEXT)')
        db.execute("INSERT INTO sensor_observations VALUES (1,'S01',0,'2024-08-03T09:00:00+08:00','rainfall',5,'mm/h','valid',30,102,'simulated')")
    database=Database(path);row=database.observations(0)[0]
    assert row['observed_at']==row['timestamp'] and row['received_at'] is None
    assert row['quality_code']=='LEGACY_VALID' and row['value']==5
    database.engine.dispose()

def test_recursive_evaluation_reproduces_60_minute_errors(service):
    f=service.forecaster;metrics=f.multistep_evaluation
    assert len(metrics)==48 and {m['horizon_minutes'] for m in metrics}=={5,15,30,60}
    data=[r['value'] for r in service.db.observations(-1,1440) if r['station_id']=='S01' and r['type']=='rainfall']
    a=np.array(data);x=np.array([a[i-12:i] for i in range(12,len(a))]);y=a[12:];split=int(len(y)*.75)
    model=Ridge(alpha=1).fit(x[:split],y[:split]);origins=np.arange(12+split,len(a)-11)
    context=np.array([a[i-12:i] for i in origins])
    for _ in range(12):context=np.column_stack([context,np.clip(model.predict(context[:,-12:]),0,200)])
    error=context[:,-1]-a[origins+11]
    actual=next(m for m in metrics if m['type']=='rainfall' and m['model']=='AR' and m['horizon_minutes']==60)
    assert actual['mae']==pytest.approx(abs(error).mean())
    assert len({m['test_samples'] for m in metrics})==1

def test_late_sensor_cannot_trigger_preposition(service):
    forecast=service.forecaster.predict(service.db.observations(0),30)
    assert not forecast['eligible_for_decision']
    s=deepcopy(service.state);s['forecast']=forecast
    assert 'PREPOSITION' not in plan(s)['tasks_considered']

def test_nonperiodic_p1_and_reinforcement_trigger(service):
    service.state['tasks'][0]['release']=3
    service.state['resources'][0]['available_at']=3
    service.advance(3)
    triggers=service.state['plan']['triggers']
    assert '新增P1任务 V01' in triggers and '增援到达 RES01' in triggers
    assert '10分钟周期兜底' not in triggers

def test_resource_failure_preserves_elapsed_time_and_excludes_resource(service):
    service.optimize();service.advance(10)
    r=next(r for r in service.state['resources'] if r.get('active'))
    rid=r['id'];position=r['node'];now=service.state['minute']
    service.fail_resource(rid)
    assert r['status']=='failed' and r['node']==position and service.state['minute']==now
    assert all(a['resource']!=rid for a in service.state['plan']['assignments'])
    assert service.db.load()['plan']['triggers']==['资源故障 '+rid]

def test_osm_oneway_and_private_access_from_raw_fixture():
    snapshot={'elements':[{'type':'node','id':i,'lat':30,'lon':102+i*.001} for i in range(1,5)]+[
        {'type':'way','id':20,'nodes':[1,2,3],'tags':{'highway':'residential','oneway':'yes'}},
        {'type':'way','id':21,'nodes':[3,4],'tags':{'highway':'service','access':'private'}}]}
    seed={'nodes':[{'id':'A','lat':30,'lon':102.001,'kind':'station','population':0,'name':'A'},
                   {'id':'B','lat':30,'lon':102.003,'kind':'station','population':0,'name':'B'}]}
    s=build(snapshot,seed,{})
    g=graph(s)
    assert g.has_edge('A','B') and not g.has_edge('B','A')
    assert s['roads'][0]['osm_node_ids']==[1,2,3]
    assert all(21 not in r['osm_way_ids'] for r in s['roads'])

def test_downloaded_osm_used_by_optimizer_and_blocking(service):
    service.reset('osm');before=deepcopy(service.state);p=service.optimize()
    assert service.state['routing_mode']=='osm' and len(service.state['roads'])>100
    assert p['assignments']
    assert any(a['geometry'] for a in p['assignments'])
    validate(before,p)
    road_id=next(seg['road_id'] for a in p['assignments'] for seg in a['segments'])
    service.block(road_id)
    assert all(seg['road_id']!=road_id for a in service.state['plan']['assignments'] for seg in a['segments'])
    assert len(service.db.history())>=3
