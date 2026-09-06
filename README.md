# 动态灾害应急决策与资源调度

**新版 V2 已实现参考图对应的六页工作台。** 本机启动 `./run-v2.ps1`，访问 http://127.0.0.1:8800；新环境安装、操作流程与验证见 [README-V2.md](README-V2.md)。以下保留 V1 基线运行说明。

以康定山洪泥石流为案例背景，演示“新灾情 → 预案检索 → 人工确认任务 → 资源分配 → 执行与重规划”。**模拟参数用于方法验证，不是康定实际路网、实际队伍或指挥记录。**

## 立即运行（PowerShell）

```powershell
cd D:\自然灾害考核
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

浏览器打开 http://localhost:8501 。依次点击四次“推进下一阶段”，观察道路中断、新增需求和增援；可切换算法重新回放。在“新灾情与依据”输入文字、提取并核对候选，确认后才更新状态。

无需 API 的命令行演示：

```powershell
.\.venv\Scripts\python.exe -m disaster --method dynamic
.\.venv\Scripts\python.exe -m disaster.experiments
.\.venv\Scripts\python.exe -m pytest -q
```

## 在新环境复现

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m disaster
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Python 3.11；requirements.txt 固定直接依赖，requirements.lock.txt 固定本次运行的完整依赖。数据已随项目提供，不需联网下载才能演示。`scripts/build_scenario.py` 与 `scripts/build_knowledge.py` 可重建初始数据；运行会覆盖对应数据文件。

## 模型接入

支持 OpenAI 兼容的 Chat Completions JSON 接口，默认配置方式如下。用自己的凭据替换示例，密钥不写进仓库、日志或报告。

```powershell
$env:DISASTER_API_KEY = '在本机填写密钥'
$env:DISASTER_BASE_URL = 'https://api.deepseek.com'
$env:DISASTER_MODEL = 'deepseek-chat'
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

界面开启“使用实时模型 API”。其他兼容服务修改地址和模型名即可；要求服务支持 `response_format=json_object`。此接口形状已经用模拟响应测试；没有用户提供的密钥时，不声称已经调用任何真实模型。请求失败不会提交候选事件。

`.env.example` 只作说明，程序**不会自动读取 .env**。实时分析向所配置提供商发送用户输入的灾情文本、候选节点及检索条款；只发送任务所需数据。

实际评估模型（会调用已配置服务）：

```powershell
.\.venv\Scripts\python.exe -m disaster.experiments --nlp-only --live
```

界面明确区分实时调用、固定示例缓存、离线规则。缓存是代理逐字段核对的示例，不是冒充实际模型输出的记录。离线评估结果不代表 DeepSeek/GPT 能力。

## 文件导航

| 内容 | 位置 |
|---|---|
| 模拟节点、队伍、任务与四阶段事件 | `data/scenario.json` |
| 真实通报事实及发布时间 | `data/case_facts.json` |
| 20 条预案节选、版本、来源、适用范围 | `data/policies.json` |
| 来源清单与已核对节选 | `data/sources.json`、`data/sources/` |
| 20 条人工设定的文本标注 | `data/evaluation/extraction_gold.json` |
| 调度器、路网、执行模拟器 | `disaster/core.py` |
| 检索、模型适配、候选与引用校验 | `disaster/knowledge.py` |
| 实验指标与逐分钟事件轨迹 | `results/metrics.csv`、`results/traces/` |
| 问题形式化、接口与限制 | `docs/model.md`、`docs/data.md` |
| 文献与工程参考 | `docs/research.md` |
| 报告、PPT 与讲稿 | `deliverables/` |

## 结果怎么读

每项任务可需要多支队伍；一支队伍对应一个需求单位。紧急满足率指截至模拟第180分钟已到达的紧急需求单位比例，**不是人员获救率**。已到达与已完成作业分别统计。

三个方法共享场景、路网、能力约束和执行器。贪心与动态方法均每5分钟或新事件后决策；静态方法仅第0分钟分配一次，不响应后续任务或增援，是刻意设置的弱基线。不要把相对静态方案的优势全归因于优化算法，重点对照动态与贪心的差异。

平均响应时间只覆盖已到达任务，必须同时看未满足量、迟到量和完成数。优化器仅对每次当前可用资源的分配求解；不是多阶段随机规划复现，也不保证整个过程全局最优。

## 来源与限制

采用2024年1月国家自然灾害救助预案、2024年5月四川地质灾害预案。四川2024年8月15日实施的新救助预案不用于8月3日回放。国家一级响应条款仅作为研究背景，系统不自动推导或宣称事件属于一级响应。

当前网络无法从部分官方站点直接下载全文；已保存带链接的核对节选。四川条款以官方PDF搜索索引核对，未伪称完成整份PDF校对。`scripts/collect_sources.py` 可在网络允许时获取原文并计算校验值，重新采集后仍需复核标注。

本版不模拟天气预测、伤员存活概率、车辆载重、多个队伍同步作业、工程任务自动修复道路或队伍疲劳。道路中断采用最近到达节点的离散回退抽象，已经消耗的时间不退还；不声称真实车辆能够瞬间返回。
