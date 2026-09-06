"""OSM-derived directed routing graph, with explicit experimental speeds."""
from copy import deepcopy
from math import radians, sin, cos, asin, sqrt, ceil
import hashlib
import json
import networkx as nx
from disaster.core import ROOT, read_json

SPEEDS={'motorway':60,'trunk':50,'primary':40,'secondary':35,'tertiary':30,'unclassified':20,'residential':20,'service':10,'living_street':10}

def meters(a,b):
    lat1,lon1,lat2,lon2=map(radians,[a['lat'],a['lon'],b['lat'],b['lon']])
    return 6371000*2*asin(min(1,sqrt(sin((lat2-lat1)/2)**2+cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2)))

def build(snapshot,seed,manifest):
    points={e['id']:e for e in snapshot['elements'] if e['type']=='node'}
    g=nx.DiGraph()
    for way in snapshot['elements']:
        if way['type']!='way':continue
        tags=way.get('tags',{});kind=tags.get('highway','').removesuffix('_link')
        if kind not in SPEEDS:continue
        access=next((tags[k] for k in ('motor_vehicle','vehicle','access') if k in tags),'yes')
        if access in ('no','private'):continue
        direction=tags.get('oneway','yes' if tags.get('junction')=='roundabout' or kind=='motorway' else 'no')
        for u,v in zip(way['nodes'],way['nodes'][1:]):
            if u not in points or v not in points:continue
            length=meters(points[u],points[v]);seconds=length/(SPEEDS[kind]/3.6)
            pairs=[(v,u)] if direction=='-1' else [(u,v)] if direction in ('yes','1','true') else [(u,v),(v,u)]
            for a,b in pairs:
                if not g.has_edge(a,b) or seconds<g[a][b]['seconds']:
                    g.add_edge(a,b,seconds=seconds,length_m=length,way_id=way['id'],highway=tags['highway'])
    # Keep all components. Nearest business anchors may legitimately be unreachable.
    aliases={};anchors=[]
    for n in seed['nodes']:
        nearest=min((p for p in g if p not in aliases),key=lambda p:meters(n,points[p]))
        aliases[nearest]=n['id'];anchors.append(dict(n,osm_id=nearest,original_lat=n['lat'],original_lon=n['lon'],
            lat=points[nearest]['lat'],lon=points[nearest]['lon'],snap_meters=round(meters(n,points[nearest]),1),provenance='simulated_site_snapped_to_osm'))
    # Degree-2 chains can be compressed, but junctions, direction changes and anchors remain.
    undirected=g.to_undirected()
    keep=set(aliases)|{n for n in g if undirected.degree(n)!=2 or g.in_degree(n)!=g.out_degree(n)}
    for component in nx.connected_components(undirected):
        if not keep.intersection(component):keep.add(min(component))
    roads=[];seen=set();selected={}
    for start in sorted(keep):
        for following in g.successors(start):
            if (start,following) in seen:continue
            path=[start,following];seen.add((start,following));seconds=g[start][following]['seconds'];length=g[start][following]['length_m'];ways=[g[start][following]['way_id']]
            previous,current=start,following
            while current not in keep:
                successors=[v for v in g.successors(current) if v!=previous]
                if len(successors)!=1:break
                nxt=successors[0]
                if (current,nxt) in seen:break
                seen.add((current,nxt));edge=g[current][nxt]
                path.append(nxt);seconds+=edge['seconds'];length+=edge['length_m'];ways.append(edge['way_id']);previous,current=current,nxt
            if current==start:continue
            key=(start,current)
            edge=dict(id='OSM-'+hashlib.sha256(json.dumps(path).encode()).hexdigest()[:12],u=aliases.get(start,f'O{start}'),v=aliases.get(current,f'O{current}'),
                minutes=max(1,ceil(seconds/60)),seconds=round(seconds,2),length_m=round(length,1),blocked=False,directed=True,
                osm_node_ids=path,osm_way_ids=sorted(set(ways)),geometry=[[points[p]['lat'],points[p]['lon']] for p in path],
                provenance='osm_geometry_simulated_speed',travel_time_source='experimental_speed_by_highway')
            # DiGraph retains fastest parallel corridor; exact selected geometry is retained.
            if key not in selected or edge['seconds']<selected[key]['seconds']:selected[key]=edge
    roads=list(selected.values());used={e[k] for e in roads for k in ('u','v')}
    nodes=anchors+[dict(id=f'O{p}',name=f'OSM {p}',lat=points[p]['lat'],lon=points[p]['lon'],osm_id=p,kind='road',population=0,provenance='osm')
        for p in sorted(g) if p not in aliases and f'O{p}' in used]
    result=deepcopy(seed);result.update(nodes=nodes,roads=roads,routing_mode='osm',routing_manifest=dict(manifest,
        speeds_kmh=SPEEDS,graph_nodes=len(nodes),directed_edges=len(roads),simplification='degree-2 chains; fastest parallel corridor',
        limitations='No turn restrictions, vehicle dimensions, conditional restrictions or live traffic. Sites snapped; no historical 2024 claim.'))
    return result

def load_scenario():
    folder=ROOT/'data/v2/osm';manifest=read_json(folder/'manifest.json');raw=(folder/'snapshot.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=manifest['sha256']:raise ValueError('OSM快照校验失败')
    return build(json.loads(raw),read_json(ROOT/'data/v2/scenario.json'),manifest)

if __name__=='__main__':
    s=load_scenario();print(json.dumps({'nodes':len(s['nodes']),'roads':len(s['roads']),'snaps':[(n['id'],n['snap_meters']) for n in s['nodes'] if 'snap_meters' in n]},ensure_ascii=False))
