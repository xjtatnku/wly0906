"""Optional visual smoke check; requires Playwright in the executing environment."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
    page.goto('http://127.0.0.1:8501',wait_until='networkidle')
    page.get_by_role('button',name='推进下一阶段',exact=True).click()
    page.get_by_text('下一阶段 E1 · 第 5 分钟',exact=True).wait_for()
    page.get_by_text('当前队伍状态',exact=True).wait_for()
    page.screenshot(path=str(ROOT/'results/ui_initial.png'),full_page=True)
    page.get_by_role('button',name='推进下一阶段',exact=True).click()
    page.get_by_text('下一阶段 E2 · 第 20 分钟',exact=True).wait_for()
    page.screenshot(path=str(ROOT/'results/ui_road_closed.png'),full_page=True)
    print('Browser smoke screenshots saved:',page.title())
    browser.close()
