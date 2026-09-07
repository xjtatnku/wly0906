"""Measure cold startup separately from real Service delayed-event transactions."""
import argparse,json,os,subprocess,tempfile,time
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import numpy as np
from disaster.core import ROOT
from disaster.v2.service import Service
from disaster.v2.planning import plan
from disaster.v2.intake import extract
from disaster.v2.evaluation import audit

OUT=ROOT/'results/v23/final'

def cold():
    with tempfile.TemporaryDirectory() as tmp:
        start=time.perf_counter();service=Service(Path(tmp)/'cold.sqlite');created=time.perf_counter()
        warm=service.warmup_forecasts();end=time.perf_counter();service.db.engine.dispose()
    return dict(service_init_ms=(created-start)*1000,additional_warmup_ms=(end-created)*1000,total_ready_ms=(end-start)*1000,panels=warm['panels'])

def run():
    import sys
    OUT.mkdir(exist_ok=True,parents=True)
    cold_runs=[json.loads(subprocess.check_output([sys.executable,'-m','scripts.benchmark_warmup','--cold'],env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'))) for _ in range(3)]
    records=[]
    with tempfile.TemporaryDirectory() as tmp:
        service=Service(Path(tmp)/'warm.sqlite');service.warmup_forecasts()
        for mode in ('synthetic','historical'):
            service.reset(environment_mode=mode,risk_mode='rule');baseline=deepcopy(service.state)
            for i in range(30):
                revision=service.state['revision'];service.state=deepcopy(baseline);service.state['revision']=revision
                # Identical causal baseline, same real transaction path, fresh prediction cache.
                from disaster.v2.joint_forecast import JointForecaster
                JointForecaster.predictions.clear()
                candidate=extract(service,'S02监测数据延迟。')
                def limited(state,**settings):return plan(state,**settings,budget=.3)
                start=time.perf_counter()
                with patch('disaster.v2.service.plan',limited):service.confirm_batch(candidate)
                elapsed=(time.perf_counter()-start)*1000
                violations=audit(service.state);assert not violations,violations
                records.append(dict(environment=mode,repetition=i,latency_ms=elapsed,violations=len(violations),
                    eligible=service.state['forecast']['eligible_for_decision'],status=service.state['plan']['status']))
                print('Warm event',mode,i+1,flush=True)
        service.db.engine.dispose()
    result=dict(cold_start=cold_runs,warm_records=records,
        summary=[dict(environment=mode,repetitions=30,**{f'p{p}_ms':float(np.percentile([r['latency_ms'] for r in records if r['environment']==mode],p)) for p in (50,95,99)}) for mode in ('synthetic','historical')],
        protocol='3 isolated-process cold service startups. Warm: 30 identical delayed S02 batch transactions per environment; trained model cache warm, result cache cleared before every event; real SQLite save and view serialization included, HTTP and LLM excluded. Solver budget .3s. Not directly comparable with archived in-memory stress timings.')
    (OUT/'warmup_benchmark.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cold',action='store_true');args=parser.parse_args()
    if args.cold:print(json.dumps(cold()))
    else:run()
