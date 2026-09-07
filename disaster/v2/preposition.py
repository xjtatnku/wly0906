"""Residual-capacity multi-zone coverage optimization, not disaster probability."""
import time
import networkx as nx
from ortools.sat.python import cp_model

def preposition_plan(state,assignments,g,horizon,budget):
    from disaster.v2.planning import distance
    now=state['minute'];forecast=state.get('forecast',{})
    zones=[z for z in forecast.get('zones',[]) if z.get('eligible',True) and z['score']>0]
    empty=dict(status='NOT_RUN',reason='No valid zone forecast or residual capacity',assignments=0)
    if not forecast.get('eligible_for_decision',False) or not zones or budget<=0:return [],empty
    used={a['resource'] for a in assignments}
    resources=[r for r in state['resources'] if r['id'] not in used and not r.get('active') and r['available_at']<=now
               and r['status']!='failed' and r['type'] in ('rescue_team','drone')]
    if not resources:return [],empty
    # No residual resource may be moved if it serves an existing plan during the horizon.
    # Explicit experimental low/medium/high assumptions, independent of hazard probability.
    target=max(zones,key=lambda z:z['score'])['node']
    incident=sorted([(u,v,e) for u,v,e in g.edges(data=True) if target in (u,v)],key=lambda item:item[2]['road']['id'])
    high_graph=g.copy();blocked=[]
    if incident:
        u,v,e=incident[0];high_graph.remove_edge(u,v);blocked.append(e['road']['id'])
        if high_graph.is_directed() and high_graph.has_edge(v,u):high_graph.remove_edge(v,u)
    scenarios=[dict(name='low',probability=.4,demand_weight=0,blocked_roads=[]),
               dict(name='medium',probability=.4,demand_weight=1,blocked_roads=[]),
               dict(name='high',probability=.2,demand_weight=2,blocked_roads=blocked)]
    model=cp_model.CpModel();choices={};options={};travel=[];coverage=[];baseline=0;BIG=1000
    for r in resources:
        opts=[(r['node'],0)]+[(z['node'],distance(g,r['node'],z['node'])) for z in zones if z['node']!=r['node']]
        opts=[(node,d) for node,d in opts if d is not None and d+1<=min(horizon,30)]
        options[r['id']]=opts
        for node,d in opts:
            var=model.new_bool_var(r['id']+'_'+node);choices[r['id'],node]=var
            travel.append(d*var)
        model.add(sum(choices[r['id'],node] for node,_ in opts)==1)
    scenario_terms={}
    for scenario in scenarios:
      scenario_terms[scenario['name']]=[]
      if not scenario['demand_weight']:continue
      future_graph=high_graph if scenario['name']=='high' else g
      for z in zones:
        kind_times=[];base_kinds=[]
        for kind in ('rescue_team','drone'):
            estimates=[];base=[]
            for r in resources:
                if r['type']!=kind:continue
                current=distance(future_graph,r['node'],z['node']);base.append(current if current is not None else BIG)
                for node,_ in options[r['id']]:
                    d=distance(future_graph,node,z['node']);d=d if d is not None else BIG
                    t=model.new_int_var(0,2*BIG,'coverage');model.add(t==d+BIG*(1-choices[r['id'],node]));estimates.append(t)
            value=model.new_int_var(0,2*BIG,'best_type')
            if estimates:model.add_min_equality(value,estimates)
            else:model.add(value==BIG)
            kind_times.append(value);base_kinds.append(min(base,default=BIG))
        response=model.new_int_var(0,2*BIG,'zone_response');model.add_max_equality(response,kind_times)
        weight=max(1,round(z['score']*100))*scenario['demand_weight']
        probability=round(10*scenario['probability'])
        coverage.append(probability*weight*response);baseline+=probability*weight*max(base_kinds)
        scenario_terms[scenario['name']].append(weight*response)
    model.minimize(sum(coverage)+500*sum(travel))
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=min(budget,.6);solver.parameters.num_search_workers=1
    start=time.perf_counter();status=solver.solve(model);elapsed=time.perf_counter()-start
    report=dict(status=solver.status_name(status),seconds=elapsed,scenarios=scenarios,baseline_cost=baseline/10,
        score_kind='normalized risk weights, not probabilities',opportunity_rule='Only resources unused by all current horizon tasks; travel penalty 50 per minute',
        hypothesis='Independent candidate-zone compound demand needs one rescue team and one drone; medium weight 1, high P1 weight 2 plus closure; no simultaneous zone capacity recourse; positioning limit 30 minutes')
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):return [],report
    report['optimized_cost']=solver.objective_value/10;report['estimated_cost_reduction']=(baseline-solver.objective_value)/10
    report['scenario_costs']={name:sum(solver.value(term) for term in terms)+50*sum(solver.value(term) for term in travel) for name,terms in scenario_terms.items()}
    if solver.objective_value>=baseline:return [],report
    result=[]
    for r in resources:
        node,d=next((node,d) for node,d in options[r['id']] if solver.value(choices[r['id'],node]))
        if node==r['node']:continue
        result.append(dict(resource=r['id'],task=f'PREPOSITION:{r["id"]}:{now}',name='预测覆盖前置 '+node,type=r['type'],node=node,
            depart=now,arrival=now+d,start=now+d,end=now+d+1,path=nx.shortest_path(g,r['node'],node,weight='weight'),travel=d,provisional=True))
    report['assignments']=len(result)
    return result,report
