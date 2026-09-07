"""Bronze -> native-resolution Silver -> causal hourly Gold for retrospective replay."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import csv,hashlib,json,math
from disaster.core import ROOT

EPOCH=datetime(2024,8,3,1,tzinfo=timezone.utc)
def build():
    bronze=ROOT/'data/bronze/environment';silver=ROOT/'data/silver';gold=ROOT/'data/gold';silver.mkdir(exist_ok=True);gold.mkdir(exist_ok=True)
    rows=[];sources=[];seen=set()
    for path in sorted(bronze.glob('*.json')):
        if path.name.endswith('.manifest.json'):continue
        if not (path.name.startswith('era5_') or (path.name.startswith('gpm_2024') and '_' in path.stem[4:])):continue
        manifest=json.loads(path.with_suffix('.manifest.json').read_text(encoding='utf-8'));raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=manifest['sha256']:raise ValueError('Bronze checksum mismatch')
        data=json.loads(raw);sources.append(dict(file=path.relative_to(ROOT).as_posix(),**manifest))
        if path.name.startswith('gpm'):
            for sample in data['samples']:
                observed=datetime.fromtimestamp(sample['attributes']['stdtime']/1000,timezone.utc)
                value=float(sample['value'])
                rows.append(dict(station_id=f'S{sample["locationId"]+1:02}',type='rainfall',observed_at=observed.isoformat(),
                    value=value,unit='mm/h',lat=sample['location']['y'],lon=sample['location']['x'],cadence_minutes=30,
                    interval_end=(observed+timedelta(minutes=30)).isoformat(),source='GPM_IMERG_Final_V07',
                    source_file=path.name,source_sha256=manifest['sha256'],received_at=manifest['download_time'],quality='valid' if 0<=value<=200 else 'invalid'))
        else:
            station=path.stem.split('_')[1]
            for stamp,value in zip(data['hourly']['time'],data['hourly']['soil_moisture_0_to_7cm']):
                observed=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
                rows.append(dict(station_id=station,type='soil_moisture',observed_at=observed.isoformat(),value=value*100 if value is not None else None,
                    unit='%',lat=data['latitude'],lon=data['longitude'],cadence_minutes=60,interval_end=observed.isoformat(),
                    source='ERA5_Land_OpenMeteo',source_file=path.name,source_sha256=manifest['sha256'],received_at=manifest['download_time'],
                    quality='valid' if value is not None and 0<=value<=1 else 'invalid'))
    unique=[]
    for row in rows:
        key=(row['station_id'],row['type'],row['observed_at'])
        if key in seen:raise ValueError('Duplicate canonical observation')
        seen.add(key);unique.append(row)
    if not unique:raise ValueError('No verified historical data')
    (silver/'environment_native.json').write_text(json.dumps(unique,ensure_ascii=False,indent=2),encoding='utf-8')
    aligned=[]
    for station in ('S01','S02','S03'):
        soil={datetime.fromisoformat(r['observed_at']):r for r in unique if r['station_id']==station and r['type']=='soil_moisture' and r['quality']=='valid'}
        rain={datetime.fromisoformat(r['observed_at']):r for r in unique if r['station_id']==station and r['type']=='rainfall' and r['quality']=='valid'}
        for stamp,s in sorted(soil.items()):
            intervals=[rain.get(stamp-timedelta(minutes=m)) for m in (60,30)]
            if any(r is None for r in intervals):continue
            for kind,items,value in [('rainfall',intervals,sum(r['value']*.5 for r in intervals)),('soil_moisture',[s],s['value'])]:
                aligned.append(dict(station_id=station,type=kind,minute=int((stamp-EPOCH).total_seconds()/60),timestamp=stamp.isoformat(),observed_at=stamp.isoformat(),
                    received_minute=int((stamp-EPOCH).total_seconds()/60),received_at=max(r['received_at'] for r in items),value=value,
                    unit='mm/h' if kind=='rainfall' else '%',lat=items[0]['lat'],lon=items[0]['lon'],quality='valid',provenance='historical_reanalysis_retrospective',
                    source_id=items[0]['source'],source_sha256=[r['source_sha256'] for r in items],cadence_minutes=60,
                    transformation='previous two completed half-hour rates integrated then expressed as hourly mean rate' if kind=='rainfall' else 'volume fraction times 100'))
    aligned.sort(key=lambda r:(r['minute'],r['station_id'],r['type']))
    (gold/'environment_hourly.json').write_text(json.dumps(aligned,ensure_ascii=False,indent=2),encoding='utf-8')
    report=dict(native_rows=len(unique),hourly_rows=len(aligned),sources=sources,water_level='not available; excluded',displacement='not available; excluded',
        mode='retrospective environmental forcing',clock='observation-clock replay, NOT original publication availability',
        warning='IMERG Final and ERA5-Land use retrospective information; cannot claim historical operational forecast skill',
        alignment='No interpolation to 5 minutes. Hourly gold uses only intervals completed at or before the row time.')
    (gold/'environment_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('native_rows','hourly_rows')}))
    return report

class HistoricalFeed:
    def __init__(self):
        self.rows=json.loads((ROOT/'data/gold/environment_hourly.json').read_text(encoding='utf-8'))
    def observations(self,minute,limit=1440):return [r for r in self.rows if minute-limit<=r['minute']<=minute and r['received_minute']<=minute]
    def health(self,minute):
        result=[]
        for station in ('S01','S02','S03'):
            for kind in ('rainfall','soil_moisture'):
                rows=[r for r in self.observations(minute,10000) if r['station_id']==station and r['type']==kind]
                latest=rows[-1] if rows else None;age=(minute-latest['minute'])*60 if latest else None
                result.append(dict(source_id=station+':'+kind,observed_at=latest['observed_at'] if latest else None,received_at=latest['received_at'] if latest else None,
                    freshness_seconds=age,heartbeat_age_seconds=age,source_status='FRESH' if age is not None and age<=3600 else 'STALE',quality_rate=1 if latest else None,
                    missing_rate=1-len({r['minute'] for r in rows if minute//60*60-360<=r['minute']<=minute})/7,clock='retrospective_hourly',cadence_minutes=60))
        return result

if __name__=='__main__':build()
