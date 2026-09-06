"""Stateful simulation. Times are integer simulated minutes, never historical facts."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path
import time
import networkx as nx
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = {'rescue', 'medical', 'engineering'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


@dataclass
class Team:
    id: str
    capability: str
    node: str
    available_at: int = 0
    task_id: str | None = None
    path: list[str] = field(default_factory=list)
    edge_left: int = 0
    service_end: int | None = None
    status: str = 'idle'


@dataclass
class Task:
    id: str
    node: str
    capability: str
    required: int
    priority: int
    deadline: int
    duration: int
    release: int
    description: str = ''
    completed: int = 0
    citations: list[str] = field(default_factory=list)


@dataclass
class State:
    now: int
    graph: nx.Graph
    teams: dict[str, Team]
    tasks: dict[str, Task] = field(default_factory=dict)
    seen: set[str] = field(default_factory=set)
    logs: list[dict] = field(default_factory=list)
    arrivals: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    def log(self, kind, **fields):
        self.logs.append({'minute': self.now, 'kind': kind, **fields})


def load_state(scenario=None):
    scenario = deepcopy(scenario or read_json(ROOT / 'data/scenario.json'))
    graph = nx.Graph()
    for n in scenario['nodes']:
        graph.add_node(n['id'], **{k: v for k, v in n.items() if k != 'id'})
    for e in scenario['roads']:
        if e['minutes'] <= 0:
            raise ValueError('Road travel time must be positive')
        graph.add_edge(e['u'], e['v'], minutes=e['minutes'], blocked=False)
    teams = {t['id']: Team(**t) for t in scenario['teams']}
    return State(0, graph, teams)


def open_graph(state):
    return nx.subgraph_view(state.graph, filter_edge=lambda u, v: not state.graph[u][v]['blocked'])


def route(state, start, end):
    try:
        path = nx.shortest_path(open_graph(state), start, end, weight='minutes')
        return path, sum(state.graph[u][v]['minutes'] for u, v in zip(path, path[1:]))
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None, None


def committed(state, task_id):
    return sum(t.task_id == task_id for t in state.teams.values())


def gap(state, task):
    return max(0, task.required - task.completed - committed(state, task.id))


def validate_task(raw, state):
    allowed = set(Task.__dataclass_fields__) - {'completed'}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError('Invalid task fields')
    task = Task(**raw)
    if not isinstance(task.id, str) or not task.id or task.id in state.tasks:
        raise ValueError('Duplicate or empty task ID')
    if task.node not in state.graph or task.capability not in CAPABILITIES:
        raise ValueError('Unknown node or capability')
    for name in ['required', 'priority', 'deadline', 'duration', 'release']:
        if type(getattr(task, name)) is not int:
            raise ValueError(f'{name} must be integer')
    if not (1 <= task.required <= 8 and task.priority in (1, 2) and 1 <= task.duration <= 1440):
        raise ValueError('Task bounds exceeded')
    if task.release != state.now or not task.release <= task.deadline <= task.release + 1440:
        raise ValueError('Task times must match event minute; deadline within 24 hours')
    if not isinstance(task.citations, list) or any(not isinstance(c, str) for c in task.citations):
        raise ValueError('Invalid citations')
    return task


def apply_event(state, event):
    """Validate transaction before mutation; repeated event IDs have no effects."""
    if not isinstance(event, dict) or not isinstance(event.get('id'), str) or not event['id']:
        raise ValueError('Event ID required')
    if event['id'] in state.seen:
        return False
    if type(event.get('minute')) is not int or event['minute'] != state.now:
        raise ValueError('Advance state to event minute first')
    new_tasks, ids = [], set(state.tasks)
    for raw in event.get('tasks', []):
        t = validate_task(raw, state)
        if t.id in ids:
            raise ValueError('Duplicate task ID in event')
        ids.add(t.id)
        new_tasks.append(t)
    closures = event.get('blocked_roads', [])
    for edge in closures:
        if not isinstance(edge, list) or len(edge) != 2 or not state.graph.has_edge(*edge):
            raise ValueError('Unknown road')
    for tid in event.get('activate_teams', []):
        if tid not in state.teams:
            raise ValueError('Unknown reinforcement')
    state.seen.add(event['id'])
    for t in new_tasks:
        state.tasks[t.id] = t
    for tid in event.get('activate_teams', []):
        state.teams[tid].available_at = state.now
    for u, v in closures:
        state.graph[u][v]['blocked'] = True
    state.log('event', event_id=event['id'], text=event.get('text', ''), new_tasks=[t.id for t in new_tasks])
    if closures:
        for team in state.teams.values():
            if team.status != 'travel':
                continue
            if not any(state.graph[u][v]['blocked'] for u, v in zip(team.path, team.path[1:])):
                continue
            # Conservative discrete-node abstraction: restart at last reached node.
            # Time already spent remains spent; no claim of physical mid-edge location.
            path, _ = route(state, team.node, state.tasks[team.task_id].node)
            if path is None:
                state.log('blocked', team=team.id, task=team.task_id, node=team.node)
                team.task_id, team.path, team.edge_left, team.status = None, [], 0, 'idle'
            else:
                team.path, team.edge_left = path, 0
                state.log('reroute', team=team.id, task=team.task_id, path=path)
                _start_edge_or_service(state, team)
    return True


def candidates(state):
    result = []
    for team in sorted(state.teams.values(), key=lambda t: t.id):
        if team.task_id or team.available_at > state.now:
            continue
        for task in sorted(state.tasks.values(), key=lambda t: t.id):
            if gap(state, task) <= 0 or task.capability != team.capability:
                continue
            path, travel = route(state, team.node, task.node)
            if path is not None:
                result.append({'team': team.id, 'task': task.id, 'path': path, 'travel': travel,
                               'arrival': state.now + travel, 'late': max(0, state.now + travel - task.deadline)})
    return result


def solve(state, method='dynamic', time_limit=5.0):
    """Lexicographic CP-SAT with a shared wall-clock budget for all levels."""
    start = time.perf_counter()
    pairs = candidates(state)

    def greedy():
        chosen, used, counts = [], set(), {}
        for p in sorted(pairs, key=lambda p: (state.tasks[p['task']].priority, p['travel'], p['task'], p['team'])):
            if p['team'] not in used and counts.get(p['task'], 0) < gap(state, state.tasks[p['task']]):
                chosen.append(p)
                used.add(p['team'])
                counts[p['task']] = counts.get(p['task'], 0) + 1
        return chosen

    status, levels, best = 'GREEDY', [], None
    if method == 'greedy':
        best = greedy()
    elif method not in ('dynamic', 'static'):
        raise ValueError('Unknown method')
    elif not pairs:
        status, best = 'NO_CANDIDATES', []
    else:
        model = cp_model.CpModel()
        x = [model.new_bool_var(f'x{i}') for i in range(len(pairs))]
        for tid in state.teams:
            model.add(sum(x[i] for i, p in enumerate(pairs) if p['team'] == tid) <= 1)
        for tid, task in state.tasks.items():
            model.add(sum(x[i] for i, p in enumerate(pairs) if p['task'] == tid) <= gap(state, task))
        objectives = [
            -sum(x[i] for i, p in enumerate(pairs) if state.tasks[p['task']].priority == 1),
            -sum(x[i] for i, p in enumerate(pairs) if state.tasks[p['task']].priority == 2),
            sum(x[i] * p['late'] for i, p in enumerate(pairs)),
            sum(x[i] * p['travel'] for i, p in enumerate(pairs)),
        ]
        for objective in objectives:
            remaining = time_limit - (time.perf_counter() - start)
            if remaining <= 0:
                status = 'TIMEOUT_WITH_INCUMBENT' if best is not None else 'FALLBACK_GREEDY'
                break
            model.minimize(objective)
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = remaining
            solver.parameters.num_search_workers = 1
            solver.parameters.random_seed = 0
            outcome = solver.solve(model)
            status = solver.status_name(outcome)
            if outcome in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                best = [p for i, p in enumerate(pairs) if solver.value(x[i])]
                if outcome == cp_model.OPTIMAL:
                    value = int(round(solver.objective_value))
                    levels.append(value)
                    model.add(objective == value)
                else:
                    break
            else:
                status = 'TIMEOUT_WITH_INCUMBENT' if best is not None else 'FALLBACK_GREEDY'
                break
        if best is None:
            best = greedy()
            status = 'FALLBACK_GREEDY'
    validate_assignments(state, best)
    return {'minute': state.now, 'method': method, 'status': status, 'assignments': best,
            'optimal_levels': levels, 'seconds': time.perf_counter() - start}


def validate_assignments(state, assignments):
    used, counts = set(), {}
    for p in assignments:
        team, task = state.teams[p['team']], state.tasks[p['task']]
        if team.id in used or team.task_id or team.available_at > state.now:
            raise ValueError('Resource double booking or unavailable')
        if team.capability != task.capability:
            raise ValueError('Capability mismatch')
        path = p['path']
        if not path or path[0] != team.node or path[-1] != task.node:
            raise ValueError('Invalid route endpoints')
        if any(not state.graph.has_edge(u, v) or state.graph[u][v]['blocked'] for u, v in zip(path, path[1:])):
            raise ValueError('Blocked or nonexistent route')
        travel = sum(state.graph[u][v]['minutes'] for u, v in zip(path, path[1:]))
        if travel != p['travel'] or state.now + travel != p['arrival']:
            raise ValueError('Invalid travel or arrival numbers')
        if p['late'] != max(0, state.now + travel - task.deadline):
            raise ValueError('Invalid lateness number')
        counts[task.id] = counts.get(task.id, 0) + 1
        if counts[task.id] > gap(state, task):
            raise ValueError('Excess allocation')
        used.add(team.id)


def _start_edge_or_service(state, team):
    if len(team.path) <= 1:
        task = state.tasks[team.task_id]
        team.status = 'service'
        team.service_end = state.now + task.duration
        team.edge_left = 0
        state.arrivals.append({'team': team.id, 'task': task.id, 'minute': state.now,
                               'response': state.now - task.release, 'late': max(0, state.now - task.deadline)})
        state.log('arrival', team=team.id, task=task.id)
    else:
        team.status = 'travel'
        team.edge_left = state.graph[team.path[0]][team.path[1]]['minutes']


def dispatch(state, decision):
    validate_assignments(state, decision['assignments'])
    for p in decision['assignments']:
        team = state.teams[p['team']]
        team.task_id, team.path = p['task'], list(p['path'])
        state.log('dispatch', **p)
        _start_edge_or_service(state, team)
    state.decisions.append(deepcopy(decision))


def tick(state):
    state.now += 1
    for team in state.teams.values():
        if team.status == 'travel':
            team.edge_left -= 1
            if team.edge_left == 0:
                team.node = team.path[1]
                team.path = team.path[1:]
                _start_edge_or_service(state, team)
        elif team.status == 'service' and team.service_end <= state.now:
            state.tasks[team.task_id].completed += 1
            state.log('complete', team=team.id, task=team.task_id)
            team.task_id, team.path, team.service_end, team.status = None, [], None, 'idle'
    assert_invariants(state)


def assert_invariants(state):
    for task in state.tasks.values():
        if task.completed + committed(state, task.id) > task.required:
            raise AssertionError('Overfilled task')
    for team in state.teams.values():
        if team.task_id and team.capability != state.tasks[team.task_id].capability:
            raise AssertionError('Mismatched execution')


def advance(state, until, method='dynamic', auto_dispatch=True):
    if until < state.now:
        raise ValueError('Cannot rewind executed state')
    while state.now < until:
        tick(state)
        # Same 5-minute opportunities for greedy and dynamic; static never reallocates.
        if auto_dispatch and method != 'static' and state.now % 5 == 0 and state.now < until:
            dispatch(state, solve(state, method))


def gap_reason(state, task):
    if gap(state, task)==0:
        return '作业已完成' if task.completed==task.required else '已有队伍承诺执行'
    matching=[t for t in state.teams.values() if t.capability==task.capability]
    if not matching:
        return '没有该能力类型的队伍'
    idle=[t for t in matching if not t.task_id and t.available_at<=state.now]
    if not idle:
        waiting=sum(t.available_at>state.now for t in matching)
        busy=sum(t.task_id is not None for t in matching)
        return f'匹配队伍无空闲：{busy}支执行中，{waiting}支尚未增援'
    reachable=[t for t in idle if route(state,t.node,task.node)[0] is not None]
    return '空闲匹配队伍均无法经当前道路到达' if not reachable else '存在可用队伍，等待下一轮分配或资源竞争'


def task_rows(state):
    return [dict(asdict(t), committed=committed(state, t.id), gap=gap(state, t),gap_reason=gap_reason(state,t)) for t in state.tasks.values()]


def snapshot(state):
    return {'minute': state.now, 'teams': [asdict(t) for t in state.teams.values()],
            'tasks': task_rows(state), 'logs': state.logs, 'arrivals': state.arrivals, 'decisions': state.decisions}


def metrics(state):
    urgent = [t for t in state.tasks.values() if t.priority == 1]
    total = sum(t.required for t in state.tasks.values())
    urgent_total = sum(t.required for t in urgent)
    arrived = {tid: sum(a['task'] == tid for a in state.arrivals) for tid in state.tasks}
    return {'urgent_satisfaction': sum(min(t.required, arrived[t.id]) for t in urgent) / max(1, urgent_total),
            'unmet_units': total - sum(min(t.required, arrived[t.id]) for t in state.tasks.values()),
            'completed_units': sum(t.completed for t in state.tasks.values()),
            'mean_response': sum(a['response'] for a in state.arrivals) / max(1, len(state.arrivals)),
            'late_minutes': sum(a['late'] for a in state.arrivals),
            'violations': len(state.violations), 'solver_seconds': sum(d['seconds'] for d in state.decisions),
            'arrived_units': len(state.arrivals), 'total_units': total}


def run_scenario(scenario=None, method='dynamic', horizon=180):
    scenario = deepcopy(scenario or read_json(ROOT / 'data/scenario.json'))
    state = load_state(scenario)
    for event in scenario['events']:
        advance(state, event['minute'], method)
        apply_event(state, event)
        if method != 'static' or not state.decisions:
            dispatch(state, solve(state, method))
    advance(state, horizon, method)
    return state
