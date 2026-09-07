from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import numpy as np
import pytest

from disaster.core import ROOT, read_json
from disaster.v2.environment import HistoricalFeed
from disaster.v2.joint_forecast import JointForecaster
from disaster.v2.metrics import disruption, gini
from disaster.v2.planning import plan, graph, validate
from disaster.v2.preposition import preposition_plan
from disaster.v2.service import Service


@pytest.fixture(scope='module')
def service(tmp_path_factory):
    service = Service(tmp_path_factory.mktemp('v22') / 'state.sqlite')
    yield service
    service.db.engine.dispose()


def tiny():
    state = read_json(ROOT / 'data/v2/scenario.json')
    state.update(minute=0, plan={}, forecast={})
    state['resources'] = [state['resources'][0]]
    state['tasks'] = [dict(id='T1', name='test', node='N0', priority=1, requirements={'rescue_team':1},
        release=0, deadline=50, duration=5, status='pending', actual_start=None)]
    return state


def test_response_objective_starts_early_even_before_deadline():
    state = tiny()
    state['resources'][0]['available_at'] = 7
    result = plan(state, forecast=False, budget=1)
    assert result['assignments'][0]['start'] == 7
    assert result['objective_terms']['response'] == 5 * 7
    assert result['objective_terms']['lateness'] == 0
    assert result['objective'] == result['verified_objective']


def test_weighted_response_orders_priority_and_unserved_has_zero_response():
    state = tiny()
    other = dict(state['tasks'][0], id='T2', priority=2)
    state['tasks'].append(other)
    result = plan(state, forecast=False, budget=1)
    starts = {a['task']: a['start'] for a in result['assignments']}
    assert starts['T1'] == 0 and starts['T2'] == 5
    assert result['objective'] == result['verified_objective']
    state['resources'] = []
    empty = plan(state, forecast=False, budget=1)
    assert empty['objective_terms']['response'] == 0
    assert empty['objective_terms']['unmet'] == 12000
    assert empty['gaps'] and empty['verified_objective'] == 12000
    assert empty['objective'] == empty['verified_objective']


def test_disruption_excludes_first_allocation_new_jobs_completion_and_lock():
    state = tiny()
    a = dict(resource='RES01', task='T1', depart=3)
    assert disruption(state, [a])['disruption'] == 0
    state['plan'] = {'assignments': [a]}
    assert disruption(state, [a, dict(a, task='NEW')])['disruption'] == 0
    assert disruption(state, [])['withdrawals'] == 1
    state['tasks'][0]['status'] = 'completed'
    assert disruption(state, [])['disruption'] == 0
    state['tasks'][0]['status'] = 'committed'
    assert disruption(state, [])['disruption'] == 0


def test_resource_swap_counted_once_per_resource():
    state = tiny()
    state['tasks'].append(dict(state['tasks'][0], id='T2'))
    old = [dict(resource='A', task='T1', depart=3), dict(resource='B', task='T2', depart=3)]
    state['plan'] = {'assignments': old}
    change = disruption(state, [dict(old[0], task='T2'), dict(old[1], task='T1')])
    assert change['reassignments'] == 2 and change['withdrawals'] == 0


def test_real_bronze_hashes_and_native_causal_alignment():
    manifest = read_json(ROOT / 'data/gold/environment_manifest.json')
    assert manifest['native_rows'] == 3672 and manifest['hourly_rows'] == 2442
    for source in manifest['sources']:
        assert hashlib.sha256((ROOT / source['file']).read_bytes()).hexdigest() == source['sha256']
    native = read_json(ROOT / 'data/silver/environment_native.json')
    gold = read_json(ROOT / 'data/gold/environment_hourly.json')
    assert {r['cadence_minutes'] for r in native} == {30, 60}
    assert {r['type'] for r in gold} == {'rainfall', 'soil_moisture'}
    rain = {(r['station_id'], r['observed_at']): r for r in native if r['type'] == 'rainfall'}
    for row in gold:
        assert row['cadence_minutes'] == 60 and row['minute'] % 60 == 0
        if row['type'] != 'rainfall':
            continue
        time = datetime.fromisoformat(row['observed_at'])
        source_rows = [rain[row['station_id'], (time - timedelta(minutes=m)).isoformat()] for m in (60, 30)]
        assert row['value'] == pytest.approx(sum(r['value'] * .5 for r in source_rows))
        assert all(datetime.fromisoformat(r['interval_end']) <= time for r in source_rows)


def test_historical_native_horizons_and_time_filter():
    feed = HistoricalFeed()
    engine = JointForecaster(feed.observations(-1, 999999), 60)
    result = engine.predict(feed.observations(17), 17)
    assert len(result['multistep_evaluation']) == 72
    assert {r['horizon_minutes'] for r in result['multistep_evaluation']} == {60, 180, 360, 720}
    assert len(result['station_series']) == 6
    assert all(r['minute'] <= 17 for r in feed.observations(17))
    assert all(v['history'][-1]['minute'] == 0 for v in result['station_series'].values())
    assert result['risk'][0]['minute'] == 60


