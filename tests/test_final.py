from copy import deepcopy
import hashlib
from unittest.mock import patch
import pytest
from sqlalchemy import select
from disaster.core import ROOT,read_json
from disaster.v2.service import Service
from disaster.v2.joint_forecast import JointForecaster
from disaster.v2.data import Observation
from disaster.v2.ood_evaluation import atoms,summary

@pytest.fixture(scope='module')
def service(tmp_path_factory):
    s=Service(tmp_path_factory.mktemp('final')/'state.sqlite')
    yield s
    s.db.engine.dispose()

def test_observation_projection_retains_values_and_causal_filters(service):
    for minute,limit in [(-1,999999),(17,180),(70,1440)]:
        with service.db.sessions() as session:
            rows=session.scalars(select(Observation).where(Observation.minute<=minute,Observation.received_minute<=minute,Observation.minute>=minute-limit).order_by(Observation.minute)).all()
            expected=[{c.name:getattr(r,c.name) for c in Observation.__table__.columns} for r in rows]
        assert service.db.observations(minute,limit)==expected

def test_warmup_is_causal_and_does_not_mutate_state(service):
    before=deepcopy(service.state);ready=service.warmup_forecasts()
    assert ready['ready'] and len(ready['panels'])==2
    assert service.state==before
    # Warm models must be reusable even when the request result cache is empty.
    from sklearn.pipeline import Pipeline
    from sklearn.multioutput import MultiOutputRegressor
    with patch.object(Pipeline,'fit',side_effect=AssertionError('unexpected request fit')),patch.object(MultiOutputRegressor,'fit',side_effect=AssertionError('unexpected request fit')):
        for mode in ('synthetic','historical'):
            service.state['environment_mode']=mode
            service.state['delayed_sources']={'S02':{'cutoff':-240 if mode=='historical' else -20,'expires':30}}
            JointForecaster.predictions.clear()
            for model in ('Persistence','AR','Gradient Boosting'):
                forecast=service.forecast_result(model)
                assert not forecast['eligible_for_decision']
                assert forecast['training_sha256']==next(r['training_sha256'] for r in ready['panels'] if r['environment']==mode)
    service.state=before

def test_challenge_is_frozen_and_distinct_from_diagnostic():
    path=ROOT/'data/v23/final/ood.json';rows=read_json(path);manifest=read_json(path.with_name('ood_manifest.json'))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['sha256']
    assert len(rows)==120 and len({r['category'] for r in rows})==12
    assert not {r['text'] for r in rows}&{r['text'] for r in read_json(ROOT/'data/v23/extraction_gold.json')}
    for row in rows:
        for event in row['gold']['events']:
            assert event['node'] is None or event['node'] in row['text']

def test_evaluation_counts_duplicates_and_rejection_as_abstention():
    event={'event_type':'disaster_report','node':'N4','missing':2,'count_mode':'absolute'}
    candidate={'events':[event,event]};gold={'events':[event]}
    assert sum(atoms(candidate,'numeric').values())==2
    records=[dict(gold=gold,arms={'raw':dict(candidate=candidate,latency_ms=10,grounded_pass=True,fallback=False),
        'grounded':dict(candidate={'events':[]},latency_ms=11,grounded_pass=False,fallback=True)})]
    assert summary(records,'raw')['numeric_f1']==pytest.approx(2/3)
    assert summary(records,'grounded')['numeric_f1']==0
    assert summary(records,'grounded')['fallback_rate']==1
    assert not atoms({'events':None},'event')
