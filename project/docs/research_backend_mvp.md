# Phase 1–5：文献比较后端切片

更新：2026-11-10（R54，优先于以下历史记录）。R54工作区任务控制：暂停/继续/取消、明确取消确认、revision与预算响应校验、失败锁定和迟到响应屏障。类型/构建、19组执行浏览器检查、11组真实HTTP合成文献检查及34项后端回归通过；外部模型0，未改后端生产状态机或业务数据。旧历史恢复限制保留，未推送。见 [R54记录](research_task_controls.md)。

更新：2026-11-09（R53）。本页描述真实代码和验收边界，优先于旧轮次的“下一步”记录。[R53审阅导出](research_review_export.md) 已提供当前Markdown、审计JSON、原机器快照和原稿对照；下载前复验，不把撤下结论重新带入当前稿。类型/构建、10导出单测与54浏览器组通过，真实HTTP用合成文献。个人审阅不等于独立人工质量，R49协议仍未验收。

当前已经实现结构化切分、手动版本索引、局部来源图谱、可持久化的文献比较任务、证据核验和比较表生成。**这是单一场景的后端功能闭环，研究质量验收仍未通过。** 默认上传、RAG3 检索和聊天不改为 Agent；已有[研究阅读台](research_reading_workspace.md)和[文献选择/计划预览/确认创建](research_task_creation.md)，完整执行工作区未完成。

## 阶段状态

| 阶段 | 可运行能力 | 尚未完成的验收或范围 |
| --- | --- | --- |
| Phase 0 | RAG3 基线、环境回归；三篇官方论文和 20 题开发集 | AI 标签未人工冻结，不是独立金标准 |
| Phase 1 | ParsedDocument、DocumentChunk、ChunkSet、确定性版本身份、父子片、来源/页码、兼容开关 | PDF/DOCX 版式抽取；检索质量仍有缺口 |
| Phase 2 | 原手动准备、构建、验证、激活、回滚、恢复和幂等；新增只读快照入口 | 无可靠后台调度或生产验收；本轮不继续扩建索引平台 |
| Phase 3 | GraphStore、MemoryGraphStore、实体/提及/来源边、最多两跳探索、HybridEvidenceEngine | 未证明真实图谱收益；无 Neo4j、全局实体消歧或社区发现 |
| Phase 4 | 固定 3–5 篇比较计划、任务/步骤、受控工具、SQL checkpoint、暂停/恢复/取消、HTTP/CLI | 非通用自主规划；无队列、无人值守恢复、全局任务配额 |
| Phase 5 | 原文定位、数字门禁、模型支持核验、可追溯比较表、缺口与冲突、结构化引用来源 | 机器核验仍会错；人工支持率 ≥90% 和 4/4 缺口题未验收 |
| Phase 6/7 | 已有选择→预览→创建→执行/读取/受限恢复，真实三论文新副本已完成，机器4支持/8缺口，Agent审阅稿3条/9缺口 | paused/running/旧控制历史、真实语义/人工验收、业务部署及训练仍缺 |

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

当前入口以 [R53记录](research_review_export.md) 为准：completed审阅和可追溯导出已可用，原机器稿保留。下一片收口现有暂停/继续/取消与状态反馈，不追加模型设施。失败部分稿审阅/Task联合断言报告/独立人工质量未完成，R46保守稿保留，R47仅引文不晋级。图谱收益未证明，不扩建Neo4j/队列。Phase2接口可复用，前置为ready来源、成功jobs/builds、verified manifest和迁移核对。


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


## 2026-10-20：可恢复逐文档核验与窗口策略

新增 plan_version=research-comparison-v2，每篇 verify_document 至多四条并保存 VerificationBatch，merge_verification 在全部文档成功后合并；默认仍 v1。请求 budget 省略时按计划选择有限预算，自定义不足则拒绝。新增 context_policy=local-window-v3 和 candidate_policy=lexical-fusion-v2，均须显式选择，默认策略保持。EvidenceItem 保存窗口原父片偏移，引用与持久化按真实文字计数和映射。

真实四次请求两成功/两超时，成功两份报告保留但没有完整产物；q09 开发锚点补齐，q12 未改善。工程恢复通过不等于模型/网络超时消失或语义质量通过。详见 [实现与实验记录](research_batching_context.md)。

