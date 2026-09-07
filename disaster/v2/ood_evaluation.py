"""Frozen challenge evaluation: raw and grounded arms share the same API response."""
import hashlib,json,os,tempfile,time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from disaster.core import ROOT,read_json
from disaster.v2.service import Service
from disaster.v2.intake import extract,grounded

OUT=ROOT/'results/v23/final'

def atoms(candidate,metric):
    result=Counter()
    if not isinstance(candidate,dict):return result
    events=candidate.get('events',[])
    if not isinstance(events,list):return result
    for e in events:
        if not isinstance(e,dict):continue
        kind=e.get('event_type');node=e.get('node')
        if metric=='event':
            if kind and kind!='uncertain_report':result[(kind,)]+=1
        elif metric=='entity':
            if node:result[(kind,'node',str(node))]+=1
            for key in ('road_ids','resource_ids','station_ids','needs'):
                if isinstance(e.get(key),list):
                    for v in e[key]:result[(kind,key,str(v))]+=1
        else:
            for key in ('missing','injured'):
                if e.get(key) is not None:result[(kind,str(node),key,str(e[key]),e.get('count_mode','absolute'))]+=1
    return result

def summary(records,method):
    counts={k:[0,0,0] for k in ('event','entity','numeric')};latency=[];passed=fallback=unsafe=negatives=0
    for row in records:
        r=row['arms'][method];latency.append(r['latency_ms']);passed+=r['grounded_pass'];fallback+=r['fallback']
        negative=not atoms(row['gold'],'event');negatives+=negative
        unsafe+=bool(negative and atoms(r['candidate'],'event'))
        for metric in counts:
            p=atoms(r['candidate'],metric);g=atoms(row['gold'],metric)
            counts[metric]=[x+y for x,y in zip(counts[metric],(sum((p&g).values()),sum((p-g).values()),sum((g-p).values())))]
    result=dict(method=method,samples=len(records),grounded_pass_rate=passed/len(records),fallback_rate=fallback/len(records),
        negative_samples=negatives,false_action_rate=unsafe/negatives if negatives else None,
        latency_p50_ms=float(np.quantile(latency,.5)),latency_p95_ms=float(np.quantile(latency,.95)),latency_mean_ms=float(np.mean(latency)))
    for k,(tp,fp,fn) in counts.items():result[k+'_f1']=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 1;result[k+'_counts']=dict(tp=tp,fp=fp,fn=fn)
    return result

def run():
    OUT.mkdir(exist_ok=True,parents=True)
    path=ROOT/'data/v23/final/ood.json';manifest=read_json(path.with_name('ood_manifest.json'))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['sha256']
    rows=read_json(path);records=[]
    def evaluate(service,row):
        rule=extract(service,row['text']);live=extract(service,row['text'],True)
        raw=live.get('model_candidate') or {'events':[]};start=time.perf_counter()
        try:grounded(raw,row['text'],service.state);passed=True
        except Exception:passed=False
        check_ms=(time.perf_counter()-start)*1000
        try:grounded(rule['candidate'],row['text'],service.state);rule_pass=True
        except Exception:rule_pass=False
        # Rejection is abstention, never credit rule fallback as LLM success.
        arms={'rules':dict(candidate=rule['candidate'],latency_ms=rule['latency_ms'],grounded_pass=rule_pass,fallback=False),
              'deepseek_raw':dict(candidate=raw,latency_ms=live['latency_ms'],grounded_pass=passed,fallback=False),
              'deepseek_grounded':dict(candidate=raw if passed else {'events':[]},latency_ms=live['latency_ms']+check_ms,grounded_pass=passed,fallback=not passed)}
        return dict(**row,arms=arms,live_success=live['live_success'],json_received=live['json_received'],error=live['error'],
                    deployed_fallback_candidate=live['candidate'] if not passed else None)
    with tempfile.TemporaryDirectory() as tmp:
        service=Service(Path(tmp)/'ood.sqlite')
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures=[executor.submit(evaluate,service,row) for row in rows]
            for future in as_completed(futures):
                records.append(future.result());records.sort(key=lambda r:r['id'])
                (OUT/'ood_records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
                print('Evaluated',len(records),'/',len(rows),flush=True)
        service.db.engine.dispose()
    methods=('rules','deepseek_raw','deepseek_grounded')
    result=dict(manifest=manifest,model=os.environ.get('DISASTER_MODEL'),results=[summary(records,m) for m in methods],
        categories={c:[summary([r for r in records if r['category']==c],m) for m in methods] for c in sorted({r['category'] for r in records})},
        caveats=['No independent annotator; this is held-out developer challenge coverage, not evidence of real-world generalization.',
                 'Raw and grounded arms reuse one API output per text. Grounding rejection is scored as abstention, with operational fallback recorded separately.',
                 'Raw latency includes extraction wrapper validation/fallback overhead; grounded latency adds separately measured validation. Network dominates.',
                 'Grounding checks evidence presence, not full semantic entailment or negation; passing does not guarantee correct events.'])
    (OUT/'ood_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Evaluation complete',flush=True)

if __name__=='__main__':run()
