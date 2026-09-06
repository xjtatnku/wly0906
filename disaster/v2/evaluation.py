"""Paired execution experiments on V2 synthetic scenarios; no live model calls."""
import argparse
import csv
import json
import random
import tempfile
from copy import deepcopy
from pathlib import Path
from threading import RLock
from unittest.mock import patch
from disaster.core import ROOT
from disaster.v2.service import Service
from disaster.v2.planning import plan

class MemoryDatabase:
    def __init__(self,rows):self.rows=rows
    def observations(self,minute,limit=1440):return [r for r in self.rows if minute-limit<=r['minute']<=minute]
    def save(self,state):pass

def audit(state):
    errors=[]
    active={}
    for r in state['resources']:
        a=r.get('active')
        if not a:continue
        if a['resource']!=r['id'] or a['type']!=r['type']:errors.append('resource_identity')
        if a['end']<=state['minute']:errors.append('expired_commitment')
        remaining=a['path'][a['path'].index(r['node']):] if r['node'] in a['path'] else []
        if any(e['blocked'] and any({u,v}=={e['u'],e['v']} for u,v in zip(remaining,remaining[1:])) for e in state['roads']):errors.append('blocked_remaining_route')
        active.setdefault(a['task'],[]).append(r)
    for t in state['tasks']:
        if t['status']!='committed':continue
        group=active.get(t['id'],[])
        if any(sum(r['type']==kind for r in group)!=n for kind,n in t['requirements'].items()):errors.append('compound_requirement')
        if any(r['active']['start']!=t['actual_start'] for r in group):errors.append('synchronization')
    return errors

