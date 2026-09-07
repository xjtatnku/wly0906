"""Paired uncertainty, heterogeneous events, lexicographic and beta baselines."""
import json,csv,random,tempfile
from pathlib import Path
from copy import deepcopy
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
from disaster.core import ROOT
from disaster.v2 import research as base
from disaster.v2.service import Service

OUT=ROOT/'results/v23'


def paired_statistics():
    with (ROOT/'results/v22/scheduling.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    rng=np.random.default_rng(906);results=[]
    for scale in (1,.75,.5,.35):
      for rate in ('low','medium','high'):
        for method in ('rolling','rolling_forecast'):
          for metric,higher in [('urgent_satisfaction',True),('mean_response',False),('unmet',False)]:
            subset=[r for r in rows if float(r['resource_scale'])==scale and r['event_rate']==rate]
            left={int(r['seed']):r for r in subset if r['method']=='greedy'}
            right={int(r['seed']):r for r in subset if r['method']==method}
            differences=np.array([float(right[s][metric])-float(left[s][metric]) for s in sorted(left.keys()&right.keys()) if left[s][metric] and right[s][metric]])
            bootstrap=rng.choice(differences,(10000,len(differences)),replace=True).mean(axis=1)
            low,high=np.quantile(bootstrap,[.025,.975]);std=differences.std(ddof=1)
            results.append(dict(resource_scale=scale,event_rate=rate,method=method,baseline='constraint_aware_greedy',metric=metric,pairs=len(differences),
                mean_difference=differences.mean(),median_difference=np.median(differences),ci_low=low,ci_high=high,
                paired_standardized_effect=differences.mean()/std if std else None,
                win_rate=float(np.mean(differences>1e-9 if higher else differences< -1e-9)),tie_rate=float(np.mean(abs(differences)<=1e-9)),
                inference='exploratory pointwise percentile bootstrap; no multiple-comparison correction'))
    base.write_csv(OUT/'paired_statistics.csv',results)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(11,6),constrained_layout=True)
    for row,method in enumerate(('rolling','rolling_forecast')):
      for col,metric in enumerate(('urgent_satisfaction','mean_response','unmet')):
        matrix=np.array([[next(r['win_rate'] for r in results if r['method']==method and r['metric']==metric and r['resource_scale']==s and r['event_rate']==rate) for rate in ('low','medium','high')] for s in (1,.75,.5,.35)])
        ax=axes[row,col];ax.imshow(matrix,vmin=0,vmax=1,cmap='YlGnBu')
        ax.set(xticks=range(3),xticklabels=['low','medium','high'],yticks=range(4),yticklabels=['100%','75%','50%','35%'],title=method+' / '+metric)
        for (i,j),value in np.ndenumerate(matrix):ax.text(j,i,f'{value:.0%}',ha='center',va='center',color='white' if value>.55 else 'black')
    fig.suptitle('Win rate vs constraint-aware greedy (20 paired seeds per cell; ties excluded from wins)')
    fig.savefig(OUT/'paired_win_rates.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(11,6),constrained_layout=True)
    for row,method in enumerate(('rolling','rolling_forecast')):
      for col,metric in enumerate(('urgent_satisfaction','mean_response','unmet')):
        matrix=np.array([[next(r['mean_difference'] for r in results if r['method']==method and r['metric']==metric and r['resource_scale']==s and r['event_rate']==rate) for rate in ('low','medium','high')] for s in (1,.75,.5,.35)])
        bound=max(abs(r['mean_difference']) for r in results if r['metric']==metric) or 1
        ax=axes[row,col];plot=ax.imshow(matrix,vmin=-bound,vmax=bound,cmap='RdBu')
        ax.set(xticks=range(3),xticklabels=['low','medium','high'],yticks=range(4),yticklabels=['100%','75%','50%','35%'],title=method+' / '+metric)
        for (i,j),value in np.ndenumerate(matrix):ax.text(j,i,f'{value:+.3f}',ha='center',va='center',color='white' if abs(value)>.6*bound else 'black')
        fig.colorbar(plot,ax=ax,shrink=.7)
    fig.suptitle('Paired mean difference vs greedy: positive favors P1, negative favors response / unmet')
    fig.savefig(OUT/'paired_differences.png',dpi=180);plt.close(fig)


def diverse_scenario(seed,rate):
    state=base.scenario(seed,.5,rate);rng=random.Random(2300+seed)
    for task in state['tasks']:
        if not task['id'].startswith('ADD'):continue
        task['node']=rng.choice(['N3','N4','N5','N6','N7','N8'])
        kind=rng.choices(['rescue','medical','engineering','supply'],weights=[4,3,2,1])[0]
        task['requirements']={'rescue':{'rescue_team':rng.choice([1,2]),'drone':1},'medical':{'medical_team':1,'ambulance':1},
                              'engineering':{'engineering_team':1,'excavator':1},'supply':{'supply_vehicle':1}}[kind]
        task['priority']=1 if rng.random()<(.45 if rate=='medium' else .7) else 2
        task['release']=rng.randint(5,85);task['deadline']=task['release']+rng.randint(20,45);task['duration']=rng.randint(10,25)
    state['experiment_events']=[] if rate=='low' else [dict(minute=32,kind='failure',id='RES01')]
    if rate=='high':state['experiment_events'].append(dict(minute=55,kind='road',id='RD03'))
    return state


def seed_run(seed):
    rows=[];betas=[];stress=[]
    for rate in ('low','medium','high'):
        state=diverse_scenario(seed,rate)
        for method in ('greedy','static','rolling','lexicographic','rolling_forecast'):
            result=base.simulate(state,method,.3)
            result.setdefault('lex_complete_calls',None);result.setdefault('lex_proven_p1_calls',None)
            rows.append(dict(seed=seed,event_rate=rate,resource_scale=.5,method=method,**result))
    state=diverse_scenario(seed,'high')
    for beta in (0,1,2,5,10,20,50):
        betas.append(dict(seed=seed,beta=beta,**base.simulate(state,'rolling',.3,response_weight=beta)))
    return rows,betas


def stress_run(repetition):
    return [dict(repetition=repetition,scenario=name,**base.simulate(base.scenario(906,1,'medium'),'rolling_forecast',.3,stress=name))
            for name in ('road_closure','new_p1','resource_failure','delayed_sensor','reinforcement','simultaneous')]


def run():
    OUT.mkdir(exist_ok=True);paired_statistics()
    with tempfile.TemporaryDirectory() as tmp:
        service=Service(Path(tmp)/'research.sqlite');service.reset(environment_mode='synthetic',risk_mode='rule')
        forecasts={}
        for minute in range(0,121,5):service.state['minute']=minute;forecasts[minute]=service.forecast_result()
        service.state['minute']=0;service.state['forecast']=forecasts[0]
        context=dict(state=deepcopy(service.state),observations=service.db.observations(120,10000),forecasts=forecasts)
        service.db.engine.dispose()
    rows=[];betas=[];stress=[]
    with ProcessPoolExecutor(max_workers=6,initializer=base.initialize,initargs=(context,)) as pool:
        futures={pool.submit(seed_run,seed):seed for seed in range(20)}
        for future in as_completed(futures):
            result,sensitivity=future.result();rows.extend(result);betas.extend(sensitivity)
            base.write_csv(OUT/'lexicographic.csv',rows);base.write_csv(OUT/'beta_sensitivity.csv',betas)
            print('Completed scheduling seed',futures[future],flush=True)
        futures=[pool.submit(stress_run,i) for i in range(30)]
        for future in as_completed(futures):
            stress.extend(future.result());base.write_csv(OUT/'stress_repeated.csv',stress)
            print('Stress runs',len(stress),flush=True)
    config=dict(seeds=list(range(20)),budget=.3,workers=6,resource_scale=.5,event_rates=['low','medium','high'],
        beta=[0,1,2,5,10,20,50],stress_repetitions=30,
        input_hash=base.input_fingerprint(context['state']),
        notes=['New experiment family, not pooled with V2.2 inputs. Additional tasks vary location/type/priority/duration and release.',
               'Medium/high include RES01 failure at minute32; high adds RD03 closure at minute55. All methods share inputs.',
               'Lexicographic fixes only proven optimal levels; feasible/time-limited levels stop the sequence.',
               'Stress timing uses in-memory simulator and includes repeated scenario execution; excludes HTTP/database/network and LLM latency.',
               'Paired bootstrap uses 10000 seed resamples within each original V2.2 cell; exploratory pointwise intervals.'])
    (OUT/'experiment_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')


if __name__=='__main__':run()
