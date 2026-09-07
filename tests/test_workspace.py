import json
import pytest
from fastapi.testclient import TestClient
from disaster.v2.api import app
from disaster.v2.workspace import present
from disaster.v2.intake import rules

@pytest.fixture(scope='module')
def client(tmp_path_factory):
    from disaster.v2.service import Service
    svc=Service(tmp_path_factory.mktemp('workspace')/'state.sqlite')
    app.state.service=svc
    yield TestClient(app)
    svc.db.engine.dispose()

def test_public_contract_excludes_internal_details(client,monkeypatch):
    monkeypatch.delenv('DISASTER_ENABLE_RESEARCH_API',raising=False)
    response=client.get('/api/workspace/state');assert response.status_code==200
    payload=response.json();encoded=json.dumps(payload)
    for forbidden in ('database','training_sha256','objective_terms','decision_traces','lexicographic_levels','source_sha256','quality_code','api_key','DISASTER_MODEL','OPTIMAL'):
        assert forbidden not in encoded
    for path in ('/api/state','/api/health','/api/research/current','/docs','/openapi.json','/assets/research.js','/assets/package.json'):
        assert client.get(path).status_code==404
    invalid=client.post('/api/workspace/advance',json={'minutes':'bad','secret':'do-not-echo'}).json()
    assert 'do-not-echo' not in json.dumps(invalid)
    assert set(invalid)=={'detail'}

def test_review_token_stale_rejection_and_nine_stage_flow(client,monkeypatch):
    monkeypatch.delenv('DISASTER_ENABLE_RESEARCH_API',raising=False)
    assert client.post('/api/workspace/start').status_code==200
    first=client.post('/api/workspace/prepare').json()
    assert 'revision' not in first and 'model_candidate' not in first and 'error' not in first
    assert client.post('/api/workspace/advance',json={'minutes':1}).status_code==200
    stale=client.post('/api/workspace/confirm',json={'token':first['token'],'events':first['events']})
    assert stale.status_code==409
    client.post('/api/workspace/start')
    for index in range(9):
        candidate=client.post('/api/workspace/prepare').json()
        result=client.post('/api/workspace/confirm',json={'token':candidate['token'],'events':candidate['events']})
        assert result.status_code==200,result.text
        assert client.post('/api/workspace/confirm',json={'token':candidate['token'],'events':candidate['events']}).status_code==409
    state=client.get('/api/workspace/state').json()
    assert state['casualties']['missing']==15 and len(state['reports'])==3
    assert state['scenario_cursor']==9

def test_errors_are_not_exposed_and_mutations_return_only_receipts(client,monkeypatch):
    monkeypatch.delenv('DISASTER_ENABLE_RESEARCH_API',raising=False)
    response=client.post('/api/workspace/road',json={'road':'not-a-road'})
    assert response.status_code==422
    monkeypatch.setattr(app.state.service,'advance',lambda *a:(_ for _ in ()).throw(RuntimeError('private database path')))
    failed=client.post('/api/workspace/advance',json={'minutes':1})
    assert failed.status_code==500 and 'private' not in failed.text
