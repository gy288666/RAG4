# Phase 1–5：文献比较后端切片

更新：2026-10-13。本页描述真实代码和验收边界，优先于旧轮次的“下一步”记录。

当前已经实现结构化切分、手动版本索引、局部来源图谱、可持久化的文献比较任务、证据核验和比较表生成。**这是单一场景的后端功能闭环，研究质量验收仍未通过。** 默认上传、RAG3 检索和聊天不改为 Agent；没有研究工作区前端。

## 阶段状态

| 阶段 | 可运行能力 | 尚未完成的验收或范围 |
| --- | --- | --- |
| Phase 0 | RAG3 基线、环境回归；三篇官方论文和 20 题开发集 | AI 标签未人工冻结，不是独立金标准 |
| Phase 1 | ParsedDocument、DocumentChunk、ChunkSet、确定性版本身份、父子片、来源/页码、兼容开关 | PDF/DOCX 版式抽取；检索质量仍有缺口 |
| Phase 2 | 原手动准备、构建、验证、激活、回滚、恢复和幂等；新增只读快照入口 | 无可靠后台调度或生产验收；本轮不继续扩建索引平台 |
| Phase 3 | GraphStore、MemoryGraphStore、实体/提及/来源边、最多两跳探索、HybridEvidenceEngine | 未证明真实图谱收益；无 Neo4j、全局实体消歧或社区发现 |
| Phase 4 | 固定 3–5 篇比较计划、任务/步骤、受控工具、SQL checkpoint、暂停/恢复/取消、HTTP/CLI | 非通用自主规划；无队列、无人值守恢复、全局任务配额 |
| Phase 5 | 原文定位、数字门禁、模型支持核验、可追溯比较表、缺口与冲突、结构化引用来源 | 机器核验仍会错；人工支持率 ≥90% 和 4/4 缺口题未验收 |
| Phase 6/7 | 未实现新的工作区，未执行正式训练 | 先解决比较任务质量，再扩展界面/训练 |

## 接口与领域模型

`app/chunking` 的既有 Phase 1 模型和 `split_blocks` 保持兼容。本轮新增 `app/research`，只接受用户显式选定的文档及保留索引版本。

- `EvidenceCorpus`：所有者、完整 ChunkSet 与来源版本形成隔离身份；校验文档范围和证据来源。
- `RetrievalOptions`、`VectorHit`、`EvidenceItem`、`EvidenceBundle`：有界检索、匹配子片、来源通道、警告、耗时和确定性身份。`evidence-floor-v2` 先选子片，再在预算内升级父片，不能为展开父片丢掉已选证据。
- `Citation`：切片 ID、原始字符起止和完全一致的原文。排版等价匹配只允许 NFKC/空白变化，唯一匹配后映射回原始区间；歧义或改写拒绝。
- `GraphStore`：`replace_document/retrieve/remove_document/explore`；`MemoryGraphStore` 按用户、语料版本和文档隔离，先全量校验再原子替换。`GraphRelation/GraphEntity/EntityMention/GraphPath/GraphView` 保留每跳来源。两跳邻接不等于因果证明，字面来源校验不等于关系语义已经核实。
- `ResearchTask/ResearchStep/SourceBinding/TaskBudget/BundleRef`：冻结文件 SHA、chunk set、索引、模型配置、计划和预算；记录状态、修订号、步骤结果、错误、耗时、用量和证据引用。
- `ResearchToolRegistry/ToolResult/ToolContext`：固定注册 `search_evidence`、`compare_evidence`、`verify_evidence`、`compose_artifact`。参数严格校验；无任意命令或网络工具。
- `ResearchAgent.step`：每次执行一个工具；执行前用 SQL CAS 领取并预留预算，执行后再核对来源和修订号。外部调用不占用数据库事务；暂停/取消后迟到结果不能发布。控制操作不依赖模型或向量服务可用。
- `SQLResearchTaskStore`：创建、所有者查询、列表和 CAS checkpoint；JSON payload 带 SHA 校验。错误只记录代码和类型，不保存凭据或异常原文。
- `CompletionSpec/JsonResearchModel`：显式模型、endpoint、版本、超时、调用上限；严格 JSON、完整输出、无隐式重试。调用方提供 HTTP client 时保留其所有权，同时落实每次调用的超时。
- `Claim/QuotedClaim/VerificationResult/EvidenceVerifier`：先核对真实来源和数字，再让模型判断支持性。`exact-source-numeric-and-model-v2` 不接受引用没有的字面数值；不做单位换算、四舍五入或推导算术。
- `ArtifactComposer/ComparisonArtifact/ArtifactSource`：仅展示已通过当前核验的事实；区分缺失、不确定和冲突；引用保留 chunk set、章节、原文区间以及引用实际所在页。`comparison-table-v2` 明确 `partial/ready_for_review`，后者也不是人工批准。
- `load_version_snapshot`：Phase 2 新增公开只读入口，核对 manifest、当前文档集合和完整向量读回；不会激活、重建或改变旧索引。

