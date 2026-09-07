function renderHealth(){
 const rows=state.data_health||[];
 const statusType=s=>s==='FRESH'?'good':s==='DELAYED'?'warn':'danger';
 $('#content').insertAdjacentHTML('afterbegin',panel('数据时效与接收质量',`<div class="panel-body"><p class="notice">在线仿真模式：新鲜度与接收间隔使用模拟时钟；received_at 是本机实际入库时间。预生成数据按时刻释放，没有接入真实传感器或硬件心跳。模拟源阈值5/15/30分钟；历史小时回放的FRESH阈值60分钟。历史产品的真实发布延迟不由模拟时钟推断。</p>${table(['数据流','最新观测时间','实际接收时间','观测年龄 / 接收间隔','源状态','通过率','采样窗口缺失率'],rows.map(r=>[esc(r.source_id),esc(r.observed_at||'无'),esc(r.received_at||'旧数据未记录'),`${r.freshness_seconds??'—'} / ${r.heartbeat_age_seconds??'—'} 秒`,badge(r.source_status,statusType(r.source_status)),r.quality_rate===null?'—':(100*r.quality_rate).toFixed(1)+'%',(100*r.missing_rate).toFixed(1)+'%']))}</div>`,'FRESH / DELAYED / STALE / OFFLINE','full'));
}
function displayAssignments(){
 const active=state.resources.flatMap(r=>r.active?[{...r.active,locked:true}]:[]);
 const keys=new Set(active.map(a=>`${a.resource}/${a.task}/${a.depart}`));
 return [...active,...(state.plan.assignments||[]).filter(a=>a.end>state.minute&&!keys.has(`${a.resource}/${a.task}/${a.depart}`))];
}
async function renderExperiments(){
 const result=await api('experiments');if(!result.rows.length)return;
 const labels={greedy:'最近可行贪心',static:'初始静态计划',dynamic:'动态 λ=20',dynamic_prediction:'动态＋规则前置',stability_0:'动态 λ=0',stability_5:'动态 λ=5',stability_50:'动态 λ=50',stability_100:'动态 λ=100'};
 const methods=[...new Set(result.rows.map(r=>r.method))];
 const rows=methods.map(method=>{const subset=result.rows.filter(r=>r.method===method),mean=k=>subset.reduce((s,r)=>s+Number(r[k]),0)/subset.length;return [labels[method]||esc(method),subset.length,mean('completed').toFixed(2),(mean('urgent_satisfaction')*100).toFixed(1)+'%',mean('mean_start_delay').toFixed(2),mean('response_gini_started').toFixed(3),mean('plan_changes').toFixed(1),subset.reduce((s,r)=>s+Number(r.violations),0)]});
 $('#content').insertAdjacentHTML('beforeend',panel('固定种子实验与稳定性敏感性',`<div class="panel-body"><p class="notice">${result.rows.length}条实测记录 · 标准场景＋20种子 · 模拟基线路网 · 每轮${result.config.solver_budget_seconds}秒预算 · 第120分钟统计。与OSM演示分别验证；平均响应和Gini仅针对已开始任务，需结合完成率解读。Gini越低仅表示这些已开始任务等待差异越小，不表示整体救援公平。</p>${table(['配置','场景数','完成任务 / 12','P1完成率','已开始任务平均等待','响应Gini','累计计划变更','违规数'],rows)}</div>`,'原始CSV结果均值，不预设优化器胜出','full'));
}
async function renderMultistep(){
 const f=await api('forecast');
 $('#content').insertAdjacentHTML('beforeend',panel('A · 联合递归预测验证',`<div class="panel-body"><p class="notice">三个站点联合构造12阶滞后特征。固定训练段，每个验证起点只读取当时已有观测，之后递归反馈预测值；各时距使用相同起点。当前数据：${f.eligible_for_decision?'可用于实验前置':'过期或缺口，暂停预测前置'}。</p><div class="toolbar"><span>当前查看 ${forecastStation}</span><select id="eval-kind">${Object.entries(state.sensor_types).map(([k,v])=>`<option value="${k}">${v.label} / ${v.unit}</option>`).join('')}</select><a href="/api/research/export/forecast_${f.environment_mode==='historical'?'historical':'synthetic'}">下载完整预测误差 CSV</a></div><div id="eval-table"></div></div>`,`${f.cadence_minutes===60?'历史小时数据：60 / 180 / 360 / 720':'模拟数据：5 / 15 / 30 / 60'} 分钟`,'full'));
 const update=()=>{$('#eval-table').innerHTML=table(['模型','预测时距','MAE','RMSE','共同验证起点数','联合特征数'],f.multistep_evaluation.filter(e=>e.station_id===forecastStation&&e.type===$('#eval-kind').value).map(e=>[esc(e.model),e.horizon_minutes+'分钟',e.mae.toFixed(3),e.rmse.toFixed(3),e.test_samples,e.features]))};
 $('#eval-kind').onchange=update;update();
}
function renderRoutingControls(){
 const osm=state.routing_mode==='osm',m=state.routing_manifest;
 $('#content').insertAdjacentHTML('afterbegin',panel('路网来源与事件触发',`<div class="panel-body"><div class="toolbar"><label>调度路网</label><select id="routing-mode"><option value="simulated" ${!osm?'selected':''}>模拟基线路网</option><option value="osm" ${osm?'selected':''}>OSM 道路快照寻路</option></select><button id="switch-routing" class="primary">切换并重置演示</button><label>模拟资源故障</label><select id="failure-resource">${state.resources.filter(r=>r.status!=='failed').map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('')}</select><button id="fail-resource">确认故障并重规划</button></div><p class="notice">${osm?`真实 OSM 道路几何 / ${m.graph_nodes} 节点 / ${m.directed_edges} 有向路段；快照时间 ${esc(m.osm_base)}。车速、分钟取整、任务和封路为模拟；不代表2024年历史路况。保留单行方向，尚未处理转向限制和车辆尺寸。`:'当前为10节点模拟基线。切换 OSM 后，优化器和执行器使用 OSM 道路连接关系及单行方向，历史快照保留。'}<br>重规划触发：新增P1、资源故障、增援到达、风险等级变化、道路中断；每10分钟兜底。<br>最近触发：${esc((state.plan.triggers||['手动优化 / 尚未规划']).join('；'))}</p>${osm?'<details><summary>查看业务点吸附距离与原始节点（10项）</summary>'+table(['实验业务点','原坐标→最近独立道路节点距离','OSM 节点编号'],state.nodes.filter(n=>n.kind!=='road').map(n=>[esc(n.name),n.snap_meters+' m',esc(n.osm_id)]))+'</details>':''}</div>`,'当前模式：'+(osm?'OSM拓扑＋模拟任务':'全模拟拓扑'),'full'));
 $('#switch-routing').onclick=()=>action(async()=>{await api('reset',{routing_mode:$('#routing-mode').value});toast('路网已切换；任务重置，历史保留')});
 $('#fail-resource').onclick=()=>action(async()=>{await api('resources/'+$('#failure-resource').value+'/fail',{});toast('故障已记录并重新规划')});
}
