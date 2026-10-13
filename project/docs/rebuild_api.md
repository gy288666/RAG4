# Phase 2.10：用户级重建任务管理接口

Phase 2.15 新增可选 idempotency_key，同用户同键同参数返回原任务，不同参数返回 409，详见 [创建幂等契约](rebuild_idempotency.md)。需先部署 007 增量表。

Phase 2.16 新增 [用户创建配额](rebuild_quota.md)：默认最多 8 个 pending/running/failed 任务，新创建超限返回 429（data 含 limit/open_count），同键同参重放不占额外额度。

后续 Phase 2.11 已补 [独立执行 worker](rebuild_worker.md)：显式执行 pending/failed 任务，绑定当前管理员凭据与冻结模型身份；HTTP 创建仍不自动执行。

入口 `/api/v1/index-rebuilds`，使用现有 Bearer JWT。禁用账号、失效令牌沿用统一认证规则。所有任务查询和修改以当前用户 ID 为准，管理员也不能通过这些接口越权操作其他用户。响应沿用 `{code, message, data}`。

| 方法与路径 | 行为 |
| --- | --- |
| POST `/index-rebuilds` | 冻结当前就绪文档、管理员 Embedding 配置和切分配置，创建 pending 任务 |
| GET `/index-rebuilds?limit=20&offset=0` | 当前用户分页列表，limit 1–100，offset 非负；按创建时间和 ID 倒序 |
| GET `/index-rebuilds/{id}` | 当前用户任务详情和进度 |
| POST `/index-rebuilds/{id}/cancel` | pending/failed 立即取消；running 仅持久化取消请求，执行器在边界停止 |

创建请求示例：

```json
{"dimension":4096,"chunking":{"chunking_version":"rag4-structured-v1","child_max_tokens":256,"parent_max_tokens":1024}}
```

dimension 必填且为 1–65536 的整数，必须匹配管理员配置模型的实际输出维度；本接口不请求模型验证，执行阶段仍会验证。chunking 可省略。当前仅支持 remote Embedding，endpoint/model/version 从管理员运行配置读取；额外的 user_id、endpoint、api_key 等字段拒绝。创建时必须有文档且全部 ready、源文件可读。创建错误统一返回 400，不暴露本地路径；未知或他人任务返回相同 404。

任务响应包含 id、status、base_revision、attempt、cancel_requested、version_id、error_code/error_document_id、duration_ms、document_count、completed_document_count、模型与切分版本、创建/完成时间。completed_document_count 来自已提交 checkpoint，不是当前文档内的实时百分比。列表返回 items/total/limit/offset，并发更新时总数和页内容不保证同一快照。

新增服务 `list_rebuilds(user_id, *, limit=20, offset=0)` 在 SQL 层按所有者过滤并限制页大小。创建和取消沿用 usage_service 记录事件 `index_rebuild_create` / `index_rebuild_cancel` 的耗时和成败；监控日志不是事务性强审计。不会返回内部 request_json/checkpoints_json、文件路径或凭据。

## 明确边界

**POST 创建只返回 pending，不自动执行、排队或激活。** 当前没有可靠后台队列；执行仍由受控 Python 服务 `run_rebuild(user_id, task_id, api_key=...)` 调用。HTTP 执行、重试、恢复和激活接口尚未开放。本轮不把同步长任务放到请求线程，也不声称任务工作区完成。

不传 idempotency_key 的重复 POST 在配额内仍会产生不同任务；带键请求按 Phase 2.15 契约去重。取消 ready/cancelled 任务为无操作，不会停用当前 active 版本。running 的取消请求不会立即释放额度。分页查询仅读取状态，不修改索引。

无需新迁移或依赖，复用 005 的任务表；默认 RAG3 上传/检索和 active 指针不变。下一切片应明确任务执行调度与凭据绑定后开放执行控制，再提供独立 CAS 激活入口。本阶段不实现 Graph、ResearchAgent 或前端工作区。
