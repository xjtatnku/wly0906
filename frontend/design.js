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
let chinaPromise;
function attachCountry(map,el,fit,id){
 const canvas=document.createElement('div');canvas.className='country-map';el.append(canvas);
 let countryChart,disposed=false,mode=id==='main-map'?'country':'local';
 const toggle=value=>{mode=value;el.classList.toggle('country-view',mode==='country');el.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('selected',b.dataset.view===mode);b.setAttribute('aria-pressed',String(b.dataset.view===mode))});el.parentElement.querySelector('.map-status').textContent=mode==='country'?'全国区位 · 点击四川查看康定现场':'康定现场 · 道路、风险与救援资源';if(mode==='local'){map.invalidateSize();fit()}else countryChart?.resize()};
 el.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>toggle(b.dataset.view));
 map.on('unload',()=>{disposed=true;if(countryChart)countryChart.dispose()});
 toggle(mode);
 chinaPromise??=fetch('/assets/china.json').then(r=>{if(!r.ok)throw Error();return r.json()});
 chinaPromise.then(geo=>{if(disposed)return;echarts.registerMap('china-workspace',geo);countryChart=echarts.init(canvas,null,{renderer:'canvas',width:el.clientWidth,height:el.clientHeight});charts.push(countryChart);
 countryChart.setOption({animation:false,tooltip:{trigger:'item',formatter:p=>p.name==='四川省'?'四川省 · 康定工作区域<br>点击进入现场':esc(p.name||'中国地图')+'<br>当前未接入此区域业务数据'},geo:{map:'china-workspace',roam:true,layoutCenter:['50%','54%'],layoutSize:'93%',label:{show:true,fontSize:9,color:'#7391ac'},itemStyle:{areaColor:'#deedf8',borderColor:'#90b9d9',borderWidth:.8,shadowColor:'#588bbd18',shadowBlur:7},emphasis:{label:{color:'#246db2'},itemStyle:{areaColor:'#bbdcf5'}},regions:[{name:'四川省',itemStyle:{areaColor:'#70b4ee'},label:{color:'#124e85',fontWeight:'bold'}}]},series:[{type:'scatter',coordinateSystem:'geo',symbolSize:13,itemStyle:{color:'#f18050',borderColor:'#fff',borderWidth:2},label:{show:true,formatter:'康定',position:'left',color:'#225378',fontSize:11},data:[{name:'康定',value:[102.18,30.08]}]}]});countryChart.on('click',p=>{if(p.name==='四川省'||p.name==='康定')toggle('local')});if(mode==='country')countryChart.resize();
 }).catch(()=>{if(!disposed){canvas.innerHTML='<div class="empty">全国地图暂不可用，请切换康定现场。</div>'}});
}
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
   L.marker([n.lat+.005,n.lon+.065],{interactive:false,icon:L.divIcon({className:'zone-label',html:`${score>=.7?'高风险':'中风险'}区域`,iconSize:[72,22]})}).addTo(zones);
  }
  const kind=n.kind==='hospital'?'medical':n.kind==='shelter'?'home':n.kind==='base'?'shield':'pin';
  const marker=L.marker([n.lat,n.lon],{icon:L.divIcon({className:'map-node '+kind,html:icon(kind),iconSize:[26,26],iconAnchor:[13,13]})});
  const right=['N4','N5','N8','N9','N2'].includes(n.id);
  marker.addTo(map).bindTooltip(esc(n.name.replace('模拟','')),{permanent:true,direction:right?'right':'left',className:'node-label',offset:[right?13:-13,0]})
   .bindPopup(`<b>${esc(n.name)}</b><p>区域人口 ${n.population}</p>`);
 }
 for(const road of state.roads){
  const a=node(road.u),b=node(road.v),geometry=road.geometry||[[a.lat,a.lon],[b.lat,b.lon]];
  L.polyline(geometry,{color:'#162f37',weight:6,opacity:.75,interactive:false}).addTo(routes);
  L.polyline(geometry,{color:road.blocked?'#ff6268':'#e4bf74',weight:road.blocked?3.5:2,dashArray:road.blocked?'6 6':null}).addTo(routes)
   .bindPopup(`<b>${esc(roadName(road.id))} · ${road.blocked?'道路阻断':'可通行'}</b><p>${road.minutes} 分钟 · 预计行程</p>`);
  if(road.blocked){const middle=geometry[Math.floor(geometry.length/2)];L.marker(middle,{icon:L.divIcon({className:'road-block',html:'−',iconSize:[22,22]})}).addTo(routes)}
 }
 const colors={rescue_team:'#58aaff',medical_team:'#ff7e9d',ambulance:'#ff7e9d',engineering_team:'#3dd8b0',excavator:'#3dd8b0',drone:'#ba9bff',supply_vehicle:'#ffc15c'};
 for(const a of displayAssignments())L.polyline(a.geometry?.length?a.geometry:a.path.map(n=>[node(n).lat,node(n).lon]),{color:colors[a.type]||'#58aaff',weight:3,dashArray:'9 5',opacity:.95}).addTo(resources)
  .bindPopup(`${esc(resource(a.resource))} → ${esc(publicText(a.name))}<p>出发 ${timeAt(a.depart)} · 到达 ${timeAt(a.arrival)} · 结束 ${timeAt(a.end)}</p>`);
 // Aggregate co-located resources; do not invent jittered geographic positions.
 for(const n of state.nodes){const group=state.resources.filter(r=>r.node===n.id&&r.available_at<=state.minute);if(!group.length)continue;
  L.marker([n.lat,n.lon],{icon:L.divIcon({className:'resource-count',html:`${icon('people')}<b>${group.length}</b>`,iconSize:[38,22],iconAnchor:[-14,-9]})}).addTo(resources)
   .bindPopup(`<b>${esc(n.name)} · ${group.length} 项资源</b>`+group.map(r=>`<p>${esc(r.name)} · ${esc(statusName(r.status))}</p>`).join(''));
 }
 const tile=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18});
 let errors=0;tile.on('tileerror',()=>{if(++errors===3){el.parentElement.querySelector('.map-status').textContent='街道地图暂不可用，请使用简洁地图'}});
 const controls=el.querySelector('.map-tools');L.DomEvent.disableClickPropagation(controls);L.DomEvent.disableScrollPropagation(controls);
 controls.querySelectorAll('[data-base]').forEach(b=>b.onclick=()=>{
  const online=b.dataset.base==='online';if(online)tile.addTo(map);else map.removeLayer(tile);
  el.classList.toggle('online-base',online);controls.querySelectorAll('[data-base]').forEach(x=>x.classList.toggle('selected',x===b));
  el.parentElement.querySelector('.map-status').textContent=online?'街道地图':'康定工作区域';
 });
 for(const [key,layer] of [['risk',zones],['resources',resources]])controls.querySelector(`[data-layer="${key}"]`).onclick=function(){const active=map.hasLayer(layer);if(active)map.removeLayer(layer);else layer.addTo(map);this.classList.toggle('selected',!active);this.setAttribute('aria-pressed',String(!active))};
 attachCountry(map,el,fit,id);
 controls.querySelector('[data-fit]').onclick=()=>{el.querySelector('[data-view=local]').click();fit()};
 return map;
}
