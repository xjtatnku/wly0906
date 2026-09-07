"""Small offline OSM cartographic context from the already verified snapshot."""
import json,math,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def simplify(points,tolerance=.00012):
    if len(points)<3:return points
    a,b=points[0],points[-1];dx=b[0]-a[0];dy=b[1]-a[1];length=dx*dx+dy*dy
    distances=[]
    for p in points[1:-1]:
        t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0
        distances.append(math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy))
    maximum=max(distances)
    if maximum<=tolerance:return [a,b]
    split=distances.index(maximum)+1
    return simplify(points[:split+1],tolerance)[:-1]+simplify(points[split:],tolerance)

def build():
    source=ROOT/'data/v2/osm/snapshot.json';raw=source.read_bytes();data=json.loads(raw);ways=[]
    nodes={e['id']:e for e in data['elements'] if e['type']=='node'}
    for e in data['elements']:
        g=e.get('geometry',[nodes[n] for n in e.get('nodes',[]) if n in nodes]);tags=e.get('tags',{})
        if len(g)<2:continue
        points=simplify([[round(p['lat'],5),round(p['lon'],5)] for p in g])
        ways.append(dict(points=points,kind=tags.get('highway','road')))
    output=dict(attribution='© OpenStreetMap contributors · ODbL',snapshot_at=data['osm3s']['timestamp_osm_base'],
        source_sha256=hashlib.sha256(raw).hexdigest(),description='Simplified current OSM roads for visual context only; not the 2024 disaster road network or solver input.',ways=ways)
    (ROOT/'frontend/map-context.json').write_text(json.dumps(output,separators=(',',':')),encoding='utf-8')
    print(len(ways),'context ways')
if __name__=='__main__':build()
