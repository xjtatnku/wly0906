"""V2.2 real-data switch, multistation charts, objective control and human review."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'results/v22'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1680,'height':1050})
    page.set_default_timeout(60000)
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    url='http://127.0.0.1:8800'
    assert page.request.post(url+'/api/reset',data={'routing_mode':'simulated','environment_mode':'synthetic','risk_mode':'rule'}).ok
    page.goto(url,wait_until='networkidle')
    page.locator('[data-page="data"]').click()
    page.locator('#environment-mode').select_option('historical')
    page.locator('#risk-mode').select_option('empirical')
    page.locator('#apply-environment').click()
    page.wait_for_function("document.querySelector('#environment-mode')?.value==='historical' && !document.querySelector('#apply-environment').disabled")
    state=page.request.get(url+'/api/state').json()
    assert state['environment_mode']=='historical' and len(state['sensor_types'])==2
    assert len(state['data_health'])==6 and state['forecast']['cadence_minutes']==60
    assert page.request.post(url+'/api/ingest',data={'rows':[]}).status==422
    page.screenshot(path=str(out/'historical-data.png'),full_page=True)
    page.locator('[data-page="prediction"]').click()
    page.locator('#forecast-station').select_option('S03')
    page.locator('#eval-kind').wait_for()
    page.locator('#eval-kind').select_option('soil_moisture')
    assert page.locator('#eval-table tbody tr').count()==12
    assert '720分钟' in page.locator('#eval-table').inner_text()
    assert page.request.get(url+'/api/research/export/forecast_historical').ok
    assert '${' not in page.locator('#content').inner_text()
    page.screenshot(path=str(out/'historical-prediction.png'),full_page=True)
    page.locator('[data-page="dispatch"]').click()
    page.locator('#response-weight').fill('0')
    page.locator('#apply-response').click()
    page.wait_for_function("document.querySelector('#apply-response') && !document.querySelector('#apply-response').disabled")
    state=page.request.get(url+'/api/state').json()
    assert state['settings']['response_weight']==0
    assert state['decision_traces'][-1]['environment_mode']=='historical'
    assert 'station_observations' in state['decision_traces'][-1]
    page.screenshot(path=str(out/'historical-decision.png'),full_page=True)
    page.locator('[data-page="strategy"]').click()
    page.locator('#extract').click()
    page.locator('#reject-event').wait_for()
    before=page.request.get(url+'/api/state').json()
    page.locator('#reject-event').click()
    page.wait_for_function("!document.querySelector('#reject-event') && !document.querySelector('#extract').disabled")
    after=page.request.get(url+'/api/state').json()
    assert after['tasks']==before['tasks'] and after['resources']==before['resources']
    assert after['events'][-1]['kind']=='rejected' and after['revision']==before['revision']+1
    page.locator('#extract').click()
    page.locator('#candidate-node').select_option('N8')
    page.locator('#confirm-event').click()
    page.wait_for_function("!document.querySelector('#confirm-event') && !document.querySelector('#extract').disabled")
    after=page.request.get(url+'/api/state').json()
    assert any(t['node']=='N8' and t['provenance']=='user_confirmed' for t in after['tasks'])
    page.locator('[data-page="replay"]').click()
    page.locator('#result-scale').select_option('0.35')
    page.locator('#result-rate').select_option('high')
    assert page.locator('#factorial-results tbody tr').count()==4
    page.screenshot(path=str(out/'research-replay.png'),full_page=True)
    page.set_viewport_size({'width':1280,'height':900})
    for target in ['data','prediction','dispatch','strategy','replay']:
        page.locator(f'[data-page="{target}"]').click()
        page.wait_for_timeout(600)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),target
    assert not errors,errors
    (out/'browser_validation.json').write_text(json.dumps(dict(errors=errors,checks=['six pages','historical switch','native horizons',
        'multistation display','response objective','persistent trace','reject audit','edited approval','factorial filter','1280px no overflow']),indent=2),encoding='utf-8')
    print('V2.2 browser checks passed; no page errors',flush=True)
    # Leave the local console in a clean, reproducible demo state.
    assert page.request.post(url+'/api/reset',data={'routing_mode':'simulated','environment_mode':'synthetic','risk_mode':'rule'}).ok
    assert page.request.post(url+'/api/optimize',data={'response_weight':10,'forecast':True,'horizon':60,'stability':20}).ok
    browser.close()
