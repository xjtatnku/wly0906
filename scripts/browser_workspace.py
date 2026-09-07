import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path('results/workspace');OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1680,'height':1050});page.set_default_timeout(60000)
    errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url) if r.resource_type!='other' else None)
    page.goto('http://127.0.0.1:8800',wait_until='networkidle')
    page.wait_for_function('typeof state!=="undefined"&&!!state')
    for width in (1680,1280,390):
        page.set_viewport_size({'width':width,'height':1050 if width==1680 else 900})
        for name in ('overview','data','prediction','dispatch','strategy','replay'):
            page.evaluate('(name)=>navigate(name)',name);page.wait_for_timeout(300)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,name)
            body=page.locator('body').inner_text()
            for term in ('SQLite','JSON','CP-SAT','OPTIMAL','DeepSeek','API','SHA','schema','.env','数据库','求解','TF-IDF'):
                assert term not in body,(name,term)
            assert page.locator('pre').count()==0
            if width==1680:page.screenshot(path=str(OUT/(name+'.png')))
    page.set_viewport_size({'width':1680,'height':1050});page.evaluate("()=>navigate('overview')")
    assert page.locator('.country-view').count()==1
    page.locator('[data-view="local"]').click();assert page.locator('.country-view').count()==0
    page.locator('[data-layer="risk"]').click();assert page.locator('[data-layer="risk"]').get_attribute('aria-pressed')=='false'
    page.locator('[data-view="country"]').click();assert page.locator('.country-view').count()==1
    assert page.request.get('http://127.0.0.1:8800/api/state').status==404
    assert page.request.get('http://127.0.0.1:8800/openapi.json').status==404
    page.evaluate("()=>navigate('strategy')");page.locator('#start-exercise').click();page.locator('#modal-confirm').click()
    page.wait_for_function('state.scenario_cursor===0&&!document.querySelector("#prepare-stage").disabled')
    for i in range(9):
        page.locator('#prepare-stage').click();page.locator('#confirm-report').wait_for()
        assert page.locator('.review-form').count()>0
        if i==1:page.screenshot(path=str(OUT/'review.png'),full_page=True)
        page.locator('#confirm-report').click()
        page.wait_for_function('(i)=>state.scenario_cursor===i&&!document.querySelector("#confirm-report")',arg=i+1)
    assert page.evaluate('state.casualties.missing')==15
    assert page.evaluate('state.reports.length')==3
    page.evaluate("()=>navigate('dispatch')");page.locator('#preference').select_option('urgent');page.locator('#dispatch-action').click()
    page.wait_for_function('!document.querySelector("#dispatch-action").disabled')
    page.evaluate("()=>navigate('overview')")
    assert not errors,errors
    assert not [url for url in requests if '/api/research' in url],requests
    result=dict(errors=errors,pages=6,widths=[1680,1280,390],country_local_toggle=True,internal_ui_terms=False,legacy_api_blocked=True,stages=9,missing=15,report_versions=3)
    (OUT/'browser_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');b.close();print('Workspace browser acceptance passed')
