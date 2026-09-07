"""Compare only actionable promises, excluding initial allocation and completion."""
def actionable(state):
    pending={t['id'] for t in state['tasks'] if t['status']=='pending' and t['release']<=state['minute']}
    return [a for a in state.get('plan',{}).get('assignments',[]) if a['task'] in pending and a['depart']>=state['minute']]

def disruption(state,assignments):
    old=actionable(state);old_tasks={a['task'] for a in old};resources={a['resource'] for a in old}
    rows=[]
    for rid in sorted(resources):
        before={a['task'] for a in old if a['resource']==rid}
        after={a['task'] for a in assignments if a['resource']==rid and a['task'] in old_tasks}
        if before!=after:
            rows.append(dict(resource=rid,before=sorted(before),after=sorted(after),kind='reassignment' if after else 'withdrawal'))
    return dict(reassignments=sum(r['kind']=='reassignment' for r in rows),withdrawals=sum(r['kind']=='withdrawal' for r in rows),
                disruption=len(rows),details=rows,scope='Only previous actionable pending task promises; new tasks/completed/locked actions excluded')

def gini(values):
    if not values:return None
    total=sum(values)
    return sum(abs(a-b) for a in values for b in values)/(2*len(values)*total) if total else 0.0