旧 verifier/composer v1 可读取以保留历史身份，但新产物不能直接信任旧 v1 核验，必须重新通过 v2。没有 selector_version 的旧证据包不能重新水合执行。

## 数据库与操作入口

新增 `project/docs/migrations/008_research_tasks.sql`，仅创建 `research_tasks`，包含用户、状态、revision、LONGTEXT payload、摘要和时间。没有删表或改旧索引表。本轮只在隔离 SQLite 和 MySQL 3307 新建测试库验证；**未迁移业务库**。已有 Phase 2 的结构/恢复门禁不包含 008，正式启用前须单独检查迁移、备份、表权限及任务数据恢复。

登录用户调用 `/api/v1/research-tasks`：

| 方法/路径 | 行为 |
| --- | --- |
| POST 空路径 | `index_version_id/document_ids/goal/budget` 创建；可选 `extraction_protocol/response_format` 冻结于任务；不自动执行 |
| GET 空路径 | 分页查询自己的任务 |
| GET `/{task_id}` | 读取计划、步骤、证据引用、核验和产物 |
| POST `/{task_id}/run` | 执行一个工具并保存 checkpoint |
| POST `/{task_id}/control` | `action=pause/resume/cancel`，必须提供 `expected_revision` |

默认预算 12 个工具调用、8 个模型调用、每篇上下文 6000 字符。三篇计划为 8 步，五篇为 12 步；模型调用预留计入失败尝试，显式恢复也不能绕过预算。当前只支持单操作者串行执行；进程中断后的 running 步骤由操作者确认旧进程停止，再暂停、恢复，不会自动重复外部调用。

后台入口（在 backend，先显式设置目标 DATABASE_URL 和已核对的管理员运行配置）：

```powershell
python scripts/run_research_task.py --user-id 1 --task-id <existing-task-id> --steps 1
```

这里的数字只是命令示例；真实任务必须属于该用户。创建要求 3–5 篇 ready 文档、成功切分任务、未改变的原文件和可读回的保留索引。研究可使用未激活的已验证版本；创建、执行和产物发布都不改变 active 指针。来源、模型绑定或快照失配时失败封闭。

## 修改文件索引

本轮新增：

- `project/backend/app/research/{__init__,evidence,graph,artifacts,model,tasks,tools,agent,store,runtime}.py`
- `project/backend/app/models/research_task.py`、`app/api/v1/research.py`
- `project/backend/scripts/{run_research_task,evaluate_research_comparison,evaluate_bounded_evidence,replay_research_verification}.py`
- `project/backend/tests/test_research_{evidence,agent,runtime}.py`
- `project/docs/migrations/008_research_tasks.sql`
- 本页、[真实运行报告](research_comparison_report.md)，以及 `backend/evaluation/results` 下 20261013 结果文件。

改动：API/model 注册、`index_version_service.py` 的只读入口、测试清理 fixture；此前未提交的 `evaluate_literature.py` 增加可选 HTTP client 与逐调用超时，原默认路径保留。同步根计划/基线/README、开发过程、索引验收和评测说明。此前文献试点文件、用户的其他修改及 `artifacts/` 保留；没有新增依赖、训练或前端修改。

## 验证与回滚

在 `C:\Users\gy\.conda\envs\rag4-py3.11`，backend 下执行：

```powershell
python -m pytest -o addopts='' -q --tb=short --show-capture=no
python -m pytest tests/test_literature_pilot.py tests/test_research_evidence.py tests/test_research_agent.py tests/test_research_runtime.py -o addopts='' -q --tb=short --show-capture=no
```

