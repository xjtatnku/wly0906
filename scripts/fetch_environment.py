"""Immutable HTTP response snapshots for retrospective environmental research."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,requests

ROOT=Path(__file__).resolve().parents[1]
NASA='https://gis.earthdata.nasa.gov/portal/rest/services/GESDISC/GPM_3IMERGHH/ImageServer'
POINTS=[(102.15,30.15),(102.25,30.05),(102.25,30.15)]

def fetch():
    folder=ROOT/'data/bronze/environment';folder.mkdir(parents=True,exist_ok=True)
    session=requests.Session();session.trust_env=False
    def get(name,url,params,source,license):
        path=folder/(name+'.json');manifest=folder/(name+'.manifest.json')
        if path.exists():
            metadata=json.loads(manifest.read_text(encoding='utf-8'))
            assert hashlib.sha256(path.read_bytes()).hexdigest()==metadata['sha256']
            return json.loads(path.read_bytes())
        response=session.get(url,params=params,timeout=50);response.raise_for_status();data=response.json()
        if 'error' in data:raise RuntimeError(str(data['error']))
        raw=response.content;path.write_bytes(raw)
        manifest.write_text(json.dumps(dict(source=source,url=url,query=params,download_time=datetime.now(timezone.utc).isoformat(),
            sha256=hashlib.sha256(raw).hexdigest(),license=license,scope='Retrospective final/reanalysis product, not available in real time at the 2024 event'),ensure_ascii=False,indent=2),encoding='utf-8')
        return data
    get('gpm_service',NASA,{'f':'json'},'NASA GES DISC IMERG Final V07','NASA Earthdata open data; cite GPM_3IMERGHH_07')
    get('gpm_item','https://gis.earthdata.nasa.gov/portal/sharing/rest/content/items/cfa9a890b89b49d884871567844e9080',{'f':'json'},'NASA Earthdata EGIS','NASA Earthdata')
    for period in range(17*4):
        start=datetime(2024,7,20,tzinfo=timezone.utc)+timedelta(hours=period*6);end=start+timedelta(hours=6)
        where=f"StdTime >= timestamp '{start:%Y-%m-%d %H:%M:%S}' AND StdTime < timestamp '{end:%Y-%m-%d %H:%M:%S}'"
        params=dict(f='json',geometry=json.dumps({'points':POINTS,'spatialReference':{'wkid':4326}}),geometryType='esriGeometryMultipoint',
            returnFirstValueOnly='false',outFields='*',mosaicRule=json.dumps({'where':where}),interpolation='RSP_NearestNeighbor')
        data=get('gpm_'+start.strftime('%Y%m%d_%H'),NASA+'/getSamples',params,'NASA GES DISC IMERG Final V07','NASA Earthdata open data; cite GPM_3IMERGHH_07')
        expected={(i,int((start+timedelta(minutes=30*j)).timestamp()*1000)) for i in range(3) for j in range(12)}
        actual={(r['locationId'],r['attributes']['stdtime']) for r in data.get('samples',[])}
        if actual!=expected:raise ValueError(f'Incomplete sample grid: {len(actual)} of {len(expected)}')
        print(start.isoformat(),'verified GPM samples',len(actual),flush=True)
    for i,(lon,lat) in enumerate(POINTS,1):
        data=get(f'era5_S0{i}','https://archive-api.open-meteo.com/v1/archive',dict(latitude=lat,longitude=lon,start_date='2024-07-20',
            end_date='2024-08-05',hourly='soil_moisture_0_to_7cm',models='era5_land',timezone='UTC',cell_selection='nearest',elevation='nan'),
            'ERA5-Land via Open-Meteo archive API','CC BY 4.0; Copernicus Climate Change Service/ECMWF and Open-Meteo')
        print('ERA5',i,len(data['hourly']['time']),flush=True)

if __name__=='__main__':fetch()
