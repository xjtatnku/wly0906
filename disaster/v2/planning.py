"""Multi-resource, multi-task horizon scheduling with sequence-dependent travel."""
import time
import networkx as nx
from ortools.sat.python import cp_model
from disaster.v2.metrics import actionable,disruption

def graph(state):
    g=nx.DiGraph() if state.get('routing_mode')=='osm' else nx.Graph()
    g.add_nodes_from(n['id'] for n in state['nodes'])
    for e in state['roads']:
        if not e['blocked']:g.add_edge(e['u'],e['v'],weight=e['minutes'],road=e)
    return g

def distance(g,a,b):
    cache=g.graph.setdefault('distance_cache',{})
    if a not in cache:cache[a]=nx.single_source_dijkstra_path_length(g,a,weight='weight')
    return int(cache[a][b]) if b in cache[a] else None

def plan(state,horizon=60,stability=20,forecast=True,budget=4,response_weight=10,preposition_mode='multizone'):
    now=state['minute'];g=graph(state);deadline=now+horizon
    tasks=[t for t in state['tasks'] if t['release']<=now and t['status']=='pending']
    # Forecast tasks are explicit provisional jobs, never ground-truth future incidents.
    if forecast and preposition_mode=='legacy' and state.get('forecast',{}).get('eligible_for_decision',True) and state.get('forecast',{}).get('score',0)>=.7 and not any(r.get('active',{}).get('task')=='PREPOSITION' for r in state['resources']) and not all(any(r['type']==kind and r['node']=='N2' and not r.get('active') for r in state['resources']) for kind in ('rescue_team','drone')):
        tasks=tasks+[dict(id='PREPOSITION',name='高风险区资源前置',node='N2',requirements={'rescue_team':1,'drone':1},
                         priority=3,release=now+5,deadline=deadline,duration=5,status='provisional')]
    resources=[r for r in state['resources'] if r.get('status')!='failed'];m=cp_model.CpModel();chosen={};starts={};ends={};x={};travel_cost=[];change_cost=[];delays=[]
    previous={(a['resource'],a['task']) for a in actionable(state)}
    previous_tasks={tid for _,tid in previous};responses=[];priority_weights={1:5,2:3,3:1}
    availability={}
    for r in resources:
        if r.get('active'):
            availability[r['id']]=(r['active']['end'],r['active']['node'])
        else:availability[r['id']]=(max(now,r['available_at']),r['node'])
    for t in tasks:
        tid=t['id'];chosen[tid]=m.new_bool_var('choose_'+tid)
        starts[tid]=m.new_int_var(now,deadline,'start_'+tid);ends[tid]=m.new_int_var(now,deadline+t['duration'],'end_'+tid)
        m.add(starts[tid]>=max(now,t['release']))
        m.add(ends[tid]==starts[tid]+t['duration'])
        m.add(ends[tid]<=deadline).only_enforce_if(chosen[tid])
        late=m.new_int_var(0,horizon+1440,'late_'+tid)
        m.add(late>=starts[tid]-t['deadline']).only_enforce_if(chosen[tid]);m.add(late==0).only_enforce_if(chosen[tid].Not())
        delays.append(late)
        response=m.new_int_var(0,max(0,deadline-t['release']),'response_'+tid)
        m.add(response==starts[tid]-t['release']).only_enforce_if(chosen[tid])
        m.add(response==0).only_enforce_if(chosen[tid].Not())
        responses.append(priority_weights[t['priority']]*response)
        for kind,required in t['requirements'].items():
            variables=[]
            for r in resources:
                if r['type']!=kind:continue
                available,node=availability[r['id']];dist=distance(g,node,t['node'])
                if dist is None:continue
                key=(r['id'],tid);v=m.new_bool_var('x_'+r['id']+tid);x[key]=v;variables.append(v)
                m.add(v<=chosen[tid]);m.add(starts[tid]>=available+dist).only_enforce_if(v)
            m.add(sum(variables)==required*chosen[tid])
    # Circuit gives a real queue per resource; arc constraints include repositioning time.
    arcs_by_resource={}
    for r in resources:
        eligible=[t for t in tasks if (r['id'],t['id']) in x]
        if not eligible:continue
        arcs=[];arc_vars={};idle=m.new_bool_var('idle_'+r['id']);arcs.append((0,0,idle))
        for j,t in enumerate(eligible,1):
            v=x[r['id'],t['id']];arcs.append((j,j,v.Not()))
            first=m.new_bool_var(f'{r["id"]}_0_{j}');last=m.new_bool_var(f'{r["id"]}_{j}_0')
            arcs.extend([(0,j,first),(j,0,last)]);arc_vars[(0,j)]=first;arc_vars[(j,0)]=last
            dist=distance(g,availability[r['id']][1],t['node'])
            travel_cost.append(first*dist)
            for k,u in enumerate(eligible,1):
                if j==k:continue
                dist2=distance(g,t['node'],u['node'])
                if dist2 is None:continue
                arc=m.new_bool_var(f'{r["id"]}_{j}_{k}');arcs.append((j,k,arc));arc_vars[(j,k)]=arc
                m.add(starts[u['id']]>=ends[t['id']]+dist2).only_enforce_if(arc)
                travel_cost.append(arc*dist2)
        m.add_circuit(arcs);arcs_by_resource[r['id']]=(eligible,arc_vars)
    weights={1:10000,2:2000,3:300}
    unmet=sum(weights[t['priority']]*(1-chosen[t['id']]) for t in tasks)
    for rid in {r for r,_ in previous}:
        changed=m.new_bool_var('changed_'+rid);terms=[]
        for tid in previous_tasks:
            v=x.get((rid,tid),0)
            terms.append(1-v if (rid,tid) in previous else v)
        for term in terms:m.add(changed>=term)
        m.add(changed<=sum(terms));change_cost.append(changed)
    m.minimize(unmet+response_weight*sum(responses)+10*sum(delays)+sum(travel_cost)+stability*sum(change_cost))
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=budget*(.8 if forecast and preposition_mode=='multizone' else 1);solver.parameters.num_search_workers=1;solver.parameters.random_seed=906
    begin=time.perf_counter();status=solver.solve(m);elapsed=time.perf_counter()-begin
    assignments=[]
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        for r in resources:
            if r['id'] not in arcs_by_resource:continue
            eligible,arcs=arcs_by_resource[r['id']];current=0;available,node=availability[r['id']]
            while True:
                nxt=next((b for (a,b),v in arcs.items() if a==current and solver.value(v)),0)
                if nxt==0:break
                t=eligible[nxt-1];start=solver.value(starts[t['id']]);end=solver.value(ends[t['id']]);dist=distance(g,node,t['node'])
                path=nx.shortest_path(g,node,t['node'],weight='weight')
                assignments.append(dict(resource=r['id'],task=t['id'],name=t['name'],type=r['type'],node=t['node'],
                    depart=max(available,start-dist),arrival=start,start=start,end=end,path=path,travel=dist,provisional=t['id']=='PREPOSITION'))
                available,node=end,t['node'];current=nxt
    degraded=status not in (cp_model.OPTIMAL,cp_model.FEASIBLE)
    if degraded:
        # Same compound requirements and execution commitments as CP-SAT.
        free=dict(availability)
        for t in sorted(tasks,key=lambda t:(t['priority'],t['deadline'],t['id'])):
            selected=[]
            for kind,count in t['requirements'].items():
                candidates=[]
                for r in resources:
                    if r['type']!=kind:continue
                    available,node=free[r['id']];dist=distance(g,node,t['node'])
                    if dist is not None:candidates.append((available+dist,r['id'],node,dist))
                selected.extend(sorted(candidates)[:count])
            if len(selected)!=sum(t['requirements'].values()):continue
            start=max(t['release'],now,max(c[0] for c in selected));end=start+t['duration']
            if end>deadline:continue
            for _,rid,node,dist in selected:
                r=next(r for r in resources if r['id']==rid)
                assignments.append(dict(resource=rid,task=t['id'],name=t['name'],type=r['type'],node=t['node'],depart=start-dist,
                    arrival=start,start=start,end=end,path=nx.shortest_path(g,node,t['node'],weight='weight'),travel=dist,provisional=t['id']=='PREPOSITION'))
                free[rid]=(end,t['node'])
    preposition={}
    if forecast and preposition_mode=='multizone' and budget>0:
        from disaster.v2.preposition import preposition_plan
        extra,preposition=preposition_plan(state,assignments,g,horizon,max(0,budget-elapsed))
        assignments.extend(extra)
    for a in assignments:
        segments=[g[u][v]['road'] for u,v in zip(a['path'],a['path'][1:])]
        a['segments']=[dict(road_id=e['id'],minutes=e['minutes']) for e in segments]
        a['geometry']=[]
        for u,v,e in zip(a['path'],a['path'][1:],segments):
            coords=e.get('geometry')
            if coords:a['geometry'].extend(coords if e['u']==u else list(reversed(coords)))
    result=dict(minute=now,horizon=horizon,status=solver.status_name(status),seconds=elapsed,assignments=assignments,
                objective=solver.objective_value if not degraded else None,stability_weight=stability,degraded=degraded,
                forecast_enabled=forecast,unplanned=[t['id'] for t in tasks if t['id'] not in {a['task'] for a in assignments}],
                changes=len(previous.symmetric_difference({(a['resource'],a['task']) for a in assignments})),
                tasks_considered=[t['id'] for t in tasks])
    selected={a['task']:a for a in assignments if not a['provisional']}
    result['response_weight']=response_weight;result['preposition']=preposition
    result['stability']=disruption(state,assignments)
    result['objective_terms']=dict(unmet=sum(weights[t['priority']] for t in tasks if t['id'] not in selected and t['id']!='PREPOSITION'),
        response=sum(priority_weights[t['priority']]*(selected[t['id']]['start']-t['release']) for t in tasks if t['id'] in selected),
        lateness=sum(max(0,selected[t['id']]['start']-t['deadline']) for t in tasks if t['id'] in selected),
        travel=sum(a['travel'] for a in assignments if not a['provisional']),disruption=result['stability']['disruption'])
    terms=result['objective_terms'];result['verified_objective']=terms['unmet']+response_weight*terms['response']+10*terms['lateness']+terms['travel']+stability*terms['disruption']
    result['gaps']=[]
    for t in tasks:
        if t['id'] not in result['unplanned']:continue
        deficits={}
        for kind,count in t['requirements'].items():
            feasible=0
            for r in resources:
                if r['type']!=kind:continue
                at,node=availability[r['id']];dist=distance(g,node,t['node'])
                if dist is not None and max(at+dist,t['release'])+t['duration']<=deadline:feasible+=1
            if feasible<count:deficits[kind]=count-feasible
        result['gaps'].append(dict(task=t['id'],name=t['name'],requirements=t['requirements'],deficits=deficits,
            reason='所需类型资源不足、不可达或无法在窗口内完成' if deficits else '资源竞争或加权目标取舍，本轮未完整安排协同资源'))
    validate(state,result)
    return result