最终全量：在 `project/backend` 执行 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`，**483 passed / 749.89s**，无失败、无跳过。本轮新增17项覆盖；编译和差异空白检查、公开JSON与凭据模式检查通过。源码摘要见 `project/backend/evaluation/results/research_batching_tests_20261020.json`。该结果不替代人工语义验收。

## R26：来源角色提示与核验续接

创建 API 新增可选 `candidate_policy="source-role-v3"`，仅对缺失索引文字的同篇候选进行来源角色排序；默认 vector-v1、既有 lexical-fusion-v2 保留。配置持久化在 ResearchTask，继续使用只读冻结语料和现有 EvidenceBundle 引用校验。

离线六路对照补齐 q12 的 DPR 方法证据，配合 local-window-v3 的开发锚点覆盖为 53.13%、完整 8/16；未重新生成全部答案。新预算副本完成三份核验报告，保留原成功批次与全部失败，生成 4 条机器支持/8 缺口的部分表；有效方法误拒和局限分项误判仍存。续接工具、谱系与预算接口、命令和限制见 [R26 记录](research_continuation.md)。无新增依赖或迁移。

## R28：按结论类别核验候选（2026-10-31）

创建任务可显式选择 verification_protocol=facet-handles-v5，历史和默认仍为 numeric-model-v2。服务器通过 FacetRequirements/facet-scope-v1 为四个 facet 选择条件检查目标，模型操作 verify_facets，报告 exact-facet-handles-v5。仍需全部三项通过及精确来源编号校验；逐文档批次、合并、产物复查和历史身份已接入。v4 来源编号本身保持稳定。

本轮用四次上限的原/新协议对照分别检验真实误判和合成迁移案例，不把契约测试通过当作语义准确。实现、预算、结果及限制见 [R28 记录](research_facet_verification.md)。无新增依赖、业务迁移、索引激活或前端实现。


R28 最终全量 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`：**509 passed /501.85s**，无失败/跳过。真实v5读取超时，合成原/新均4/4；不声明真实修复或默认切换，详见上述R28记录。


## R29：逐条诊断入口

新增evaluate_single_claims.py及原复核脚本的显式输出预算与前后来源守卫。固定四次真实请求，单条v5两条正反例符合预期，v4为1/2。生产模块未改，不在verify_document内部隐式循环模型；先做独立样本与预算验证。相关32项通过，历史全量509项及摘要保留，详见 [R29记录](research_single_verification.md)。


## R30：诊断Claim及语义红灯

复核CLI新增与claim-id互斥的claim-file，文件仍须通过任务范围、精确引用和确定性身份验证。跨论文六例v5实测5/6，FiD背景方法误归属阻塞切换；离线score-report对该账本返回2，不能把请求成功算作质量通过。相关45项通过，生产研究代码及默认不变，详见 [R30记录](research_cross_paper_verification.md)。


## R31：可选核验前文窗口

创建API新增verification_context_policy（默认cited-chunk-v1），preceding-children-v1只与facet-handles-v5组合。ContextPart/VerificationContext持久化规范chunk引用和确定性窗口身份；最多两前序子片、6000字符，原support_ids目录不扩大，批次和成品复查来源。模型调用次数不增加，旧默认及历史身份保留。全量549 passed /265.06s；真实归属负例改善，正例ConnectTimeout未判断，不声明无退化。字段、预算、回滚与下一入口见 [R31记录](research_verification_context.md)。


## R32：窗口复测与试点CLI

preceding-children-v1在同六个冻结DPR/FiD案例上取得6/6开发预期符合，生产实现不改。evaluate_research_comparison.py新增显式计划/检索/核验/上下文设置和有限输出预算，v2预算沿用runtime准入，旧默认保留；无效组合提前拒绝。相关44项通过，历史全量549项记录保留；本轮未执行新端到端任务。运行命令、预算与限制见 [R32记录](research_context_suite.md)。


## R33：新任务端到端、有界恢复与来源复核（2026-11-01）

保留R28–R32及用户artifacts。按R32入口对DPR/FiD/REALM重新查询、抽取与逐篇核验，复用经绑定校验的旧文档向量。首轮6次Completion的最后REALM核验ReadTimeout，DPR/FiD检查点保留；不把失败记录改成成功。新增`resume_research_comparison.py`，仅在新SQLite副本对末篇网络失败显式恢复一次，随后合并/产物；拒绝语义错误、付费步骤未完成、预算不足、缺报告或凭据重定向。

恢复成功；累计12/13步、7/8次Completion（6成功1超时），3批查询Embedding，无新增文档Embedding。已报Token合计36863，失败请求用量与费用未知。成功报告、原JSON和向量不变，Claim/引用/上下文/正式Artifact离线重建一致。执行后追加提供商绑定检查，原执行脚本摘要归档，最终测试源码摘要另存，无额外付费复跑。

机器产物partial，12条中6条支持6缺口。Agent逐条来源复核发现REALM方法引文未支持所述训练目标，结果38.5/52.0遗漏CC-News条件；只从另存展示稿撤回2条，保留原机器判断和Artifact。展示稿4条/8待确认，未经人工验收。另记DPR数据集/FiD结果疑似误拒、DPR结果百分点问题、错误引用与背景归属；质量门槛仍false，不能将六例开发测试通过外推到新任务质量。

