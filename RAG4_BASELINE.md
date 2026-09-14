# RAG4 基线记录

> 记录日期：2026-09-14

## 当前基线

RAG4 当前以 `project/` 下导入的 RAG3 代码作为可运行基线。RAG4 的 Research Agent、知识图谱和混合证据引擎尚未实现；这些能力仍以根目录的 `RAG4_DEVELOPMENT_PLAN.md` 为设计目标。

## 目录与入口

- 后端：`project/backend/`，FastAPI 入口为 `app.main:app`。
- 前端：`project/frontend/`，Vite + React + TypeScript。
- 需求/API/部署文档：`project/docs/` 与 `project/deploy/`。
- 后端测试：`project/backend/tests/`，共 6 个测试文件。

## 已验证结果

- Node.js `v24.15.0`、npm `11.12.1`。
- `npm ci` 成功；安装后报告 3 个 audit vulnerabilities（2 moderate、1 high）。
- `npm run lint` 成功。
- `npm run build` 成功，产物输出到 `project/frontend/dist/`。
- 使用独立 Conda `rag4-py3.11` 环境（Python 3.11.15，按项目 requirements 安装，含 Chroma 0.5.23 与 pytest 8.3.4）执行 `python -m pytest -q` 成功，测试进度达到 100%，退出码为 0。

## 环境阻断

系统 Python 3.13 创建的 `project/backend/.venv` 安装依赖时会在 `chroma-hnswlib==0.7.6` 处因缺少 MSVC 编译工具失败；RAG4 不使用该环境。项目使用独立的 Conda `rag4-py3.11` 环境运行基线：

## 运行基线

前端：

```powershell
cd project/frontend
npm ci
npm run lint
npm run build
```

后端（推荐 Python 3.10–3.12）：

```powershell
cd project/backend
conda create -n rag4-py3.11 python=3.11 -y
conda run -n rag4-py3.11 python -m pip install -r requirements.txt
conda run -n rag4-py3.11 python -m pytest -q
```

后续第一项功能开发应从计划中的 `ChunkingEngine` 开始，并以本文件记录的前后端检查作为回归基线。
