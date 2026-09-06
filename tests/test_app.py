from streamlit.testing.v1 import AppTest
from disaster.core import ROOT


def button(app,label):
    return next(b for b in app.button if b.label==label)


def test_full_ui_replay_reset_and_candidate():
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=40).run()
    assert not app.exception
    button(app,'推进下一阶段').click().run()
    assert not app.exception
    button(app,'提取灾情并检索依据').click().run()
    assert not app.exception
    assert app.session_state['candidate_result']['result']['candidate']['node']=='N4'
    button(app,'确认事件并更新调度').click().run()
    assert not app.exception
    for _ in range(3):
        button(app,'推进下一阶段').click().run()
        assert not app.exception
    button(app,'推进 10 分钟').click().run()
    assert not app.exception
    assert app.session_state['state'].now==50
    button(app,'重置场景').click().run()
    assert not app.exception
    assert app.session_state['state'].now==0
    assert not app.session_state['state'].tasks