def test_joint_features_all_stations_and_no_future_leakage(service):
    rows = service.db.observations(-1, 999999)
    engine = JointForecaster(rows)
    assert engine.models['AR'].n_features_in_ == 144
    assert len(engine.evaluation) == 144
    future = [dict(r, minute=10, value=100) for r in rows[-12:]]
    assert JointForecaster(rows + future).fingerprint == engine.fingerprint
    visible = service.db.observations(0)
    before = engine.predict(visible, 0)
    changed = [dict(r, value=r['value'] + 1) if r['station_id']=='S02' and r['minute']==0 else r for r in visible]
    after = engine.predict(changed, 0)
    assert before['station_series']['S01:rainfall']['forecast'] != after['station_series']['S01:rainfall']['forecast']
    assert before['station_series'] == engine.predict(visible + future, 0)['station_series']


def test_delayed_or_gapped_joint_panel_disables_preposition(service):
    engine = JointForecaster(service.db.observations(-1, 999999))
    rows = service.db.observations(0)
    assert not engine.predict(rows, 20)['eligible_for_decision']
    rows = [r for r in rows if not (r['minute'] == -10 and r['station_id'] == 'S02')]
    assert not engine.predict(rows, 0)['eligible_for_decision']
    assert plan(dict(tiny(), forecast=engine.predict(rows, 0)), budget=1)['preposition']['status'] == 'NOT_RUN'


def test_empirical_risk_components_are_normalized(service):
    engine = JointForecaster(service.db.observations(-1, 999999))
    result = engine.predict(service.db.observations(0), 0, risk_mode='empirical')
    assert sum(c['weight'] for c in result['components']) == pytest.approx(1)
    assert sum(c['contribution'] for c in result['components']) == pytest.approx(result['zones'][0]['forecast_scores'][0])
    assert all(0 <= z['score'] <= 1 for z in result['zones'])


def test_preposition_respects_current_demand_and_scenario_closure():
    state = read_json(ROOT / 'data/v2/scenario.json')
    state.update(minute=0, plan={}, tasks=[], forecast={'eligible_for_decision': True,
                 'zones':[dict(node='N4', score=.95), dict(node='N5', score=.6), dict(node='N8', score=.8)]})
    held = [{'resource':'RES01'}]
    assignments, report = preposition_plan(state, held, graph(state), 60, 1)
    assert all(a['resource'] != 'RES01' for a in assignments)
    assert len({a['resource'] for a in assignments}) == len(assignments)
    assert report['scenarios'][2]['blocked_roads']
    assert report['optimized_cost'] <= report['baseline_cost']
    assert report['optimized_cost'] == pytest.approx(sum(s['probability'] * report['scenario_costs'][s['name']] for s in report['scenarios']))
    validate(state, {'assignments':assignments})


def test_trace_persistence_and_objective_numbers(service):
    service.reset(environment_mode='synthetic')
    result = service.optimize({'forecast':False})
    trace = service.db.load()['decision_traces'][-1]
    assert trace['verified_objective'] == result['objective']
    assert trace['objective_delta'] is None
    assert trace['stability']['disruption'] == 0
    assert trace['added'] and trace['zones'] and trace['observations']


def test_history_switch_excludes_synthetic_variables(service):
    view = service.reset(environment_mode='historical', risk_mode='empirical')
    assert set(view['sensor_types']) == {'rainfall','soil_moisture'}
    assert len(view['data_health']) == 6
    assert all(r['provenance'] == 'historical_reanalysis_retrospective' for r in view['observations'])
    assert service.db.load()['environment_mode'] == 'historical'
    service.reset(environment_mode='synthetic')


def test_fairness_handles_unserved_regions_explicitly():
    assert gini([]) is None and gini([0, 0]) == 0
    assert gini([10, 30]) == .25


def test_future_schema_and_late_training_rows_cannot_change_fit(service):
    rows=service.db.observations(-1,999999)
    baseline=JointForecaster(rows)
    future=dict(rows[-1],station_id='UNSEEN',minute=10,received_minute=10)
    late=dict(rows[-1],station_id='LATE',minute=-10,received_minute=20)
    changed=JointForecaster(rows+[future,late])
    assert changed.fingerprint==baseline.fingerprint and changed.keys==baseline.keys


def test_rejection_is_audited_without_dispatch_and_checks_revision(service):
    service.reset(environment_mode='synthetic')
    candidate=service.extract('N4 需要搜救支援')
    before=deepcopy(service.state)
    service.reject(candidate)
    saved=service.db.load()
    assert saved['tasks']==before['tasks'] and saved['resources']==before['resources']
    assert saved['plan']==before['plan'] and saved['events'][-1]['kind']=='rejected'
    assert saved['revision']==before['revision']+1
    with pytest.raises(ValueError):service.reject(candidate)
