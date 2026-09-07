/* Shared vector icons and local cartography. No additional runtime dependency. */
const iconPaths={
 home:'M3 11 12 3l9 8M5 10v11h5v-6h4v6h5V10',
 data:'M4 5c0-4 16-4 16 0v14c0 4-16 4-16 0ZM4 5c0 4 16 4 16 0M4 12c0 4 16 4 16 0',
 pulse:'M2 12h5l3-8 4 16 3-8h5',
 truck:'M3 6h11v12H3ZM14 10h4l4 4v4h-8M6 18a2 2 0 1 0 0 .1M18 18a2 2 0 1 0 0 .1',
 strategy:'M12 3v6M5 15V9h14v6M3 15h4v5H3ZM10 15h4v5h-4ZM17 15h4v5h-4',
 clock:'M12 7v5l4 2M21 12a9 9 0 1 1-3-6M21 3v6h-6',
 rain:'M6 14a5 5 0 1 1 1-9 6 6 0 0 1 11 3 3 3 0 0 1 0 6ZM7 18l-1 3M12 18l-1 3M17 18l-1 3',
 alert:'M12 3 2 21h20ZM12 9v5M12 17v.1',
 people:'M9 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3 21v-4c0-5 12-5 12 0v4M17 5a3 3 0 0 1 0 6M19 14c3 0 3 4 3 7',
 heart:'M12 21C5 16 1 12 3 7s7-4 9 0c2-4 8-5 9 0s-2 9-9 14',
 medical:'M8 3h8v5h5v8h-5v5H8v-5H3V8h5Z',
 road:'M8 3 4 21M16 3l4 18M12 4v3M12 10v4M12 17v3',
 check:'m5 12 4 4L20 5',
 send:'m3 10 18-7-7 18-3-8ZM11 13l10-10',
 layers:'m12 3 10 6-10 6L2 9ZM2 14l10 6 10-6M2 19l10 5 10-5',
 pin:'M12 22S4 14 4 9a8 8 0 1 1 16 0c0 5-8 13-8 13ZM12 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
 target:'M12 2v4M12 18v4M2 12h4M18 12h4M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0ZM12 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4',
 box:'m3 7 9-5 9 5v11l-9 5-9-5ZM3 7l9 5 9-5M12 12v11',
 shield:'m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6ZM8 11l3 3 5-6'
};
function icon(name){return `<svg class="ui-icon" viewBox="0 0 24 26" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${iconPaths[name]||iconPaths.layers}"/></svg>`}
const metricIcons={'▦':'data','⌁':'pulse','▥':'layers','✓':'check','◷':'clock','◈':'strategy','♟':'people','➤':'send','▤':'layers','⇄':'road','☁':'rain','!':'alert','♡':'heart','✚':'medical'};
let contextPromise;
function mapContext(){return contextPromise??=fetch('/assets/map-context.json').then(r=>{if(!r.ok)throw Error('map context');return r.json()}).catch(()=>null)}
function cartographicMap(id,risk=false){
 const el=document.getElementById(id);if(!el)return;
 const map=L.map(el,{zoomControl:false,preferCanvas:true,attributionControl:false,zoomSnap:.25});maps.push(map);
 const bounds=state.nodes.filter(n=>n.kind!=='road').map(n=>[n.lat,n.lon]);
 const fit=()=>map.fitBounds(bounds,{paddingTopLeft:[60,98],paddingBottomRight:[60,45]});fit();
 L.control.zoom({position:'bottomright'}).addTo(map);
 L.control.scale({position:'bottomright',imperial:false,maxWidth:90}).addTo(map);
 const background=L.layerGroup().addTo(map),zones=L.layerGroup().addTo(map),routes=L.layerGroup().addTo(map),resources=L.layerGroup().addTo(map);
 let disposed=false;map.on('unload',()=>disposed=true);
 mapContext().then(context=>{if(disposed||!context)return;for(const way of context.ways){const major=['trunk','primary','secondary','motorway'].includes(way.kind);L.polyline(way.points,{color:major?'#84aaa0':'#5a827b',weight:major?1.8:.7,opacity:major?.5:.3,interactive:false}).addTo(background)}});
 for(const n of state.nodes){
  if(n.kind==='road')continue;
  const zone=state.forecast.zones?.find(z=>z.node===n.id);
  if(zone){const score=zone.score,color=score>=.7?'#ff665d':score>=.45?'#ffbf56':'#3acaa2';
   L.circle([n.lat,n.lon],{radius:1400+score*1400,color,weight:1.5,fillOpacity:risk?.25:.15}).addTo(zones);
   L.circle([n.lat,n.lon],{radius:900+score*800,color,weight:0,fillOpacity:.09}).addTo(zones);
   L.marker([n.lat+.005,n.lon+.065],{interactive:false,icon:L.divIcon({className:'zone-label',html:`${esc(n.id)} · ${score.toFixed(2)}`,iconSize:[72,22]})}).addTo(zones);
  }
  const kind=n.kind==='hospital'?'medical':n.kind==='shelter'?'home':n.kind==='base'?'shield':'pin';
  const marker=L.marker([n.lat,n.lon],{icon:L.divIcon({className:'map-node '+kind,html:icon(kind),iconSize:[26,26],iconAnchor:[13,13]})});
  const right=['N4','N5','N8','N9','N2'].includes(n.id);
  marker.addTo(map).bindTooltip(esc(n.name.replace('模拟','')),{permanent:true,direction:right?'right':'left',className:'node-label',offset:[right?13:-13,0]})
   .bindPopup(`<b>${esc(n.name)}</b><p>模拟节点 ${esc(n.id)} · 人口 ${n.population}</p>`);
 }
 for(const road of state.roads){
  const a=node(road.u),b=node(road.v),geometry=road.geometry||[[a.lat,a.lon],[b.lat,b.lon]];
  L.polyline(geometry,{color:'#162f37',weight:6,opacity:.75,interactive:false}).addTo(routes);
  L.polyline(geometry,{color:road.blocked?'#ff6268':'#e4bf74',weight:road.blocked?3.5:2,dashArray:road.blocked?'6 6':null}).addTo(routes)
   .bindPopup(`<b>${esc(road.id)} · ${road.blocked?'道路阻断':'可通行'}</b><p>${road.minutes} 分钟 · 实验行程</p>`);
  if(road.blocked){const middle=geometry[Math.floor(geometry.length/2)];L.marker(middle,{icon:L.divIcon({className:'road-block',html:'−',iconSize:[22,22]})}).addTo(routes)}
 }
 const colors={rescue_team:'#58aaff',medical_team:'#ff7e9d',ambulance:'#ff7e9d',engineering_team:'#3dd8b0',excavator:'#3dd8b0',drone:'#ba9bff',supply_vehicle:'#ffc15c'};
 for(const a of displayAssignments())L.polyline(a.geometry?.length?a.geometry:a.path.map(n=>[node(n).lat,node(n).lon]),{color:colors[a.type]||'#58aaff',weight:3,dashArray:'9 5',opacity:.95}).addTo(resources)
  .bindPopup(`${esc(a.resource)} → ${esc(a.name)}<p>出发 ${a.depart} · 到达 ${a.arrival} · 结束 ${a.end}</p>`);
 // Aggregate co-located resources; do not invent jittered geographic positions.
 for(const n of state.nodes){const group=state.resources.filter(r=>r.node===n.id&&r.available_at<=state.minute);if(!group.length)continue;
  L.marker([n.lat,n.lon],{icon:L.divIcon({className:'resource-count',html:`${icon('people')}<b>${group.length}</b>`,iconSize:[38,22],iconAnchor:[-14,-9]})}).addTo(resources)
   .bindPopup(`<b>${esc(n.name)} · ${group.length} 项资源</b>`+group.map(r=>`<p>${esc(r.name)} · ${esc(statusName(r.status))}</p>`).join(''));
 }
 const tile=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18});
 let errors=0;tile.on('tileerror',()=>{if(++errors===3){el.querySelector('.map-status').textContent='在线底图不可用 · 可切回本地路网'}});
 const controls=el.querySelector('.map-tools');L.DomEvent.disableClickPropagation(controls);L.DomEvent.disableScrollPropagation(controls);
 controls.querySelectorAll('[data-base]').forEach(b=>b.onclick=()=>{
  const online=b.dataset.base==='online';if(online)tile.addTo(map);else map.removeLayer(tile);
  el.classList.toggle('online-base',online);controls.querySelectorAll('[data-base]').forEach(x=>x.classList.toggle('selected',x===b));
  el.querySelector('.map-status').textContent=online?'在线 OSM · 底图需联网':'本地 OSM 路网 · 可离线交互';
 });
 for(const [key,layer] of [['risk',zones],['resources',resources]])controls.querySelector(`[data-layer="${key}"]`).onclick=function(){const active=map.hasLayer(layer);if(active)map.removeLayer(layer);else layer.addTo(map);this.classList.toggle('selected',!active);this.setAttribute('aria-pressed',String(!active))};
 controls.querySelector('[data-fit]').onclick=fit;
 return map;
}
function finishDesign(){
 document.body.dataset.page=page;
 const navIcons={overview:'home',data:'data',prediction:'pulse',dispatch:'truck',strategy:'strategy',replay:'clock'};
 document.querySelectorAll('[data-page]').forEach(b=>{b.querySelector('.icon').innerHTML=icon(navIcons[b.dataset.page]);b.setAttribute('aria-label',b.querySelector('.label').textContent);b.setAttribute('aria-current',b.dataset.page===page?'page':'false')});
 document.querySelectorAll('.metric .symbol').forEach(el=>{if(!el.querySelector('svg'))el.innerHTML=icon(metricIcons[el.textContent]||'layers')});
 // Place diagnostics after the operational dashboard, preserving all controls.
 for(const section of [...document.querySelectorAll('#content>.panel')]){
  const title=section.querySelector('.panel-title>span')?.textContent||'';
  if(title.startsWith('决策追踪')){$('#content').append(section);section.classList.add('trace-panel')}
  if(page==='data'&&(title==='研究数据与预测模式'||title==='数据时效与接收质量'))$('#content').append(section);
  if(page==='dispatch'&&title==='路网来源与事件触发')$('#content').append(section);
 }
 const latest=state.decision_traces?.at(-1);
 const status=$('#session-status');if(status)status.innerHTML=`<span class="status-dot"></span>${state.environment_mode==='historical'?'历史产品回放':'模拟事件演练'}<span class="session-separator"></span>${state.routing_mode==='osm'?'OSM 寻路':'模拟路网'}<span class="session-separator"></span>${latest?'最近触发：'+esc(latest.triggers[0]):'等待事件输入'}`;
 requestAnimationFrame(()=>{charts.forEach(c=>!c.isDisposed()&&c.resize());maps.forEach(m=>m.invalidateSize())});
}
function renderFinalResearch(data){
 if(data.ood_summary){const d=data.ood_summary;$('#content').insertAdjacentHTML('beforeend',panel('自然语言挑战集 · 模型增量价值',`<div class="panel-body"><p class="notice">120条冻结文本 / 12类表达。由开发过程辅助编写，未经过第三方独立标注；原始模型与校验方法共享同一次API输出。校验拒绝按弃答计分，离线回退单独记录。</p><div class="two-columns"><div class="chart large" id="ood-chart"></div><div>${table(['方法','事件F1','实体F1','数值F1','校验通过','回退率'],d.results.map(r=>[esc(r.method),...['event_f1','entity_f1','numeric_f1','grounded_pass_rate','fallback_rate'].map(k=>(100*r[k]).toFixed(1)+'%')]))}<p class="notice warn">证据出现在原文中不等于语义正确。否定与含糊信息仍可能被误读，校验通过不能替代人工审核。</p></div></div><details><summary>分组结果与推理延迟</summary>${table(['方法','P50/ms','P95/ms','否定/无关样本的误报率'],d.results.map(r=>[r.method,r.latency_p50_ms.toFixed(1),r.latency_p95_ms.toFixed(1),(100*r.false_action_rate).toFixed(1)+'%']))}${table(['类别','规则事件F1','模型事件F1','校验后事件F1'],Object.entries(d.categories).map(([c,rows])=>[esc(c),...rows.map(r=>(100*r.event_f1).toFixed(1)+'%')]))}</details></div>`,'冻结基线 · 如实记录失败','full'));
 chart('ood-chart',{legend:{bottom:0,textStyle:{fontSize:10}},grid:{left:40,right:18,top:25,bottom:55},tooltip:{trigger:'axis'},xAxis:{type:'category',data:['事件 F1','实体 F1','数值 F1'],axisLabel:{fontSize:11}},yAxis:{type:'value',max:1,splitLine:{lineStyle:{color:'#edf2f7'}}},series:d.results.map(r=>({name:({rules:'规则',deepseek_raw:'DeepSeek',deepseek_grounded:'DeepSeek + 校验'})[r.method],type:'bar',barMaxWidth:22,itemStyle:{borderRadius:[4,4,0,0]},data:[r.event_f1,r.entity_f1,r.numeric_f1]}))});
 }
 if(data.warmup_benchmark){const d=data.warmup_benchmark;$('#content').insertAdjacentHTML('beforeend',panel('预测预热 · 启动与事件耗时分开报告',`<div class="panel-body">${table(['预热后事件路径','次数','P50/ms','P95/ms','P99/ms'],d.summary.map(r=>[r.environment==='synthetic'?'模拟环境':'历史环境',r.repetitions,...['p50_ms','p95_ms','p99_ms'].map(k=>r[k].toFixed(1))]))}<p class="notice">每次事件清空预测结果缓存，但保留已训练模型；包含校验、调度、SQLite保存和状态返回，不包含HTTP及模型网络请求。单轮求解预算0.3秒。与旧内存压力实验口径不同。</p><details><summary>三次独立进程冷启动</summary>${table(['运行','服务初始化/ms','补充预热/ms','就绪总耗时/ms'],d.cold_start.map((r,i)=>[i+1,r.service_init_ms.toFixed(0),r.additional_warmup_ms.toFixed(0),r.total_ready_ms.toFixed(0)]))}</details></div>`,'模拟 / 历史 · 各30次','full'))}
}
