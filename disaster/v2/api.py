from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal
import csv
from disaster.core import ROOT, read_json
from disaster.v2.service import Service

@asynccontextmanager
async def lifespan(app):
    app.state.service=Service()
    yield

app=FastAPI(title='DisasterResponseAI V2',lifespan=lifespan)
class Step(BaseModel):minutes:int=Field(default=10,ge=1,le=60)
class Settings(BaseModel):
    horizon:int=Field(default=60,ge=30,le=120)
    stability:int=Field(default=20,ge=0,le=200)
    forecast:bool=True
    response_weight:int=Field(default=10,ge=0,le=100)
class Text(BaseModel):text:str=Field(min_length=1,max_length=3000);live:bool=False
class WhatIf(BaseModel):blocked:str|None=None;additional:bool=False
class Import(BaseModel):rows:list[dict]=Field(max_length=10000)
class Reset(BaseModel):
    routing_mode:Literal['simulated','osm']|None=None
    environment_mode:Literal['synthetic','historical']|None=None
    risk_mode:Literal['rule','empirical']|None=None

def service():return app.state.service

@app.get('/api/state')
def state():
    with service().lock:return service().view()
@app.post('/api/advance')
def advance(body:Step):
    try:return service().advance(body.minutes)
    except ValueError as e:raise HTTPException(422,str(e))
@app.post('/api/reset')
def reset(body:Reset|None=None):
    try:return service().reset(body.routing_mode if body else None,body.environment_mode if body else None,body.risk_mode if body else None)
    except (ValueError,FileNotFoundError) as e:raise HTTPException(422,str(e))
@app.post('/api/optimize')
def optimize(body:Settings):return service().optimize(body.model_dump())
@app.post('/api/roads/{road_id}/block')
def block(road_id:str):
    try:return service().block(road_id)
    except ValueError as e:raise HTTPException(422,str(e))
@app.post('/api/resources/{resource_id}/fail')
def fail(resource_id:str):
    try:return service().fail_resource(resource_id)
    except ValueError as e:raise HTTPException(422,str(e))
@app.get('/api/forecast')
def forecast(model:str='AR'):
    if model not in ('AR','Persistence','Gradient Boosting'):raise HTTPException(422,'未知模型')
    with service().lock:return service().forecast_result(model)
@app.get('/api/policies')
def policies(q:str='人员搜救 医疗救治 道路运输',mode:str='hybrid'):return service().retrieve(q,mode)
@app.get('/api/catalog')
def catalog():return {'sources':read_json(ROOT/'data/sources.json'),'facts':read_json(ROOT/'data/case_facts.json')}
@app.get('/api/experiments')
def experiments():
    folder=ROOT/'results/v21'
    if not (folder/'dispatch_metrics.csv').exists():return {'rows':[],'config':{}}
    with (folder/'dispatch_metrics.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    return {'rows':rows,'config':read_json(folder/'experiment_config.json')}
@app.get('/api/research')
def research():
    folder=ROOT/'results/v22';result={}
    for name in ('scheduling','stress','forecast_synthetic','forecast_historical','ablation'):
        path=folder/(name+'.csv')
        if path.exists():
            with path.open(encoding='utf-8-sig') as f:result[name]=list(csv.DictReader(f))
    return result
@app.get('/api/environment')
def environment():
    path=ROOT/'data/gold/environment_manifest.json'
    return read_json(path) if path.exists() else {'native_rows':0,'hourly_rows':0,'sources':[]}
@app.get('/api/research/export/{name}')
def research_export(name:Literal['scheduling','stress','forecast_synthetic','forecast_historical','ablation']):
    path=ROOT/'results/v22'/(name+'.csv')
    if not path.exists():raise HTTPException(404,'实验尚未运行')
    return FileResponse(path,media_type='text/csv',filename=name+'.csv')
@app.post('/api/extract')
def extract(body:Text):
    try:return service().extract(body.text,body.live)
    except Exception as e:raise HTTPException(422,f'提取失败：{type(e).__name__}，状态未提交')
@app.post('/api/confirm')
def confirm(body:dict):
    try:return service().confirm(body)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e))
@app.post('/api/reject')
def reject(body:dict):
    try:return service().reject(body)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e))
@app.post('/api/whatif')
def whatif(body:WhatIf):return service().whatif(body.blocked,body.additional)
@app.get('/api/history')
def history():return service().db.history()
@app.get('/api/history/{revision}')
def historical(revision:int):
    saved=service().db.at(revision)
    if not saved:raise HTTPException(404,'历史快照不存在')
    return service().view(saved)
@app.post('/api/ingest')
def ingest(body:Import):
    with service().lock:
        if service().state.get('environment_mode')=='historical':raise HTTPException(422,'历史产品回放使用已核验的不可变文件；请切换模拟环境后测试观测导入')
        report=service().db.ingest(body.rows,received_minute=service().state['minute']);previous=service().state['forecast']['level']
        service().refresh();service().event(f"数据接入：新增{report['accepted']}，重复{report['duplicates']}，拒绝{report['rejected']}",'ingestion')
        if report['accepted'] and service().state['forecast']['level']!=previous:service().replan(['数据接入引起风险等级变化'])
        service().save()
        return report
@app.get('/api/health')
def health():return {'status':'ok','revision':service().state['revision']}

frontend=ROOT/'frontend'
app.mount('/assets',StaticFiles(directory=frontend),name='assets')
@app.get('/')
def index():return FileResponse(frontend/'index.html')
