"""Derive the report and figures from completed V2.2 CSVs; never hand-pick seeds."""
import csv
import json
import statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/v22'


def load(name):
    with (OUT/(name+'.csv')).open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def mean(rows,key):
    values=[float(r[key]) for r in rows if r[key]!='']
    return statistics.mean(values) if values else None


def run():
    rows=load('scheduling');ablation=load('ablation');stress=load('stress')
    expected={(seed,scale,rate,method) for seed in range(20) for scale in (1,.75,.5,.35)
              for rate in ('low','medium','high') for method in ('greedy','static','rolling','rolling_forecast')}
    actual={(int(r['seed']),float(r['resource_scale']),r['event_rate'],r['method']) for r in rows}
    assert actual==expected and len(rows)==960
    assert len(ablation)==20 and len(stress)==6
    assert all(int(r['violations'])==0 for r in rows+ablation+stress)
    methods=('greedy','static','rolling','rolling_forecast')
    summaries=[]
    for scale in (1,.75,.5,.35):
        for rate in ('low','medium','high'):
            for method in methods:
                subset=[r for r in rows if float(r['resource_scale'])==scale and r['event_rate']==rate and r['method']==method]
                summaries.append(dict(resource_scale=scale,event_rate=rate,method=method,seeds=len(subset),
                    **{k:mean(subset,k) for k in ('urgent_satisfaction','mean_response','unmet','travel','reassignments','withdrawals','region_gini','unserved_regions')}))
    with (OUT/'scheduling_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    figure,axes=plt.subplots(1,3,figsize=(12,3.6),sharey=True)
    colors=['#eea642','#8c99aa','#2680cf','#1ca58f']
    for axis,rate in zip(axes,('low','medium','high')):
        for method,color in zip(methods,colors):
            subset=sorted((r for r in summaries if r['method']==method and r['event_rate']==rate),key=lambda r:r['resource_scale'])
            axis.plot([100*r['resource_scale'] for r in subset],[100*r['urgent_satisfaction'] for r in subset],'-o',label=method,color=color,markersize=4)
        axis.set(title=rate+' event rate',xlabel='Resource scale (%)',xticks=[35,50,75,100],ylim=(0,105))
        axis.grid(alpha=.2)
    axes[0].set_ylabel('P1 tasks completed by t=120 (%)')
    axes[-1].legend(fontsize=8,loc='lower right')
    figure.suptitle('Synthetic paired experiments: 20 fixed seeds per cell; mean completion rate')
    figure.tight_layout()
    figure.savefig(OUT/'resource_sensitivity.png',dpi=180)
    figure.savefig(OUT/'resource_sensitivity.svg')
    svg=OUT/'resource_sensitivity.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
    plt.close(figure)
    lines=['# V2.2 实验结果（由 CSV 自动生成）','',
        '本表来自全部960条配对记录，不筛选算法胜出的种子。4种资源比例 × 3种事件强度 × 20种子，每方法240条；统计至第120分钟。任务、资源、事件和通行时间为模拟设定。','',
        '| 方法 | P1完成率 | 已开始任务平均响应/分 | 未满足资源单位 | 实际行程/分 | 改派 | 撤回 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for method in methods:
        selected=[r for r in rows if r['method']==method]
        values=[mean(selected,k) for k in ('urgent_satisfaction','mean_response','unmet','travel','reassignments','withdrawals')]
        lines.append(f'| {method} | {100*values[0]:.2f}% | '+' | '.join(f'{v:.2f}' for v in values[1:])+' |')
    lines+=['','总均值仅作概览；同一方法在不同资源/事件组合上的变化见下图与 [48个分组结果](../results/v22/scheduling_summary.csv)。响应只覆盖已经开始的任务，Static 的低响应值伴随大量未满足任务，不能当作更好的服务。',
        '', '![资源比例与事件强度](../results/v22/resource_sensitivity.png)', '',
        '## 响应目标消融','', '同一批20种子，50%资源 / 高事件强度，只改变 β；禁用预测前置。', '',
        '| 响应权重 | P1完成率 | 已开始任务平均响应/分 | 未满足资源单位 |', '|---|---:|---:|---:|']
    compare=[r for r in rows if r['method']=='rolling' and float(r['resource_scale'])==.5 and r['event_rate']=='high']
    for label,selected in [('β=0',ablation),('β=10',compare)]:
        lines.append(f"| {label} | {100*mean(selected,'urgent_satisfaction'):.2f}% | {mean(selected,'mean_response'):.2f} | {mean(selected,'unmet'):.2f} |")
    lines+=['','加入响应项修正了“期限内早到没有代价差异”的建模问题，但本次消融不支持所有指标均改善的结论。优化的是每轮加权目标，评价的是完整执行过程；开始任务集合、任务优先级与超时解都可能不同。','',
        '## 压力与约束审计','',
        '| 第17分钟注入情景 | 事件处理与重规划/ms | 全程违规 | 最终预测可用于前置 |', '|---|---:|---:|---|']
    for r in stress:
        lines.append(f"| {r['scenario']} | {float(r['latency_ms']):.2f} | {r['violations']} | {r['forecast_eligible']} |")
    lines+=['','960组调度、20组消融、6组压力测试的逐分钟执行审计均为0违规。延迟数据情景最终禁用预测前置。压力测试仅各运行一次，耗时不是可靠的分位数或服务等级保证。','',
        '## 预测误差','',
        '以下仅汇总三个点降雨的MAE，单位 mm/h；全部变量、点位、RMSE与样本数保留在原CSV。真实小时与模拟五分钟表分开，不跨频率比较优劣。','']
    for name,title in [('forecast_synthetic','模拟降雨'),('forecast_historical','真实历史产品降雨')]:
        predictions=load(name);horizons=sorted({int(r['horizon_minutes']) for r in predictions})
        lines += [f'### {title}','', '| 模型 | '+' | '.join(f'MAE@{h}分' for h in horizons)+' |', '|---|'+'---:|'*len(horizons)]
        for model in ('Persistence','AR','Gradient Boosting'):
            values=[mean([r for r in predictions if r['model']==model and r['type']=='rainfall' and int(r['horizon_minutes'])==h],'mae') for h in horizons]
            lines.append('| '+model+' | '+' | '.join(f'{v:.3f}' for v in values)+' |')
        lines.append('')
    lines+=['IMERG Final和ERA5-Land包含事后处理信息，此表是最终历史产品上的留出序列预测误差，不能证明2024年当时可在线获取的灾害预警能力。','',
        '## 结论范围','',
        '完整保留滚动调度、预测前置或响应目标未胜出的结果。总表中滚动方法的平均条件响应与缺口较贪心有所下降，但P1完成率未全面领先；前置也未在各指标上持续改善。应按资源比例和事件强度逐组分析，而不是把系统复杂度解释成算法优势。','',
        '未满足量与区域未服务数必须和条件响应、区域Gini一起解读。前置目前是剩余资源下的情景覆盖代理，没有同时多区域需求的容量补救优化。所有实验均不能推出真实康定救援效果。','',
        '原始文件：[调度](../results/v22/scheduling.csv)、[消融](../results/v22/ablation.csv)、[压力](../results/v22/stress.csv)、[模拟预测](../results/v22/forecast_synthetic.csv)、[历史预测](../results/v22/forecast_historical.csv)。复现参数与方法限制见 [V2.2说明](../README-V22.md)。',
        '', '重新生成本文与图片：`python scripts/summarize_v22.py`。']
    (ROOT/'docs/results-v22.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Verified 960 factorial + 20 ablation + 6 stress rows; summary and figures exported.')


if __name__=='__main__':run()
