# RAG4

**当前进度（2026-11-04）：Phase 1–5文献比较最小后端已接通，研究质量验收仍未通过。** R39新增失败任务部分稿的授权只读接口，返回比较表、引用原文与缺口；先验任务归属/状态/版本，再复验来源，0模型调用、不修改任务。隔离真实R37任务验证200/401/404/409，保留两条方法和10缺口，原任务仍failed。见 [接口与验证记录](project/docs/research_partial_artifact_api.md)。

R28–R33已推送至 `4f4fff8`；本次提交汇总R34–R39的代码、测试和开发记录。R39相关 **102 passed /115.66s**，新增16项，未重复R37历史641项；当前收集694项，不称已全量执行694。下一步是最小前端阅读路径，复用登录、任务和文档接口，先查看既有成果/来源。R37错误精确根因、人工验收、完整研究工作区、Neo4j及正式微调仍待完成。范围以 [计划第3.4节](RAG4_DEVELOPMENT_PLAN.md) 为准。

以下为已发生的分阶段记录，其中“本轮”指对应历史轮次；开发过程与当前执行安排见 [开发记录](project/docs/development_process.md)。

Phase 2.16（2026-10-10）已完成 [用户重建创建配额](project/docs/rebuild_quota.md)：默认 8 个未完成任务，超限 429；幂等重放与恢复不重复占额。相关回归 **73 passed / 234.58s**，补充及认证/文档回归 **39 passed / 89.16s**；MySQL 3307 合成并发验证通过。后端收集 378 项，该轮未重跑全量或迁移业务库；代码后于 2026-10-12 推送。

Phase 2.15（2026-09-26）已完成 [创建幂等键](project/docs/rebuild_idempotency.md)：同用户同键同参返回原任务，异参 409；新增 007 迁移，独立 MySQL 并发验证通过。最新相关回归 **61 passed / 106.10s**，本轮未重跑全量或迁移业务库。

最新 Phase 2.14 验证：后端全量 **349 passed / 618.48s**，当前 MySQL/上传/Chroma 组合恢复通过。手动索引闭环已有实现与测试，生产上线条件仍未满足，见 [验收索引](project/docs/phase2_acceptance.md)。以下分阶段记录保留各轮结果。

RAG4 以证据驱动的学术 Research Agent 为目标，从 RAG3 逐步演进。`project/` 中已有可运行的 RAG3 前后端、远程/本地 Embedding 与 Reranker Adapter、按 Embedding 版本隔离的索引，以及 Embedding、Reranker、LoRA-SFT 训练入口。

Phase 1/2 历史验收：结构化 ChunkingEngine、staging 验证、用户级激活/回滚、批量 checkpoint 和显式中断续接已实现；MySQL 上的向量复用及恢复演练已记录。默认仍使用 RAG3。349 passed 是旧轮次结果，当前进度和验证以上文及开发记录为准；部署与恢复入口见 [中断恢复](project/docs/rebuild_recovery.md)。

基线验证与环境限制见 [RAG4_BASELINE.md](RAG4_BASELINE.md)。RAG3 项目细节见 [RAG3_PROJECT_OVERVIEW.md](RAG3_PROJECT_OVERVIEW.md)。

Phase 2.7 已完成 [合成关系数据库备份恢复演练](project/docs/migration_restore_drill.md)：MySQL 3307 两次通过，相关回归 **34 passed**。该验证不含 Chroma/上传文件，也不等于业务库上线验收；本轮未重跑全量测试。

Phase 2.8 已完成 [停写文件与 Chroma 配套恢复](project/docs/offline_restore.md)：合成 SQLite、上传文件、真实 Chroma 恢复后检索及 baseline 回退通过，相关回归 **30 passed**。MySQL 与配套文件的统一恢复尚待组合验证。

Phase 2.9 已完成 [MySQL/上传/Chroma 组合演练](project/docs/mysql_combined_restore.md)：32882ms 通过，全量 **282 passed / 421.93s**。Phase 2.8 待组合验证项已有合成停写证据，正式业务迁移仍未执行。

Phase 2.10 已提供 [用户重建任务管理 API](project/docs/rebuild_api.md)：JWT 保护的创建、分页、详情和取消，管理员也不通过这些接口越权访问其他用户任务。创建仅生成 pending，不自动执行或激活；本轮相关回归 29 passed，全量 282 passed 为上轮记录。

Phase 2.11 已增加 [单任务执行 worker](project/docs/rebuild_worker.md)，执行前绑定管理员配置与凭据，复用原子领取和失败重试，成功不自动激活。相关回归 **39 passed**；尚无自动队列或 HTTP 长任务执行。

Phase 2.12 已增加 [用户级 active 管理 API](project/docs/index_version_api.md)，显式 revision 激活/回滚/停用，冲突 409。停用不依赖向量后端初始化；相关 **37 passed / 122.75s**，本轮未重跑全量。

Phase 2.13 已补历史版本列表与详情，以及创建→worker执行→激活→历史发现→回滚检索闭环。历史清单完整性与当前可激活性分开验证，相关 **26 passed / 75.70s**；无生产迁移或自动调度。

开发时间线、实现过程、问题修正、验证证据与下一阶段交接见 [开发过程记录](project/docs/development_process.md)；切分接口与开关说明见 [RAG4 ChunkingEngine](project/docs/rag4_chunking.md)。

来源编号核验与范围对照纳入 2026-10-19 GitHub 交付批次；实验与测试日期为 2026-10-14，语义质量门槛仍未通过。

## 快速验证

```powershell
cd project/frontend
npm ci
npm run lint
npm run build
```

后端固定使用 Conda Python 3.11 环境 `rag4-py3.11`；完整步骤见 [project/README.md](project/README.md)，模型训练见 [project/training/README.md](project/training/README.md)。
