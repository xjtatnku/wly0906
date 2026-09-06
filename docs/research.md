# 核验后的参考体系

此页保留V1依据；V2.1扩充的A-DREAM、CrisiSense-RAG、JRC、OGC和开源工程对照见 [research-v21.md](research-v21.md)。下表中的“本版”指V1。

核验日期：2026-09-06。以下仅使用作者、论文和官方工程资料；没有复制整套第三方源码或声称复现其论文实验。

| 参考 | 已核验的内容 | 本项目借鉴 | 没有实现的部分 |
|---|---|---|---|
| Bhattarai & Song, *Multistage stochastic programming for integrated network optimization in hurricane relief logistics and evacuation planning*, Networks, DOI 10.1002/net.22249；2024在线、2025卷期 | 出版页及作者仓库均确认多阶段灾害物流/疏散规划与公开数据代码 | 将随时间变化的信息、状态与行动显式分开；设置动态与静态对照 | 未实现Markov灾害过程、SDDP、多阶段随机规划或原论文实验 |
| Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, 2020 | 作者论文提出检索与生成结合的知识任务方法 | 先找可追溯条款，再以引用约束解释 | 未训练稠密检索器或联合生成模型；本版仅TF-IDF检索与API |
| Google OR-Tools Assignment / CP-SAT 官方示例 | 官方示例展示整数变量、分配约束和求解状态 | 本版自行实现能力/道路过滤与四级词典序分配 | 并非灾害专用算法；本轮最优不等于长期全局最优 |

## 来源

- [Networks 出版页](https://onlinelibrary.wiley.com/doi/10.1002/net.22249)
- [Bhattarai 与 Song 作者代码和数据](https://github.com/sudhan-bhattarai/MSSP_IHRLEP_Networks)
- [RAG 作者论文](https://arxiv.org/abs/2005.11401)
- [OR-Tools 分配问题示例](https://developers.google.com/optimization/assignment/assignment_example)
- [CP-SAT 求解状态与建模](https://developers.google.com/optimization/cp/cp_solver)

选择理由：短期考核首先需要可解释、可运行和可评价的完整闭环。以上三项分别支撑动态问题建模、依据检索和可计算分配。此前分享对话中的其他论文暂不列为项目依据，避免在未完成核验时堆叠引用。

下一步研究问题是：加入未来需求预测后，保留空闲资源是否比立即分配更好？这需要前瞻规划和新的实验，不由本次的逐轮分配结果推断。