最终全量 **440 passed / 470.62s**，无失败/跳过；详见 [开发记录 R19](development_process.md)。测试覆盖用户隔离、来源伪造、图谱故障降级、父片预算不丢子片、两跳来源、数字错配、引用排版/实际页码、旧身份读取、严格工具协议、失败预算、CAS 迟到结果、暂停取消、SQLite/API 及 Local/Chroma 快照。

MySQL 8.4.9/3307 隔离库验证新增 DDL、中文 payload 往返和 stale-revision CAS 拒绝通过；不代表全部真实模型流程已在 MySQL 或生产验收。测试库保留，没有 DROP。真实运行失败、超时与旧错误产物也保留于忽略目录，公开结果不包含 key、密码、完整 PDF 或向量。

回滚操作是停止研究 worker/研究入口，继续原 RAG3；已有任务和研究表保留以便核对。若曾显式激活索引，仍使用已有版本 rollback/deactivate；研究流程本身不激活索引。禁止以删数据库或覆盖旧产物作为回滚。

## 下一验收切片

先核对 FiD 引用丢弃与 REALM 严格响应协议失败，补来源上下文和有界质量回归；用现有 20 题区分检索定位、陈述支持和缺口识别，人工审阅比较表。q09/q12 未改善，图谱收益尚未证明，不扩建 Neo4j/队列。Phase 2 接口已可供后续任务直接复用；前置条件为完整 ready 来源、成功 jobs/builds、verified manifest 和迁移核对，不需要再增加索引平台层。


## R20 引用修复补充

新增 source-handles-v2：新 HTTP 研究任务默认使用来源区间编号，历史 CompletionSpec 缺省仍为 literal-quote-v1。JSON 输出由 response_format 显式选择（HTTP 默认 text，试点明确 json_object）；不做静默兼容降级。引用目录连续、不重叠、不扩大已选上下文；接收最多八条候选，输出仍最多四个 facet，并记录重复/超量诊断。新增 protocol.py 和 test_research_citations.py；诊断脚本仅用于离线 AI 锚点，不作为生产检索策略。

真实 checkpoint 有界续接成功；在线 6/12 机器支持，二次 AI 来源审阅又撤下两条 REALM，最终部分表 4 条、8 缺口。这不是人工审核或生产语义核验修复。q09/q12 仍未改善。详见 [引用修复记录](research_citation_fix.md) 与 [当前部分表](../backend/evaluation/results/citation_comparison_20261013.md)。本页前面的 R19 数字/实验为历史记录，最新全量 440 passed / 470.62s。


## 2026-10-14：显式逐项核验候选

创建研究任务时可传 `verification_protocol: "source-checks-v3"`，冻结于 CompletionSpec；缺省和历史任务均为 `numeric-model-v2`。新报告 exact-source-checks-v3 保存每条结论的 attribution、conditions、entailment，每项有 status/reason/support_quote，所有支持项须通过精确原文检查；ArtifactComposer 重查分项，历史产物身份保持兼容。

新协议尚未达到默认切换门槛：真实诊断六条全部拒绝，包含引文抄写误拒与残余语义误判；相关协议/任务/存储回归 46 项通过不代表语义质量通过。可用独立回放脚本保存新结果，不修改原任务。详见 [逐项核验记录](research_source_checks.md) 和 [开发记录 R22](development_process.md)。

最终全量回归：在 `project/backend` 执行 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`，**451 passed / 494.48s**，无失败、无跳过。编译检查与差异空白检查通过。测试通过不代表上述真实语义质量门槛通过。


## 2026-10-14：来源编号核验候选

任务创建可显式选择 verification_protocol=source-handles-v4。模型返回三项检查的 support_ids，服务端在结论自己的引用目录中还原并保存 support_quote；成品阶段重验编号/文本映射。未知/重复/跨结论编号与空选择不能发布支持结论。既有 v2/v3 保留兼容，默认仍为 v2。

六条诊断子集不再发生引文抄写失败，但只一条获机器支持，完整十二条请求超时；q09/q12 的显式文档范围过滤也没有改善锚点覆盖。故不切换默认，不宣称完成语义质量或检索验收。详见 [来源编号与范围对照](research_verification_handles.md)。

最终全量：在 `project/backend` 执行 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`，**466 passed / 521.87s**，无失败或跳过。本轮新增 15 项回归覆盖（含 API 参数化新增两项）。编译、差异空白、公开结果 JSON 和凭据模式检查通过；语义质量门槛仍未通过。
