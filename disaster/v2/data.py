from pathlib import Path
from datetime import datetime, timedelta, timezone
import csv, math, random
from sqlalchemy import create_engine, Column, Integer, String, Float, JSON, UniqueConstraint, select, delete
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from disaster.core import ROOT, read_json, write_json

class Base(DeclarativeBase): pass
class Observation(Base):
    __tablename__='sensor_observations'
    id=Column(Integer,primary_key=True)
    station_id=Column(String); minute=Column(Integer); timestamp=Column(String)
    type=Column(String); value=Column(Float); unit=Column(String); quality=Column(String)
    lat=Column(Float); lon=Column(Float); provenance=Column(String,default='simulated')
    __table_args__=(UniqueConstraint('station_id','minute','type'),)
class Record(Base):
    __tablename__='state_snapshots'
    id=Column(Integer,primary_key=True); minute=Column(Integer); revision=Column(Integer); payload=Column(JSON)
class Event(Base):
    __tablename__='hazard_events'
    id=Column(String,primary_key=True); minute=Column(Integer); payload=Column(JSON)
class Road(Base):
    __tablename__='road_edges'
    id=Column(String,primary_key=True); payload=Column(JSON)
class Resource(Base):
    __tablename__='resources'
    id=Column(String,primary_key=True); payload=Column(JSON)
class TaskRow(Base):
    __tablename__='tasks'
    id=Column(String,primary_key=True); payload=Column(JSON)
class Plan(Base):
    __tablename__='dispatch_plans'
    id=Column(Integer,primary_key=True); minute=Column(Integer); payload=Column(JSON)
class Policy(Base):
    __tablename__='policy_clauses'
    id=Column(String,primary_key=True); payload=Column(JSON)
class Log(Base):
    __tablename__='decision_logs'
    id=Column(Integer,primary_key=True); minute=Column(Integer); payload=Column(JSON)

KINDS={'rainfall':('降雨强度','mm/h',0,200),'water_level':('河道水位','m',0,30),
       'soil_moisture':('土壤含水率','%',0,100),'displacement':('边坡位移','mm',0,500)}
RESOURCE_NAMES={'rescue_team':'搜救队','medical_team':'医疗队','engineering_team':'工程队','ambulance':'救护车',
                'excavator':'挖掘机','drone':'无人机','supply_vehicle':'物资车'}

