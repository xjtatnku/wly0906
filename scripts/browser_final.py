"""Browser acceptance: real controls, local-only maps, viewports and event replay."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/v23/final'

def run():
    OUT.mkdir(exist_ok=True,parents=True);errors=[];measurements=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1680,'height':1050});page.set_default_timeout(60000)
        page.on('pageerror',lambda e:errors.append(str(e)))
        # Default dashboard must not require network tile services.
        external=[]
        page.route('https://**/*',lambda route:(external.append(route.request.url),route.abort()))
        page.goto('http://127.0.0.1:8800',wait_until='networkidle')
        page.evaluate("async()=>{await api('reset',{environment_mode:'synthetic',routing_mode:'simulated'});await api('optimize',{...state.settings,objective_mode:'weighted'});await refresh()}")
        for width in (1680,1280,390):
            page.set_viewport_size({'width':width,'height':1050 if width==1680 else 900})
            for name in ('overview','data','prediction','dispatch','strategy','replay'):
                started=time.perf_counter();page.evaluate('(name)=>navigate(name)',name)
                page.wait_for_timeout(300)
                overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                assert not overflow,(width,name)
                assert page.locator('#content .panel').count()>0
                assert page.locator('.leaflet-container').count()<=1
                if width==1680:
                    page.screenshot(path=str(OUT/(name+'.png')),full_page=True)
                    page.screenshot(path=str(OUT/(name+'-screen.png')))
                measurements.append(dict(page=name,width=width,navigation_ms=(time.perf_counter()-started)*1000,
                    dom_elements=page.locator('*').count(),horizontal_overflow=overflow))
        page.set_viewport_size({'width':1680,'height':1050});page.evaluate("()=>navigate('overview')")
        layer=page.locator('[data-layer="risk"]');layer.click();assert layer.get_attribute('aria-pressed')=='false';layer.click()
        page.locator('[data-fit]').click()
        assert not external,external
        page.evaluate("()=>navigate('strategy')")
        assert page.locator('#event-text').count()==0
        page.locator('#batch-live').check();page.locator('#batch-extract').click();page.locator('#batch-json').wait_for()
        assert '实时 DeepSeek' in page.locator('#batch-review').inner_text()
        assert page.locator('.candidate-card').count()>=1
        page.screenshot(path=str(OUT/'review.png'),full_page=True)
        page.locator('#batch-reject').click();page.wait_for_function("!document.querySelector('#batch-json')")
        page.locator('#scenario-start').click()
        page.wait_for_function("document.querySelector('#scenario-prepare')&&!document.querySelector('#scenario-prepare').disabled")
        for index in range(9):
            page.locator('#scenario-prepare').click();page.locator('#batch-json').wait_for()
            page.locator('#batch-confirm').click()
            page.wait_for_function('(i)=>state.scenario_cursor===i&&!document.querySelector("#batch-json")',arg=index+1)
        assert page.evaluate('state.casualties.missing')==15
        assert page.evaluate('Object.keys(state.situation_reports).length')==3
        page.evaluate("()=>navigate('dispatch')")
        page.locator('#objective-mode').select_option('lexicographic');page.locator('#objective-apply').click()
        page.wait_for_function("state.settings.objective_mode==='lexicographic'&&!document.querySelector('#objective-apply').disabled")
        for _ in range(3):
            for name in ('overview','dispatch','strategy'):page.evaluate('(name)=>navigate(name)',name)
        assert page.evaluate('maps.length')==0
        assert page.evaluate('charts.length')==0
        assert not errors,errors
        page.evaluate("()=>navigate('overview')")
        result=dict(errors=errors,measurements=measurements,external_requests_default=external,stages=9,missing=15,report_versions=3,
            real_deepseek_extraction=True,lexicographic=True,map_controls=True,repeat_navigation=True,
            note='Navigation time includes API/state load, rendering, 300ms animation settle, and screenshot on 1680px; not a pure paint benchmark.')
        (OUT/'browser_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        browser.close();print('Browser acceptance passed',flush=True)

if __name__=='__main__':run()
