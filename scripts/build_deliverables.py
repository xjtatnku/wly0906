"""Generate report and 12-slide deck from measured outputs, without invented claims."""
from pathlib import Path
import sys
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from docx import Document
from docx.shared import Inches as DInches, Pt as DPt
from docx.oxml.ns import qn
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from disaster.core import ROOT, read_json, write_json


def main():
    out=ROOT/'deliverables'
    out.mkdir(exist_ok=True)
    metrics=pd.read_csv(ROOT/'results/metrics.csv')
    means=metrics.groupby('method').mean(numeric_only=True)
    nlp=read_json(ROOT/'results/extraction_offline_summary.json')
    d,g,s=(means.loc[x] for x in ['dynamic','greedy','static'])
    rows=[]
    for method in ['dynamic','greedy','static']:
        r=means.loc[method]
        rows.append([method,f"{r.urgent_satisfaction:.1%}",f'{r.unmet_units:.2f}',f'{r.mean_response:.2f}',f'{r.late_minutes:.2f}'])
    sections=[
        ('问题与完成内容',[
            '给定持续变化的灾情、道路、有限救援队伍和应急预案，研究如何形成可追溯的候选任务并保持动态调度与实际执行状态一致。',
            '本次交付包含本地单页系统、离线命令行、两份预案的20条核对节选、4条真实通报事实、10节点8队伍12任务的模拟场景、三方法63次实验以及自动化测试。',
            '真实材料说明案例背景，模拟材料验证程序行为。队伍、路网、任务和分钟不是对康定救援过程的重建。']),
        ('数据与依据',[
            '公开通报采用新华社2024年8月4日21:39:21报道，并列出康定市政府专栏通报作交叉来源。每项事实记录事件时间、发布时间、来源链接及原文定位；不能把后续发布的信息提前用于历史态势。',
            '预案采用国办函〔2024〕11号和四川2024年度地质灾害预案。8月15日实施的四川新救助预案被排除。国家一级响应条款仅用于特定范围的知识解释，不构成康定实际响应级别判定。',
            '部分官方站点直接下载遇到TLS错误。国家条款已对照网页正文，四川条款对照官方PDF搜索索引；本地保存核对节选与明确核验状态，尚未完成整份四川PDF复核。']),
        ('系统方法与数学模型',[
            '文本经结构化提取后进入候选区，字符2—4 gram TF-IDF结合固定任务模板词检索前五条预案。人工核对地点、能力、需求数量、时限与引用后提交事件。',
            '设x(i,j)为队伍i是否派往任务j。仅保留能力匹配、资源当前可用、路网可达的组合；约束每队伍至多一个任务、每任务分配量不超过未完成且未承诺的需求。',
            '词典序最小化紧急缺口、普通缺口、预计迟到、行程时间。使用CP-SAT分级求解，共享5秒预算，只有当前级证明最优才进入下一级。超时保留可行解或明确降级为贪心。',
            '执行器以1分钟推进，记录逐边行进、到达、作业和释放；每5分钟或新事件后重规划。在途方案遇阻时按最近到达节点的离散抽象绕行，不可达则释放承诺。既有作业不被重新分配。',
            '模型不直接决定数值派遣，解释阶段只选择受限理由代码；所有队伍、任务、路线与到达数字均由程序校验与渲染。']),
        ('实验设计与测量结果',[
            '标准场景与seed=0…19扰动共21组，每组分别运行最近可行队伍贪心、一次性静态优化、动态优化，共63次。方法共享相同输入和执行器，固定180分钟观察窗口。',
            '扰动改变道路行程、任务作业时长和需求数量。静态方法仅初始分配一次，不能响应新增任务及增援，是弱的无重规划对照。动态与贪心均每5分钟和事件发生时重新分配。',
            f'动态优化紧急需求到达率均值{d.urgent_satisfaction:.1%}，贪心{g.urgent_satisfaction:.1%}，静态{s.urgent_satisfaction:.1%}。动态与贪心在所有场景终点均无未满足单位。',
            f'动态平均响应{d.mean_response:.2f}分钟，贪心{g.mean_response:.2f}分钟；动态累计迟到均值{d.late_minutes:.2f}分钟，贪心{g.late_minutes:.2f}分钟。结果没有证明动态优化全面优于贪心；后续资源释放和任务组合可能改变长期效果。',
            '静态方法平均响应较小不能解释成更好，因为只服务了初始部分任务。到达率是队伍需求满足率，不是获救人数或存活率；平均响应只计算已到达单位。',
            f'离线文本20条样例的地点/能力准确率分别为{nlp["node_accuracy"]:.0%}/{nlp["capability_accuracy"]:.0%}；人工条款集Recall@5为{nlp["gold_clause_recall_at5"]:.0%}，引用精度为{nlp["citation_precision_against_authored_gold"]:.0%}。这些是小型代理标注集上的离线规则/缓存结果，不代表任何真实大模型。']),
        ('验证、限制与下一步',[
            '测试覆盖小规模穷举与CP-SAT目标一致性、重复事件事务、能力缺失、资源耗尽、封闭全部道路、在途绕行、作业占用、超时降级、历史知识截止、伪造模型字段/引用、界面交互以及本地假服务的真实SDK协议。测试输出见results/test_output.txt。',
            '实际DeepSeek/GPT服务尚需用户在本机配置API后运行20条实测。当前兼容接口通过本地假服务与错误响应验证，不能替代真实提供商连通性和模型质量测试。',
            '本系统是逐轮确定性分配；未实现多阶段随机规划、未来需求预测、伤员生存概率、工程任务自动修复路网、多队伍同步作业、车辆载重和疲劳。道路受阻的节点抽象不能解释成现实车辆瞬间返回。',
            '下一步优先独立复核预案及文本标注、扩大任务与道路扰动，再研究保留资源、前瞻规划和更加真实的执行模型。不要根据此实验推广现实救援成效。']),
    ]
    doc=Document()
    normal=doc.styles['Normal']
    normal.font.name='Microsoft YaHei'
    normal.font.size=DPt(10)
    normal._element.rPr.rFonts.set(qn('w:eastAsia'),'Microsoft YaHei')
    doc.add_heading('动态灾害应急决策与资源调度',0)
    doc.add_paragraph('康定案例背景下的研究原型｜实现与实测结果｜2026-09-06')
    md=['# 动态灾害应急决策与资源调度','', '康定案例背景下的研究原型；报告由实际结果文件生成。','']
    for title,paragraphs in sections:
        doc.add_heading(title,level=1)
        md+=['## '+title,'']
        for p in paragraphs:
            doc.add_paragraph(p)
            md += [p,'']
        if title=='实验设计与测量结果':
            table=doc.add_table(rows=1, cols=5)
            table.style='Light Shading Accent 1'
            headers=['方法','紧急到达率','未满足单位','平均响应/分','累计迟到/分']
            for c,text in zip(table.rows[0].cells,headers):
                c.text=text
            for row in rows:
                for c,text in zip(table.add_row().cells,row):
                    c.text=text
            doc.add_picture(str(ROOT/'results/comparison.png'),width=DInches(6.2))
            md+=['| '+' | '.join(headers)+' |','|---|---|---|---|---|']
            md += ['| '+' | '.join(row)+' |' for row in rows]+['']
    doc.add_heading('参考来源',level=1)
    refs=read_json(ROOT/'data/sources.json')[:3]
    for item in refs:
        line=item['title']+'\n'+item['url']
        doc.add_paragraph(line)
        md += [f"- [{item['title']}]({item['url']})"]
    for title,url in [('Bhattarai & Song, Networks','https://doi.org/10.1002/net.22249'),
                      ('Lewis et al., RAG','https://arxiv.org/abs/2005.11401'),
                      ('OR-Tools assignment','https://developers.google.com/optimization/assignment/assignment_example')]:
        doc.add_paragraph(title+'\n'+url)
        md += [f'- [{title}]({url})']
    doc.save(out/'技术报告.docx')
    (out/'技术报告.md').write_text('\n'.join(md),encoding='utf-8')

    slides=[
        ('动态灾害应急决策与资源调度',['康定案例背景下的可运行研究原型','信息变化 → 任务确认 → 资源派遣 → 执行反馈','真实来源与模拟参数分别标注'], '先运行系统演示，再解释方法；明确这不是实际救援指挥系统。'),
        ('把开放题变成可验证问题',['输入：不同时间的灾情、预案、道路和有限队伍','输出：可执行分配、未满足需求与可追溯依据','观察重点：新信息出现后，行动如何变化'], '导师考察的是理解、分析、实现和评价，而不是复现现成问答页面。'),
        ('数据边界与时间可见性',['4条公开事实；事件时间与发布时间分开','2份灾害前预案，20条节选；四川完整PDF待复核','10节点 / 8队伍 / 12任务 / 14需求单位均属模拟'], '真实材料只支撑案例背景；不把总人数分割成所谓真实队伍。'),
        ('四阶段可重复演示',['第0分钟：初始搜救、医疗与工程需求','第5分钟：道路中断；第20分钟：紧急需求增加','第40分钟：增援到达；观察至第180分钟'], '点击下一阶段，重点指出路径变化、资源占用和任务缺口。'),
        ('系统闭环',['灾情提取 → TF-IDF条款检索 → 人工确认任务','CP-SAT分配 → 执行模拟 → 事件/周期重规划','实时API、固定缓存和离线规则明确区分'], '模型不能直接写入调度结果；人确认候选，程序维护状态。'),
        ('可计算的调度模型',['变量：队伍 i 是否分配到任务 j','约束：能力、可达性、唯一占用、任务剩余需求','词典序：紧急缺口 → 普通缺口 → 迟到 → 行程'], '每轮求解当前资源分配，5秒共享预算；这不是全过程最优保证。'),
        ('动态状态保持一致',['队伍逐边行进，到达后作业，完成后释放','封路检查剩余路径：绕行或释放未完成承诺','重复事件不重复提交；执行中队伍不重新派遣'], '最近到达节点是离散抽象，已消耗时间不会被抹去。'),
        ('实验对照与公平条件',['21组相同场景 × 3方法 = 63次实验','动态与贪心同频决策；静态只初始分配','报告到达率、缺口、响应、迟到和求解时间'], '静态是弱对照，平均响应只统计已服务任务，应与缺口一起读。'),
        ('实际结果：没有全面胜出',[f'动态/贪心终点紧急到达率均为100%；静态{s.urgent_satisfaction:.1%}',
                                  f'动态响应{d.mean_response:.2f}分，贪心{g.mean_response:.2f}分',
                                  f'动态迟到{d.late_minutes:.2f}分，贪心{g.late_minutes:.2f}分'], '动态平均响应稍快，但迟到更高。这个反例说明局部目标与长期表现的差异。'),
        ('结果图：同时读覆盖与时间',[], '误差线为21组场景标准差。静态低响应时间受未服务样本选择影响。'),
        ('验证与真实限制',['自动测试：优化目标、执行状态、失败分支、界面与API协议',
                         f'离线20条：字段{nlp["node_accuracy"]:.0%}，条款Recall@5 {nlp["gold_clause_recall_at5"]:.0%}',
                         '真实模型尚未实测；小型代理标注不能证明泛化能力'], '引用ID合法不等于法律适用正确；不要把离线数字当成GPT或DeepSeek能力。'),
        ('交付与下一步',['已交付：可运行系统、数据、模型说明、实验与轨迹','先做独立数据/标注复核，再扩大场景和约束','研究方向：前瞻需求、资源预留、执行模型真实性'], '以实际系统和可复现实验收尾，指出发现的新问题和真实未完成的验证。'),
    ]
    prs=Presentation()
    prs.slide_width=Inches(13.333)
    prs.slide_height=Inches(7.5)
    notes=[]
    for i,(title,bullets,note) in enumerate(slides):
        slide=prs.slides.add_slide(prs.slide_layouts[6])
        bg=slide.background.fill
        bg.solid()
        bg.fore_color.rgb=RGBColor.from_string('F6F8FB')
        def textbox(x,y,w,h,text,size,color='20364B',bold=False):
            box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
            tf=box.text_frame
            tf.word_wrap=True
            for j,line in enumerate(text.split('\n')):
                p=tf.paragraphs[0] if j==0 else tf.add_paragraph()
                p.text=line
                p.font.name='Microsoft YaHei'
                p.font.size=Pt(size)
                p.font.bold=bold
                p.font.color.rgb=RGBColor.from_string(color)
                p.space_after=Pt(18)
            return box
        textbox(.65,.35,12,.4,'RESEARCH PROTOTYPE  /  KANGDING CASE CONTEXT',12,'4E8CA9')
        textbox(.65,1.0,12,1.0,title,30,bold=True)
        if i==9:
            slide.shapes.add_picture(str(ROOT/'results/comparison.png'), Inches(.7), Inches(2.35), width=Inches(12))
        else:
            textbox(.85,2.5,11.8,3.65,'\n'.join('• '+b for b in bullets),23)
        textbox(.7,6.95,11.6,.3,'模拟研究 · 数据可追溯 · 结果可复现 · 不等于真实救援成效',11,'718294')
        textbox(12.0,6.9,.7,.35,f'{i+1:02}',12,'4E8CA9')
        slide.notes_slide.notes_text_frame.text=note
        notes += [f'## 第{i+1}页：{title}',note,'']
    prs.save(out/'课题汇报.pptx')
    (out/'演示讲稿.md').write_text('# 演示与讲稿\n\n先启动应用，按四阶段回放；PPT第4页切换到浏览器，第8页返回PPT。\n\n'+'\n'.join(notes),encoding='utf-8')
    write_json(out/'manifest.json',dict(slides=12,generated_from=['results/metrics.csv','results/extraction_offline_summary.json'],
        api_validation='local fake provider only; real provider untested until credentials supplied',
        files=['技术报告.docx','技术报告.md','课题汇报.pptx','演示讲稿.md']))
    print('Generated report, 12-slide PPTX and speaker notes from measured results.')


if __name__=='__main__':
    main()
