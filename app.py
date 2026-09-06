from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import streamlit as st
from disaster.core import ROOT, read_json, load_state, apply_event, advance, dispatch, solve, snapshot, task_rows, metrics
from disaster.knowledge import Retriever, extract_event, suggest_task, build_event, explain_decision, visible_facts, CAP_LABELS, provider_configured, retrieval_query

st.set_page_config(page_title='灾害应急调度研究原型',page_icon='🗺️',layout='wide')
st.title('动态灾害应急决策与资源调度')
st.caption('康定案例背景 · 模拟路网与资源 · 单机研究原型')
scenario=read_json(ROOT/'data/scenario.json')


@st.cache_resource
def retriever():
    return Retriever()


def reset():
    st.session_state.state=load_state(scenario)
    st.session_state.stage=0
    st.session_state.last_explanation=None
    st.session_state.pop('candidate_result',None)


if 'state' not in st.session_state:
    reset()
state=st.session_state.state
with st.sidebar:
    st.header('回放控制')
    method=st.selectbox('调度方法',['dynamic','greedy','static'],format_func=lambda x:{'dynamic':'动态重规划','greedy':'最近可行队伍贪心','static':'一次性静态优化'}[x])
    if 'method' not in st.session_state:
        st.session_state.method=method
    if method!=st.session_state.method:
        st.session_state.method=method
        reset()
        st.rerun()
    live=st.toggle('使用实时模型 API',value=False)
    st.caption('API 已配置' if provider_configured() else 'API 未配置；离线演示可用')
    if st.button('重置场景',use_container_width=True):
        reset()
        st.rerun()
    idx=st.session_state.stage
    if idx<len(scenario['events']):
        event=scenario['events'][idx]
        st.write(f"下一阶段 E{idx} · 第 {event['minute']} 分钟")
        if st.button('推进下一阶段',type='primary',use_container_width=True):
            advance(state,max(state.now,event['minute']),method)
            # Interleaved user actions can move beyond a scenario timestamp; block mixing.
            if state.now!=event['minute']:
                st.error('已越过此阶段，请重置后回放。')
            else:
                apply_event(state,event)
                if method!='static' or not state.decisions:
                    decision=solve(state,method)
                    explanation=explain_decision(state,decision,live)
                    dispatch(state,decision)
                    st.session_state.last_explanation=explanation
                st.session_state.stage+=1
                st.session_state.pop('candidate_result',None)
                st.rerun()
    else:
        if st.button('推进 10 分钟',use_container_width=True):
            advance(state,state.now+10,method)
            if method!='static':
                decision=solve(state,method)
                dispatch(state,decision)
            st.session_state.pop('candidate_result',None)
            st.rerun()
    st.divider()
    st.caption('先运行初始阶段，再输入新灾情。所有新增任务的数量、时限、作业时长均为实验参数。')
    st.download_button('导出当前状态',json.dumps(snapshot(state),ensure_ascii=False,indent=2),'state.json','application/json')

m=metrics(state)
c1,c2,c3,c4=st.columns(4)
c1.metric('模拟时间',f'{state.now} 分钟')
c2.metric('可用队伍',sum(t.task_id is None and t.available_at<=state.now for t in state.teams.values()))
c3.metric('待分配需求',sum(t['gap'] for t in task_rows(state)))
c4.metric('紧急需求已到达',f"{m['urgent_satisfaction']:.0%}")
tabs=st.tabs(['态势与调度','新灾情与依据','真实案例与来源','实验结果'])
with tabs[0]:
    left,right=st.columns([1.1,1])
    with left:
        st.subheader('模拟路网')
        plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
        fig,ax=plt.subplots(figsize=(8,5))
        pos={n:(a['x'],a['y']) for n,a in state.graph.nodes(data=True)}
        labels={n:f"{n}\n{a['name']}" for n,a in state.graph.nodes(data=True)}
        nx.draw_networkx_nodes(state.graph,pos,ax=ax,node_color='#d7e9f7',node_size=1250)
        nx.draw_networkx_labels(state.graph,pos,labels,ax=ax,font_family='Microsoft YaHei',font_size=8)
        opened=[(u,v) for u,v,a in state.graph.edges(data=True) if not a['blocked']]
        blocked=[(u,v) for u,v,a in state.graph.edges(data=True) if a['blocked']]
        nx.draw_networkx_edges(state.graph,pos,edgelist=opened,ax=ax,edge_color='#8aa1b4')
        nx.draw_networkx_edges(state.graph,pos,edgelist=blocked,ax=ax,edge_color='#d84f4f',style='dashed',width=3)
        for team in state.teams.values():
            if team.status=='travel':
                nx.draw_networkx_edges(state.graph,pos,edgelist=list(zip(team.path,team.path[1:])),ax=ax,edge_color='#e79626',width=2,alpha=.65)
        nx.draw_networkx_edge_labels(state.graph,pos,{(u,v):a['minutes'] for u,v,a in state.graph.edges(data=True)},ax=ax,font_size=8)
        ax.axis('off')
        st.pyplot(fig)
        plt.close(fig)
        st.caption('边上数字为模拟分钟；红虚线为阻断，橙色为在途计划。节点位置不是经纬度。')
    with right:
        st.subheader('当前队伍状态')
        st.dataframe(pd.DataFrame([dict(队伍=t.id,能力=CAP_LABELS[t.capability],最近到达节点=t.node,
                                       状态='待增援' if t.available_at>state.now else t.status,任务=t.task_id or '—',
                                       当前边剩余分钟=t.edge_left) for t in state.teams.values()]),hide_index=True)
        if state.decisions:
            d=state.decisions[-1]
            st.write(f"最近求解：{d['status']} · {d['seconds']:.3f}s · 第 {d['minute']} 分钟")
            st.dataframe(pd.DataFrame(d['assignments']),hide_index=True)
    st.subheader('任务与资源缺口')
    if state.tasks:
        st.dataframe(pd.DataFrame(task_rows(state)),hide_index=True)
    explanation=st.session_state.last_explanation
    if explanation:
        st.caption(explanation['mode'])
        for line in explanation['lines']:
            st.write(line)
    with st.expander('事件与执行日志',expanded=True):
        st.dataframe(pd.DataFrame([dict(分钟=e['minute'],类型=e['kind'],详情=json.dumps({k:v for k,v in e.items() if k not in ('minute','kind')},ensure_ascii=False)) for e in reversed(state.logs[-60:])]),hide_index=True)

