import pytest
from disaster.core import *
from disaster.knowledge import *
import disaster.knowledge as knowledge


def test_corpus_has_two_versions_and_history_cutoff():
    r=Retriever()
    assert len(r.clauses)==20
    assert len({c['source_id'] for c in r.clauses})==2
    assert not r.search('搜救',as_of='2023-01-01T00:00:00+08:00')
    assert len(r.search('搜救'))==5
    assert visible_facts('2024-08-03T23:59:59+08:00')==[]
    assert len(visible_facts('2024-08-04T23:59:59+08:00'))==4


def test_cache_rules_and_ambiguity_are_labeled():
    state=load_state()
    assert extract_event('村落甲发现人员被困，需要搜救。',state)['mode'].startswith('缓存回放')
    assert extract_event('村落乙有伤员。',state)['mode']=='离线规则'
    assert extract_event('某地有灾害',state)['candidate'] is None
    assert extract_event('村落甲和村落乙有人受伤',state)['candidate'] is None
    assert extract_event('道路交汇点有人员失联，开展搜救。',state)['candidate']['capability']=='rescue'
    assert extract_event('医疗点周边需要道路抢通。',state)['candidate']['capability']=='engineering'


def test_api_failure_does_not_mutate_state(monkeypatch):
    def fail(*args,**kwargs):
        raise RuntimeError('secret_should_not_be_exposed')
    monkeypatch.setattr(knowledge,'provider_json',fail)
    state=load_state()
    before=snapshot(state)
    result=extract_event('村落乙有伤员',state,True)
    assert result['candidate'] is None
    assert 'secret' not in result['error']
    assert snapshot(state)==before


def test_invalid_model_output_rejected(monkeypatch):
    monkeypatch.setattr(knowledge,'provider_json',lambda *a,**k: {'node':'UNKNOWN','capability':'rescue','evidence':'fake','event_time':None})
    assert extract_event('村落甲有人被困',load_state(),True)['candidate'] is None


def test_valid_model_response_and_citation_guard(monkeypatch):
    text='村落甲有人被困'
    raw=dict(node='N4',capability='rescue',evidence=text,event_time=None)
    monkeypatch.setattr(knowledge,'provider_json',lambda *a,**k:raw)
    state=load_state()
    assert extract_event(text,state,True)['mode']=='实时调用'
    monkeypatch.setattr(knowledge,'provider_json',lambda *a,**k:dict(citations=['FORGED'],reason='fake'))
    hits=Retriever().search(text)
    suggestion=suggest_task(raw,hits,state,True)
    assert 'FORGED' not in suggestion['citations']
    assert '失败' in suggestion['mode']


def test_confirmed_event_idempotence_and_unknown_citation():
    state=load_state()
    e=build_event('村落甲有人被困',state,'N4','rescue')
    assert apply_event(state,e)
    assert not apply_event(state,build_event('村落甲有人被困',state,'N4','rescue'))
    with pytest.raises(ValueError):
        build_event('other',state,'N4','rescue',citations=['FORGED'])


def test_explanation_cannot_invent_assignments(monkeypatch):
    state=load_state()
    apply_event(state,read_json(ROOT/'data/scenario.json')['events'][0])
    d=solve(state)
    monkeypatch.setattr(knowledge,'provider_json',lambda *a,**k:dict(reasons=[dict(team='FAKE',task='FAKE',code='URGENT')]))
    explanation=explain_decision(state,d,True)
    assert 'FAKE' not in str(explanation)
    assert '未通过' in explanation['mode']
