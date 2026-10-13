# Phase 2.11：显式执行 worker 与凭据绑定

后续 Phase 2.12 已提供 [用户级 CAS 激活与停用](index_version_api.md)。worker 仍不会自动激活，ready 后需由用户显式切换。

新增 `app.services.rebuild_execution.execute_configured_rebuild(user_id, task_id, *, store=None)` 和 `scripts/run_index_rebuild.py`。这是受信任的运维/worker 执行入口，不是用户 HTTP 认证接口，不接受用户提交的模型地址或 API Key。

## 执行契约

1. 检查任务归属、账号存在且启用。
2. 已 running/ready/cancelled 或已有取消请求的任务直接返回当前状态，不重复调用模型。
3. 对 pending/failed 任务，读取当前管理员配置；provider 必须 remote，endpoint、model_id、version 必须逐项等于任务冻结配置，密钥不能为空。
4. 校验通过后调用原 `run_rebuild`。数据库条件 UPDATE 负责领取；并发执行者只有一个增加 attempt 并执行。失败重试仍复用已提交 checkpoint，使用新候选命名空间。
5. 成功仅生成 ready 与 version_id，active 指针不变；后续仍需显式 CAS 激活。配置不匹配或凭据缺失在领取前拒绝，不改变任务状态。

密钥只在本次进程内传给模型 Adapter，不进入任务 JSON。允许同一模型配置下轮换密钥；模型配置改变后旧任务必须重新创建或由运维恢复匹配配置，worker 不偷偷更新冻结请求。配置和账号检查是执行开始时的快照，不会撤销已经发出的远程调用；运行中取消沿用协作停止。

## 命令

先通过管理 API 创建任务，然后在 backend 目录由可信操作者运行：

```powershell
python scripts/run_index_rebuild.py --user-id 123 --task-id rebuild_TASK_ID
```

必须通过进程环境显式提供 `DATABASE_URL`，避免误连历史默认数据库；数据库密码不要放在命令行参数中。其他 UPLOAD_DIR/CHROMA_DIR/ENV_FILE 等配置须与创建任务的部署一致，模型密钥从目标库的管理员配置读取。命令不 init_db、不执行迁移、也不创建默认管理员。

输出 JSON 包含 task_id、status、attempt、version_id、error_code、累计任务耗时和本次 worker 耗时。退出码 0 表示 ready，1 表示返回非 ready 状态（包括仍 running、failed、cancelled），2 表示前置条件或调用拒绝。失败不输出异常正文、连接串或密钥。必须结合 status 判断状态，不能把退出码 1 一概当作模型执行失败。

## 当前边界

一次命令只执行一个已存在任务，没有队列、调度循环、心跳或自动崩溃接管。HTTP 仍仅提供创建/查询/取消，未开放长任务执行；部署方可以在受控独立进程运行此命令。进程崩溃可能留下 running，继续使用已有显式 recover_rebuild 创建隔离续接任务。错误状态和耗时由任务/worker 输出追踪；worker JSON 输出需操作者自行保存，不是持久化调度日志。

没有新增依赖、数据库迁移或默认行为变更。下一步开放权限受控的 CAS 激活/停用接口及冲突语义，再补部署级调度。Graph/ResearchAgent/研究工作区仍未实现。
