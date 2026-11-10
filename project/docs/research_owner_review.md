# R51：所有者结论审阅与撤下记录

日期：2026-11-08。实际检查发现阅读台已有比较表、引文和原文定位，但没有结论级审阅记录。本轮新增完成产物的**后端审阅闭环**，不调用模型，不修改原机器稿；前端尚未接入这些新接口，现有页面仍展示原机器稿。

## 已实现能力

| 结构/接口 | 行为 |
| --- | --- |
| ClaimReviewEvent | 版本 owner-claim-review-v1、任务/原产物/结论身份、服务器确定的 actor_id、UTC 时间、顺序、任务 revision、前事件及原因 |
| ClaimReviewItem | 原声明、精确引文与页码/来源定位，unreviewed / retained / withdrawn 状态和最后事件 |
| ClaimReviewView | 原机器产物身份、完整事件历史及派生比较稿，确定性 view_id；quality_gate_passed 始终 false |
| GET /api/v1/research-tasks/{id}/review | 只读、no-store、可传 expected_revision；复验冻结来源，不执行/写入任务 |
| POST /api/v1/research-tasks/{id}/claims/{claim_id}/review | 所有者显式保留/撤下/重置，需当前 revision 和原产物身份，追加一个事件 |

来源和术语见根 CONTEXT.md。所有者意见与机器 AssertionReview 是不同概念；它不是独立人工质量验收或自动训练标签。retain 只记录保留意见，不提升原本不足的声明。withdraw 使派生稿对应单元格回到待核验，完整结论和引用仍留在 items 与原稿中。reset 追加新事件、回到未审阅状态，恢复原机器稿可见内容，既不删除旧撤下记录，也不代表人工确认。

当前仅支持 completed、已保存当前 composer-v2 产物的任务，以及原机器稿的 citations。pending/running/paused/failed/cancelled、失败部分稿、未入稿候选不支持审阅，不在本轮隐式扩大范围。没有向新协议 Task/API 默认核验路径注入额外调用。

### 请求示例

先 GET 获取 ClaimReviewView，然后用 **view.source_artifact_id**，不要用撤下后的 view.artifact.artifact_id：

```json
{
  "expected_revision": 25,
  "source_artifact_id": "artifact_原机器稿身份",
  "decision": "withdraw",
  "reason": "该引文未覆盖声明中的训练目标。"
}
```

decision 限 retain/withdraw/reset，reason 必须非空白且最多1000字符。请求不接受 actor_id、时间或其他额外字段，身份与时间由服务器生成。每任务最多100条事件，仍受既有1MB检查点上限；达到上限拒绝新写入，不截断历史。响应是新视图，带最新 task_revision，可据此继续操作。

匿名401、禁用403、非所有者404（管理员也不能越权）、未知结论404、旧 revision/错误原稿/非完成状态409、来源变化/无效输入400。读取与写入均先验证所有者及状态，再初始化向量适配器；所有者、source hash、ChunkSet、版本 manifest 和 Task 快照保持原有检查。

## 不覆盖旧数据与并发保证

原 task.artifact、task.verification、候选声明、步骤、预算和模型/工具用量不变。新增 claim_reviews 默认空且序列化省略，真实 R46 旧检查点重新序列化与原 payload 字节相同。审阅只增加 history 和 revision，原 RAG3 行为不受影响，无数据库迁移。

SQLResearchTaskStore 在 CAS 事务内检查已提交历史：必须恰追加一个事件，历史前缀不变，除 revision/claim_reviews 外的完成任务字段不变。两个存储回归先失败，证实通用检查点写入能清空历史/夹带其他字段，再加此前缀和快照限制；不能只依赖 API 的追加逻辑。未知、重排、伪造或越范围事件也会在加载/保存校验中拒绝。

读视图前后复验来源并检查任务是否变化；写入先完成原稿重建、视图构造和两次来源观测，再进行 revision CAS。观察到的来源漂移或并发修改会拒绝写入。文件和 SQL 不共享事务，不能保证检查结束后文件永远不再变化；历史绑定原稿，下次读取继续复验来源。

