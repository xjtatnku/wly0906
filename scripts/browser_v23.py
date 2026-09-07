"""Real model + nine-stage browser acceptance; leaves current scenario intact."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/v23'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1680,'height':1050})
    page.set_default_timeout(90000);errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    url='http://127.0.0.1:8800'
    for _ in range(30):
        try:
            if page.request.get(url+'/api/health',timeout=1500).ok:break
        except Exception:pass
        time.sleep(1)
    page.goto(url,wait_until='networkidle')
    page.locator('[data-page="strategy"]').click();page.locator('#scenario-start').click()
    page.wait_for_function("document.querySelector('#scenario-prepare') && !document.querySelector('#scenario-prepare').disabled")
    # Exercise actual DeepSeek extraction without committing or consuming the stage sequence.
    page.locator('#batch-text').fill('N4 失联8人，受伤3人，需要搜救和医疗。')
    page.locator('#batch-live').check();page.locator('#batch-extract').click()
    page.locator('#batch-json').wait_for()
    live_mode=page.locator('#batch-review').inner_text()
    assert '实时 DeepSeek' in live_mode,live_mode[:120]
    page.screenshot(path=str(OUT/'deepseek-intake.png'),full_page=True)
    page.locator('#batch-reject').click()
    page.wait_for_function("!document.querySelector('#batch-json')")
    traces=[]
    for index in range(9):
        page.locator('#scenario-prepare').click();page.locator('#batch-json').wait_for()
        page.locator('#batch-confirm').click()
        page.wait_for_function("!document.querySelector('#batch-json') && document.querySelector('#scenario-start') && !document.querySelector('#scenario-start').disabled")
        state=page.request.get(url+'/api/state').json()
        assert state['scenario_cursor']==index+1
        traces.append(dict(stage=index,minute=state['minute'],casualties=state['casualties'],trace=state['decision_traces'][-1]))
        if index in (1,3,7):
            page.locator('[data-page="dispatch"]').click();page.locator('#objective-mode').wait_for()
            page.screenshot(path=str(OUT/f'stage-{index}-dispatch.png'),full_page=True)
            page.locator('[data-page="strategy"]').click();page.locator('#scenario-prepare').wait_for()
    assert state['casualties']['missing']==15 and len(state['situation_reports'])==3
    page.locator('#explain-live').click()
    page.wait_for_function("!document.querySelector('#explain-live').disabled && document.querySelector('#explain-result').textContent.length>0")
    assert '实时 DeepSeek' in page.locator('#explain-result').inner_text()
    page.screenshot(path=str(OUT/'stage-final-strategy.png'),full_page=True)
    page.locator('[data-page="dispatch"]').click()
    page.locator('#objective-mode').select_option('lexicographic');page.locator('#objective-apply').click()
    page.wait_for_function("!document.querySelector('#objective-apply').disabled")
    state=page.request.get(url+'/api/state').json()
    assert state['settings']['objective_mode']=='lexicographic' and state['plan']['lexicographic_levels']
    page.locator('[data-page="replay"]').click();page.locator('#paired-table').wait_for()
    page.screenshot(path=str(OUT/'paired-replay.png'),full_page=True)
    page.set_viewport_size({'width':1280,'height':900})
    for target in ('strategy','dispatch','replay'):
        page.locator(f'[data-page="{target}"]').click();page.wait_for_timeout(800)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),target
    assert not errors,errors
    (OUT/'event_replay_traces.json').write_text(json.dumps(traces,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'browser_validation.json').write_text(json.dumps(dict(errors=errors,stages=9,live_extraction=True,live_explanation=True,
        missing_final=15,report_versions=3,lexicographic_ui=True,viewport_1280=True),indent=2),encoding='utf-8')
    print('Live extraction/explanation and nine-stage browser replay passed',flush=True)
    browser.close()
