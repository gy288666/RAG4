# RAG4 本地项目概览

> 调研日期：2026-09-14  
> 调研范围：`E:\RAG4` 当前工作区；以本地文件为唯一实现证据。

## 结论

该工作区目前是**规划阶段，而非已初始化的应用仓库**。根目录只有 RAG3 调研摘要和 RAG4 开发计划；没有 `.git`、源码目录、依赖清单、锁文件、Docker 配置、测试、环境配置或可运行入口。因此，现阶段无法启动、构建或验证 RAG4 的实际实现。

## 当前布局与 Git 状态

| 路径 | 作用 | 实现状态 |
|---|---|---|
| [RAG4_DEVELOPMENT_PLAN.md](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:1) | RAG4 v2.0 产品、架构、里程碑与交付规划 | 设计文档 |
| [RAG3_PROJECT_OVERVIEW.md](E:/RAG4/RAG3_PROJECT_OVERVIEW.md:1) | RAG3 固定提交的基线调研摘要 | 参考资料 |

`E:\RAG4` 及其父目录中未检测到 Git 仓库元数据；所以没有可报告的分支、提交基线或工作树改动。也没有现成的代码/文档目录约定可供继承。

## 已有设计与拟定技术栈

RAG4 的定位是个人学术资料的、证据驱动的 Research Agent，而不是普通单轮 RAG 问答。[开发计划](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:11) 将 RAG3 定为基线：React 18、TypeScript、FastAPI、SQLAlchemy 与 Chroma。[计划元数据](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:3) 还设计了 Neo4j 图谱、结构感知父子切片、混合证据引擎，以及受限工具调用的任务 Agent。[总体架构](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:143)

这些均为**目标架构**，不是本地已安装或已经接线的依赖。计划中的目录（`backend/app`、`backend/tests`、`frontend/src`、`deploy`）也只是建议结构，尚未出现在工作区。[目录结构建议](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:1224)

## 计划中的入口与交付面

尚无真实 HTTP、CLI、前端或容器入口。规划中的外部服务接口包括：

- `ResearchAgent.start / continue_task / get_state`，作为任务编排入口。[ResearchAgent 设计](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:198)
- `/api/v1/research`、图谱和文档相关接口，作为后端 API 目标。[后端接口计划](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:705)
- 新建研究任务、任务工作区、文档详情、知识图谱与研究笔记页面，作为前端目标。[前端信息架构](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:826)

## 参考基线与实施状态

RAG3 参考资料记录的已实现基线包括文档解析、用户级 Chroma 检索、可选 rerank、SSE 问答和管理能力。[RAG3 概览](E:/RAG4/RAG3_PROJECT_OVERVIEW.md:5) 同时明确 GraphRAG/知识图谱在 RAG3 中仍是未来设计，而非既有实现。[关键边界](E:/RAG4/RAG3_PROJECT_OVERVIEW.md:27)

RAG4 计划把第一项实际工作定为：先恢复并冻结 RAG3 的可复现测试/评测基线，再独立实现切分模块；随后才引入图谱、Agent 和前端工作区。[开工顺序](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:1554) 第 0 阶段要求从 RAG3 创建独立分支、启动既有测试与构建、固定配置和评测样本。[第 0 阶段](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:1304)

## 建议的下一步

1. 将 RAG3 源码以独立 Git 仓库/分支导入 `E:\RAG4`，保留可追溯基线。
2. 先按 RAG3 文档运行后端测试、前端 lint/build 与评测，记录结果。
3. 仅在基线可复现后，按计划的第 1 阶段实现并测试结构感知父子切片。

该顺序也与计划中“不要在没有测试基线时大规模重写”的开发纪律一致。[开发纪律](E:/RAG4/RAG4_DEVELOPMENT_PLAN.md:1488)
