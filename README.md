# RAG4

RAG4 是从 RAG3 演进的证据驱动学术 Research Agent。当前仓库处于基线阶段：`project/` 中包含可运行的 RAG3 前后端，RAG4 的结构感知切分、知识图谱、混合检索与 Agent 能力按 [开发计划](RAG4_DEVELOPMENT_PLAN.md) 分阶段实现。

基线验证与环境限制见 [RAG4_BASELINE.md](RAG4_BASELINE.md)。RAG3 项目细节见 [RAG3_PROJECT_OVERVIEW.md](RAG3_PROJECT_OVERVIEW.md)。

## 快速验证

```powershell
cd project/frontend
npm ci
npm run lint
npm run build
```

后端需要 Python 3.10–3.12、数据库和模型配置；完整步骤见 [project/README.md](project/README.md)。