def validate(state,result):
    g=graph(state);resources={r['id']:r for r in state['resources']};tasks={t['id']:t for t in state['tasks']}
    grouped={}
    for a in result['assignments']:
        if a['resource'] not in resources:raise ValueError('未知资源')
        r=resources[a['resource']]
        if r.get('status')=='failed':raise ValueError('故障资源不可派遣')
        if a['type']!=r['type'] or not a['depart']<=a['arrival']==a['start']<a['end']:raise ValueError('计划时间或资源类型不一致')
        if any(not g.has_edge(u,v) for u,v in zip(a['path'],a['path'][1:])):raise ValueError('路径已阻断')
        grouped.setdefault(a['resource'],[]).append(a)
    for rid,items in grouped.items():
        r=resources[rid];available,node=(r['active']['end'],r['active']['node']) if r.get('active') else (max(state['minute'],r['available_at']),r['node'])
        for a in sorted(items,key=lambda a:a['start']):
            if a['depart']<available or a['path'][0]!=node or a['path'][-1]!=a['node']:raise ValueError('资源重叠或路径端点错误')
            dist=sum(g[u][v]['weight'] for u,v in zip(a['path'],a['path'][1:]))
            if dist!=a['travel'] or a['arrival']-a['depart']!=dist:raise ValueError('行程时间错误')
            available,node=a['end'],a['node']
    for tid in {a['task'] for a in result['assignments']}:
        if tid.startswith('PREPOSITION'):
            if any(not a['provisional'] or a['end']-a['start']!=1 for a in result['assignments'] if a['task']==tid) and tid!='PREPOSITION':raise ValueError('前置任务定义错误')
            continue
        assigned=[a for a in result['assignments'] if a['task']==tid];task=tasks[tid]
        if task['status']!='pending' or task['release']>state['minute']:raise ValueError('任务未发布或已执行')
        if any(a['node']!=task['node'] or a['end']-a['start']!=task['duration'] or a['start']<task['release'] for a in assigned):raise ValueError('任务地点或作业时间错误')
        if any(a['type'] not in task['requirements'] for a in assigned):raise ValueError('资源类型不在任务需求内')
        if len({a['start'] for a in assigned})!=1:raise ValueError('协同任务未同步开始')
        for kind,count in task['requirements'].items():
            if sum(a['type']==kind for a in assigned)!=count:raise ValueError('多资源需求未完整满足')
