# Phase 2.4：可重试的批量重建任务

本切片将现有单文档准备、候选构建和完整版本组装串成显式用户级任务。适用于上传/删除后生成完整新版本，以及失败后从已完成文档继续。没有自动后台调度或隐式激活。

## 调用

```python
from app.services.index_build_service import EmbeddingSpec
from app.services.index_rebuild_service import create_rebuild, run_rebuild, get_rebuild, cancel_rebuild
from app.services.index_version_service import switch_version

spec = EmbeddingSpec(endpoint="https://api.siliconflow.cn/v1/embeddings",
    model_id="Pro/BAAI/bge-m3", version="bge-m3-r1", dimension=1024)
task = create_rebuild(user_id, spec)
result = run_rebuild(user_id, task.id, api_key=key_from_secure_config)
if result.status == "ready":
    switch_version(user_id, result.version_id, expected_revision=result.base_revision)
elif result.status == "failed":
    # 修复外部原因后重试同一个 task.id；已完成文档不重复向量化。
    result = run_rebuild(user_id, task.id, api_key=key_from_secure_config)
```

创建任务时要求所有文档 ready，冻结文档 ID/文件名/原文件 SHA-256、ChunkingConfig、EmbeddingSpec 和当时 active revision。完整重建任务每次创建有独立 ID，执行同一个 ID 是幂等的；尚无创建请求级幂等键。

`user_index_rebuilds` 保存 request_json、checkpoints_json（文档 ID → 已验证 build ID）、attempt、cancel_requested、version_id、错误分类/文档、累计执行耗时与时间。所有查询、运行和取消均检查用户所有权；Key 仅执行时传入，不持久化。

## 状态与恢复

- `pending → running → ready/failed/cancelled`。失败可再次调用 run_rebuild，attempt 加一；ready/cancelled 重复执行返回现状。
- SQL 条件更新抢占，重复调用 running 不并行执行。每完成一个文档立即保存 checkpoint，重试先重新验证该候选而不再调用模型。
- 未完成文档每次尝试创建新的准备任务和候选 namespace，键为 `任务ID-尝试序号-文档序号`；失败子任务和旧向量不会被覆盖。
- 执行开始及组装版本前重新核对完整源快照，准备任务的摘要也必须匹配。源/文档集合变化时拒绝继续，需新建任务；不会偷偷采用最新文件代替被冻结输入。
- 只有全部候选完成才组装用户级版本。ready 仅表示候选版本可交给切换服务，不会自动激活；active 修订号已变化时，原 base_revision 的激活会被拒绝。
- pending/failed 可立即取消，running 在文档边界和准备结束后检查取消。正在进行的远程请求不强制中断；请求返回后保存已验证进度，再停止后续文档。
- 最终发布使用 SQL CASE 读取最新 cancel_requested，防止取消后仍发布 ready。取消恰逢版本组装可能留下未激活的版本清单，保留用于审计，尚无 GC。

## 兼容与当前边界

不会更新 active 指针、旧文档状态或旧向量。当前完整重建会重新处理全部文档，重试才复用同任务 checkpoint；尚未做跨任务/版本的自动增量复用。新增/删除导致旧 active 失配时，仍需显式停用恢复 baseline，或完成并激活新版本。

受控失败可重试同任务；Phase 2.5 已新增 [显式中断恢复](rebuild_recovery.md)，持久化取消旧 running 任务并创建独立续接任务，不重置旧状态复跑。仍没有租约/心跳或自动接管。子任务副作用完成但 checkpoint 尚未提交时，续接可能重复计算，但写入新 namespace。

同步服务接口，未新增 HTTP/UI、任务队列、进度推送或生产调度器。大语料快照哈希、内存用量和查询全量回读开销尚需后续优化。

## 迁移

按 002 → 003 → 004 → `005_index_rebuilds.sql` 执行增量脚本，005 仅增加任务表，不修改旧表。开发 init_db() 可创建新表；代码回退保留表即可。真实验证脚本已覆盖批量重建 ready、显式激活与停用，使用独立数据库和合成文本，不触碰业务库。
