# RAG4

RAG4 以证据驱动的学术 Research Agent 为目标，从 RAG3 逐步演进。`project/` 中已有可运行的 RAG3 前后端、远程/本地 Embedding 与 Reranker Adapter、按 Embedding 版本隔离的索引，以及 Embedding、Reranker、LoRA-SFT 训练入口。

截至 `4b0e1dd`，Phase 1 结构化 ChunkingEngine 已实现：父子切片、章节/页码/来源 metadata、确定性版本身份及新上传兼容开关；默认仍使用 RAG3。最近完整后端回归为 **156 passed**。下一阶段是版本化索引重建与 active version；知识图谱、混合证据、ResearchAgent 和研究工作区尚未实现。详细路线见 [开发计划](RAG4_DEVELOPMENT_PLAN.md)。

基线验证与环境限制见 [RAG4_BASELINE.md](RAG4_BASELINE.md)。RAG3 项目细节见 [RAG3_PROJECT_OVERVIEW.md](RAG3_PROJECT_OVERVIEW.md)。

开发时间线、实现过程、问题修正、验证证据与下一阶段交接见 [开发过程记录](project/docs/development_process.md)；切分接口与开关说明见 [RAG4 ChunkingEngine](project/docs/rag4_chunking.md)。

## 快速验证

```powershell
cd project/frontend
npm ci
npm run lint
npm run build
```

后端固定使用 Conda Python 3.11 环境 `rag4-py3.11`；完整步骤见 [project/README.md](project/README.md)，模型训练见 [project/training/README.md](project/training/README.md)。
