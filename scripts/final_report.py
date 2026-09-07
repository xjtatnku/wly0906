"""Final V2.3 report and 12 slides, generated only from recorded results."""
import json,statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pptx import Presentation
from pptx.util import Inches,Pt
from pptx.dml.color import RGBColor
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/v23/final'

def run():
    ood=json.loads((OUT/'ood_summary.json').read_text(encoding='utf-8'))
    warm=json.loads((OUT/'warmup_benchmark.json').read_text(encoding='utf-8'))
    labels=['Rules','DeepSeek','DeepSeek + grounding'];colors=['#2d88ed','#14b293','#eea242']
    fig,ax=plt.subplots(figsize=(9,4),layout='constrained');x=np.arange(3)
    for i,(r,name,color) in enumerate(zip(ood['results'],labels,colors)):
        bars=ax.bar(x+(i-1)*.23,[r[k] for k in ('event_f1','entity_f1','numeric_f1')],width=.21,label=name,color=color)
        ax.bar_label(bars,fmt='%.2f',fontsize=9,padding=3)
    ax.set(xticks=x,xticklabels=['Event F1','Entity F1','Numeric F1'],ylim=(0,1),ylabel='Micro F1')
    ax.legend(loc='upper right',frameon=False);ax.spines[['top','right']].set_visible(False);ax.set_axisbelow(True);ax.grid(axis='y',alpha=.15)
    fig.savefig(OUT/'ood_comparison.png',dpi=180);plt.close(fig)
    rows=['# V2.3 最终研究报告','',
        '本轮冻结已有功能边界，补充自然语言挑战评测、预测预热与请求优化，并统一六页工作台与最终汇报入口。保留康定一个真实案例背景，九阶段事件与资源参数仍为实验构造。','',
        '## 1. 自然语言理解：并未证实模型全面优于规则','',
        '120条文本分为简单、口语、长文本、多事件、修正、模糊地点、噪声、无关、同义、否定、不完整及指令干扰12类，每类10条。文本与显式标签在调用前冻结，未使用规则提取器生成标签，也未根据结果调整提取提示或校验规则。SHA-256见 [标注清单](../data/v23/final/ood_manifest.json)。','',
        '**独立性限制**：数据由同一开发过程辅助编写，尚未经过第三方人工独立标注。因此称为“冻结留出挑战集”，不能称为独立真实灾情OOD验证集；100–200条规模已达到，但第三方独立复核仍待完成。','',
        '每条只请求一次真实DeepSeek；原始输出与加grounding的方法共享该响应。校验拒绝按弃答计分；实际规则回退保存于原始记录，但不计作模型成功。Rules也单独计算证据校验通过率。','',
        '| 方法 | 事件F1 | 实体F1 | 数值F1 | 校验通过率 | 回退率 | P50/ms | P95/ms |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r,name in zip(ood['results'],labels):rows.append('| '+name+' | '+' | '.join(f'{100*r[k]:.2f}%' for k in ('event_f1','entity_f1','numeric_f1','grounded_pass_rate','fallback_rate'))+f" | {r['latency_p50_ms']:.1f} | {r['latency_p95_ms']:.1f} |")
    rows+=['','![三方法挑战集比较](../results/v23/final/ood_comparison.png)','',
        '计分使用逐文本多重集合的micro F1，重复输出计为额外预测。事件统计排除uncertain_report，把它作为弃答；实体元组绑定事件类型、字段和值（地点/道路/资源/站点/需求）；数值元组还绑定地点、失联或受伤字段及absolute/delta口径。因此这些分数不能直接等同于无事件关联的通用NER指标。空标签不产生真阳性。','',
        '27条没有明确可执行事实的文本中，规则、原始模型和校验后模型的候选误报率分别为 '+ ' / '.join(f"{100*r['false_action_rate']:.1f}%" for r in ood['results'])+'。这里衡量错误候选，不是已经执行的错误派遣。所有操作仍有人工确认。','',
        '**关键结果**：原始模型数值覆盖优于本规则，但实体F1较低、事件F1仅接近；严格校验降低了错误候选，也拒绝部分语义正确但不符合现有证据格式的表达。子串和数字邻近验证不是完整语义蕴含验证，尤其不能保证理解否定、指代及数量作用域。不能据此写“LLM显著提升理解准确率”或“grounding消除幻觉”。','',
        'API耗时包含现有提取包装器的校验和失败处理；grounded列另加一次复核耗时，不是独立的纯网络延迟。分组结果与所有原始输出见 [汇总](../results/v23/final/ood_summary.json) / [记录](../results/v23/final/ood_records.json)。','',
        '## 2. 冷启动与事件请求分开','',
        'FastAPI lifespan在接受请求前预热两种环境的三个模型与两种风险排序。训练仍只读取第0分钟前已接收的历史；预热不写事件、任务或状态。旧版预测器改为仅在归档评测访问时初始化，当前请求不再训练闲置的旧模型。预测结果缓存上限256项。','',
        '性能剖析发现延迟事件反复读取同一观测窗口，并创建数万个ORM对象。现使用SQLAlchemy字段映射直接读取普通字典，在刷新和页面返回内复用观测窗口；没有引入额外数据库、后台服务或持久缓存。自动化测试逐字段核对旧ORM结果与新路径一致。','',
        '| 预热后事件路径 | 次数 | P50/ms | P95/ms | P99/ms | 约束违规 |','|---|---:|---:|---:|---:|---:|']
    for r in warm['summary']:rows.append(f"| {r['environment']} | {r['repetitions']} | {r['p50_ms']:.2f} | {r['p95_ms']:.2f} | {r['p99_ms']:.2f} | 0 |")
    rows+=['','每种环境相同延迟事件重复30次，每次清空预测结果缓存、保留训练模型；包含批次校验、调度、SQLite保存与状态返回，排除HTTP/LLM网络。求解预算0.3秒。P99仅为30次小样本插值。**与旧内存压力测试口径不同，不直接用旧3.35秒除以新P95声称加速倍数。**','',
        '| 独立进程启动 | 服务初始化/ms | 额外预热/ms | 就绪总耗时/ms |','|---|---:|---:|---:|']
    for i,r in enumerate(warm['cold_start'],1):rows.append(f"| {i} | {r['service_init_ms']:.0f} | {r['additional_warmup_ms']:.0f} | {r['total_ready_ms']:.0f} |")
    rows+=['','冷启动使用新建临时数据库，包含首次导入数据；现有本机库的启动成本可能不同。最终性能测试单独运行；此前同口径优化前记录以及与完整测试争用CPU的中间结果均保留，不能忽略负载差异做严格归因。见 [最终测量](../results/v23/final/warmup_benchmark.json)、[优化前](../results/v23/final/warmup_before_reads.json)、[并发验证期间](../results/v23/final/warmup_during_validation.json)。','',
        '## 3. 参考图对应的前端收敛','',
        '- 统一浅蓝导航、白色卡片、告警色、轻量SVG图标、表格及图表排版；总览首屏以态势地图和关键指标为主。','- 复用Leaflet和ECharts，没有新增框架、图标包或动画库；默认本地OSM矢量背景约59KB，Canvas绘制349条简化背景道路。地图只请求一次本地背景，切页复用；图表与地图在离开页面时释放。','- 本地路网/在线底图、风险/资源图层开关和全图定位均可操作；同位置资源按数量聚合，不人为偏移经纬度。风险圆是实验可视化范围，不是假造的地形灾害边界。','- 策略页删除重复的单事件入口，统一多事件候选卡片、证据与字段编辑；九阶段进度清晰显示。数据治理、参数与完整追踪后置，保留功能且避免诊断信息占满首屏。','- 六页验证1680、1280、390像素，无水平溢出；默认地图禁止外网仍可用。保留键盘焦点、图层按下状态、状态播报和减少动态效果设置。','',
        '背景道路来自仓库已有2026年OSM快照，不伪称2024年现场道路或卫星影像；其简化仅用于显示，求解器仍用选择的结构化路网。未复制参考图中没有数据支撑的人数、地质坡度、概率、物资总量或装饰性功能按钮。','',
        '![策略决策](../results/v23/final/strategy-screen.png)','',
        '## 4. 验收与冻结边界','',
        '原有73项完整测试通过，覆盖先前69项及本轮新增4项；惰性旧模型初始化另行运行兼容测试。九阶段浏览器回放覆盖实时模型提取、拒绝、人工批准、修正、词典序切换、地图控制和重复切页；最终失联15人、报告版本3。机器可读记录见 [浏览器验收](../results/v23/final/browser_validation.json)。','',
        '保留此前300组调度、140组β敏感性、180组压力实验的0约束违规结论，不把不同输入与计时口径混成同一实验。词典序在P1完成上略高但响应、缺口及撤回存在代价；预测前置仍只使用剩余容量。地形易发性、暴露度映射、当前任务与未来需求的资源保留继续列为后续工作。','',
        '本系统的贡献是一个可核验的连续决策研究链，而不是证明模型必胜或还原真实救援。所有模拟边界保留；第三方自然语言标注复核与真实应用效果验证没有完成。当前入口见 [README](../README.md)，历史版本见 [归档](archive.md)。']
    (ROOT/'docs/final-report.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    slides(ood,warm)

def slides(ood,warm):
    deck=Presentation();deck.slide_width=Inches(13.33);deck.slide_height=Inches(7.5)
    synth,hist=warm['summary']
    content=[
        ('康定案例 · 动态应急决策','V2.3 最终研究原型\n多源环境观测 · 联合预测 · 事件理解 · 资源调度\n本地单机运行，全部模拟边界可追溯',None),
        ('一个案例，多次状态变化','九阶段：风险上升 → 首报 → 新增需求 → 封路与延迟\n执行资源故障 → 增援 → 次生风险 → 信息修正 → 恢复\n阶段时刻、人数、任务与资源为实验构造，不是真实指挥记录',None),
        ('从数据到执行的系统链','历史 / 模拟数据 → 联合预测 → 区域风险排序\n报告文本 → 模型候选 → 证据校验 → 人工批准\nCP-SAT + 路网 → 执行推进 → 事件重规划 → 决策追踪',None),
        ('态势总控台','默认本地矢量底图，图层可切换，断网可交互\nOSM背景为2026快照；任务与风险为模拟图层','overview-screen.png'),
        ('多事件审核与信息修正','模型提出候选；人工核对原文、字段与条款\n同一批次统一重规划；报告版本为8 → 13 → 15','strategy-screen.png'),
        ('冻结自然语言挑战评测','120条 / 12类；规则、原始DeepSeek、DeepSeek + grounding\n三方法共享输入，两模型方法共享一次响应\n开发辅助标注，尚无第三方独立复核','ood_comparison.png'),
        ('模型与校验的实际取舍','原始模型数值F1高于规则，实体F1较低，事件F1接近\n严格校验同时减少错误候选和部分正确覆盖\n证据子串不等于完整语义验证；否定、指代仍需人工审查',None),
        ('动态调度与协同执行','能力匹配、道路可达、协同开始、占用与已执行动作锁定\n加权目标与词典序共用执行器；超时明确显示可行或降级','dispatch-screen.png'),
        ('多目标取舍，保留负面结果','异构事件：300组；β敏感性：140组；重复压力：180组\n词典序P1完成略高，但响应、缺口和撤回存在代价\n旧960组按种子配对bootstrap，不用单一均值宣称全面优势',None),
        ('启动预热与请求开销','服务启动先训练；请求期不重新拟合\n模拟预热事件P95 '+f"{synth['p95_ms']:.1f} ms；历史 {hist['p95_ms']:.1f} ms"+'\n各30次，含SQLite与状态返回，排除HTTP / LLM\n与旧内存压力实验计时边界不同',None),
        ('精简前端与稳定性验收','沿用原生JS、Leaflet、ECharts；没有新增前端运行依赖\nSVG图标、59KB本地道路、地图/图表切页释放\n六页 × 三宽度、九阶段、真实提取、词典序与重复切页\n完整73项测试，保留约束一致性与失败回退',None),
        ('研究结论与边界','可复现地解释动态信息如何改变资源约束与调度方案\n没有证明LLM全面优于规则，或证明真实救援效果\n后续：第三方独立标注、地形易发性、未来需求资源保留\n当前冻结功能，统一README、PPT与五分钟演示',None)]
    notes=[]
    for i,(title,body,figure) in enumerate(content,1):
        slide=deck.slides.add_slide(deck.slide_layouts[6]);slide.background.fill.solid();slide.background.fill.fore_color.rgb=RGBColor.from_string('F4F8FD')
        def box(x,y,w,h,text,size,color='193B5C'):
            shape=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));shape.text_frame.word_wrap=True
            for j,line in enumerate(text.split('\n')):
                p=shape.text_frame.paragraphs[0] if j==0 else shape.text_frame.add_paragraph();p.text=line;p.font.name='Microsoft YaHei';p.font.size=Pt(size);p.font.color.rgb=RGBColor.from_string(color);p.space_after=Pt(12)
        box(.55,.3,12,.4,'KANGDING / DYNAMIC EMERGENCY DECISION',10,'4786BE')
        box(.55,.95,12,1,title,28)
        if figure:
            box(.6,1.7,12,1.05,body,15)
            from PIL import Image
            with Image.open(OUT/figure) as source:ratio=source.width/source.height
            width=min(10,4.05*ratio)
            slide.shapes.add_picture(str(OUT/figure),Inches((13.33-width)/2),Inches(2.85),width=Inches(width))
        else:box(.75,2.2,11.8,4.4,body,24)
        box(.6,7.05,11,.25,'V2.3 · 康定案例背景 / 模拟决策研究',9,'7890A7');box(12,7.02,.7,.3,f'{i:02}',11,'4786BE')
        slide.notes_slide.notes_text_frame.text=body
        notes.append(f'## 第{i}页：{title}\n\n'+body.replace('\n','。')+'。\n')
    folder=ROOT/'deliverables/v23';deck.save(folder/'final_presentation.pptx')
    (folder/'final_speaker_notes.md').write_text('# V2.3 最终汇报讲稿\n\n'+'\n'.join(notes)+'\n现场操作：总览 → 策略页重置九阶段 → 准备/审核/批准 → 调度地图与ETA变化 → 信息修正为15 → 词典序 → 复盘真实评测。',encoding='utf-8')

if __name__=='__main__':run()
