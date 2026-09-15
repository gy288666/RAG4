# RAG4

RAG4 是从 RAG3 演进的证据驱动学术 Research Agent。`project/` 中包含可运行的 RAG3 前后端，并已加入第一批 RAG4 基础设施：可替换的远程/本地 Embedding 与 Reranker Adapter、模型/索引版本隔离，以及 Embedding、Reranker、LoRA-SFT 训练入口。结构感知切分、知识图谱、混合检索与 Agent 能力继续按 [开发计划](RAG4_DEVELOPMENT_PLAN.md) 分阶段实现。

基线验证与环境限制见 [RAG4_BASELINE.md](RAG4_BASELINE.md)。RAG3 项目细节见 [RAG3_PROJECT_OVERVIEW.md](RAG3_PROJECT_OVERVIEW.md)。

## 快速验证

```powershell
cd project/frontend
npm ci
npm run lint
npm run build
```

后端固定使用 Conda Python 3.11 环境 `rag4-py3.11`；完整步骤见 [project/README.md](project/README.md)，模型训练见 [project/training/README.md](project/training/README.md)。
