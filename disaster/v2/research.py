"""V2.2 paired factorial experiments, actual execution metrics and stress tests."""
import argparse
import csv
import hashlib
import json
import math
import random
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
from threading import RLock
from unittest.mock import patch

from disaster.core import ROOT
from disaster.v2.evaluation import MemoryDatabase, audit
from disaster.v2.metrics import gini
from disaster.v2.planning import plan
from disaster.v2.service import Service

END = 120
METHODS = ('greedy', 'static', 'rolling', 'rolling_forecast')
CONTEXT = None


def input_fingerprint(state):
    fields=('nodes','roads','resources','tasks','settings','environment_mode','risk_mode','routing_mode')
    canonical={k:state[k] for k in fields}
    return hashlib.sha256(json.dumps(canonical,sort_keys=True).encode()).hexdigest()


def write_csv(path, rows):
    if not rows:
        return
    temporary=path.with_suffix('.partial')
    with temporary.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def initialize(context):
    global CONTEXT
    CONTEXT = context


def scenario(seed, scale, rate):
    state = deepcopy(CONTEXT['state'])
    rng = random.Random(seed)
    for road in state['roads']:
        road['minutes'] = max(1, round(road['minutes'] * rng.uniform(.75, 1.3)))
    pool = []
    for kind in sorted({r['type'] for r in state['resources']}):
        group = [r for r in state['resources'] if r['type'] == kind]
        # Nested prefixes, at least one of each type; actual counts are exported.
        pool.extend(group[:max(1, math.floor(len(group) * scale))])
    state['resources'] = pool
    original = deepcopy(state['tasks'])
    for task in state['tasks']:
        task['duration'] = max(5, round(task['duration'] * rng.uniform(.8, 1.2)))
    # Baseline 12 tasks; additive medium/high streams retain the same first 12.
    for i in range({'low': 0, 'medium': 12, 'high': 24}[rate]):
        task = deepcopy(original[i % len(original)])
        task.update(id=f'ADD{i:02}', release=5 + (i * 7) % 86, status='pending', actual_start=None, completed_at=None)
        task['deadline'] = task['release'] + 35
        state['tasks'].append(task)
    return state


