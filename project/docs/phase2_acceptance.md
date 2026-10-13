# Phase 2 验收索引（2026-09-22）

2026-10-10 Phase 2.16 更新：创建配额已实现，重建相关 73 passed / 234.58s，补充及原认证/文档 39 passed / 89.16s；MySQL 3307 合成配额并发 passed / 8843ms。以下 349 项及组合恢复数字是 Phase 2.14 历史结果，本轮未重跑全量。没有进行生产迁移或发布。

范围是手动触发的版本化索引闭环，默认 RAG3 行为保留。下表区分已实现、验证方式和部署前仍需完成的条件，不能作为“已上线”的声明。最新实际执行结果见 [基线记录](../../RAG4_BASELINE.md)。

本轮最终后端全量 **349 passed / 618.48s**，专项损坏测试 **14 passed / 52.27s**，当前代码 MySQL 组合恢复 **passed / 29979ms**。compileall、git diff --check 通过。所有变更仍在工作区，未提交或推送。

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

## 尚未通过的上线条件

- 生产专用库选择、正式迁移、部署配置切换和运维责任确认；已有验证均为隔离合成库。
- 自动后台队列、调度、心跳、进程故障自动检测；当前只有单任务命令和显式恢复。
- 在线一致性备份、大规模恢复和跨主机恢复；现有组合演练依赖全部写入进程已退出。
- worker 执行并发/模型费用预算、索引保留/GC 和跨任务增量复用；Phase 2.15 已提供可选幂等键，Phase 2.16 已限制用户未完成任务的创建数量，尚无物理执行资源上限。
- 大规模检索性能；当前 active 查询完整回读校验候选。
- 冻结真实业务评测集和端到端检索质量门槛；Fake Adapter 的功能测试不能替代质量评测。
- 前端任务工作区，以及 Graph、ResearchAgent、EvidenceVerifier 等后续阶段。

因此可称“Phase 2 手动闭环已实现并有测试”，不能称“自动化索引平台或生产发布已验收”。后续优先处理明确的上述缺口，避免继续累加只有名称的阶段完成标记。