事件/视图摘要是完整性标识，不是签名，不防御拥有数据库写权限且能重算全套摘要的管理员。应用接口和存储正常路径保证追加，不将其称为不可伪造的审计系统。日志只含事件/视图 ID 和耗时，不记录原因或引文；原因不注入比较表 Markdown。

## 实际修改文件

- `backend/app/research/claim_reviews.py`：事件、视图、历史验证、追加和保守派生稿。
- `backend/app/research/tasks.py`：有界 claim_reviews 字段与旧空字段省略；`agent.py` 校验审阅历史。
- `backend/app/research/store.py`：保留 CAS，增加历史前缀与完成快照保护。
- `backend/app/research/runtime.py`：read_claim_review / record_claim_review，来源前后检查、无模型配置依赖、耗时日志。
- `backend/app/api/v1/research.py`：两个 JWT 所有者接口及严格请求类型。
- `backend/tests/test_claim_reviews.py`、`test_claim_review_api.py`：领域/持久化/权限/来源/并发测试。
- `backend/evaluation/results/research_owner_review_20261108.json`、检查记录、本页、根 CONTEXT/README/计划/基线及 development_process/research_backend_mvp。

## 真实三论文隔离验证

对 R46 保留输入创建新 SQLite 副本，以开发签名 JWT 经过真实 FastAPI ASGI HTTP 鉴权链操作；不是生产账号登录或用户本人确认。原始 payload 字节兼容检查通过。

首次 GET200，撤下 REALM 引用不覆盖训练目标的结论 POST200：revision25→26，派生稿3条结论/9缺口，原机器稿仍4条/8缺口。迟到重发409、匿名401，重复读取 view_id 相同。存储加固后在新进程重新加载得到相同视图，再 reset/withdraw，两次200，最终 revision28、历史 withdraw/reset/withdraw 三条，派生稿仍3条/9缺口，原机器稿不改。

原任务文件、原 SQLite、所有原向量文件摘要不变，副本 active 状态和已有预算计数不变；模型/Embedding 请求0。开发事件明确注明不是实际用户确认或独立人工评测。原 R46 保守稿及 R49/R50 数据保留。公开证据见 [HTTP/真实来源验证](../backend/evaluation/results/research_owner_review_20261108.json)，本地副本 `backend/data/research-owner-review-20261108/`。

## 测试与边界

新增测试先以404复现缺失接口，领域与权限实现后通过；存储保护两个红灯修复后另行回归。最终相关 **144 passed /248.00s**，其中新增43项实例（领域17、Local/Chroma API26）。此前142项为存储加固前执行，不将它冒充最终源码验证；加固后先47项通过，再运行此144项。未跑后端全量或前端。

```powershell
# E:\RAG4\project\backend，Conda rag4-py3.11
python -m pytest tests/test_claim_review_api.py tests/test_claim_reviews.py tests/test_research_agent.py tests/test_research_run_revision.py tests/test_research_explicit_retry.py tests/test_research_verification_batches.py tests/test_partial_artifact_api.py tests/test_research_runtime.py -o addopts='' -q --tb=short
# 144 passed /248.00s
python -m pytest tests/test_research_preview.py tests/test_research_goal_preview.py -o addopts='' -q --tb=short
# 27 passed /55.82s
```

两组不重叠，共171项相关测试通过；47项加固后快测是其中子集，不重复累加。精确源码摘要和范围见 [检查记录](../backend/evaluation/results/research_owner_review_checks_20261108.json)，JSON/凭据模式/原输入保全及 git diff --check 通过。

无新增依赖、业务 MySQL 操作、索引激活、模型训练或 GitHub 推送，用户 artifacts 和此前修改保留。回退为禁用新审阅入口并保留数据；已写审阅的新任务需要支持 claim_reviews 的解析器，直接回滚旧程序可能无法读取，不能通过删字段或删事件解决。

下一片把这两个接口接入现有阅读台，显示未审阅/保留/撤下、原文定位、原因和历史，提交携带 revision 与原稿身份；失败/冲突重新核对，不能偷偷重发或仍把原机器稿当作撤下后视图。完整前端、失败部分稿审阅、独立人工质量及 R49 新协议语义验收仍未完成。
