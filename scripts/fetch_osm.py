"""Download a bounded, attributable OSM snapshot. Never called during app startup."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
QUERY='[out:json][timeout:45];way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street)(_link)?$"](29.96,102.02,30.15,102.25);out meta;>;out skel qt;'

def fetch():
    out=ROOT/'data/v2/osm';out.mkdir(exist_ok=True)
    session=requests.Session();session.trust_env=False
    session.headers['User-Agent']='KangdingResearchPrototype/2.1 (bounded academic demo)'
    failures=[]
    for endpoint in ['https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter']:
        try:
            response=session.get(endpoint,params={'data':QUERY},timeout=55);response.raise_for_status()
            data=response.json()
            if 'remark' in data or not data.get('elements'):raise ValueError('Incomplete Overpass result')
            raw=response.content;(out/'snapshot.json').write_bytes(raw)
            manifest=dict(endpoint=endpoint,query=QUERY,retrieved_at=datetime.now(timezone.utc).isoformat(),
                osm_base=data.get('osm3s',{}).get('timestamp_osm_base'),sha256=hashlib.sha256(raw).hexdigest(),
                attribution='© OpenStreetMap contributors',license='ODbL 1.0',license_url='https://www.openstreetmap.org/copyright',
                scope='Current OSM snapshot, NOT historical 2024 roads; no live closures or measured travel times.')
            (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f"Downloaded {len(data['elements'])} elements, {len(raw)} bytes",flush=True);return
        except (requests.RequestException,ValueError) as exc:
            failures.append(type(exc).__name__);print(endpoint,type(exc).__name__,flush=True)
    raise RuntimeError('OSM snapshot unavailable: '+','.join(failures))

if __name__=='__main__':fetch()