def memory_service(state):
    service = Service.__new__(Service)
    service.state = deepcopy(state)
    service.lock = RLock()
    service.db = MemoryDatabase(CONTEXT['observations'])
    service.view = lambda *args, **kwargs: None
    # Exogenous forecasts are computed once with the SAME causal engine for all methods.
    # Copy precomputed observations-clock snapshots, never future forecasts.
    service.refresh = lambda: service.state.update(forecast=deepcopy(CONTEXT['forecasts'][service.state['minute'] // 5 * 5]))
    return service


def measure(state, calls, violations, travel):
    tasks = [t for t in state['tasks'] if t['release'] <= END]
    urgent = [t for t in tasks if t['priority'] == 1]
    starts = [t for t in tasks if t.get('actual_start') is not None and t['actual_start'] <= END]
    responses = [t['actual_start'] - t['release'] for t in starts]
    zones = []
    for node in sorted({t['node'] for t in tasks}):
        all_zone = [t for t in tasks if t['node'] == node]
        served = [t for t in starts if t['node'] == node]
        zones.append(dict(node=node, tasks=len(all_zone), started=len(served),
                          wait=sum(t['actual_start'] - t['release'] for t in served) / len(served) if served else None,
                          unstarted=len(all_zone) - len(served)))
    p1_starts = [t for t in starts if t['priority'] == 1]
    return dict(completed=sum(t['status'] == 'completed' for t in tasks), total_tasks=len(tasks),
        urgent_satisfaction=sum(t['status'] == 'completed' for t in urgent) / len(urgent) if urgent else None,
        mean_response=sum(responses) / len(responses) if responses else None,
        p1_response=sum(t['actual_start'] - t['release'] for t in p1_starts) / len(p1_starts) if p1_starts else None,
        weighted_response=sum({1: 5, 2: 3, 3: 1}[t['priority']] * (t['actual_start'] - t['release']) for t in starts),
        started_tasks=len(starts), unmet=sum(sum(t['requirements'].values()) for t in tasks if t['status'] != 'completed'),
        lateness=sum(max(0, t['actual_start'] - t['deadline']) for t in starts), travel=travel,
        reassignments=sum(p.get('stability', {}).get('reassignments', 0) for p in calls),
        withdrawals=sum(p.get('stability', {}).get('withdrawals', 0) for p in calls),
        violations=len(violations), solve_seconds=sum(p.get('seconds', 0) for p in calls), solver_calls=len(calls),
        fallback_calls=sum(p.get('degraded', False) for p in calls),
        region_gini=gini([z['wait'] for z in zones if z['wait'] is not None]),
        unserved_regions=sum(z['started'] == 0 for z in zones), region_waits=json.dumps(zones, separators=(',', ':')))


def simulate(state, method, budget, stress=None, response_weight=10):
    service = memory_service(state)
    service.state['settings'].update(forecast=method == 'rolling_forecast', response_weight=response_weight)
    calls = []
    violations = []
    travel = 0
    latency = 0
    event_trace = None

    def solve(current, **settings):
        if method == 'static' and current['minute'] > 0:
            old = deepcopy(current['plan'])
            pending = {t['id'] for t in current['tasks'] if t['status'] == 'pending'}
            failed = {r['id'] for r in current['resources'] if r['status'] == 'failed'}
            invalid = {a['task'] for a in old['assignments'] if a['resource'] in failed or any(
                e['blocked'] and any({u, v} == {e['u'], e['v']} for u, v in zip(a['path'], a['path'][1:])) for e in current['roads'])}
            old['assignments'] = [a for a in old['assignments'] if a['task'] in pending - invalid and a['depart'] >= current['minute']]
            old.update(status='STATIC_NO_REALLOCATION', seconds=0, stability={'reassignments': 0, 'withdrawals': 0})
            return old
        result = plan(current, **settings, budget=0 if method == 'greedy' else budget)
        calls.append(result)
        return result

    with patch('disaster.v2.service.plan', solve):
        service.optimize()
        for minute in range(END + 1):
            if minute:
                service.advance(1)
            if minute == (17 if stress else 20):
                started = time.perf_counter()
                if stress in (None, 'road_closure', 'simultaneous'):
                    service.block('RD00', replan=stress != 'simultaneous')
                if stress in ('new_p1', 'simultaneous'):
                    task = deepcopy(state['tasks'][0])
                    task.update(id='STRESS_P1', node='N8', release=minute, deadline=minute + 20, actual_start=None, status='pending')
                    service.state['tasks'].append(task)
                if stress in ('resource_failure', 'simultaneous'):
                    resource = next((r for r in service.state['resources'] if r.get('active')), service.state['resources'][0])
                    service.fail_resource(resource['id'])
                if stress == 'delayed_sensor':
                    # Freeze reception at -5: source ages > 3 cadences at minute 17.
                    from disaster.v2.joint_forecast import JointForecaster
                    training = [r for r in CONTEXT['observations'] if r['minute'] < 0]
                    engine = JointForecaster(training)
                    visible = [r for r in CONTEXT['observations'] if r['minute'] <= -5]
                    service.refresh = lambda: service.state.update(forecast=engine.predict(visible, service.state['minute']))
                    service.refresh()
                if stress == 'reinforcement':
                    extra = deepcopy(state['resources'][0])
                    extra.update(id='STRESS_REINFORCEMENT', available_at=minute, node='N0', status='idle')
                    service.state['resources'].append(extra)
                if stress:
                    service.replan([stress])
                latency = (time.perf_counter() - started) * 1000
                event_trace = deepcopy(service.state.get('decision_traces', [None])[-1])
            violations.extend(audit(service.state))
            # Actual occupied travel minutes, including interrupted partial paths; no projected future legs.
            if minute < END:
                travel += sum(bool(r.get('active')) and r['active']['depart'] <= minute < r['active']['arrival'] for r in service.state['resources'])
    result = measure(service.state, calls, violations, travel)
    if stress:
        result.update(latency_ms=latency, event_trace=json.dumps(event_trace, ensure_ascii=False, separators=(',', ':')),
                      forecast_eligible=service.state['forecast']['eligible_for_decision'])
    assert not violations, (method, stress, violations[:10])
    return result


def run_seed(seed, budget):
    rows = []
    for scale in (1, .75, .5, .35):
        for rate in ('low', 'medium', 'high'):
            state = scenario(seed, scale, rate)
            for method in METHODS:
                rows.append(dict(seed=seed, resource_scale=scale, resource_count=len(state['resources']), event_rate=rate,
                                 method=method, **simulate(state, method, budget)))
    # A matched ablation changes beta only; no forecast, same seed 50% / high input.
    state = scenario(seed, .5, 'high')
    ablation = dict(seed=seed, resource_scale=.5, event_rate='high', method='rolling_beta_0',
                    **simulate(state, 'rolling', budget, response_weight=0))
    return rows, ablation


def run(seeds=20, budget=.2, workers=4, resume=False):
    output = ROOT / 'results/v22'
    output.mkdir(exist_ok=True)
    from disaster.v2.joint_forecast import JointForecaster
    from disaster.v2.environment import HistoricalFeed
    with tempfile.TemporaryDirectory() as tmp:
        base = Service(Path(tmp) / 'research.sqlite')
        base.reset(environment_mode='synthetic', risk_mode='rule', routing_mode='simulated')
        forecasts = {}
        for minute in range(0, END + 1, 5):
            base.state['minute'] = minute
            forecasts[minute] = base.forecast_result()
        base.state['minute'] = 0
        base.state['forecast'] = forecasts[0]
        context = dict(state=deepcopy(base.state), observations=base.db.observations(END, 10000), forecasts=forecasts)
        write_csv(output / 'forecast_synthetic.csv', forecasts[0]['multistep_evaluation'])
        historical = JointForecaster(HistoricalFeed().observations(-1, 999999), 60)
        write_csv(output / 'forecast_historical.csv', historical.evaluation)
        base.db.engine.dispose()
    initialize(context)
    rows, ablations = [], []
    completed=set();seed_workers={}
    if resume and (output/'scheduling.csv').exists() and (output/'ablation.csv').exists():
        config=json.loads((output/'experiment_config.json').read_text(encoding='utf-8'))
        if config['solver_budget_seconds']!=budget:raise ValueError('Resume budget differs from saved experiment')
        with (output/'scheduling.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
        with (output/'ablation.csv').open(encoding='utf-8-sig') as f:ablations=list(csv.DictReader(f))
        for seed in range(seeds):
            selected=[r for r in rows if int(r['seed'])==seed]
            keys={(float(r['resource_scale']),r['event_rate'],r['method']) for r in selected}
            if len(selected)==48 and len(keys)==48 and any(int(r['seed'])==seed for r in ablations):completed.add(seed)
        rows=[r for r in rows if int(r['seed']) in completed]
        ablations=[r for r in ablations if int(r['seed']) in completed]
        seed_workers={str(seed):config.get('seed_workers',{}).get(str(seed),config['workers']) for seed in completed}
        print(f'Resuming {len(completed)} completed paired seeds',flush=True)
    with ProcessPoolExecutor(max_workers=workers, initializer=initialize, initargs=(context,)) as executor:
        futures = {executor.submit(run_seed, seed, budget): seed for seed in range(seeds) if seed not in completed}
        for future in as_completed(futures):
            result, ablation = future.result()
            rows.extend(result)
            ablations.append(ablation)
            write_csv(output / 'scheduling.csv', sorted(rows, key=lambda r: (int(r['seed']), float(r['resource_scale']), r['event_rate'], r['method'])))
            write_csv(output / 'ablation.csv', sorted(ablations, key=lambda r: int(r['seed'])))
            print(f"seed {futures[future]}: {len(rows)} factorial runs exported", flush=True)
    stress_rows = []
    for name in ('road_closure', 'new_p1', 'resource_failure', 'delayed_sensor', 'reinforcement', 'simultaneous'):
        stress_rows.append(dict(scenario=name, **simulate(scenario(906, 1, 'medium'), 'rolling_forecast', budget, stress=name)))
    write_csv(output / 'stress.csv', stress_rows)
    config = dict(seeds=list(range(seeds)), resource_scales=[1, .75, .5, .35], event_rates={'low': 12, 'medium': 24, 'high': 36},
        methods=METHODS, horizon=60, end_minute=END, solver_budget_seconds=budget, workers=workers, response_weight=10,
        scarcity='Per-type nested prefix floor(n*scale), minimum one; actual resource count exported.',
        input_sha256=input_fingerprint(context['state']),
        input_hash_scope='Initial nodes/roads/resources/tasks/settings/environment/risk/routing; excludes UUIDs, receipt timestamps and measured model runtime',
        resumed_seeds=sorted(completed),seed_workers={str(seed):seed_workers.get(str(seed),workers) for seed in range(seeds)},
        protocol='Shared synthetic input / exogenous joint forecasts / execution simulator; one-minute invariant audit.',
        notes=['Static only allocates at time zero, cancels blocked/failed future tasks, never reallocates.',
               'Travel is occupied execution minutes before minute 120, including interrupted legs.',
               'Response and regional Gini condition on started tasks. Unmet, started counts and unserved regions must accompany them.',
               'Closure RD00 at minute 20 for all factorial methods. Stress events occur off-period at minute 17.',
               'Beta-zero ablation uses 50% resources / high event rate, matched seeds and other settings.',
               'Wall-clock time and timeout-dependent feasible solutions may vary. Fallback counts are exported.',
               'Forecast tables separate synthetic 5/15/30/60 min and real historical 60/180/360/720 min.',
               'Real IMERG Final/ERA5-Land are retrospective forcing, not historically available operational data.'])
    (output / 'experiment_config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, default=20)
    parser.add_argument('--budget', type=float, default=.2)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--resume', action='store_true', help='Continue complete saved paired seeds with matching budget')
    args = parser.parse_args()
    run(args.seeds, args.budget, args.workers,args.resume)