with tabs[1]:
    st.subheader('文本 → 候选 → 人工确认 → 调度')
    text=st.text_area('灾情原文',value='村落甲发现人员被困，需要搜救。',max_chars=3000)
    if st.button('提取灾情并检索依据',disabled=not state.tasks):
        result=extract_event(text,state,live)
        hits=retriever().search(retrieval_query(text,result['candidate']))
        suggestion=suggest_task(result['candidate'],hits,state,live) if result['candidate'] else {'citations':[],'reason':'请人工补全地点和任务类型。','mode':'人工填写'}
        st.session_state.candidate_result=dict(result=result,hits=hits,suggestion=suggestion,text=text,minute=state.now)
    pending=st.session_state.get('candidate_result')
    if pending and (pending['text']!=text or pending['minute']!=state.now):
        st.info('原文或时间已改变，请重新提取后确认。')
    elif pending:
        result=pending['result']
        st.caption(result['mode'])
        if result['error']:
            st.warning(result['error'])
        else:
            st.json(result['candidate'])
        suggestion=pending['suggestion']
        st.write(suggestion['reason'])
        st.caption(suggestion['mode'])
        for h in pending['hits']:
            with st.expander(f"{h['id']} · {h['section']} · {h['score']:.3f}"):
                st.write(h['text'])
                st.markdown(f"[原文件]({h['url']}) · {h['version']}")
                st.caption(h['scope'])
                st.caption(h['verification'])
        cand=result['candidate'] or {'node':'N4','capability':'rescue'}
        with st.form('confirm'):
            cols=st.columns(3)
            node=cols[0].selectbox('确认地点',list(state.graph),index=list(state.graph).index(cand['node']))
            cap=cols[1].selectbox('确认能力',list(CAP_LABELS),index=list(CAP_LABELS).index(cand['capability']),format_func=lambda x:CAP_LABELS[x])
            req=cols[2].number_input('队伍数量（模拟）',1,8,1)
            cols=st.columns(3)
            pri=cols[0].selectbox('优先级（模拟）',[1,2],format_func=lambda x:'紧急' if x==1 else '普通')
            due=cols[1].number_input('期望多少分钟内到达',1,1440,30)
            duration=cols[2].number_input('作业分钟',1,1440,20)
            cites=st.multiselect('确认引用条款',[h['id'] for h in pending['hits']],default=suggestion['citations'])
            submitted=st.form_submit_button('确认事件并更新调度')
        if submitted:
            try:
                event=build_event(text,state,node,cap,int(req),pri,int(due),int(duration),cites)
                changed=apply_event(state,event)
                if changed and (method!='static' or not state.decisions):
                    d=solve(state,method)
                    explanation=explain_decision(state,d,live)
                    dispatch(state,d)
                    st.session_state.last_explanation=explanation
                st.success('事件已确认，调度状态已更新。' if changed else '重复事件，未重复新增任务。')
                st.rerun()
            except (ValueError,TypeError) as exc:
                st.error(str(exc))
    with st.expander('人工录入道路中断'):
        edge=st.selectbox('阻断道路',list(state.graph.edges()),format_func=lambda e:f'{e[0]}—{e[1]}')
        if st.button('确认道路中断',disabled=not state.tasks):
            event=dict(id=f'ROAD-{state.now}-{edge[0]}-{edge[1]}',minute=state.now,blocked_roads=[list(edge)],tasks=[],text='人工确认道路中断')
            changed=apply_event(state,event)
            if changed and method!='static':
                dispatch(state,solve(state,method))
            st.rerun()

with tabs[2]:
    st.subheader('真实通报：按发布时间查看')
    st.write('此处与模拟分钟完全分开。发布时间晚于截止时间的记录不会显示；网页只有日期时保守取当天末尾。')
    cutoff=st.selectbox('公开信息截止时间',['2024-08-03T23:59:59+08:00','2024-08-04T23:59:59+08:00','2024-08-05T23:59:59+08:00'],index=1)
    facts=visible_facts(cutoff)
    if facts:
        st.dataframe(pd.DataFrame(facts),hide_index=True)
    else:
        st.info('当前收集的通报在该时点尚未公开；不能用后续报道回填当时态势。')
    for s in read_json(ROOT/'data/sources.json'):
        st.markdown(f"[{s['title']}]({s['url']}) · {s['published_at']}")
    st.info(scenario['warning'])

with tabs[3]:
    path=ROOT/'results/summary.csv'
    if path.exists():
        data=pd.read_csv(path)
        st.dataframe(data,hide_index=True)
        st.bar_chart(data.set_index('method')[['urgent_satisfaction_mean']])
        st.caption('标准场景＋20 个固定种子扰动；静态方案仅初始派遣。满足率以到达队伍数计算，非获救人数。')
        st.download_button('下载逐场景指标',(ROOT/'results/metrics.csv').read_bytes(),'metrics.csv','text/csv')
    else:
        st.info('运行 python -m disaster.experiments 生成结果。')
