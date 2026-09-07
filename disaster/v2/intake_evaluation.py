"""Paired rule/live evaluation. Model failures are not credited as model predictions."""
import json,os,time,tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from disaster.core import ROOT,read_json
from disaster.v2.service import Service
from disaster.v2.intake import extract


def labels(candidate,key):
    events=(candidate or {}).get('events',[])
    if key=='event_type':return sorted(e.get('event_type','') for e in events)
    if key=='location':return sorted((e.get('event_type',''),e.get('node') or '') for e in events)
    if key=='casualties':return {(e.get('node'),kind,e.get('count_mode'),e[kind]) for e in events for kind in ('missing','injured') if e.get(kind) is not None}
    return {(e.get('event_type'),value) for e in events for value in e.get('road_ids',[])}


def summarize(records,method):
    selected=[r for r in records if r['method']==method];totals={k:[0,0,0] for k in ('casualties','roads')}
    event_ok=location_ok=0
    for row in selected:
        predicted=row['result']['candidate'] if method=='rules' or row['result']['live_success'] else {'events':[]}
        event_ok+=labels(predicted,'event_type')==labels(row['gold'],'event_type')
        location_ok+=labels(predicted,'location')==labels(row['gold'],'location')
        for key in totals:
            p=labels(predicted,key);g=labels(row['gold'],key)
            totals[key]=[a+b for a,b in zip(totals[key],[len(p&g),len(p-g),len(g-p)])]
    result=dict(method=method,samples=len(selected),event_type_accuracy=event_ok/len(selected),location_accuracy=location_ok/len(selected),
        json_valid_rate=sum(r['result']['json_received'] is True for r in selected)/len(selected) if method!='rules' else 1,
        validated_live_rate=sum(r['result']['live_success'] for r in selected)/len(selected) if method!='rules' else None,
        mean_latency_ms=sum(r['result']['latency_ms'] for r in selected)/len(selected))
    for key,(tp,fp,fn) in totals.items():result[key+'_f1']=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 1
    return result


def run():
    folder=ROOT/'results/v23';folder.mkdir(exist_ok=True)
    gold=read_json(ROOT/'data/v23/extraction_gold.json');records=[]
    with tempfile.TemporaryDirectory() as tmp:
        service=Service(Path(tmp)/'intake.sqlite')
        for row in gold:records.append(dict(id=row['id'],method='rules',gold=row['gold'],result=extract(service,row['text'])))
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures={executor.submit(extract,service,row['text'],True):row for row in gold}
            for future in as_completed(futures):
                row=futures[future];records.append(dict(id=row['id'],method='deepseek',gold=row['gold'],result=future.result()))
                (folder/'intake_records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
                print('Live evaluated',sum(r['method']=='deepseek' for r in records),'of',len(gold),flush=True)
        service.db.engine.dispose()
    summary=dict(model=os.environ.get('DISASTER_MODEL'),evaluation='50 human-authored synthetic texts, same inputs, no model tuning on labels',
        failure_policy='Failed live calls get empty predictions in DeepSeek metrics; offline fallback is recorded separately',
        results=[summarize(records,m) for m in ('rules','deepseek')])
    (folder/'intake_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True),flush=True)


if __name__=='__main__':run()
