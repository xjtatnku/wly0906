"""Human-authored experimental stages and 50 extraction labels; no historical claims."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def event(kind,text,node=None,**fields):
    return dict(event_type=kind,node=node,missing=None,injured=None,count_mode='absolute',road_ids=[],resource_ids=[],
                station_ids=[],needs=[],risk_level=None,correction_of=None,evidence=text,**fields) if not fields else {
        **event(kind,text,node),**fields}


def build():
    folder=ROOT/'data/v23';folder.mkdir(exist_ok=True)
    rows=[]
    def add(text,events,category):rows.append(dict(id=f'TXT{len(rows)+1:02}',text=text,gold={'events':events},category=category,provenance='human_authored_synthetic_annotation'))
    for i in range(5):
        n=['N4','N5','N8','N4','N5'][i];m=i+3;j=i+1
        text=[f'{n} 发生泥石流，失联{m}人，受伤{j}人，需要搜救和医疗支援。',
              f'现场通报：{n} 失踪{m}人，伤员{j}人，请开展搜寻和救治。',
              f'{n} 山洪现场，失联 {m} 人、受伤 {j} 人，申请搜救及医疗。',
              f'请向{n}安排搜救与医疗；现场失联{m}人，受伤{j}人。',
              f'{n} 最新核实：失联{m}人；受伤{j}人，需要搜救和医疗支援。'][i]
        # Keep one report sentence here; combinations are labeled separately below.
        text=text.replace('；','，')
        add(text,[event('disaster_report',text,n,missing=m,injured=j,needs=['rescue','medical'])],'disaster')
    for i in range(5):
        text=[f'N4 新增失联{i+1}人，需要搜救。',f'N5 新增受伤{i+1}人，申请医疗支援。',
              f'N8 报告新增失踪{i+1}人。',f'N4 新增伤员{i+1}人，请救治。',f'N5 新增失联{i+1}人，继续搜寻。'][i]
        missing=i+1 if i in (0,2,4) else None;injured=i+1 if i in (1,3) else None
        add(text,[event('casualty_update',text,['N4','N5','N8','N4','N5'][i],missing=missing,injured=injured,count_mode='delta',
                        needs=['rescue'] if i in (0,4) else ['medical'] if i in (1,3) else [])],'delta')
    for i in range(5):
        text=f'{["N4","N5","N8","N4","N5"][i]} 核实后，{["失联人数修正为","受伤人数更正为","失踪人数修正为","失联修正为","伤员更正为"][i]}{i+8}人。'
        add(text,[event('information_correction',text,['N4','N5','N8','N4','N5'][i],missing=i+8 if i in (0,2,3) else None,injured=i+8 if i in (1,4) else None)],'correction')
    for i,phrase in enumerate(['道路RD00已经中断。','RD01封闭，车辆不通。','通报：RD02路段无法通行，请标记中断。','确认RD03道路中断。','RD04发生二次中断。']):
        add(phrase,[event('road_closure',phrase,road_ids=[f'RD{i:02}'])],'road')
    for rid,text in zip(['RES01','MED01','ENG01','AMB01','DRO01'],['RES01资源故障，无法继续执行。','MED01医疗队设备故障。','ENG01发生故障，请重新安排。','AMB01救护车故障。','DRO01报告失效。']):
        add(text,[event('resource_failure',text,resource_ids=[rid])],'failure')
    for rid,text in zip(['RES06','MED04','ENG03','AMB04','DRO03'],['增援RES06已经到达。','MED04增援已到，可以使用。','收到ENG03增援到达报告。','外部增援AMB04到达集结点。','DRO03增援到位。']):
        add(text,[event('reinforcement',text,resource_ids=[rid])],'reinforcement')
    for node,level,kind,text in [('N4','high','risk_change','N4 风险上升到高等级。'),('N5','medium','risk_change','N5 当前风险为中等级。'),
        ('N8','low','risk_change','N8 风险下降到低等级。'),('N4','high','secondary_risk','N4 次生灾害风险升高。'),('N8','high','secondary_risk','N8 出现次生风险，评定高等级。')]:
        add(text,[event(kind,text,node,risk_level=level)],'risk')
    for i,text in enumerate(['S01数据延迟，尚未收到新观测。','S02监测数据迟到。','S03传输延迟，请核对时效。','S01接收延迟。','S02持续延迟，数据未更新。']):
        add(text,[event('sensor_delay',text,station_ids=[['S01','S02','S03','S01','S02'][i]])],'delay')
    for i,text in enumerate(['N7 灾情趋稳，需要安置物资。','N4 进入恢复阶段，申请物资。','N5 灾情趋稳，开展安置。','N7 恢复阶段需要补给。','N8 趋稳，申请安置物资。']):
        add(text,[event('recovery',text,['N7','N4','N5','N7','N8'][i],needs=['supply'])],'recovery')
    for text in ['某地可能有险情，人数和地点均待核实。','信息不明，请等待核查。']:
        add(text,[event('uncertain_report',text)],'ambiguous')
    for indices in [(15,20),(25,30),(17,22,36)]:
        parts=[rows[i] for i in indices];add('；'.join(p['text'] for p in parts),[e for p in parts for e in p['gold']['events']],'simultaneous')
    assert len(rows)==50
    (folder/'extraction_gold.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    stages=[]
    specs=[(0,'灾前环境与风险','N4 强降雨后风险上升至高等级。',event('risk_change','N4 强降雨后风险上升至高等级。','N4',risk_level='high')),
           (5,'首次灾情与救援需求','N4 发生泥石流，失联8人，受伤3人，需要搜救和医疗。',None),
           (12,'新增紧急需求','N4 新增失联5人，需要搜救。',None),
           (20,'封路与数据延迟','RD00道路中断；S02监测数据延迟。',None),
           (27,'执行资源故障','RES01资源故障。',None),
           (35,'外部增援到达','RES06和MED04及DRO03增援到达。',None),
           (42,'邻区次生风险','N8 出现次生灾害高风险，需要搜救。',None),
           (50,'信息修正与二次封路','N4 失联人数修正为15人；RD03发生二次中断。',None),
           (65,'趋稳与恢复','N7 灾情趋稳，需要安置物资。',None)]
    # Reviewed stage candidates are explicit, never labeled as historical truth or model outputs.
    from disaster.v2.intake import rules
    state=json.loads((ROOT/'data/v2/scenario.json').read_text(encoding='utf-8'))
    for minute,title,text,_ in specs:
        stages.append(dict(id=f'STAGE{len(stages)}',minute=minute,title=title,text=text,candidate=rules(text,state).model_dump(),
                           adaptive_resource=minute==27,provenance='reviewed_synthetic_event_stage'))
    (folder/'event_scenario.json').write_text(json.dumps(dict(case='康定8·03案例背景',boundary='全部阶段时间、人数、扰动与资源为模拟；不还原真实指挥',stages=stages),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':build()
