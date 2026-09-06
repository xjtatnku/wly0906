"""Create explicitly synthetic scenario and independently specified extraction labels."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from disaster.core import ROOT, write_json


def main():
    names = ['指挥点', '西侧集结点', '北侧集结点', '道路交汇点', '村落甲', '村落乙', '医疗点', '安置点', '上游点', '增援入口']
    xy = [(0,1),(0,3),(2,4),(2,2),(4,3),(5,1),(2,0),(4,0),(6,4),(0,0)]
    nodes = [dict(id=f'N{i}', name=name, x=xy[i][0], y=xy[i][1], provenance='simulated') for i,name in enumerate(names)]
    edges = [(0,1,6),(0,3,8),(0,9,5),(1,2,8),(1,3,7),(2,3,5),(2,4,10),(3,4,6),(3,5,10),
             (3,6,6),(4,5,5),(4,8,12),(5,7,6),(5,8,8),(6,7,10),(6,9,8)]
    teams = [dict(id=f'R{i+1}', capability=cap, node=node, available_at=at) for i,(cap,node,at) in enumerate([
        ('rescue','N0',0),('rescue','N1',0),('rescue','N2',0),('medical','N6',0),
        ('medical','N0',0),('engineering','N1',0),('rescue','N9',10000),('engineering','N9',10000)])]
    specs = [
        ('N4','rescue',2,1,18,25,0),('N5','medical',1,1,20,20,0),('N8','rescue',1,1,25,20,0),
        ('N3','engineering',1,2,35,15,0),('N7','medical',1,2,40,15,0),('N5','rescue',1,2,45,20,0),
        ('N4','engineering',1,1,30,20,5),('N8','medical',1,1,45,20,5),
        ('N5','rescue',2,1,38,30,20),('N4','medical',1,1,40,25,20),
        ('N8','engineering',1,2,65,20,20),('N7','rescue',1,2,75,15,20)]
    tasks = [dict(id=f'T{i+1:02}',node=n,capability=c,required=r,priority=p,deadline=d,duration=du,
                  release=re,description=f'{names[int(n[1:])]}：'+{'rescue':'人员搜救','medical':'医疗救治','engineering':'道路保障'}[c],citations=[])
             for i,(n,c,r,p,d,du,re) in enumerate(specs)]
    events = [dict(id='E0',minute=0,text='初始灾情：村落与上游出现搜救及医疗需求。',tasks=[t for t in tasks if t['release']==0]),
              dict(id='E1',minute=5,text='道路交汇点至村落甲道路中断，出现工程与医疗需求。',blocked_roads=[['N3','N4']],tasks=[t for t in tasks if t['release']==5]),
              dict(id='E2',minute=20,text='村落乙新增紧急搜救需求，村落甲需要医疗支援。',tasks=[t for t in tasks if t['release']==20]),
              dict(id='E3',minute=40,text='增援入口新增一支搜救队、一支工程队。',activate_teams=['R7','R8'],tasks=[])]
    for e in events:
        e['provenance']='simulated'
    write_json(ROOT/'data/scenario.json',dict(title='康定案例背景下的模拟调度场景',provenance='simulated',
        warning='节点、队伍、道路权重、任务、分钟与四阶段均为模拟；非真实康定路网或指挥记录。',
        horizon=180,nodes=nodes,roads=[dict(u=f'N{u}',v=f'N{v}',minutes=w,provenance='simulated') for u,v,w in edges],teams=teams,events=events))
    # Gold labels are authored here, not outputs copied from the extraction implementation.
    labels = []
    examples = [
        ('村落甲发现人员被困，需要搜救。','N4','rescue'),('村落乙有人受伤，请派医疗队。','N5','medical'),
        ('上游点需要工程队清理塌方。','N8','engineering'),('安置点有伤员等待救治。','N7','medical'),
        ('道路交汇点有人员失联，开展搜救。','N3','rescue'),('西侧集结点需要抢修道路。','N1','engineering'),
        ('北侧集结点发现被困人员。','N2','rescue'),('医疗点有人受伤。','N6','medical'),
        ('增援入口需要道路抢通。','N9','engineering'),('指挥点需要医疗支援。','N0','medical'),
        ('村落甲需要转移受困群众。','N4','rescue'),('村落乙发生塌方，工程队支援。','N5','engineering'),
        ('上游点多人失联。','N8','rescue'),('安置点需要医疗支援。','N7','medical'),
        ('道路交汇点需工程队抢修。','N3','engineering'),('西侧集结点需要搜救支援。','N1','rescue'),
        ('北侧集结点有伤员。','N2','medical'),('医疗点周边需要道路抢通。','N6','engineering'),
        ('增援入口发现被困人员。','N9','rescue'),('指挥点旁需要清理塌方。','N0','engineering')]
    for i,(text,node,cap) in enumerate(examples):
        labels.append(dict(id=f'Q{i+1:02}',text=text,minute=20,expected=dict(node=node,capability=cap),
                           acceptable_source='national2024' if cap=='medical' else 'sichuan2024',
                           acceptable_citations={'rescue':['sichuan2024-01','sichuan2024-02','national2024-11'],
                                                 'medical':['national2024-12'],
                                                 'engineering':['national2024-10']}[cap],
                           provenance='agent_authored_gold',review='作者人工设定，尚未由用户独立复核；非外部基准'))
    write_json(ROOT/'data/evaluation/extraction_gold.json',labels)
    write_json(ROOT/'data/cache/reviewed.json',[
        dict(text=examples[0][0],review='逐字段对照此固定示例，代理复核；不是模型实测输出',
             candidate=dict(node='N4',capability='rescue',evidence=examples[0][0],event_time=None))])
    print('Created 10 nodes, 8 teams, 12 tasks, 4 events and 20 authored labels.')


if __name__=='__main__':
    main()
