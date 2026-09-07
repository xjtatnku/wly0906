from copy import deepcopy
import os
import pytest
from disaster.core import ROOT,read_json
from disaster.config import load_local_env,NAMES
from disaster.v2.service import Service
from disaster.v2.intake import extract,rules,grounded
from disaster.v2.planning import plan
from disaster.v2.evaluation import audit


@pytest.fixture(scope='module')
def service(tmp_path_factory):
    service=Service(tmp_path_factory.mktemp('v23')/'test.sqlite')
    yield service
    service.db.engine.dispose()


def test_env_is_data_not_code_and_preserves_process_values(tmp_path,monkeypatch):
    for key in NAMES:monkeypatch.delenv(key,raising=False)
    path=tmp_path/'.env';path.write_text('sk-example_not_a_real_credential',encoding='utf-8')
    assert load_local_env(path)
    assert os.environ['DISASTER_MODEL']=='deepseek-v4-flash'
    monkeypatch.setenv('DISASTER_MODEL','explicit-model')
    path.write_text('DISASTER_MODEL=from-file\nUNSUPPORTED=ignored',encoding='utf-8')
    load_local_env(path)
    assert os.environ['DISASTER_MODEL']=='explicit-model'
    assert 'UNSUPPORTED' not in os.environ


def test_chinese_adjacent_ids_and_no_partial_match(service):
    result=rules('N4发生泥石流；RES01资源故障。',service.state)
    assert result.events[0].node=='N4' and result.events[1].resource_ids==['RES01']
    assert rules('N40发生泥石流。',service.state).events[0].node is None


def test_live_error_returns_labeled_fallback_and_never_commits(service,monkeypatch):
    before=deepcopy(service.state)
    def failure(*args):raise RuntimeError('secret_should_not_appear')
    monkeypatch.setattr('disaster.v2.intake.provider_json',failure)
    result=extract(service,'RES01资源故障。',True)
    assert result['error']=='RuntimeError' and not result['live_success']
    assert 'secret_should_not_appear' not in str(result)
    assert result['candidate']['events'][0]['resource_ids']==['RES01']
    assert service.state==before


def test_model_numbers_and_unknown_roads_are_rejected(service,monkeypatch):
    text='N4 失联8人。';raw=rules(text,service.state).model_dump()
    raw['events'][0]['missing']=88
    with pytest.raises(ValueError):grounded(raw,text,service.state)
    raw=rules('RD00道路中断。',service.state).model_dump();raw['events'][0]['road_ids']=['FAKE']
    with pytest.raises(ValueError):grounded(raw,'RD00道路中断。',service.state)


def test_grounded_explanation_rejects_fabricated_route_and_citation(service,monkeypatch):
    from disaster.v2.grounded_explanation import explain
    service.reset();service.optimize()
    before=deepcopy(service.state)
    monkeypatch.setattr('disaster.v2.grounded_explanation.provider_json',lambda *args:dict(policy_support=[dict(clause_id='FAKE',quote='fake',action='rescue')],allocations=[]))
    result=explain(service,True)
    assert result['error']=='ValueError' and 'FAKE' not in str(result)
    assert service.state==before


def test_delayed_source_view_and_forecast_agree(service):
    service.reset(environment_mode='synthetic');service.advance(10)
    service.confirm_batch(extract(service,'S02数据延迟。'))
    view=service.view()
    assert not view['forecast']['eligible_for_decision']
    assert all(r['minute']<=-10 for r in view['observations'] if r['station_id']=='S02')
    assert all(r['source_status']=='STALE' for r in view['data_health'] if ':S02:' in r['source_id'])


def test_correction_replaces_count_keeps_history_and_no_duplicate_task(service):
    service.reset(environment_mode='synthetic')
    service.confirm_batch(extract(service,'N4 失联8人，受伤3人，需要搜救。'))
    first=service.state['current_reports']['N4'];tasks=len(service.state['tasks'])
    service.confirm_batch(extract(service,'N4 新增失联5人。'))
    assert service.state['casualties']['missing']==13
    service.confirm_batch(extract(service,'N4 失联人数修正为15人。'))
    assert service.state['casualties']=={'missing':15,'injured':3}
    assert len(service.state['tasks'])==tasks and first in service.state['situation_reports']
    assert len(service.state['situation_reports'])==3


def test_failed_batch_rolls_back_road_resource_and_database(service):
    service.reset();before=deepcopy(service.state);saved=service.db.load()
    payload=extract(service,'RD00道路中断；N4 新增失联3人。')
    with pytest.raises(ValueError):service.confirm_batch(payload)
    assert service.state==before and service.db.load()==saved


def test_simultaneous_batch_replans_once_and_duplicate_is_idempotent(service):
    service.reset();payload=extract(service,'RD00道路中断；RES01资源故障。')
    service.confirm_batch(payload)
    assert len(service.state['decision_traces'])==1
    assert len(service.state['plan']['triggers'])==2
    previous=deepcopy(service.state)
    payload['revision']=service.state['revision']
    service.confirm_batch(payload)
    assert service.state==previous


def test_nine_stage_replay_actual_corrections_and_state_invariants(service):
    service.start_scenario()
    for i in range(9):
        candidate=service.prepare_stage()
        assert candidate['stage_index']==i
        service.confirm_batch(candidate)
        assert not audit(service.state)
    assert service.state['scenario_cursor']==9
    assert service.state['casualties']['missing']==15
    assert len(service.state['situation_reports'])==3
    assert any(r['status']=='failed' for r in service.state['resources'])
    assert any(e['kind']=='secondary_risk' for e in service.state['events'])
    with pytest.raises(ValueError):service.prepare_stage()


def test_lexicographic_prioritizes_p1_and_verifies_each_level():
    state=read_json(ROOT/'data/v2/scenario.json');state.update(minute=0,plan={},forecast={})
    state['resources']=[state['resources'][0]]
    state['tasks']=[dict(id='P1',name='P1',node='N0',requirements={'rescue_team':1},priority=1,release=0,deadline=20,duration=10,status='pending'),
                    dict(id='P2',name='P2',node='N0',requirements={'rescue_team':1},priority=2,release=0,deadline=20,duration=10,status='pending')]
    result=plan(state,horizon=30,budget=2,forecast=False,objective_mode='lexicographic')
    assert result['lexicographic_complete']
    assert result['verified_lexicographic']==[0,0,0,0]
    assert [v['value'] for v in result['lexicographic_levels']]==result['verified_lexicographic']
    assert next(a['start'] for a in result['assignments'] if a['task']=='P1')==0
    fallback=plan(state,budget=0,forecast=False,objective_mode='lexicographic')
    assert fallback['degraded'] and not fallback['lexicographic_complete']