最终相关24 passed /3.62s，新增11项，无失败/跳过；生产模块摘要与R31一致，未重复549项历史全量。无依赖、业务库访问、默认策略切换、前端、Neo4j、训练或GitHub推送。完整命令、实际文件、4份公开结果和下一切片见 [R33记录](research_context_end_to_end.md)。下一步修复本次声明引用匹配及条件核验，先验证语义收益，不追加索引设施。


## R34：固定声明配对核验、机械拒绝分离与候选停止（2026-11-01）

先检查git，保留用户artifacts；R28–R33已推送4f4fff8。固定R33两条REALM错误接受及DPR/FiD两个疑似误拒，离线真实原报告0/4复现。新增显式operator候选版本、提示词摘要和有界成对诊断CLI，旧默认及序列化保留，不增加核验协议或隐式请求。

8次真实请求全部成功，27022已报Token，无Embedding/重新抽取/激活。新旧最终均2/4，旧版其中一条因复制无效证据ID被机械拒绝，不能称为识别条件遗漏；离线评分强化后排除此项，旧1/4、新2/4。候选改善本次FiD定性结果误拒，但仍接受两个REALM负例，不晋级；原Artifact/引文/展示稿不变。执行脚本摘要已归档，评分修改后未增加调用。

完整577 passed /233.94s；此后增加离线机械评分保护用例，最终相关33 passed /2.35s，本轮新增8项。明确完整收集时点，未把578项当作全量已运行。无依赖、业务库访问、默认切换、前端、Neo4j、正式训练或推送。文件、接口、命令、原始账本与限制见 [R34记录](research_claim_audit.md)。下一切片在固定来源/旧提示词上最多4请求单变量检查更强核验模型；不继续叠加提示词或索引设施，抽取引用匹配与人工验收仍待完成。


## R35：模型单变量诊断与下一步收敛（2026-11-01）

先检查git，保留R34及用户artifacts。实际查询硅基流动模型清单200/98个条目，选择已列出的Qwen2.5-72B；扩展既有诊断CLI为四请求model-only模式，严格核对控制源码/清单、原始声明/任务、旧模型和提示词摘要，其他设置不改。凭据仍仅在内存/进程环境。

四次请求3成功1ConnectTimeout，10637已报Token，无重试/Embedding/抽取/激活。72B仍错误接受两个REALM负例，DPR正例支持，FiD正例未判断；不晋级、不推断整体准确率或全部大模型无效。原任务、向量、Artifact和展示稿保留。公开结果明确执行失败与开发预期不同，不把超时当拒绝或质量通过。

最终相关55 passed /7.89s，新增11项；生产模块摘要与R34一致，未重复其577项历史全量。无依赖、业务库访问、生产切换、前端、训练或推送。实际文件、接口、命令和限制见 [R35记录](research_model_audit.md)。下一切片停止盲换模型/提示词，先实现来源绑定的实验行/必要条件表示与确定性检查，覆盖真实CC-News遗漏和完整条件正例；语义断言、抽取引用匹配和人工验收仍待完成。


## R36：来源绑定实验条件与确定性门禁（2026-11-01）

先检查git，保留R34/R35及用户artifacts。应用domain-modeling与codebase-design，新增根词汇表，定义ConditionAssignment/ExperimentRow/ResultConditionAudit及单一无副作用审计接口。只支持保守的竖排数值行与显式命名赋值；所有字段绑定原引用字符区间，版本参与身份，歧义unknown，不以数字相同证明支持。

新增显式result_condition_policy，接入CompletionSpec/API冻结、核验前拦截、报告/批次持久化与合并、来源重建和产物发布门禁；禁止删除审计或降级策略绕过。默认序列化省略新字段，真实R33旧Artifact身份相等。真实隔离SQLite回放中REALM缺CC-News在调用模型前被阻止，补条件对照只获条件passed，不冒充语义验证；原任务、向量和正式产物不改，0付费模型/Embedding请求。

新增31项回归。完整619 passed /521.81s，其收集/导入早于最终标点/批次范围加固；最终相关42 passed /5.69s覆盖最终代码，之前含API/local+Chroma相关62 passed /56.64s。最终收集620，未称已全量执行620。定位修复句末数值识别；CRLF去尾空白及无效请求400按真实旧约定修正测试，未改旧接口。公开回放和测试摘要已保存。

无依赖、迁移、业务库访问、默认切换、前端、训练或推送。支持布局/语义范围有限；旧程序不能保证解析新策略任务，回滚必须保留其导出数据，不删除或改写报告。文件、接口、命令、结果与限制见 [R36记录](research_result_conditions.md)。下一切片以原有限预算运行新隔离任务，检查误拦、unknown和部分产物；方法语义及人工质量验收仍待完成。


## R37：真实新任务、可选关系修复与失败任务部分稿（2026-11-04）

