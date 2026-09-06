from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
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
class Text(BaseModel):text:str=Field(min_length=1,max_length=3000);live:bool=False
class WhatIf(BaseModel):blocked:str|None=None;additional:bool=False
class Import(BaseModel):rows:list[dict]=Field(max_length=10000)

def service():return app.state.service

@app.get('/api/state')
def state():
    with service().lock:return service().view()
@app.post('/api/advance')
def advance(body:Step):
    try:return service().advance(body.minutes)
    except ValueError as e:raise HTTPException(422,str(e))
@app.post('/api/reset')
def reset():return service().reset()
@app.post('/api/optimize')
def optimize(body:Settings):return service().optimize(body.model_dump())
@app.post('/api/roads/{road_id}/block')
def block(road_id:str):
    try:return service().block(road_id)
    except ValueError as e:raise HTTPException(422,str(e))
@app.get('/api/forecast')
def forecast(model:str='AR'):
    if model not in ('AR','Persistence','Gradient Boosting'):raise HTTPException(422,'未知模型')
    with service().lock:return service().forecaster.predict(service().db.observations(service().state['minute']),service().state['minute'],model)
@app.get('/api/policies')
def policies(q:str='人员搜救 医疗救治 道路运输',mode:str='hybrid'):return service().retrieve(q,mode)
@app.get('/api/catalog')
def catalog():return {'sources':read_json(ROOT/'data/sources.json'),'facts':read_json(ROOT/'data/case_facts.json')}
@app.post('/api/extract')
def extract(body:Text):
    try:return service().extract(body.text,body.live)
    except Exception as e:raise HTTPException(422,f'提取失败：{type(e).__name__}，状态未提交')
@app.post('/api/confirm')
def confirm(body:dict):
    try:return service().confirm(body)
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
        report=service().db.ingest(body.rows);service().refresh();service().event(f"数据接入：新增{report['accepted']}，重复{report['duplicates']}，拒绝{report['rejected']}",'ingestion');service().save()
        return report
@app.get('/api/health')
def health():return {'status':'ok','revision':service().state['revision']}

frontend=ROOT/'frontend'
app.mount('/assets',StaticFiles(directory=frontend),name='assets')
@app.get('/')
def index():return FileResponse(frontend/'index.html')
