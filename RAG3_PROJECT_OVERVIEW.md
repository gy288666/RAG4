# RAG3 项目概览

> 调研快照：[`080d3e4`](https://github.com/gy288666/RAG3/tree/080d3e4d1ad6a94de3afa87522d94f85139d5419)，2026-09-14。以下结论仅依据该仓库的 README、源码和随仓文档。

## 定位与范围

RAG3 是一个面向专业/学术文献的个人知识引擎：用户上传 PDF、DOCX、TXT 或 Markdown，系统解析、切片、向量化后以“检索 + 大模型生成”提供带原文定位的流式问答。产品还包含账户、会话历史、知识库管理，以及管理员的用户、配置和运行监控页面。[项目 README](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/project/README.md#L22-L44)

## 当前架构

- 前端为 React 18、TypeScript、Vite、TailwindCSS；后端为 Python/FastAPI/SQLAlchemy；关系库默认 MySQL（开发可用 SQLite）；向量库为 Chroma。[技术栈](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/project/README.md#L48-L59)
- 后端按 `core`、`models`、`schemas`、`api/v1`、`services` 和 `utils` 分层；RAG 服务链为查询改写、检索、可选精排、生成、引用和落库。[目录与服务职责](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/project/README.md#L61-L110)
- 问答用 SSE 推送 `chunk`、可选 `title` 和 `done` 事件；引用为 PDF 页码或文本片段序号。[接口与 SSE 约定](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/project/README.md#L174-L213)
- 隔离策略覆盖物理上传文件、每用户独立的 Chroma collection，以及所有关系库查询的 `user_id` 约束。[数据隔离说明](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/project/README.md#L249-L259)

## 本地开发与验证

后端需要 Python 3.10+，前端需要 Node 18+；常规运行需要配置数据库与模型服务。也提供 `DEV_MOCK_AI=true` + SQLite 的离线体验模式，使用本地 mock Embedding/LLM 且跳过 rerank，仅适用于开发与测试。[启动与 Mock 模式](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/project/README.md#L112-L172) 后端测试以临时 SQLite 和 Mock AI 运行；前端通过 `npm run lint` 与 `npm run build` 验证。[测试说明](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/project/README.md#L285-L307)

## 文档 / 笔记约定

- 产品需求与接口契约是实现依据：`project/docs/requirements_document.md`（v1.1）和 `project/docs/api_document.md`（v1.0）。[README 的依据声明](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/project/README.md#L3-L8)
- 项目级文档集中在 `project/docs/`；README 同时把 `backend/experiment/` 定义为切片与检索参数的单变量实验脚本及结果所在位置。[仓库入口说明](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/README.md#L3-L8)
- 开发过程使用显式的 **DONE** 与 **TODO** 区分状态；TODO 完成后移入 DONE 并写完成日期。影响架构的决定以追加 ADR 的方式记录。[维护约定](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/development_process.md#L773-L774)
- 文档开头应标注版本、更新日期和覆盖范围；尚未实现的方案应显著注明“未实现 / 设计方案”。[开发过程文档示例](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/development_process.md#L1-L6) [知识图谱章节状态](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/development_process.md#L503-L506)

## 接手时的关键边界

知识图谱/GraphRAG 在开发过程文档中是后续设计，不是现有功能；当前检索基于向量相似度。进行后续规划或实现时，应保持该状态边界，不能将该方案表述为已经交付。[现状与规划的明确区分](https://github.com/gy288666/RAG3/blob/080d3e4d1ad6a94de3afa87522d94f85139d5419/development_process.md#L503-L510)
