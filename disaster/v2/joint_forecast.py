"""Joint multi-station lag features; native-cadence causal recursive evaluation."""
import hashlib,json,time
from copy import deepcopy
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.multioutput import MultiOutputRegressor
from disaster.v2.data import KINDS

class JointForecaster:
    cache={}
    predictions={}
    def __init__(self,rows,cadence=5):
        before=[r for r in rows if r['minute']<0 and r.get('received_minute',r['minute'])<0]
        self.cadence=cadence;self.keys=sorted({(r['station_id'],r['type']) for r in before});self.lag=12
        matrix,times=self.matrix(before)
        fingerprint=hashlib.sha256(matrix.tobytes()+json.dumps(self.keys).encode()+str(cadence).encode()).hexdigest();self.fingerprint=fingerprint
        if fingerprint in self.cache:
            self.models,self.evaluation,self.reference=self.cache[fingerprint];return
        self.reference=matrix.copy();flat=np.array([matrix[i-12:i].ravel() for i in range(12,len(matrix))]);target=matrix[12:]
        split=int(len(target)*.75)
        self.models={'AR':make_pipeline(StandardScaler(),Ridge(alpha=10)),
                     'Gradient Boosting':MultiOutputRegressor(HistGradientBoostingRegressor(max_iter=35,max_leaf_nodes=6,random_state=906))}
        origins=np.arange(12+split,len(matrix)-11);self.evaluation=[]
        if len(origins)<2:raise ValueError('Insufficient complete multivariate training/validation history')
        for name in ('Persistence',*self.models):
            if name!='Persistence':self.models[name].fit(flat[:split],target[:split])
            context=np.array([matrix[i-12:i] for i in origins]);start=time.perf_counter()
            for step in range(1,13):
                pred=context[:,-1,:] if name=='Persistence' else self.models[name].predict(context[:,-12:,:].reshape(len(origins),-1))
                pred=self.clip(pred);context=np.concatenate([context,pred[:,None,:]],axis=1)
                if step in (1,3,6,12):
                    error=pred-matrix[origins+step-1]
                    for col,(station,kind) in enumerate(self.keys):
                        self.evaluation.append(dict(station_id=station,type=kind,model=name,horizon_minutes=step*cadence,
                            mae=float(abs(error[:,col]).mean()),rmse=float(np.sqrt((error[:,col]**2).mean())),test_samples=len(origins),
                            train_samples=split,features=len(self.keys)*12,cadence_minutes=cadence,milliseconds=(time.perf_counter()-start)*1000,
                            protocol='joint_lags_fixed_train_recursive_common_origins'))
        for model in self.models.values():model.fit(flat,target)
        self.cache[fingerprint]=(self.models,self.evaluation,self.reference)
    def matrix(self,rows,strict=True):
        grouped={}
        for row in rows:grouped.setdefault(row['minute'],{})[row['station_id'],row['type']]=row['value']
        times=sorted(t for t,values in grouped.items() if all(k in values and values[k] is not None for k in self.keys))
        # Training must never bridge missing native intervals.
        if strict and any(b-a!=self.cadence for a,b in zip(times,times[1:])):raise ValueError('Joint panel has gaps; no interpolation permitted')
        return np.array([[grouped[t][k] for k in self.keys] for t in times]),times
    def clip(self,pred):
        return np.column_stack([np.clip(pred[:,i],KINDS[kind][2],KINDS[kind][3]) for i,(_,kind) in enumerate(self.keys)])
    def predict(self,rows,minute,model='AR',risk_mode='rule'):
        visible=[r for r in rows if r['minute']<=minute and r.get('received_minute',r['minute'])<=minute]
        key=(self.fingerprint,model,risk_mode,minute,hashlib.sha256(json.dumps([(r['station_id'],r['type'],r['minute'],r['value']) for r in visible]).encode()).hexdigest())
        if key in self.predictions:return deepcopy(self.predictions[key])
        matrix,times=self.matrix(visible,strict=False)
        if len(matrix)<12:raise ValueError('Insufficient complete joint lag window')
        eligible=minute-times[-1]<=self.cadence*3 and all(b-a==self.cadence for a,b in zip(times[-12:],times[-11:]));context=matrix[-12:].copy();future=[]
        for _ in range(12):
            pred=context[-1:,:] if model=='Persistence' else self.models[model].predict(context[-12:].reshape(1,-1))
            pred=self.clip(pred);future.append(pred[0]);context=np.concatenate([context,pred])
        future=np.array(future);all_series={};zones=[];thresholds={'rainfall':50,'water_level':5,'soil_moisture':85,'displacement':30};weights={'rainfall':.35,'water_level':.25,'soil_moisture':.2,'displacement':.2}
        for i,(station,kind) in enumerate(self.keys):
            all_series[station+':'+kind]=dict(history=[dict(minute=t,value=float(v)) for t,v in zip(times[-36:],matrix[-36:,i])],
                forecast=[dict(minute=times[-1]+(h+1)*self.cadence,value=float(v)) for h,v in enumerate(future[:,i])],unit=KINDS[kind][1],
                data_status='valid' if eligible else 'stale',last_observed_minute=times[-1])
        for station,node in [('S01','N4'),('S02','N5'),('S03','N8')]:
            cols=[i for i,k in enumerate(self.keys) if k[0]==station];scores=[]
            for h in range(12):
                total=0;denom=sum(weights[self.keys[i][1]] for i in cols)
                for i in cols:
                    kind=self.keys[i][1];value=future[h,i]
                    rank=float((self.reference[:,i]<=value).mean()) if risk_mode=='empirical' else min(1,float(value)/thresholds[kind])
                    total+=weights[kind]*rank
                scores.append(total/denom)
            zones.append(dict(station_id=station,node=node,score=round(max(scores),4),eligible=eligible,forecast_scores=scores))
        risk=[dict(minute=times[-1]+(h+1)*self.cadence,score=round(max(z['forecast_scores'][h] for z in zones),4)) for h in range(12)]
        score=max(r['score'] for r in risk);series={kind:all_series['S01:'+kind] for s,kind in self.keys if s=='S01'}
        station_weights=sum(weights[kind] for kind in series)
        components=[]
        for kind in series:
            value=series[kind]['forecast'][0]['value'];col=self.keys.index(('S01',kind))
            rank=float((self.reference[:,col]<=value).mean()) if risk_mode=='empirical' else min(1,value/thresholds[kind])
            weight=weights[kind]/station_weights
            components.append(dict(name=KINDS[kind][0],weight=weight,contribution=weight*rank))
        result=dict(model=model,series=series,station_series=all_series,zones=zones,risk=risk,score=score,
            level='高风险' if score>=.7 else '中风险' if score>=.45 else '低风险',eligible_for_decision=eligible,
            components=components,
            evaluation=[],multistep_evaluation=self.evaluation,risk_mode=risk_mode,cadence_minutes=self.cadence,
            description='Joint multi-station lag features; risk ordering score, not disaster probability',training_sha256=self.fingerprint)
        self.predictions[key]=deepcopy(result)
        return result
