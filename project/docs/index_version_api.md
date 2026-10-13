# Phase 2.12：用户级 active 索引管理接口

Phase 2.14 统一历史/激活清单解析：即使摘要匹配，schema、成员结构、摘要格式或唯一性错误也视为损坏；历史标记 invalid，激活返回 400。详见 [验收索引](phase2_acceptance.md)。

## Phase 2.13：历史版本发现与详情

新增 GET `/api/v1/index-versions?limit=20&offset=0` 和 GET `/api/v1/index-versions/{version_id}`。使用当前 JWT 所有者过滤，管理员也不能越权；未知/他人版本统一 404。limit 为 1–100、offset 非负，列表按创建时间及 ID 倒序，返回 items/total/limit/offset。`/active` 固定路径优先，不会被当作版本 ID。

列表摘要包含 id、created_at、is_active、manifest_integrity、document_count 和 embedding 的 model_id/version/dimension。详情额外包含创建版本时的 documents（id/file_name）及 members（build_id/document_id/chunk_set_id）。不返回原始 manifest、模型 endpoint、向量 namespace 或凭据。is_active 仅为查询时读取的指针状态，切换仍必须重新读取 revision；并发查询不保证总数、列表和 active 标记属于一个一致快照。

manifest_integrity=valid 仅表示持久化清单摘要匹配、用户和基本结构可解读，**不代表候选向量完整或当前可激活**。查询不会读取向量，也不会比对当前文档集合。旧文档改名/删除后仍展示冻结清单；损坏版本保留在历史列表，以 invalid 标记且不展开其 payload，避免整个历史接口失效。激活仍调用原完整校验。

新增服务 `list_versions(user_id, limit=20, offset=0)` / `describe_version(user_id, version_id)`。版本 ID 可从列表找到，再查看详情并显式 CAS 回滚。闭环测试覆盖 HTTP 创建任务 → 受控 worker 执行 → HTTP 激活 → 再次重建激活 → 历史查询 → 回滚及检索；没有 HTTP 自动执行或前端。无新增依赖/迁移。

JWT 认证，路径 `/api/v1/index-versions/active`；使用当前登录用户，管理员也没有跨用户操作例外。

| 方法 | 请求 | 响应 data |
| --- | --- | --- |
| GET | 无 | `{ "version_id": null或版本ID, "revision": 整数 }` |
| PUT | `version_id` 和 `expected_revision` 均必填 | 成功后的 version_id 和递增 revision |

例如任务 worker 返回 ready 后，先 GET 获得当前 revision，再提交：

```json
{"version_id":"version_FROM_READY_TASK","expected_revision":0}
```

回滚使用保留的旧 version_id，同样重新读取 revision；旧版本仍须覆盖当前全部就绪文档且所有候选完整。停用必须明确提交 `version_id: null`，省略字段不代表停用。expected_revision 必须是非负整数，布尔值和额外 user_id 字段拒绝。

## 错误和并发语义

- 401/403：沿用 JWT/禁用账号规则。
- 404：版本不存在或不属于当前用户，返回相同信息。
- 409：revision 已变化；读取最新状态，让调用方重新确认，不自动重试覆盖。
- 400：请求无效，或文档/清单/向量完整性检查不通过；不回显内部异常、路径或配置。
- 500：未分类的后端故障，沿用统一错误处理。失败不会提交 active 变更或切换审计。

服务新增 `ActiveRevisionConflict(ValueError)`，保留原 ValueError 调用兼容性。HTTP 层据此区分 CAS 冲突与校验失败，不通过异常文字匹配。激活/回滚复用完整 manifest、ChunkSet、向量摘要和文档集校验；指针 UPDATE 与 IndexSwitch 写入在同一事务，usage 日志继续记录切换耗时和成败。

首次失败可能初始化一个 version_id=null、revision=0 的指针行，语义仍为 baseline，没有发布新索引。成功请求即使指向同一个版本也递增 revision；重放旧请求返回 409。

## 停用与限制

停用不会初始化或读取向量后端，因此 Chroma 不可用时仍可解除 active 指针绑定。此操作仅切回 baseline 路由，不保证故障中的向量后端立即能查询 baseline；保留所有旧版本与向量，不删除数据。

Phase 2.12 当时未增加版本列表/详情，后续 Phase 2.13 已通过上述接口补齐。仍无前端、自动激活或自动调度；使用 Phase 2.11 worker 执行任务。没有新增依赖或迁移，默认 baseline 不变。后续应收敛 Phase 2 验收、部署限制和发布前检查，尚不进入 Graph/Agent 阶段。
