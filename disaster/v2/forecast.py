import time
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from disaster.v2.data import KINDS

class Forecaster:
    def __init__(self):self.models={};self.evaluation=[]
    def fit(self,observations):
        # Train/validation wholly before simulation t=0; chronological holdout.
        for kind in KINDS:
            series=[r['value'] for r in observations if r['type']==kind and r['station_id']=='S01' and r['minute']<0]
            a=np.array(series);lag=12
            X=np.array([a[i-lag:i] for i in range(lag,len(a))]);y=a[lag:]
            split=int(len(y)*.75)
            models={'AR':Ridge(alpha=1),'Gradient Boosting':HistGradientBoostingRegressor(max_iter=60,max_leaf_nodes=8,random_state=906)}
            for name in ['Persistence',*models]:
                begin=time.perf_counter()
                if name=='Persistence':pred=X[split:,-1]
                else:
                    model=models[name];model.fit(X[:split],y[:split]);pred=model.predict(X[split:])
                error=pred-y[split:]
                self.evaluation.append(dict(type=kind,model=name,mae=float(np.abs(error).mean()),rmse=float(np.sqrt((error**2).mean())),
                    milliseconds=(time.perf_counter()-begin)*1000,train_samples=split,test_samples=len(y)-split))
            for name,model in models.items():model.fit(X,y)
            self.models[kind]=models
    def predict(self,observations,minute,model='AR'):
        result={};risk=[]
        for kind in KINDS:
            rows=[r for r in observations if r['type']==kind and r['station_id']=='S01' and r['minute']<=minute]
            values=[r['value'] for r in rows][-12:]
            future=[];start=time.perf_counter()
            for h in range(1,13):
                val=values[-1] if model=='Persistence' else float(self.models[kind][model].predict(np.array([values[-12:]]))[0])
                val=float(np.clip(val,KINDS[kind][2],KINDS[kind][3]));values.append(val)
                future.append({'minute':minute+5*h,'value':round(val,3)})
            result[kind]=dict(history=[{'minute':r['minute'],'value':r['value']} for r in rows[-36:]],forecast=future,
                              unit=KINDS[kind][1],inference_ms=(time.perf_counter()-start)*1000)
        thresholds={'rainfall':50,'water_level':5,'soil_moisture':85,'displacement':30}
        weights={'rainfall':.35,'water_level':.25,'soil_moisture':.2,'displacement':.2}
        components=[]
        for kind in KINDS:
            value=result[kind]['forecast'][-1]['value']
            components.append(dict(type=kind,name=KINDS[kind][0],weight=weights[kind],value=value,threshold=thresholds[kind],contribution=min(1,value/thresholds[kind])*weights[kind]))
        for h in range(12):
            score=sum(min(1,result[k]['forecast'][h]['value']/thresholds[k])*weights[k] for k in KINDS)
            risk.append(dict(minute=minute+(h+1)*5,score=round(score,3)))
        score=max(r['score'] for r in risk)
        return dict(model=model,series=result,risk=risk,score=score,level='高风险' if score>=.7 else '中风险' if score>=.45 else '低风险',
                    components=components,evaluation=self.evaluation,description='模拟数据上的加权风险指数，非泥石流概率；阈值为实验设定')
