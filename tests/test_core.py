from copy import deepcopy
from itertools import product
import pytest
from disaster.core import *
from disaster.experiments import perturb


def initial():
    state=load_state()
    apply_event(state,read_json(ROOT/'data/scenario.json')['events'][0])
    return state


def test_standard_runs_and_no_overbooking():
    for method in ['dynamic','greedy','static']:
        state=run_scenario(method=method)
        assert_invariants(state)
        assert 0<=metrics(state)['urgent_satisfaction']<=1
        for task in state.tasks.values():
            assert task.completed<=task.required
    assert metrics(run_scenario())['unmet_units']==0


def test_lexicographic_assignment_matches_brute_force():
    state=initial()
    state.teams={k:v for k,v in state.teams.items() if k in ('R1','R2','R3')}
    state.tasks={k:v for k,v in state.tasks.items() if k in ('T01','T03','T06')}
    pairs=candidates(state)
    def objective(selected):
        return (-sum(state.tasks[p['task']].priority==1 for p in selected),
                -sum(state.tasks[p['task']].priority==2 for p in selected),sum(p['late'] for p in selected),sum(p['travel'] for p in selected))
    feasible=[]
    for bits in product([0,1],repeat=len(pairs)):
        selected=[p for b,p in zip(bits,pairs) if b]
        try:
            validate_assignments(state,selected)
        except ValueError:
            continue
        feasible.append(objective(selected))
    assert objective(solve(state)['assignments'])==min(feasible)


def test_duplicate_event_and_transaction_failure():
    state=initial()
    before=deepcopy(snapshot(state))
    assert not apply_event(state,read_json(ROOT/'data/scenario.json')['events'][0])
    assert snapshot(state)==before
    with pytest.raises(ValueError):
        apply_event(state,{'id':'bad','minute':0,'tasks':[],'blocked_roads':[['N0','invalid']]})
    assert snapshot(state)==before


def test_task_validation_rejects_negative_and_future_release():
    state=initial()
    raw=dict(id='NEW',node='N0',capability='rescue',required=-1,priority=1,deadline=20,duration=10,release=0)
    with pytest.raises(ValueError):
        validate_task(raw,state)
    raw.update(required=1,release=5)
    with pytest.raises(ValueError):
        validate_task(raw,state)


def test_fallback_when_solver_budget_exhausted():
    state=initial()
    d=solve(state,time_limit=0)
    assert d['status']=='FALLBACK_GREEDY'
    assert d['assignments']
    validate_assignments(state,d['assignments'])


def test_exhaustion_and_capability_absence():
    state=initial()
    dispatch(state,solve(state))
    assert solve(state)['assignments']==[]
    state=initial()
    state.teams={k:t for k,t in state.teams.items() if t.capability=='medical'}
    assert all(state.tasks[p['task']].capability=='medical' for p in solve(state)['assignments'])


def test_block_all_routes_releases_commitment():
    state=initial()
    dispatch(state,solve(state))
    advance(state,1,auto_dispatch=False)
    arrivals_before=len(state.arrivals)
    apply_event(state,dict(id='ALL-CLOSED',minute=1,blocked_roads=[list(e) for e in state.graph.edges()],tasks=[]))
    assert all(t.status!='travel' for t in state.teams.values())
    assert any(e['kind']=='blocked' for e in state.logs)
    assert len(state.arrivals)==arrivals_before
    validate_assignments(state,solve(state)['assignments'])


def test_reroute_keeps_task_and_last_reached_node():
    state=initial()
    dispatch(state,solve(state))
    advance(state,5,auto_dispatch=False)
    before={t.id:(t.node,t.task_id) for t in state.teams.values()}
    apply_event(state,read_json(ROOT/'data/scenario.json')['events'][1])
    for e in state.logs:
        if e['kind']=='reroute':
            team=state.teams[e['team']]
            assert (team.node,team.task_id)==before[team.id]
            assert not any(state.graph[u][v]['blocked'] for u,v in zip(team.path,team.path[1:]))
    assert any(e['kind']=='reroute' for e in state.logs)


def test_service_cannot_be_reassigned_and_event_cannot_rewind():
    state=initial()
    dispatch(state,solve(state))
    advance(state,20,auto_dispatch=False)
    active={t.id:t.task_id for t in state.teams.values() if t.task_id}
    decision=solve(state)
    assert not set(active)&{p['team'] for p in decision['assignments']}
    with pytest.raises(ValueError):
        advance(state,0)


def test_fixed_seed_reproducible():
    base=read_json(ROOT/'data/scenario.json')
    assert perturb(base,7)==perturb(base,7)
    a,b=run_scenario(perturb(base,7)),run_scenario(perturb(base,7))
    assert a.arrivals==b.arrivals
    assert a.logs==b.logs


def test_static_does_not_dispatch_new_tasks():
    state=run_scenario(method='static')
    assert len(state.decisions)==1
    assert not any(e.get('task') in ('T09','T10') for e in state.logs if e['kind']=='dispatch')


def test_gap_reasons_distinguish_capability_busy_and_roads():
    state=initial()
    task=state.tasks['T01']
    assert '等待下一轮' in gap_reason(state,task)
    for team in state.teams.values():
        team.available_at=1000
    assert '尚未增援' in gap_reason(state,task)
    for team in state.teams.values():
        team.available_at=0
    for u,v in state.graph.edges():
        state.graph[u][v]['blocked']=True
    assert '无法' in gap_reason(state,task)
    state.teams={k:t for k,t in state.teams.items() if t.capability!='rescue'}
    assert '没有该能力' in gap_reason(state,task)
