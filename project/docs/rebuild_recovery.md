# Phase 2.5：显式中断恢复与独立续接任务

新增 `recover_rebuild(user_id, task_id)`，处理进程中断后仍停留在 running 的批量任务。它不判断进程是否死亡，不重置原任务为 pending；即使原执行者仍活着，恢复也会持久化取消标志，确保其不能发布 ready 结果。

```python
from app.services.index_rebuild_service import recover_rebuild, run_rebuild

successor = recover_rebuild(user_id, interrupted_task_id)
result = run_rebuild(user_id, successor.id, api_key=key_from_secure_config)
# result.ready 仍需显式调用版本切换接口，不能自动激活。
```

## 事务与幂等

- 条件更新只接受 running 且尚未收到取消请求的原任务，设置 cancelled/cancel_requested。
- 同一 SQL 事务复制原请求、已提交 checkpoint 和原 base_revision，创建新的 pending 任务，并插入 `index_rebuild_recoveries` 关联记录。
- 关联表 source_task_id 主键保证一个源任务仅有一个直接续接任务；重复或并发恢复返回相同的目标 ID。
- 任一事务写入失败，旧任务的取消、新任务和关联一起回滚。
- index_recovery 用量事件记录恢复操作耗时与成败；关联记录保存来源、目标和创建时间。
- failed 任务继续使用 run_rebuild 的失败重试；pending/ready/用户已请求取消的任务不能恢复。所有操作均检查所有权。
- 续接使用新的任务 ID，因此未完成文档的子任务键和向量 namespace 独立；已提交 checkpoint 在执行时重新验证后复用。
- 保留原 base_revision，避免恢复过程悄悄采用新指针修订号而覆盖其他切换。

## 旧执行者与恢复范围

cancelled 表示旧任务不能再发布 ready，并不代表旧操作系统进程已终止。已发出的远程请求可能继续消耗资源；旧执行者可能完成自己的候选或补写自己的 checkpoint，且仍可能留下未激活版本。这些写入只属于旧任务，新任务的 checkpoint 快照不会被它覆盖。旧任务最终结果由数据库中的取消标志决定，不会自动激活。

没有租约、心跳超时判定、自动恢复队列或进程强杀。调用者显式决定何时恢复；无需先证明旧进程已退出，因为两次执行已隔离。子准备/构建任务自身的 running 记录不被接管，仍保留用于审计。GC 和自动超时诊断待后续实现。

如果源文件或文档集合变化，续接执行仍按被冻结输入拒绝继续，需要创建新的完整重建任务。恢复不绕过权限、源校验、向量完整性或 active CAS 门禁。

## 迁移与验证

在 005 后执行 `006_rebuild_recovery.sql`，只增加关联表；旧任务表不改字段。应用回退可以保留新增表，不删除任何历史任务或向量。

新增 10 项 Local/Chroma 测试，模拟未捕获中断、已提交 checkpoint、旧工作线程阻塞后迟到、并发恢复、事务失败和权限/主动取消。真实 MySQL 3307 验证使用已有独立合成验证库，006 重放两次成功，复用真实 BGE 向量 checkpoint 得到 ready，新增模型调用 0 次，active 不变；两线程并发恢复也返回同一目标。不是实际终止业务进程或恢复用户生产任务的演练。
