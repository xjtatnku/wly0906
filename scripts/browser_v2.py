from pathlib import Path
import json
import time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'results/v21';out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1680,'height':1050},device_scale_factor=1)
    for attempt in range(30):
        try:
            if page.request.get('http://127.0.0.1:8800/api/health',timeout=1000).ok:break
        except Exception:pass
        time.sleep(1)
    assert page.request.post('http://127.0.0.1:8800/api/reset',data={'routing_mode':'simulated'}).ok
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8800',wait_until='networkidle')
    page.locator('.cards').wait_for()
    for target in ['overview','data','prediction','dispatch','strategy','replay']:
        page.locator(f'[data-page="{target}"]').click()
        page.wait_for_timeout(800)
        if target=='data':
            observation=page.request.get('http://127.0.0.1:8800/api/state').json()['observations'][0]
            page.locator('#import-file').set_input_files({'name':'observations.json','mimeType':'application/json','buffer':json.dumps([observation]).encode()})
            page.locator('#import-btn').click()
            page.wait_for_function("document.querySelector('#import-btn') && !document.querySelector('#import-btn').disabled")
        if target=='dispatch':
            page.locator('#optimize').click()
            page.wait_for_function("document.querySelector('#optimize') && !document.querySelector('#optimize').disabled")
            page.wait_for_timeout(500)
            page.locator('#road-select').select_option('RD00')
            page.locator('#block-road').click()
            page.wait_for_function("document.querySelector('#block-road') && !document.querySelector('#block-road').disabled")
            assert page.request.get('http://127.0.0.1:8800/api/state').json()['metrics']['blocked']==1
        if target=='strategy':
            before=page.request.get('http://127.0.0.1:8800/api/state').json()['revision']
            page.locator('#what-run').click();page.locator('.strategy').first.wait_for()
            assert page.locator('.strategy').count()==3
            assert page.request.get('http://127.0.0.1:8800/api/state').json()['revision']==before
            page.locator('#extract').click();page.locator('#candidate-node').wait_for()
        page.evaluate('window.scrollTo(0,0)')
        page.wait_for_timeout(200)
        page.screenshot(path=str(out/f'{target}.png'),full_page=True)
        print(target,'captured')
        if target=='strategy':
            page.locator('#confirm-event').click()
            page.wait_for_function("document.querySelector('#extract') && !document.querySelector('#extract').disabled && !document.querySelector('#confirm-event')")
            current=page.request.get('http://127.0.0.1:8800/api/state').json()
            assert current['casualties']=={'missing':12,'injured':5}
            page.locator('#advance').click()
            page.wait_for_function("!document.querySelector('#advance').disabled")
            assert page.request.get('http://127.0.0.1:8800/api/state').json()['minute']==10
        if target=='replay':
            page.locator('#history-select').select_option(index=0);page.locator('#load-history').click()
            page.wait_for_timeout(500)
            page.locator('#live-state').click();page.wait_for_timeout(500)
    page.set_viewport_size({'width':1280,'height':900})
    page.locator('[data-page="overview"]').click();page.wait_for_timeout(500)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(out/'overview-1280.png'),full_page=True)
    page.set_viewport_size({'width':1680,'height':1050})
    page.locator('[data-page="dispatch"]').click();page.locator('#routing-mode').wait_for()
    page.locator('#routing-mode').select_option('osm');page.locator('#switch-routing').click()
    page.wait_for_function("document.querySelector('#routing-mode')?.value==='osm' && !document.querySelector('#switch-routing').disabled")
    page.locator('#optimize').click();page.wait_for_function("!document.querySelector('#optimize').disabled")
    current=page.request.get('http://127.0.0.1:8800/api/state').json()
    assert current['routing_mode']=='osm' and len(current['roads'])>100
    assert any(a['geometry'] for a in current['plan']['assignments'])
    page.locator('#failure-resource').select_option('RES01');page.locator('#fail-resource').click()
    page.wait_for_function("!document.querySelector('#fail-resource').disabled")
    page.locator('#advance').click();page.wait_for_function("!document.querySelector('#advance').disabled")
    page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(200)
    page.screenshot(path=str(out/'osm-dispatch.png'),full_page=True)
    print('Browser errors:',errors)
    assert not errors
    browser.close()
