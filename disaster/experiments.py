"""Run standard + 20 paired seeded simulations, and separate NLP checks."""
import argparse
from copy import deepcopy
import hashlib
import random
import platform
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from disaster.core import ROOT, read_json, write_json, run_scenario, metrics, snapshot, load_state
from disaster.knowledge import Retriever, extract_event, suggest_task, provider_configured, retrieval_query


def perturb(base, seed):
    scenario=deepcopy(base)
    if seed<0:
        return scenario
    rng=random.Random(seed)
    for road in scenario['roads']:
        road['minutes']=max(1,round(road['minutes']*rng.uniform(.75,1.35)))
    for event in scenario['events']:
        for task in event.get('tasks',[]):
            task['duration']=max(5,round(task['duration']*rng.uniform(.75,1.4)))
            task['required']=max(1,min(3,task['required']+rng.choice([-1,0,0,1])))
    return scenario


def extraction_evaluation(live=False):
    if live and not provider_configured():
        raise ValueError('Configure DISASTER_API_KEY and DISASTER_MODEL before --live')
    gold=read_json(ROOT/'data/evaluation/extraction_gold.json')
    retriever=Retriever()
    state=load_state()
    rows=[]
    known={c['id'] for c in retriever.clauses}
    for sample in gold:
        state.now=sample['minute']
        result=extract_event(sample['text'],state,live)
        candidate=result['candidate'] or {}
        hits=retriever.search(retrieval_query(sample['text'],candidate))
        suggestion=suggest_task(candidate,hits,state,live) if candidate else {'citations':[],'mode':'no_candidate'}
        rows.append(dict(id=sample['id'],mode=result['mode'],suggestion_mode=suggestion['mode'],node_correct=candidate.get('node')==sample['expected']['node'],
                         capability_correct=candidate.get('capability')==sample['expected']['capability'],
                         citation_ids_valid=bool(suggestion['citations']) and set(suggestion['citations'])<=known,
                         cited_count=len(suggestion['citations']),
                         supported_cited_count=len(set(suggestion['citations']) & set(sample['acceptable_citations'])),
                         gold_clause_in_top5=bool(set(sample['acceptable_citations']) & {h['id'] for h in hits}),
                         expected_document_in_top5=sample['acceptable_source'] in {h['source_id'] for h in hits},
                         error=result['error'],citations=suggestion['citations']))
    label='live' if live else 'offline'
    frame=pd.DataFrame(rows)
    frame.to_csv(ROOT/f'results/extraction_{label}.csv',index=False,encoding='utf-8-sig')
    write_json(ROOT/f'results/extraction_{label}_summary.json',dict(mode=label,count=len(rows),
        node_accuracy=float(frame.node_correct.mean()),capability_accuracy=float(frame.capability_correct.mean()),
        nonempty_valid_citation_coverage=float(frame.citation_ids_valid.mean()),document_recall_at5=float(frame.expected_document_in_top5.mean()),
        gold_clause_recall_at5=float(frame.gold_clause_in_top5.mean()),
        citation_precision_against_authored_gold=float(frame.supported_cited_count.sum()/max(1,frame.cited_count.sum())),
        semantic_entailment='Clause IDs compared with agent-authored supporting-clause labels; not independent legal applicability or entailment review.',
        limitation='20 agent-authored simple cases; no external annotator review. Offline scores are NOT model scores.'))
    return frame


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='Run real configured API on 20 samples; billable provider calls')
    parser.add_argument('--nlp-only',action='store_true')
    args=parser.parse_args()
    (ROOT/'results').mkdir(exist_ok=True)
    if not args.nlp_only:
        base=read_json(ROOT/'data/scenario.json')
        rows=[]
        for seed in [-1]+list(range(20)):
            scenario=perturb(base,seed)
            write_json(ROOT/f'results/scenarios/seed_{seed}.json',scenario)
            for method in ['greedy','static','dynamic']:
                state=run_scenario(scenario,method,scenario['horizon'])
                rows.append(dict(seed=seed,method=method,**metrics(state)))
                write_json(ROOT/f'results/traces/{method}_{seed}.json',snapshot(state))
            print(f'Scenario {seed} complete',flush=True)
        frame=pd.DataFrame(rows)
        frame.to_csv(ROOT/'results/metrics.csv',index=False,encoding='utf-8-sig')
        summary=frame.groupby('method').agg(['mean','std']).drop(columns='seed')
        summary.columns=['_'.join(c) for c in summary.columns]
        summary.reset_index().to_csv(ROOT/'results/summary.csv',index=False,encoding='utf-8-sig')
        fig,axes=plt.subplots(1,3,figsize=(12,3.5))
        for ax,col,title in zip(axes,['urgent_satisfaction','unmet_units','mean_response'],['Urgent units arrived / required','Unmet units at 180 min','Response among arrivals (min)']):
            group=frame.groupby('method')[col]
            ax.bar(group.mean().index,group.mean(),yerr=group.std(),capsize=4,color=['#2979a3','#72a9b1','#d7a35c'])
            ax.set_title(title,fontsize=10)
            ax.grid(axis='y',alpha=.2)
        fig.tight_layout()
        fig.savefig(ROOT/'results/comparison.png',dpi=180)
        plt.close(fig)
        write_json(ROOT/'results/run_manifest.json',dict(seeds=[-1]+list(range(20)),horizon=180,python=platform.python_version(),
            scenario_sha256=hashlib.sha256((ROOT/'data/scenario.json').read_bytes()).hexdigest(),
            decision_interval=5,solver_limit_seconds=5,solver_workers=1,
            limitations=['Static sees only initial tasks and cannot allocate reinforcements; deliberately weak no-replanning baseline.',
                        'Dynamic is myopic repeated assignment, not a multi-stage stochastic optimizer.',
                        'Average response excludes unserved demand; read with unmet_units.',
                        'All travel times and task parameters are simulated.']))
    extraction_evaluation(args.live)
    print('Results saved to results/')


if __name__=='__main__':
    main()
