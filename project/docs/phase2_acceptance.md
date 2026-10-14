# 2026-10-13 文献任务补充

新增 [研究后端切片](research_backend_mvp.md) 通过公开只读 `load_version_snapshot` 复用 Phase 2；不新建索引调度层，不自动改变 active。三篇官方论文在隔离 SQLite 中完成准备、构建、读回验证、版本 1→2 激活、回滚及停用，并使用在线查询向量执行研究。文档向量来自核对 ID/text 的缓存，另记录向量值摘要；不是全新文档 Embedding 或业务 MySQL 发布验收。

MySQL 3307 只在新建隔离库验证迁移 008 的 LONGTEXT/UTF-8 checkpoint 与 CAS，业务库未改。**现有 Phase 2 的迁移/恢复门禁不包含研究表 008**；启用研究任务前须另行核对该表、备份及恢复。原生产调度、自动故障检测、完整上线验收仍未完成。当前最终回归及实验错误见 [开发记录 R19](development_process.md)。下文各轮数字是历史验收。

# Phase 2 验收索引（2026-10-12 收紧近期范围）

**当前结论：手动闭环已实现，代码已随 `476127b` 推送；范围冻结为维护基线，待当前完整回归和隔离真实文献闭环验证。** 不宣称生产上线。下一切片转向真实文献基线，近期范围与触发条件以 [开发计划第 3.4 节](../../RAG4_DEVELOPMENT_PLAN.md) 为准。

2026-10-10 Phase 2.16 更新：创建配额已实现，重建相关 73 passed / 234.58s，补充及原认证/文档 39 passed / 89.16s；MySQL 3307 合成配额并发 passed / 8843ms。以下 349 项及组合恢复数字是 Phase 2.14 历史结果，本轮未重跑全量。没有进行生产迁移或发布。

范围是手动触发的版本化索引闭环，默认 RAG3 行为保留。下表区分已实现、验证方式和部署前仍需完成的条件，不能作为“已上线”的声明。最新实际执行结果见 [基线记录](../../RAG4_BASELINE.md)。

Phase 2.14 当时后端全量 **349 passed / 618.48s**，专项损坏测试 **14 passed / 52.27s**，当时代码 MySQL 组合恢复 **passed / 29979ms**。这些是历史证据，不能替代当前 378 项的完整回归；本次计划调整未重跑业务测试。

| 验收项 | 实现入口 | 证据 |
| --- | --- | --- |
| 父/子 ChunkSet 持久化与准备任务 | index_job_service | test_index_jobs |
| 隔离候选、维度和摘要回读验证 | index_build_service | test_index_builds；历史真实模型验证 |
| 完整文档集版本、事务 CAS 和切换审计 | index_version_service | test_index_versions、test_version_api |
| 重建 checkpoint、失败重试和协作取消 | index_rebuild_service | test_index_rebuilds |
| 显式中断续接、迟到执行者隔离 | recover_rebuild | test_rebuild_recovery；历史 MySQL 并发验证 |
| 用户任务管理与权限 | /index-rebuilds | test_rebuild_api |
| 可选创建幂等性、同键冲突 | create_rebuild / RebuildRequest | test_rebuild_idempotency；MySQL 并发验证 |
| 用户任务创建配额、并发与恢复兼容 | create_rebuild / RebuildQuotaExceeded | test_rebuild_quota；不等同于执行资源预算 |
| 当前凭据与冻结模型身份绑定 | execute_configured_rebuild | test_rebuild_execution |
| 历史查询及回滚闭环 | /index-versions | test_version_history |
| 损坏清单的统一拒绝 | _read_manifest | test_manifest_integrity（摘要正确但结构错误仍拒绝） |
| 只读结构检查与迁移顺序 | check_index_schema.py | test_schema_preflight；MySQL 3307 实测 |
| 合成 MySQL/上传/Chroma 停写组合恢复 | rehearse_mysql_restore.py | test_mysql_restore、test_offline_snapshot；真实 MySQL/Chroma 演练 |

## 本轮修正

历史查询与激活原先分开解析 JSON。缺字段会产生 KeyError，HTTP 层因其继承 LookupError 可能返回 404；某些结构错误则可能成为未分类错误。现在 `_read_manifest` 统一检查摘要、schema、用户类型/身份、非空文档集、模型契约、成员字段、向量摘要格式和唯一性，再进入历史展示或实时验证。

历史损坏记录显示 invalid；激活收到标准 ValueError 并返回 400，不写 active 或 IndexSwitch。查询遇到损坏 active 继续失败关闭，用户仍能显式停用。摘要不是签名，结构校验也不替代候选内容和当前文档集验证。新增 Local/Chroma 参数化回归 14 项。

## 可用的手动流程

1. 准备独立 RAG4 数据库并核对增量表结构；先在副本演练，不能运行含 DROP DATABASE 的历史 init_db.sql 升级。
2. 使用原上传接口将文档处理为 ready。
3. 登录用户 POST /index-rebuilds，声明与管理员模型配置一致的维度和切分参数。
4. 可信运维通过显式 DATABASE_URL 运行 run_index_rebuild.py；查看任务 ready/version_id。
5. 用户 GET /index-versions/active 获取 revision，PUT 显式激活目标版本。
6. 查询检索；需要回滚时从历史列表选择保留版本并再次 CAS 切换，或明确 null 停用。

## 进入真实研究任务验证的有限收尾

- [x] 2026-10-12 发布基线实际全量 378 passed / 465.54s；新增试点后相关 108 passed / 8.03s，未重跑新增后的全量。
- [ ] 在独立评测环境，通过现有服务/CLI 串行验收真实文献的构建、激活、查询和回滚，保存命令与结果。操作者一次只启动一个 worker，恢复前确认旧进程停止；这是实验约束，不是已实现的并发保护。
- [x] 保存三篇真实论文的固定来源、20 题 AI 草稿及两条检索基线原始结果与失败清单，见 [试点报告](literature_pilot_report.md)。
- [ ] 人工核对 20 题标注与引用支持范围，确认等价证据；不能将 AI 草稿当成人工金标准。

达到以上条件即按研究场景进入 Phase 3，不等待下面所有生产条件完成。后续仅因复现的数据安全、权限或研究任务阻塞回到索引模块修复。

## 生产上线待办与重新启动条件

下列工作仍需在对应生产能力开放前完成；它们不是受控、隔离、串行研究验证的默认依赖。具体触发条件统一见开发计划第 3.4 节。

- 生产专用库选择、正式迁移、部署配置切换和运维责任确认；已有验证均为隔离合成库。
- 自动后台队列、调度、心跳、进程故障自动检测；当前只有单任务命令和显式恢复。
- 在线一致性备份、大规模恢复和跨主机恢复；现有组合演练依赖全部写入进程已退出。
- worker 执行并发/模型费用预算、索引保留/GC 和跨任务增量复用；Phase 2.15 已提供可选幂等键，Phase 2.16 已限制用户未完成任务的创建数量，尚无物理执行资源上限。
- 大规模检索性能；当前 active 查询完整回读校验候选。
- 冻结真实业务评测集和端到端检索质量门槛；Fake Adapter 的功能测试不能替代质量评测。
- 前端任务工作区与完整研究质量验收；Graph/ResearchAgent/EvidenceVerifier 最小后端已新增，见上方补充。

当前只将手动闭环作为研究实验底座。先以真实失败案例验收混合证据和研究产物；多 worker、无人值守、存储或时延瓶颈出现时，再启动有界的索引基础设施切片。
