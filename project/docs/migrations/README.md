# 增量迁移

`007_rebuild_requests.sql` 新增用户级创建请求键映射（依赖 005），不改变旧任务表。请求和任务在同一事务落库，回退可保留新表，详见 [幂等创建](../rebuild_idempotency.md)。门禁和合成恢复脚本已纳入此迁移。

已新增 [合成库备份恢复演练](../migration_restore_drill.md)，可验证 002–006 迁移前后逻辑备份、恢复和数据摘要一致性。该演练不等于业务库或 Chroma/上传文件的完整恢复验收。

执行前可使用 [只读结构门禁](../schema_preflight.md)：显式指定数据库，检查缺表和结构漂移，返回有序脚本建议；该工具不执行迁移，也不替代备份恢复演练。

`002_chunk_preparation.sql` 新增 Phase 2 切分准备任务和 ChunkSet 表，适用于已具备 users/documents 的 MySQL 库。编号 002 表示 Phase 2，不代表存在 001 迁移。

先备份并在副本演练，选择目标数据库后执行该文件。不得以含 DROP DATABASE 的历史 `../init_db.sql` 代替升级脚本。回退应用时保留新增表即可，不需要反向删除数据。

`003_index_builds.sql` 在 002 后执行，新增单文档候选索引构建记录。两份脚本已在本机 MySQL 5.7.44-log 的独立新建验证库重复执行通过，并完成真实模型构建联调；尚未执行业务库迁移或备份恢复演练。安装无新增依赖。详细接口见 [索引准备说明](../index_preparation.md)、[候选索引说明](../index_staging.md) 和 [真实验证记录](../model_connectivity_validation.md)。

`004_active_indexes.sql` 在 003 后执行，新增用户级版本清单、active 指针和切换审计三张表。旧候选缺少完整向量记录摘要时必须重建，不直接激活。代码回退可保留新表，服务停用可显式将 active 指针切回 None。详见 [激活与回滚](../index_activation.md)。

`005_index_rebuilds.sql` 新增用户级重建任务与逐文档 checkpoint，依赖之前的准备/候选/版本服务。失败重试和协作取消详见 [批量重建](../index_rebuild.md)，不具备进程崩溃自动接管能力。

`006_rebuild_recovery.sql` 在 005 后执行，新增一个源任务仅对应一个直接续接任务的关联表，原任务状态不重置；显式中断恢复见 [恢复接口](../rebuild_recovery.md)。已在 MySQL 8.4.9/3307 独立验证库重放两次通过。