def run(seeds=20,budget=.25,sensitivity=False):
    output=ROOT/'results/v21';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        base=Service(Path(tmp)/'seed.sqlite')
        rows=base.db.observations(180,1620)
        initial=deepcopy(base.state)
        forecast_metrics=base.forecaster.evaluation
        base.db.engine.dispose()
        results=[]
        for seed in [-1,*range(seeds)]:
            scenario=deepcopy(initial);rng=random.Random(seed)
            if seed>=0:
                for road in scenario['roads']:road['minutes']=max(1,round(road['minutes']*rng.uniform(.75,1.3)))
                for task in scenario['tasks']:task['duration']=max(5,round(task['duration']*rng.uniform(.8,1.2)))
            blocked=scenario['roads'][rng.randrange(len(scenario['roads']))]['id'] if seed>=0 else 'RD00'
            modes=['greedy','static','dynamic','dynamic_prediction']
            if sensitivity:modes+=['stability_0','stability_5','stability_50','stability_100']
            for mode in modes:
                s=Service.__new__(Service);s.state=deepcopy(scenario);s.lock=RLock();s.forecaster=base.forecaster
                s.db=MemoryDatabase(rows);s.view=lambda *args,**kwargs:None
                s.state['settings']['forecast']=mode=='dynamic_prediction'
                if mode.startswith('stability_'):s.state['settings']['stability']=int(mode.split('_')[1])
                calls=[];violations=[];committed=set();travel=0
                def solve(state,**settings):
                    if mode=='static' and state['minute']>0:
                        result=deepcopy(state['plan'])
                        invalid={a['task'] for a in result['assignments'] if any(e['blocked'] and any({u,v}=={e['u'],e['v']} for u,v in zip(a['path'],a['path'][1:])) for e in state['roads'])}
                        result['assignments']=[a for a in result['assignments'] if a['task'] not in invalid]
                        return result
                    result=plan(state,**settings,budget=0 if mode=='greedy' else budget)
                    calls.append(result);return result
                with patch('disaster.v2.service.plan',solve):
                    s.optimize()
                    for step in range(121):
                        if step:
                            s.advance(1)
                            if step==20:
                                s.block(blocked)
                                if mode=='static':
                                    # Preserve remaining original allocations only; no reassignment.
                                    road=next(e for e in s.state['roads'] if e['id']==blocked)
                                    invalid={a['task'] for a in s.state['plan']['assignments'] if any({u,v}=={road['u'],road['v']} for u,v in zip(a['path'],a['path'][1:]))}
                                    s.state['plan']['assignments']=[a for a in s.state['plan']['assignments'] if a['task'] not in invalid]
                        violations.extend(audit(s.state))
                        for r in s.state['resources']:
                            a=r.get('active')
                            if not a:continue
                            key=(r['id'],a['task'],a['depart'])
                            if key not in committed:travel+=a['travel'];committed.add(key)
                tasks=[t for t in s.state['tasks'] if t['release']<=120]
                served=[t for t in tasks if t['status']=='completed']
                urgent=[t for t in tasks if t['priority']==1]
                starts=[t for t in tasks if t.get('actual_start') is not None and t['actual_start']<=120]
                delays=[t['actual_start']-t['release'] for t in starts]
                gini=sum(abs(a-b) for a in delays for b in delays)/(2*len(delays)*sum(delays)) if delays and sum(delays)>0 else 0 if delays else None
                results.append(dict(seed=seed,method=mode,completed=len(served),total_tasks=len(tasks),
                    urgent_satisfaction=sum(t['status']=='completed' for t in urgent)/len(urgent),
                    unmet_resource_units=sum(sum(t['requirements'].values()) for t in tasks if t['status']!='completed'),
                    mean_start_delay=sum(t['actual_start']-t['release'] for t in starts)/len(starts) if starts else None,
                    lateness=sum(max(0,t['actual_start']-t['deadline']) for t in starts),committed_travel=travel,
                    violations=len(violations),solve_seconds=sum(p['seconds'] for p in calls),solver_calls=len(calls),
                    fallback_calls=sum(p['degraded'] for p in calls),blocked_road=blocked,
                    stability=s.state['settings']['stability'],response_gini_started=gini,started_tasks=len(starts),
                    plan_changes=sum(p['changes'] for p in calls)))
            print(f'seed {seed}: completed {len(modes)} paired methods',flush=True)
        for name,items in [('dispatch_metrics.csv',results),('forecast_metrics.csv',forecast_metrics),('forecast_multistep.csv',base.forecaster.multistep_evaluation)]:
            with (output/name).open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(items[0]));writer.writeheader();writer.writerows(items)
        metadata=dict(seeds=[-1,*range(seeds)],horizon=60,end_minute=120,solver_budget_seconds=budget,
            stability_sensitivity=[0,5,20,50,100] if sensitivity else [20],audit_interval_minutes=1,
            provenance='All sensors, coordinates, road times, tasks and resources are simulated.',
            methods={'greedy':'same compound requirements; earliest feasible available resources',
                     'static':'initial horizon plan, no new allocations; blocked future tasks removed',
                     'dynamic':'P1 release, reinforcement, risk jump, closure + 10-minute safety trigger; prediction disabled',
                     'dynamic_prediction':'same dynamic policy plus synthetic risk prepositioning'},
            notes=['Completion measured at minute 120, not projected assignments.',
                   'Mean start delay includes only tasks started by 120; report together with unmet units.',
                   'Committed travel counts planned paths when commitments first observed at 1-minute boundaries.',
                   'Wall-clock solver time and timeout-dependent solutions may vary by machine.',
                   'forecast_multistep.csv uses fixed-train recursive rolling origins at 5/15/30/60 minutes.',
                   'Response Gini is conditional on started tasks; always report together with unmet demand. Not a fairness optimization objective.'])
        (output/'experiment_config.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        assert all(r['violations']==0 for r in results), 'Execution invariant violations detected'
        return results

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seeds',type=int,default=20);parser.add_argument('--budget',type=float,default=.25);parser.add_argument('--sensitivity',action='store_true')
    args=parser.parse_args();run(args.seeds,args.budget,args.sensitivity)