def prepare():
    path=ROOT/'data/v2'
    path.mkdir(parents=True,exist_ok=True)
    if (path/'scenario.json').exists(): return
    rng=random.Random(906)
    names=['姑咱集结点','康定支援基地','北侧前置点','日地道路节点','日地村模拟搜救区','下游转移区','医疗救护点','集中安置点','上游监测区','泸定增援点']
    coords=[(30.109,102.180),(30.051,102.042),(30.137,102.190),(30.093,102.192),(30.084,102.209),
            (30.061,102.217),(30.080,102.162),(30.045,102.177),(30.111,102.234),(29.973,102.229)]
    old=read_json(ROOT/'data/scenario.json')
    nodes=[dict(id=f'N{i}',name=name,lat=coords[i][0],lon=coords[i][1],population=250+i*83,
                provenance='simulated_coordinates',kind='hospital' if i==6 else 'shelter' if i==7 else 'station' if i in (2,8) else 'village') for i,name in enumerate(names)]
    roads=[dict(id=f'RD{i:02}',**e,blocked=False) for i,e in enumerate(old['roads'])]
    resources=[]
    for kind,count in [('rescue_team',6),('medical_team',4),('engineering_team',3),('ambulance',4),('excavator',3),('drone',3),('supply_vehicle',3)]:
        for i in range(count):
            resources.append(dict(id=f'{kind[:3].upper()}{i+1:02}',type=kind,name=f'{RESOURCE_NAMES[kind]} {i+1:02}',
                node=['N0','N1','N2','N6'][i%4],capacity=1,status='idle',available_at=40 if i==count-1 else 0,queue=[]))
    specs=[('人员搜救','N4',{'rescue_team':2,'drone':1},1,0,28,18),('伤员救治转运','N5',{'medical_team':1,'ambulance':2},1,0,32,20),
           ('道路抢通','N3',{'engineering_team':1,'excavator':1},2,0,40,15),('安置物资配送','N7',{'supply_vehicle':1},2,0,50,12),
           ('上游巡查','N8',{'drone':1,'rescue_team':1},2,10,45,15),('受困群众转移','N4',{'rescue_team':2,'ambulance':1},1,20,50,20),
           ('下游清障','N5',{'engineering_team':1,'excavator':2},2,20,70,20),('紧急医疗支援','N4',{'medical_team':2,'ambulance':1},1,30,65,15),
           ('临时安置保障','N7',{'rescue_team':1,'supply_vehicle':1},2,40,85,15),('上游应急勘察','N8',{'engineering_team':1,'drone':1},2,45,90,15),
           ('河谷搜索','N5',{'rescue_team':2,'drone':1},1,60,100,20),('补给运输','N6',{'supply_vehicle':2},3,70,120,10)]
    tasks=[dict(id=f'V{i+1:02}',name=n,node=node,requirements=req,priority=p,release=rel,deadline=dead,duration=dur,
                status='pending',actual_start=None,completed_at=None,provenance='simulated') for i,(n,node,req,p,rel,dead,dur) in enumerate(specs)]
    write_json(path/'scenario.json',dict(nodes=nodes,roads=roads,resources=resources,tasks=tasks,
              provenance='模拟传感器、坐标、资源与任务；康定地区仅作为地理背景',seed=906))
    raw=path/'raw';raw.mkdir(exist_ok=True)
    for kind,(label,unit,low,high) in KINDS.items():
        with (raw/f'{kind}.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['station_id','minute','timestamp','type','value','unit','lat','lon','provenance']);w.writeheader()
            for station,node in [('S01',nodes[2]),('S02',nodes[4]),('S03',nodes[8])]:
                offset=int(station[-1])
                for minute in range(-1440,181,5):
                    storm=math.exp(-((minute-40)/145)**2)
                    values={'rainfall':max(0,5+40*storm+3*math.sin(minute/40+offset)+rng.gauss(0,1.4)),
                        'water_level':2+2.2*storm+.15*math.sin(minute/70)+rng.gauss(0,.04),
                        'soil_moisture':45+34*storm+rng.gauss(0,.6),
                        'displacement':4+19*storm+math.sin(minute/100)+rng.gauss(0,.3)}
                    w.writerow(dict(station_id=station,minute=minute,timestamp=(datetime(2024,8,3,9)+timedelta(minutes=minute)).isoformat()+'+08:00',
                        type=kind,value=round(values[kind],3),unit=unit,lat=node['lat'],lon=node['lon'],provenance='simulated'))

class Database:
    def __init__(self,path=None):
        prepare()
        self.path=Path(path or ROOT/'data/v2/platform.sqlite')
        self.engine=create_engine(f'sqlite:///{self.path}',connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(self.engine,expire_on_commit=False)

    def ingest(self, rows):
        accepted=duplicates=0; errors=[]
        with self.sessions.begin() as db:
            for index,row in enumerate(rows):
                try:
                    kind=row['type']; spec=KINDS[kind];value=float(row['value']);minute=int(row['minute'])
                    if isinstance(row['minute'],bool) or float(row['minute'])!=minute:raise ValueError('分钟必须为整数')
                    if not isinstance(row['station_id'],str) or not 1<=len(row['station_id'])<=64:raise ValueError('站点编号无效')
                    if not isinstance(row.get('provenance','user_import'),str) or len(row.get('provenance','user_import'))>100:raise ValueError('来源标签无效')
                    if not math.isfinite(value) or not spec[2]<=value<=spec[3]: raise ValueError('数值越界')
                    if row['unit']!=spec[1]: raise ValueError('单位不匹配')
                    lat,lon=float(row['lat']),float(row['lon'])
                    if not (-90<=lat<=90 and -180<=lon<=180):raise ValueError('坐标越界')
                    observed_at=datetime.fromisoformat(row['timestamp'])
                    expected=datetime(2024,8,3,9,tzinfo=timezone(timedelta(hours=8)))+timedelta(minutes=minute)
                    if observed_at.tzinfo is None or observed_at!=expected:raise ValueError('时间戳必须含时区并与模拟分钟一致')
                    exists=db.scalar(select(Observation.id).where(Observation.station_id==row['station_id'],Observation.minute==minute,Observation.type==kind))
                    if exists:duplicates+=1;continue
                    db.add(Observation(station_id=row['station_id'],minute=minute,timestamp=row['timestamp'],type=kind,value=value,unit=spec[1],
                        quality='valid',lat=lat,lon=lon,provenance=row.get('provenance','user_import')))
                    db.flush();accepted+=1
                except (KeyError,ValueError,TypeError) as exc: errors.append({'row':index,'reason':str(exc)})
        return dict(accepted=accepted,duplicates=duplicates,rejected=len(errors),errors=errors[:30])

    def bootstrap(self):
        with self.sessions() as db:
            exists=db.scalar(select(Observation.id).limit(1))
        if not exists:
            for path in (ROOT/'data/v2/raw').glob('*.csv'):
                with path.open(encoding='utf-8') as f:self.ingest(list(csv.DictReader(f)))
        with self.sessions.begin() as db:
            for clause in read_json(ROOT/'data/policies.json'):db.merge(Policy(id=clause['id'],payload=clause))

    def observations(self,minute,limit=1440):
        with self.sessions() as db:
            rows=db.scalars(select(Observation).where(Observation.minute<=minute,Observation.minute>=minute-limit).order_by(Observation.minute)).all()
            return [{c.name:getattr(r,c.name) for c in Observation.__table__.columns} for r in rows]

    def load(self):
        with self.sessions() as db:
            row=db.scalar(select(Record).order_by(Record.id.desc()).limit(1))
            return row.payload if row else None

    def save(self,state):
        with self.sessions.begin() as db:
            db.add(Record(minute=state['minute'],revision=state['revision'],payload=state))
            for model,key in [(Road,'roads'),(Resource,'resources'),(TaskRow,'tasks')]:
                db.execute(delete(model))
                for item in state[key]:db.add(model(id=item['id'],payload=item))
            for event in state['events']:db.merge(Event(id=event['id'],minute=event['minute'],payload=event))
            if state.get('plan'):db.add(Plan(minute=state['minute'],payload=state['plan']))
            db.add(Log(minute=state['minute'],payload={'revision':state['revision'],'message':state['events'][-1]['text'] if state['events'] else '初始化'}))

    def history(self):
        with self.sessions() as db:
            return [{'id':r.id,'minute':r.minute,'revision':r.revision} for r in db.scalars(select(Record).order_by(Record.id))]

    def at(self,revision):
        with self.sessions() as db:
            r=db.scalar(select(Record).where(Record.revision==revision).order_by(Record.id.desc()).limit(1))
            return r.payload if r else None
