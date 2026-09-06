# 研究与工程依据（V2.1）

核验日期：2026-09-06。以下区分论文、作者工程与本项目实现；没有复现其论文实验。

| 依据 | 已核验内容 | 本项目实现 | 未实现部分 |
|---|---|---|---|
| Long, Sun & Xu, 2024，A-DREAM，Advanced Engineering Informatics 62, 102858，DOI 10.1016/j.aei.2024.102858 | 作者机构记录确认异构协作、滚动时域、Gini公平评价 | 复合资源同步作业、滚动计划；已开始任务响应Gini及稳定权重敏感性 | 未复现A-DREAM、没有公平优化目标，Gini口径不等同原论文 |
| Bhattarai & Song，Networks，DOI 10.1002/net.22249 | V1已核验多阶段灾害物流与疏散规划及作者代码 | 状态/观测/行动边界与固定种子扰动 | 未实现SDDP、多阶段随机规划；预测前置仍是固定规则 |
| Xiao, Yin & Mostafavi，CrisiSense-RAG，2026，DOI 10.1016/j.cacaie.2026.100096；arXiv 2602.13239 | 出版摘要和作者仓库确认异步多源证据、文本/图像分支与数据下载入口 | 观测时间、实际接收时间、模拟可见时间分离；数据时效标记 | 未下载约3.2GB数据，未复现多模态融合、CLIP或交叉编码器 |
| Ronco et al.，Scientific Data，2026，DOI 10.1038/s41597-026-07036-2 | Nature作者稿确认2014—2024灾害新闻结构化、hazard/driver/impact/response | 文本转候选事件，保留依据后人工确认 | 未实现灾害知识图谱或新闻采集，不声称复现论文流水线 |
| Lewis et al.，RAG，2020 | V1已核验作者论文 | 可追溯条款检索与候选辅助；V2为TF-IDF/LSA融合 | 未训练检索器、没有BGE或联合训练 |
| OGC SensorThings API | 官方标准面向异构传感器、观测与数据流 | source_id组织数据流，区分观测和接收时间 | 没有实现OData实体接口，不宣称标准合规 |
| Sahana Eden | 官方仓库确认为人道与应急管理提供Web开发能力 | 参考事件、资源登记和持久化分离的方向 | 未引入其框架、人员和营地完整管理模块 |
| InaSAFE与HOT/OSM | 官方仓库和Wiki确认灾害影响评估及道路等地理数据工作流 | 带来源的OSM快照构建有向路网，优化器和地图共用几何 | 未实现Hazard+Exposure影响估计；OSM不是实时路况或2024历史路网 |
| OR-Tools CP-SAT | 官方建模与求解状态接口 | V1词典序单轮；V2 Circuit序列、多资源同步及加权目标 | 本轮最优不等于长期最优，复杂度不证明优于贪心 |

## 核验入口

- [A-DREAM作者机构记录](https://research.polyu.edu.hk/en/publications/dynamic-heterogeneous-resource-allocation-in-post-disaster-relief/)
- [Bhattarai与Song作者代码](https://github.com/sudhan-bhattarai/MSSP_IHRLEP_Networks)
- [CrisiSense-RAG出版页](https://www.sciencedirect.com/science/article/pii/S1093968726030823)、[作者仓库与数据说明](https://github.com/YimingXiao98/CrisiSense-RAG)
- [JRC研究Nature作者稿](https://www.nature.com/articles/s41597-026-07036-2_reference.pdf)
- [RAG论文](https://arxiv.org/abs/2005.11401)、[OGC SensorThings](https://www.ogc.org/standards/sensorthings/)
- [Sahana Eden](https://github.com/sahana/eden)、[InaSAFE](https://github.com/inasafe/inasafe)
- [HOT/OSM灾害数据](https://wiki.openstreetmap.org/wiki/Humanitarian_OSM_Team/HDX_Disaster_Data)
- [OSM单行方向](https://wiki.openstreetmap.org/wiki/Key:oneway)、[Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API)、[OSM版权](https://www.openstreetmap.org/copyright)
- [CP-SAT官方文档](https://developers.google.com/optimization/cp/cp_solver)

CLDAS官方目录可访问，但本轮未取得产品数据和账户授权，抓取内容不足以核实半小时延迟指标。没有接入CMA/CLDAS，不能列为已有系统能力：[官方目录](https://k.data.cma.cn/mekb/?datacode=NAFP_CLDAS2.0_RT&r=dataService/cdcindex)。

保留V2贪心胜出的结果。V2.1新增时效控制、递归多步评估和权重敏感性；Gini仅针对已开始任务，必须同时报告缺口。机会成本前置、区域需求预测和公平性优化仍为后续研究。
