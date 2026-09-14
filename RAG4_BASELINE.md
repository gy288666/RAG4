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
- 使用当前机器的全局 Python 测试环境执行 `pytest -q` 成功，测试进度达到 100%，退出码为 0。

## 环境阻断

项目要求 Python 3.10+。本机 Python 为 3.13.9；创建的 `project/backend/.venv` 尚未完成依赖安装。`pip install -r requirements.txt` 在 `chroma-hnswlib==0.7.6` 处失败，原因是该环境没有适配 Python 3.13 的预编译轮子，且缺少 Microsoft Visual C++ 14.0+ 编译工具。因此后端测试的可复现虚拟环境仍需 Python 3.10–3.12 或安装对应 C++ Build Tools 后重新构建。

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
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

后续第一项功能开发应从计划中的 `ChunkingEngine` 开始，并以本文件记录的前后端检查作为回归基线。
