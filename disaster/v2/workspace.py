"""Business-facing contracts: no raw snapshots, model settings or solver diagnostics."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime,timedelta
from types import SimpleNamespace
import secrets,time,logging
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field,ConfigDict
from typing import Literal
from disaster.core import ROOT,read_json
from disaster.v2.intake import Event,extract
from disaster.v2.grounded_explanation import explain

router=APIRouter(prefix='/api/workspace')
log=logging.getLogger(__name__)
EVENT_NAMES={'disaster_report':'灾情报告','casualty_update':'新增伤亡','information_correction':'信息修正','road_closure':'道路中断','resource_failure':'资源故障','reinforcement':'增援到达','risk_change':'风险变化','secondary_risk':'次生风险','sensor_delay':'监测延迟','recovery':'恢复安置','uncertain_report':'待核实信息'}
def pick(row,keys):return {k:deepcopy(row[k]) for k in keys.split() if k in row}
def label(value):return str(value).replace('模拟','')
def stamp(minute):return (datetime(2024,8,3,9)+timedelta(minutes=minute)).strftime('%H:%M')
def policies(rows):return [pick(r,'id title section text url scope') for r in rows]
def assignment(row):
    output=pick(row,'resource task type name node depart arrival start end path geometry provisional')
    output['name']='提前部署' if row.get('provisional') else label(row.get('name','救援任务'))
    return output

def present(service,saved=None):
    raw=service.view(saved);f=raw['forecast']
    result=pick(raw,'minute time revision metrics resource_names sensor_types casualties scenario_cursor')
    result['environment']='历史资料回放' if raw.get('environment_mode')=='historical' else '演练模式'
    result['nodes']=[dict(pick(r,'id kind lat lon population'),name=label(r['name'])) for r in raw['nodes']]
    result['roads']=[pick(r,'id u v minutes blocked geometry') for r in raw['roads']]
    result['resources']=[dict(pick(r,'id type node status available_at'),name=label(r['name']),active=assignment(r['active']) if r.get('active') else None) for r in raw['resources']]
    result['tasks']=[dict(pick(r,'id node priority requirements status release deadline duration actual_start completed_at'),name=label(r['name'])) for r in raw['tasks']]
    result['observations']=[pick(r,'station_id minute timestamp type value unit') for r in raw['observations'][-72:]]
    result['health']=[dict(name=('监测点 '+r['source_id'].split(':')[-2]+' · '+raw['sensor_types'].get(r['source_id'].split(':')[-1],{}).get('label','其他数据')),
        status={'FRESH':'正常','DELAYED':'延迟','STALE':'过期','OFFLINE':'离线'}.get(r['source_status'],'待核实'),age_seconds=r['freshness_seconds'],missing_rate=r['missing_rate']) for r in raw.get('data_health',[])]
    result['forecast']=pick(f,'score level eligible_for_decision cadence_minutes risk zones')
    for key in ('series','station_series'):result['forecast'][key]={k:pick(v,'history forecast unit data_status') for k,v in f.get(key,{}).items()}
    plan=raw.get('plan',{});tasks={r['id']:r['name'] for r in result['tasks']};resources={r['id']:r['name'] for r in result['resources']}
    result['plan']={'assignments':[assignment(r) for r in plan.get('assignments',[])],
        'message':'已采用备用调度方案，请复核任务安排' if plan.get('degraded') else '当前任务安排已更新' if plan else '等待生成任务安排',
        'gaps':[dict(name=label(r['name']),requirements=r['requirements'],deficits=r['deficits'],reason='资源能力或时间安排暂不能同时满足，请补充支援或调整任务时限。') for r in plan.get('gaps',[])]}
    result['timeline']=[]
    for event in raw.get('events',[])[-40:]:
        kind=event['kind']
        if kind in EVENT_NAMES:message=EVENT_NAMES[kind]+'已确认'
        elif kind=='replan':message='救援任务安排已更新'
        elif kind=='rejected':message='值守人员退回了一条待核实报告'
        elif kind=='scenario':message='已开始阶段演练'
        elif kind=='confirmed':message='灾情报告已确认'
        else:continue
        result['timeline'].append(dict(time=stamp(event['minute']),message=message))
    trace=raw.get('decision_traces',[])
    result['changes']=[]
    if trace:
        t=trace[-1]
        result['changes']=[dict(resource=resources.get(a['resource'],'救援资源'),task=tasks.get(a['task'],'任务'),before=stamp(a['before']),after=stamp(a['after'])) for a in t.get('matched_arrival_changes',[])]
        result['changes_summary']=dict(new=len(t.get('added',[])),reassigned=t.get('stability',{}).get('reassignments',0),withdrawn=t.get('stability',{}).get('withdrawals',0))
    else:result['changes_summary']=dict(new=0,reassigned=0,withdrawn=0)
    result['reports']=[dict(time=stamp(r['minute']),location=next((n['name'] for n in result['nodes'] if n['id']==r['node']),'待核实地点'),missing=r.get('missing'),injured=r.get('injured')) for r in raw.get('situation_reports',{}).values()]
    return result

def service(request):return request.app.state.service
def drafts(request):
    if not hasattr(request.app.state,'workspace_drafts'):request.app.state.workspace_drafts=OrderedDict()
    return request.app.state.workspace_drafts
def draft(request,candidate):
    svc=service(request)
    with svc.lock:
        cache=drafts(request);token=secrets.token_urlsafe(24);cache[token]=(time.monotonic(),deepcopy(candidate))
        while len(cache)>32:cache.popitem(last=False)
    return dict(token=token,text=candidate['text'],events=candidate['candidate']['events'],
        recognition='智能识别' if candidate.get('live_success') else '辅助识别，请逐项核实',clauses=policies(candidate.get('clauses',[])))

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Report(Strict):
    text:str=Field(min_length=1,max_length=2800)
    location:str|None=None
class Review(Strict):token:str=Field(min_length=20,max_length=64);events:list[Event]=Field(min_length=1,max_length=12)
class Token(Strict):token:str=Field(min_length=20,max_length=64)
class Advance(Strict):minutes:int=Field(default=10,ge=1,le=60)
class Dispatch(Strict):preference:Literal['balanced','urgent']='balanced'
class Road(Strict):road:str

@router.get('/state')
def state(request:Request):
    with service(request).lock:return present(service(request))
@router.get('/policies')
def clauses(request:Request,q:str='搜救 医疗 道路 安置'):return policies(service(request).retrieve(q[:300]))
@router.get('/stages')
def stages():return [pick(r,'title minute') for r in read_json(ROOT/'data/v23/event_scenario.json')['stages']]
@router.get('/history')
def history(request:Request):return [dict(id=r['revision'],time=stamp(r['minute'])) for r in service(request).db.history()[-60:]][::-1]
@router.get('/history/{revision}')
def historical(request:Request,revision:int):
    svc=service(request)
    with svc.lock:
        saved=svc.db.at(revision)
        if not saved:raise HTTPException(404,'未找到这条历史记录')
        return present(svc,saved)
@router.post('/extract')
def extract_report(request:Request,body:Report):
    svc=service(request)
    with svc.lock:copy=SimpleNamespace(state=deepcopy(svc.state),retrieve=svc.retrieve)
    text=body.text
    if body.location:
        location=next((n for n in copy.state['nodes'] if n['id']==body.location),None)
        if location is None:raise HTTPException(422,'请选择有效的报告地点')
        text=location['name']+'：'+text
    return draft(request,extract(copy,text,True))
@router.post('/confirm')
def confirm(request:Request,body:Review):
    svc=service(request)
    with svc.lock:
        item=drafts(request).get(body.token)
        if not item or time.monotonic()-item[0]>900:raise HTTPException(409,'待审报告已过期，请重新识别或准备阶段')
        candidate=deepcopy(item[1])
        if candidate['revision']!=svc.state['revision']:raise HTTPException(409,'态势已经变化，请重新核对这条报告')
        candidate['candidate']={'events':[e.model_dump() for e in body.events]}
        try:svc.confirm_batch(candidate)
        except (ValueError,KeyError,TypeError):raise HTTPException(422,'请核实地点、人数、增减口径及关联道路或资源后重试')
        drafts(request).pop(body.token,None)
        return {'message':'报告已确认，任务安排已更新'}
@router.post('/reject')
def reject(request:Request,body:Token):
    svc=service(request)
    with svc.lock:
        item=drafts(request).pop(body.token,None)
        if not item:raise HTTPException(409,'待审报告已失效')
        svc.reject(item[1]);return {'message':'已退回待核实报告'}
@router.post('/advance')
def advance(request:Request,body:Advance):service(request).advance(body.minutes);return {'message':'演练时间已推进'}
@router.post('/dispatch')
def dispatch(request:Request,body:Dispatch):
    svc=service(request)
    with svc.lock:svc.optimize(dict(svc.state['settings'],objective_mode='lexicographic' if body.preference=='urgent' else 'weighted'))
    return {'message':'已更新救援任务安排'}
@router.post('/road')
def road(request:Request,body:Road):
    try:service(request).block(body.road)
    except ValueError:raise HTTPException(422,'请选择有效的通行路段')
    return {'message':'道路状态已更新'}
@router.post('/start')
def start(request:Request):service(request).start_scenario();return {'message':'阶段演练已开始'}
@router.post('/prepare')
def prepare(request:Request):
    try:return draft(request,service(request).prepare_stage())
    except ValueError:raise HTTPException(422,'请先开始演练，或检查是否已经完成全部阶段')
@router.post('/explain')
def explanation(request:Request):
    svc=service(request);raw=explain(svc,True)
    with svc.lock:
        if svc.state['revision']!=raw['revision']:raise HTTPException(409,'任务安排已变化，请重新生成说明')
        resources={r['id']:r['name'] for r in svc.state['resources']};tasks={t['id']:t['name'] for t in svc.state['tasks']}
        return dict(statements=[f"{resources.get(a['resource'],'救援资源')}前往{label(tasks.get(a['task'],'任务地点'))}，预计{stamp(a['arrival'])}到达。" for a in raw['allocations']],
            citations=[{'text':p['quote']} for p in raw['policy_support']],notice='行动依据供值守人员复核，预计到达时间会随道路与任务变化更新。')
