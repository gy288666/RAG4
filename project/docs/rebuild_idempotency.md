# Phase 2.15：重建创建幂等键

创建请求支持可选 `idempotency_key`：

```json
{"dimension":4096,"idempotency_key":"rebuild-request-20260922-01"}
```

键为 1–64 位 ASCII 字母、数字、点、下划线、冒号或短横线，区分大小写，不允许空白。省略或 null 保留旧行为，每次创建新任务。

## 契约

- `(user_id, request_key)` 唯一；不同用户可以使用相同键。
- 请求指纹涵盖完整冻结 EmbeddingSpec 与 ChunkingConfig，包括维度和默认值。HTTP 的模型配置由当前管理员配置解析，因此配置变化可能令原键请求冲突；不能绕过现有 remote 配置校验。
- 同键同参数返回原任务及其当前状态，不重新读取源文件，不刷新文档快照或 base_revision，不触发执行。
- 同键不同参数返回 409，原任务保持不变。任务取消、成功或失败不会释放键；明确的新重建须使用新键。
- 创建键不绑定当前文档集合或 active revision。文档/索引变化后重发旧键仍返回第一次的冻结任务，这是重试语义，不是“重新构建当前状态”。
- 显式 recover_rebuild 创建的续接任务不会重新绑定原键；重发原键仍返回已取消的原任务。

`create_rebuild(..., idempotency_key=None)` 保持原 Python 调用兼容；新增 `RebuildRequestConflict(ValueError)`，API 映射 409。创建任务与请求映射在同一事务写入。Phase 2.16 增加用户级数据库准入锁，取得锁后复查原键，再检查配额并写入；复合主键仍是最终约束，异常冲突时整笔回滚再读取胜出记录，不留下重复任务。

## 迁移和回退

新增 `index_rebuild_requests` 表及 `007_rebuild_requests.sql`，依赖 005 的任务表。复合主键的 request_key 使用 utf8mb4_bin，与 SQLite 的区分大小写行为一致；task_id 唯一并带外键。任务或用户被删除时级联移除对应映射，没有自动清理键的接口。

使用新幂等能力前执行增量迁移并运行只读结构门禁。新表不修改历史任务，无需回填；回退旧应用时保留新表即可。未对业务库执行迁移。无新增 Python 依赖。迁移门禁和演练脚本已纳入 007。

MySQL 8.4.9/3307 独立合成库实测：007 重放两次通过，两线程同键创建返回同一个 task，任务与映射各只新增一条；含新表的 MySQL/文件/Chroma 组合恢复通过。位置与测试命令见 [基线](../../RAG4_BASELINE.md)。

后续 Phase 2.16 已加入 [创建配额](rebuild_quota.md)，同键同参重放优先于配额检查。仍无键过期、自动调度或模型费用预算。
