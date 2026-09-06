"""Curated public-policy excerpts and case facts verified against official sources."""
import sys
from pathlib import Path
import hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from disaster.core import ROOT, write_json
from collect_sources import SOURCES


def main():
    national = [
        ('1.4 工作原则','坚持人民至上、生命至上，切实把确保人民生命财产安全放在第一位落到实处；'),
        ('2.2（1）需求评估','组织开展灾情会商核定、灾情趋势研判及救灾需求评估；'),
        ('2.2（3）动态通报','调度灾情和救灾工作进展动态，按照有关规定统一发布灾情以及受灾地区需求，并向各成员单位通报；'),
        ('3（2）动态评估','加强应急值守，密切跟踪灾害风险变化和发展趋势，对灾害可能造成的损失进行动态评估，及时调整相关措施；'),
        ('3（3）物资准备','做好救灾物资准备，紧急情况下提前调拨。启动与交通运输、铁路、民航等部门和单位的应急联动机制，做好救灾物资调运准备；'),
        ('4.1.1 报告质量','地方各级应急管理部门应严格落实灾情信息报告责任，健全工作制度，规范工作流程，确保灾情信息报告及时、准确、全面，坚决杜绝迟报、瞒报、漏报、虚报灾情信息等情况。'),
        ('4.1.3 特殊情况下补报','特殊紧急情况下（如断电、断路、断网等），可先通过卫星电话、传真等方式报告，后续及时通过系统补报。'),
        ('4.1.4 先报后核','地震、山洪、地质灾害等突发性灾害发生后，遇有死亡和失踪人员相关信息认定困难的情况，受灾地区应急管理部门应按照因灾死亡和失踪人员信息“先报后核”的原则，第一时间先上报信息，后续根据认定结果进行核报。'),
        ('4.2 信息发布','灾情信息发布坚持实事求是、及时准确、公开透明的原则。'),
        ('5.1.3（4）运输与通道修复','交通运输、铁路、民航等部门和单位协调指导开展救灾物资、人员运输与重要通道快速修复等工作，充分发挥物流保通保畅工作机制作用，保障各类救灾物资运输畅通和人员及时转运。'),
        ('5.1.3（5）投入救灾力量','应急管理部迅速调派国家综合性消防救援队伍、专业救援队伍投入救灾工作，积极帮助受灾地区转移受灾群众、运送发放救灾物资等。'),
        ('5.1.3（6）医疗救治','国家卫生健康委、国家疾控局及时组织医疗卫生队伍赴受灾地区协助开展医疗救治、灾后防疫和心理援助等卫生应急工作。'),
        ('5.1.3（6）安置群众','应急管理部会同有关部门指导受灾地区统筹安置受灾群众，加强集中安置点管理服务，保障受灾群众基本生活。'),
        ('5.1.3（9）通信保障','工业和信息化部组织做好受灾地区应急通信保障工作。'),
        ('5.1.3（9）空间信息','自然资源部及时提供受灾地区地理信息数据，组织受灾地区现场影像获取等应急测绘，开展灾情监测和空间分析，提供应急测绘保障服务。'),
    ]
    sichuan = [
        ('1.4 工作原则；文件印刷页3','灾情、险情发生后，始终将人民群众和抢险救援人员安全放在首位，迅速组织应急力量开展抢险救援，及时转移受威胁人员，严防次生灾害发生，'),
        ('抢险救援组主要职责；文件印刷页9','负责人员搜救和应急抢险。负责制定抢险救援行动计划，组织各方救援队伍和力量开展人员搜救；'),
        ('5.4.1 信息报送；文件印刷页29','发现或接报突发地质灾害事件的乡镇政府（街道办事处）及企事业单位应立即向当地基层自治组织和群众示警，同时向县级人民政府及自然资源、应急管理等部门报告情况。'),
        ('7.4 通信与信息保障；文件印刷页32','充分利用现代通信手段和网络技术，逐步建立覆盖全省的地质灾害应急管理信息平台，加强地质灾害监测、预报、预警信息系统建设，并实现部门间相关信息互通共享。'),
        ('7.2 物资保障与避灾场所；文件印刷页32摘录','完善重要应急物资生产、储备、调拨、更新、登记和紧急配送机制，采取实物储备、商业储备、产能储备等方式，保证抢险救灾物资的供应，落实应急避难场所，储备用于受灾群众安置、医疗卫生保障、生活必需等必要的专用物资。'),
    ]
    policies=[]
    for source, snippets in zip(SOURCES[:2],[national,sichuan]):
        for i,(section,text) in enumerate(snippets):
            policies.append(dict(id=f"{source['id']}-{i+1:02}",source_id=source['id'],section=section,text=text,
                title=source['title'],version=source['version'],url=source['url'],published_at=source['published_at'],
                provenance='public_policy_excerpt',normalization='仅合并换行和空白，部分为条款内节选',
                verification='官方网页正文核对' if source['id']=='national2024' else '官方PDF检索索引摘录核对；完整PDF下载失败，需独立复核',
                scope='国家一级救助响应措施，仅作检索与解释背景，不用于自动判定本案例响应级别' if section.startswith('5.1.3') else '原则或组织职责；不是实验参数的法定依据'))
    write_json(ROOT/'data/policies.json',policies)
    for s in SOURCES:
        s['retrieved_at']='2026-09-06'
        s['provenance']='public_source'
        s['snapshot_status']='全文下载受网络TLS限制；本地保存已核对节选与来源，不声称完整镜像'
    SOURCES[2]['published_at']='2024-08-04T21:39:21+08:00'
    SOURCES[2]['publication_precision']='second'
    SOURCES[1]['publication_precision']='day; conservatively end-of-day'
    write_json(ROOT/'data/sources.json',SOURCES)
    # Case values are paraphrased structured facts; short anchors locate original paragraphs.
    facts=[]
    specs=[
        ('F01','2024-08-03T03:30:00+08:00','约03:30，日地村发生山洪泥石流，雅康高速桥梁损毁，国道318线中断。','国道318线断道','第2段',{'road_closed':['雅康高速','国道318线']}),
        ('F02','2024-08-03T23:00:00+08:00','截至3日23时，灾区及周边累计转移安置939人。','939人','安置部分',{'relocated_people':939}),
        ('F03','2024-08-04T14:30:00+08:00','截至4日14:30，报道分列村庄6人遇难11人失联、坠车2人遇难8人失联，另有1人获救送医。','14时30分','伤亡统计段',{'deaths':8,'missing':19,'vehicle_rescued':1}),
        ('F04',None,'截至报道所称“目前”，累计投入救援人员1554人、车辆及工程装备311台套。确切统计时刻未披露。','1554人','搜救部分资源统计',{'responders':1554,'vehicles_and_equipment':311}),
    ]
    for ident,event_time,summary,anchor,locator,values in specs:
        facts.append(dict(id=ident,event_time=event_time,published_at=SOURCES[2]['published_at'],source_id='xinhua0804',
            url=SOURCES[2]['url'],summary=summary,evidence_excerpt=anchor,source_locator=locator,values=values,
            provenance='public_fact',annotation='结构化人工整理；汇总人数不能转换为队伍级调度事实'))
    write_json(ROOT/'data/case_facts.json',facts)
    excerpt='已核对的官方预案节选。国家文件来自正文；四川文件来自官方PDF的检索索引，非完整PDF。\n\n'
    excerpt+='\n\n'.join(f"{p['id']} | {p['section']}\n{p['text']}\n{p['url']}" for p in policies)
    path=ROOT/'data/sources/verified_excerpts.txt'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(excerpt,encoding='utf-8')
    write_json(ROOT/'data/sources/excerpts_manifest.json',dict(file='verified_excerpts.txt',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),kind='curated_excerpts_not_full_source'))
    print('Created 20 policy excerpts from 2 versions and 4 timestamped fact records.')


if __name__=='__main__':
    main()