先检查git，保留R34–R36和用户artifacts。显式新条件策略、原13工具步/8次Completion预算，三篇新查询成功。首次DPR抽取ReadTimeout，预先选定恢复一次后返回成功却因relations.1.predicate非法拒绝整份结果。新增同路径回归3红/3绿，再将可选关系逐条校验，保留合法声明；必要声明结构、容器和数量界限保持严格，安全诊断不含原始模型文本。

在新SQLite副本显式schema-repair，准入仅限该首篇可选谓词错误；原检索不重跑，最多余下6次Completion/8步，不自动重试。三篇抽取和DPR/FiD报告成功，REALM返回后发生通用ValueError，累计11/13步、8/8次请求，任务保持failed。7次HTTP返回成功不能等同7次工具成功；已报35419+498=35917 Token，失败用量与费用未知。

预算用尽后零模型请求导出部分稿，成功报告原样保留，其余全部不足。DPR/FiD方法2条来源与先前逐条原文检查一致，10个缺口；Realm结果的CC-News遗漏只在离线导出中形成missing审计，不能冒充在线Realm报告成功。源任务不改、不附完成Artifact。新增摘要区分未审计/未给verdict，合并不重复计数。有效受控wire探针可过来源/审计/批次检查，但原失败响应未留存，ValueError准确根因仍未知，不把探针当语义验证。

完整641 passed /524.75s；其后新增部分导出CLI/10测试，最终相关31 passed /5.17s，本轮共新增31项。最终收集651，未称全部已跑。修复独立测试缺少workflow fixture导入后无失败/跳过。生产代码未在完整回归后改动。文件、命令、源码摘要、原失败和部分稿见 [R37记录](research_condition_end_to_end.md)。无依赖、迁移、业务库访问、默认策略切换、前端、训练或推送。下一步为返回边界增加安全错误分类与身份诊断，先定位再有限验证；Phase 1–5质量仍未通过。


## R38：返回错误安全分类与一次独立复测（2026-11-04）

保留R34–R37及用户artifacts。先构造未知/重复ID和批次约束回归，旧代码19红/1绿；新增ResponseContractError、身份计数与batch分阶段诊断，错误仅白名单code/count，不含模型原文或未知ID；未分类ValueError明确unknown，不猜测原因。ToolResult/SQL持久化保留，缺失判断仍insufficient、坏身份仍拒绝。修正scope文案兼容后最终99 passed /10.43s，新增27项，历史641项未重跑。

诊断机制验证后独立1请求复测REALM全四条并增加batch范围验证选项，源任务预算8/failed不改。请求ConnectTimeout /5548ms未获得响应，不能认定历史ValueError复现或修复；usage未返回，费用未知。另2次只读models GET均200，未发现代理配置，不据此修改代理/网络策略，也不推断chat稳定。零Embedding/抽取/新产物，原部分稿身份不变。

公开诊断/探测和测试摘要已保存，最终收集678项未声称全量执行。文件、命令、精确限制见 [R38记录](research_response_diagnostics.md)。下一交付把已保留的失败部分稿接入授权只读查看路径，支持来源核查；诊断随正常有预算执行捕获，不无限追加模型请求。未迁移业务库、切换默认、开发前端、训练或推送，质量验收仍false。


## R39：失败部分稿授权只读接口（2026-11-04）

保留R34–R38及用户artifacts。把partial_verification从CLI移入app/research/partial共享模块，新增不可变PartialArtifactView及确定性view_id；API/CLI用同一生成逻辑，原R37 Artifact身份和Markdown相等。新增GET /research-tasks/{id}/partial-artifact及可选expected_revision：JWT本人检查先于存储初始化，非failed或状态/版本冲突409；源文档/索引/ChunkSet及Task快照前后复验，no-store，日志含view_id/elapsed_ms，不依赖模型配置。

16项Local/Chroma新增回归验证本人、匿名/禁用/他人（管理员也无越权）、状态/版本、来源变化/删除、检查点损坏、并发观测变化与只读行为。首条测试404红灯后实现；最终102 passed /115.66s，未重复历史641全量，当前694项不称全量已跑。隔离R37真实三论文数据使用签名测试JWT走HTTP，200/401/404/409符合，Task/向量/active不改，模型/Embedding0；API、CLI和历史部分稿两条方法/10缺口一致，非生产登录或MySQL迁移验收。

实际接口、类型、命令、源码摘要与限制见 [R39记录](research_partial_artifact_api.md)。无依赖、迁移、业务库访问、默认策略切换、前端、训练或推送。下一切片实现自己的任务→状态/步骤→失败部分稿→引用/缺口的最小前端读取路径；先支持既有数据、不调用模型，不扩建索引或全站改版。质量、R37精确错误和方法语义仍待完成。
