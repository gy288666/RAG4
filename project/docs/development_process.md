# RAG4 开发过程记录

**当前执行安排（2026-10-13，R20）**：Phase 1/2 维护基线保留，Phase 3–5 文献比较后端已有来源引用编号、安全响应诊断和 checkpoint 受限续接。最终全量 440 项通过；在线产物仍需 AI 二次来源复核并人工审阅，q09/q12 未改善。详见 R20 和 [引用修复记录](research_citation_fix.md)。研究工作区、正式训练与生产部署未开展；2026-10-14 交付批次见本页 R21，提交状态以 Git 历史为准。

## R18. 真实文献检索切片（2026-10-12）

在保留上轮 8 份计划文档修改和独立截图的前提下，执行新范围的首轮验证。使用 research 技能并行核对三篇原始论文、许可和候选事实，新增来源注记；公开文献及标注不涉及用户私有文档。原业务代码、数据库配置和 active 指针未改变。

新增 `app/evaluation/literature.py` 的试点数据类型、PDF 指纹和证据原文区间校验、两切分器候选适配、向量校验及锚点覆盖指标；`scripts/evaluate_literature.py` 使用现有远程 Adapter 与 LocalVectorStore 在全新目录执行。输出失败阶段、版本、源码摘要、候选位置/分数、调用用量与耗时；拒绝覆盖已有实验。20 题为 AI 草稿，匹配机器校验不能代替人工语义支持审核。

初次发现 Adapter 未从 `app.chunking` 顶层导出，改为显式导入其模块；标注候选 `independently`、`770M parameters` 在声明页不唯一，改为较长锚点后 27 个证据区间全部校验成功。不是放宽校验以接受歧义。三篇 PDF 共 30 页，RAG3/RAG4 分别 254/272 子片，同用 600 字符预算；无额外 PDF 标题抽取或父片在线展开。

真实 Qwen3-Embedding-8B 首轮完成 RAG3 后在 RAG4 首批遇到 ConnectError；保留 60587ms 的 failed 报告。第二轮同参数执行、剩余调用预算 61，125176ms succeeded。两轮共 54 次调用，1 次失败，服务返回 117219 total_tokens，货币费用未知。@10 均值 33.33%→41.67%，完整题数均 5/16，q01 锚点退化；四道证据不足题未评测拒答，不作为通过。

离线诊断利用原排名与现有 ChunkSet 父片，不新增模型调用；q01/q09 锚点得到补全，完整题 7/16，但 q01 上下文从 4467 增至 12709 字符，不能宣称等预算质量提升，也没有接入在线路径。下一切片的投入依据因此是父片上下文边界和跨论文覆盖，尚无依据启动 Neo4j 或训练。

原发布基线先实际全量 378 passed / 465.54s；新增试点单测 19 passed / 3.79s，最终与引擎及旧服务相关回归 108 passed / 8.03s。详细记录、可复现输入和结果见 [试点报告](literature_pilot_report.md)。没有运行新增后 397 项全量；人工复核和真实文献 SQL 发布闭环未完成，本轮工作区尚未提交或推送。

## R17. 按研究价值收紧开发范围（2026-10-12）

用户要求修正索引基础设施持续扩展、延后研究价值验证的问题。核对代码和计划后，发现旧计划仍默认把并发/租约、Neo4j 和训练列为后续依赖；这会继续增加首个可用研究任务的成本。本轮调整计划与记录，不新增业务功能，也不把规划中的 Graph、Agent 或评测集标成完成。

近期场景收敛为“比较 3–5 篇真实论文，给出方法/数据集/结果/局限、逐项引用及知识缺口”。先冻结 20 题开发回归集与真实文献基线，再用同一场景逐步验收 MemoryGraphStore/混合证据、研究任务、EvidenceVerifier/比较表及最小界面。全量回归和隔离手动重建是 Phase 2 的有限收尾；自动化索引平台、四类任务和全站改版不再作为该 MVP 的默认前置。

受控验证期明确由单操作者串行运行 worker，恢复前确认旧进程停止，不把实验约束写成代码已具备并发保护。多 worker/无人值守启用前、或实测容量/时延/任务阻塞出现时，才重开有界基础设施切片。每个新增基础设施任务须记录阻塞验收项、证据、最小范围与退出条件。

评测区分来源定位与引用真正支持陈述，记录逐题原始结果、失败、耗时与用量；20 题只是开发回归，正式微调另建按文档/主题隔离的训练与测试数据。训练按排序/召回/生成的实际瓶颈触发，保留未微调基线。既有 experiment 脚本会改全局配置和删除实验账号文档，不能直接作为业务环境的新评测执行器。

同步修正当前发布状态、训练文档中过时的重建 API 描述和 Phase 1 父片持久化的历史边界。该轮为文档变更：检查本地链接、代码围栏和差异格式，不重复运行后端测试；378 项全量与真实文献质量结果仍待下一切片实际产生。当前计划调整尚未提交或推送。

Phase 2.16 最新相关验证（2026-10-10）：重建组 **73 passed / 234.58s**，补充配额及原认证/文档组 **39 passed / 89.16s**，覆盖 100 个不同用例；MySQL 3307 合成并发 **passed / 8843ms**。收集 378 项，未重跑全量，未迁移业务库或发布。详情见本页 R16 与基线记录。

Phase 2.15 最新相关验证：幂等创建、恢复、批量任务、管理 API、结构门禁共 **61 passed / 106.10s**。语法/差异检查通过；未重跑全量，以下 349 passed 为上一阶段记录。

Phase 2.14 最新完整验证：后端 **349 passed / 618.48s**，专项损坏回归 **14 passed / 52.27s**，MySQL 组合恢复 **29979ms passed**；语法和差异检查通过。下文旧轮次数字作为历史保留。当前验收边界见 [Phase 2 验收索引](phase2_acceptance.md)。

Phase 2.12 最新相关回归：版本 API 与原版本服务 **37 passed / 122.75s**，compileall 和 git diff --check 通过；本轮未重跑全量。

最新验证：2026-09-22 Phase 2.9 后端全量 **282 passed / 421.93s**，MySQL/上传文件/Chroma 组合演练 **32882ms passed**。compileall 和 git diff --check 通过；历史各轮测试记录保留原始结果。

Phase 2.10 后续相关验证：新 API/重建服务 **29 passed / 89.41s**，原认证/文档 API **22 passed / 42.61s**；本轮未重跑全量。compileall 和 git diff --check 通过。

> 版本：v2.18　　更新日期：2026-10-12
>
> Phase 2 开发起点：`main` / `511cbbd`；2.1–2.16 已提交并推送为 `476127b`。Phase 1 验证基准为 `4b0e1dd`。
>
> 范围：RAG3 基线、模型基础设施、Phase 1、Phase 2.1–2.16，以及研究任务优先的计划修订。后半部分保留原 RAG3 开发回顾与分阶段历史记录。

## R16. Phase 2.16：用户创建配额（2026-10-10）

先核对工作区、任务状态机、幂等创建及恢复事务，保留已有 Phase 2 修改。创建幂等键不能防止不同键或无键请求积累任务，因此本次只实现逻辑任务准入。实现假设：pending/running/failed 均占额度，默认每用户 8 个；ready/cancelled 保留数据但释放额度；失败可显式取消，不自动删除 checkpoint。该假设不代表模型物理并发限制。

新增启动配置和 RebuildQuotaExceeded，API 超限映射 429；数据库用户行无操作更新取得锁后，复查幂等键、统计数量并插入任务/映射。避免用进程内锁或先计数后无锁插入，兼容 SQLite 与 MySQL；避免 ORM 自动修改账号 updated_at。恢复先取得相同锁再交换原任务和续接任务，不新增额度，调低上限也不阻止既有恢复。

先补 12 项测试，因配置未实现而全部在 setup 失败；实现后相关 73 项通过。随后加入恢复与创建竞争、降低上限、映射回滚及配置边界测试，配额用例最终为 17 项，和原认证/文档 22 项合计 39 项通过。两个运行合计覆盖 100 个不同用例，不把测试收集或历史全量写成当前全量通过。实际命令见 [基线记录](../../RAG4_BASELINE.md)。

另在新建合成库 `rag4_restore_1c3d37503d42_source` 验证真实 MySQL 8.4.9/3307，执行增量 002–007 并通过结构门禁。四线程不同键在配额 2 下只产生两个任务及两条映射；双线程同键在配额 1 下返回同一任务；恢复、旧键重放、取消后新创建均通过。报告在 `C:\Users\gy\AppData\Local\Temp\rag4_quota_l6h4tpm2\report.json`，耗时 8843ms，数据保留，未写业务库或调用远程模型。

配置、边界和回退见 [配额契约](rebuild_quota.md)。无新增迁移/依赖，默认 RAG3 行为保持。语法和差异检查通过，工作区未提交或推送。下一步在 worker 领取边界实现独立并发/租约约束；自动队列、模型费用预算、GC、大规模性能和正式部署仍缺验收，Graph/Agent/前端未实现。

## R14. Phase 2.6：只读迁移结构检查（2026-09-17）

最新后续进展见下述 R15；本节保留当时验证范围。

为防止“脚本重复执行成功”被误认为“已有表结构正确”，新增 schema_preflight 服务和显式指定数据库的 CLI。按 ORM 对照八张 Phase 2 表和 users/documents 主键前置条件；输出缺表、字段与约束问题及有序迁移文件。工具不执行 SQL 修复，不接入业务启动流程，也不新增依赖。

首次真实验证暴露 MySQL VARCHAR 反射带 CHARACTER SET 的显示差异，已在类型比较中规范化，保留独立的 collation 检查，并新增回归用例。MySQL 8.4.9/3307 合成验证库通过（68ms），rag_high 缺八张表（51ms），符合预期；两次检查均只读。修正 database.init_db 注释，避免把含 DROP DATABASE 的历史初始化脚本作为升级入口。

接口、退出码、运行方式和未覆盖项见 [只读结构门禁](schema_preflight.md)。备份恢复演练、正式迁移、后台调度和完整上线验收仍未完成。新增 10 项结构检查测试；后端全量 255 passed / 274.98s，compileall 和 git diff --check 通过。详细命令及实测记录在本轮基线记录中保存。

## R15. Phase 2.7：合成关系数据库备份恢复（2026-09-18）

新增独立演练脚本和 10 项安全/完整性测试。通过随机新建 source/before/after 库，验证真实 mysqldump/mysql 导出导入、七张 baseline 表数据保留、十五张迁移后表恢复及 002–006 重放。准备任务和 ChunkSet 通过真实服务生成，含中文文档。拒绝已有非空目标，失败备份只保留 partial，备份摘要不匹配时拒绝恢复；报告不含密码或行内容。

MySQL 8.4.9/3307 两次通过（8972ms、最终 5717ms），相关测试 34 passed / 30.82s。未重跑全量，上一轮 255 passed 仍仅是历史全量记录。产物位置在基线中，演练接口见 [备份恢复说明](migration_restore_drill.md)。未修改业务库，没有新增 Python 依赖。后续仍需 Chroma/上传文件配套恢复和正式上线验证；Graph/Agent 不在本轮范围。

## 阅读方式与证据口径

Phase 2.15 实现可选创建幂等键，新增 007 映射表和 12 项测试。映射与任务原子提交，同键同参重放保持原快照/状态，冲突 409，省略键保持旧行为；显式恢复不会将原键转移到续接任务。此前 MySQL 合成库已验证双线程唯一任务、007 重放和组合恢复。2026-09-26 收尾时旧测试 session 不可用，重新验证相关组，实际结果记入基线。无新依赖、业务迁移或自动队列。契约见 [创建幂等](rebuild_idempotency.md)。

Phase 2.14 统一清单结构检查，修复缺字段可能误报“版本不存在”的语义问题。新增 14 项损坏回归通过（52.27s），当前代码的 MySQL 组合恢复再次通过（29979ms）。新增 [验收索引](phase2_acceptance.md)，将源码、测试和上线缺口放在同一份清单中，避免将手动闭环误记为完整生产平台。全量结果见本轮基线。

Phase 2.13 新增历史版本列表/详情，采用 owner SQL 过滤和字段白名单；冻结文档后来变化时仍保留历史可见性，损坏清单显示 invalid，而不是让列表全盘失败。查询不读向量，不声称当前可激活。新增 9 项用例及 worker/API 回滚闭环，相关 **26 passed / 75.70s**，语法和差异检查通过。本轮未重跑全量、未更改业务库、无依赖/迁移。下一步收敛 Phase 2 整体验收，说明见 [版本 API](index_version_api.md)。

Phase 2.12 新增用户级 active GET/PUT，必须提供目标版本（停用为显式 null）和 expected_revision。新增 ActiveRevisionConflict 类型保留 ValueError 兼容性，HTTP 返回 409；错误版本归属返回统一 404，完整性失败保留旧指针。发现停用原先会初始化向量库，已将其改为不依赖向量后端，增强故障时解除 active 绑定的可用性。新增 17 项 API 用例，覆盖 Local/Chroma 激活回滚、过期 revision、越权、损坏清单和后端不可用停用。命令与结果见基线，契约见 [版本 API](index_version_api.md)。没有自动激活、删除索引、迁移或新依赖。

Phase 2.11 新增受控 worker 执行入口，绑定管理员凭据与任务冻结模型身份。选择独立单任务进程，保持 HTTP 创建 pending 的语义，不引入未经验证的内存后台队列。复用 SQL 领取/失败重试机制，新增 10 项测试，执行/API/重建服务共 **39 passed / 114.98s**。语法与差异检查通过，未重跑全量、未使用远程模型、未修改业务库。限制和命令见 [worker](rebuild_worker.md)，下一步是用户级 CAS 激活/停用。

Phase 2.10（2026-09-22）从恢复验证推进到用户管理入口：新增 `/api/v1/index-rebuilds` 的创建、分页、详情、取消。复用 JWT 和既有同步重建服务；请求不能覆盖用户 ID、模型地址或凭据，模型配置由管理员配置快照获得，维度由请求显式声明、执行阶段验证。创建不自动调度，避免没有可靠 worker 时虚报已排队。新增 17 项 API 测试，与重建服务共 **29 passed / 89.41s**；首轮扩展前 27 passed / 83.05s。接口无新依赖或迁移，限制和后续执行入口见 [管理 API](rebuild_api.md)。

Phase 2.9（2026-09-22）新增 MySQL/上传/Chroma 组合演练，复用之前的文件快照、逻辑备份与索引验证接口，新增 7 项测试。MySQL 8.4.9/3307 独立库验证通过（32882ms），导入后全表摘要、active 检索、baseline 回退和源数据不变均通过。首轮相关测试 36 passed / 1 failed，原因是密码传递测试创建 URL 时漏传用户名，已修正测试夹具；全量回归结果记录在基线中。没有新增依赖、业务迁移或远程模型调用，未提交推送。详情见 [组合恢复](mysql_combined_restore.md)。

最新切片记录：Phase 2.8 新增 [停写配套恢复](offline_restore.md) 模块及合成演练，用进程退出确保 Chroma 和 SQLite 无写入者后再捕获。恢复前检查外部可信清单摘要及全部文件，恢复到新目录后复核 active 索引与 baseline 查询；旧源数据库未改变。新增 10 项测试与现有版本服务测试合计 **30 passed / 61.11s**，涵盖真实 Chroma 子进程恢复、损坏/缺失/多余文件、清单篡改、拒绝覆盖、重叠路径、复制期间源改变及链接拒绝。未重跑全量，没有新增依赖或业务迁移。下一步是 MySQL 与配套文件的统一合成恢复演练；本轮不是生产灾难恢复验收。

本文记录已经发生的开发活动及其依据；[开发计划](../../RAG4_DEVELOPMENT_PLAN.md) 负责未来路线，[基线记录](../../RAG4_BASELINE.md) 保存环境与验证结果，[切分接口说明](rag4_chunking.md) 负责 Phase 1 的详细调用契约。

证据分三类：**代码已存在**、**有已执行的验证记录**、**仅有规划或历史描述**。脚本存在不等于正式训练完成，测试全绿不等于线上性能达标，模型 Collection 版本隔离不等于索引原子激活。本次文档整理执行了源码/提交核对、测试收集与文档检查；完整测试运行结果引用上轮实际执行记录，未把收集测试写成重新运行测试。

原文 v1.0 的日期为 2026-07-26，是被导入的 RAG3 文档日期；当前仓库可追踪的提交从 2026-09-14 开始。原文的“9 个提交”“77 用例”“全链路真实模型验证”和性能数字只属于其历史记录，不能作为当前 RAG4 的验收结论。

## R1. 当前进度与功能边界

当前系统是 **RAG3 问答基线 + 模型基础设施 + 可选 RAG4 ChunkingEngine + 手动版本化索引闭环与恢复/配额**。Research Agent 仍是产品目标；现有 SSE 问答服务和索引重建任务不是 ResearchAgent。

| 阶段 | 核对结果 | 已有证据与未完成部分 |
| --- | --- | --- |
| Phase 0：基线与评测冻结 | 部分完成 | 环境、历史回归、模型接口及合成停写恢复已有证据；当前全量回归、真实文献回归集和完整研究任务评测待补 |
| 模型微调基础设施 | 代码与离线管线已有 | remote/local Embedding、Reranker、版本隔离、hard negative 构建、训练与排名评测脚本；没有正式训练产物或质量提升的验收结论 |
| Phase 1：结构化切分 | 本轮指定功能切片已完成 | 领域模型、确定性身份、token 计数接口、父子片、解析兼容、上传开关和测试；完整原文布局抽取及真实检索质量对比未完成 |
| Phase 2：版本化索引重建 | 手动闭环已实现，范围冻结 | 已有版本、恢复、管理 API、worker、幂等与配额；待当前回归和隔离文献验证，生产化待办不作为 Phase 3 默认前置 |
| Phase 3：图谱与混合证据 | 未实现 | 无 MemoryGraphStore、Neo4jGraphStore、HybridEvidenceEngine |
| Phase 4：ResearchAgent 与工具 | 未实现 | 无 ResearchTask/ResearchStep、ResearchAgent、ResearchToolRegistry |
| Phase 5：证据与产物 | 未实现 | 无 EvidenceVerifier、ArtifactComposer |
| Phase 6：研究工作区 | 未实现 | 现有前端仍为问答、知识库和管理后台；没有研究任务工作区 |
| Phase 7：评测、微调与上线门禁 | 未完成 | 有训练/评测入口，不代表完整评测冻结、训练或上线门禁通过 |

本次没有按阶段数量估算“完成百分比”：各阶段工作量不同，而且 Phase 0 仍有待补验收项。

## R2. 可追溯开发时间线

日期取自当前 Git 历史；旧 RAG3 文档叙述与本仓库提交历史分开记录。

| 日期 | 提交 | 实际变更 | 结果及边界 |
| --- | --- | --- | --- |
| 2026-09-14 | `c620adf` | 初始仓库与项目规划资料 | 尚不能据规划宣称应用实现 |
| 2026-09-14 | `170296b` | 导入 RAG3 前后端、测试、部署与文档，恢复可复现基线 | 建立 `project/`；包括问答、文档、权限、管理与部署脚本 |
| 2026-09-14 | `c1884b5`、`739e53d`、`c22ff88` | 记录 Conda 基线，建立独立 `rag4-py3.11` 环境，移除临时环境清单 | 避开系统 Python 3.13 安装 Chroma 原生依赖受阻的问题 |
| 2026-09-14 | `b59204b` | 接入版本化远程/本地模型与训练基础设施 | 基线记录为后端 82 项、训练管线 2 项通过；尚无批量索引重建 |
| 2026-09-16 | `4b0e1dd` | 实现 Phase 1 结构化切分及兼容接入 | 15 个文件变更，新增 74 项测试；后端合计 156 项通过 |
| 2026-09-16 | 同一提交 | 按用户请求推送 `main` 到 GitHub | 会话中 push 已成功，发布点为 `4b0e1dd`；本文不把本次尚未提交的文档整理写成新代码发布 |
| 2026-10-12 | `476127b` | Phase 2.1–2.16 代码、测试与记录提交并推送 | 75 个文件；手动索引能力已发布到代码仓库，未执行生产部署 |

可复核命令：`git log --reverse --oneline`、`git show --stat b59204b`、`git show --stat 4b0e1dd`。GitHub 发布记录：[Phase 1 提交](https://github.com/[本地凭据已省略]/RAG4/commit/4b0e1dd260bd024d9ef2f5c45e2be26b5d13dad4)。

## R3. 基线恢复与模型基础设施的开发过程

### R3.1 先恢复可运行基线

起点是 RAG3 的注册登录、权限、上传解析、检索精排、SSE 回答及引用、配置与运行监控。导入时保留后端 `app.main:app`、前端 Vite 入口、已有接口和数据库模型。现有部署资源包括 Dockerfile、Nginx 配置和 `deploy/docker-compose.yml`；“Docker Compose 尚未编写”是后半部分旧 TODO，现已不适用。文件存在仍不代表本次已完成容器部署实测。

环境恢复中，系统 Python 3.13 的 Chroma 原生依赖安装因缺少 MSVC 工具失败；随后使用独立 Conda `rag4-py3.11`。基线记录保留了 Python 3.11.15、Chroma 0.5.23、pytest 8.3.4 以及当时前端 lint/build 结果。后端测试使用临时 SQLite、临时向量目录和 Mock AI，不需要业务数据库或模型 API Key，但仍需安装项目依赖。

### R3.2 将模型调用与业务流程分开

在 [modeling/interfaces.py](../backend/app/modeling/interfaces.py) 定义 `ModelDescriptor`、`EmbeddingModel`、`RerankerModel` 和 `RankedIndex`，由 [registry.py](../backend/app/modeling/registry.py) 按配置解析 remote/local Adapter；Embedding/Reranker 服务继续作为业务调用入口。管理配置新增 provider、version、local_path。

向量 Collection 使用用户 ID 与 Embedding 版本共同定位；`baseline` 保留旧 `col_user_{user_id}` 名称。新模型版本使用独立 Collection，避免不同维度/语义空间混写。查询也按当前 Embedding 配置选择 Collection，因此配置切到未建好的新版本可能检索不到旧文档；目前没有“验证完成后再激活”的发布过程。

[training/](../training/README.md) 提供 hard negative 构建、Embedding/Reranker 训练、LoRA-SFT 和 Recall@K/MRR/nDCG 评测。已有两项测试验证样本选择与指标计算，并没有证明大模型训练已完成、GPU 运行已验证或生产质量提升。DDL v1.4 的变化是默认配置键扩展，没有为索引重建或研究任务创建新业务表。

## R4. Phase 1 的实施过程

### R4.1 输入、范围与起点检查

开发从 `main` 的 `b59204b` 开始，当时工作区干净。先检查旧 parser、split_blocks、上传流程、向量 metadata、测试夹具和 SQL。确认数据库初始化脚本含 `DROP DATABASE` 后仅读取，没有用其做迁移。真实计划和基线文件位于根目录，而非名为 `RAG4/` 的子目录。

本阶段以独立切分模块为可验证切片：保留 `chunking_service.py` 的 RAG3 行为，先建立纯计算接口，再接入新上传。Graph、Agent、前端工作区和索引重建未进入实现范围。

### R4.2 先定义模型和身份，再实现切分

| 文件/接口 | 实际职责 | 关键约束 |
| --- | --- | --- |
| [models.py](../backend/app/chunking/models.py) | ParsedDocument/ParsedBlock、DocumentChunk、ChunkSet、ChunkingConfig、来源和结构 metadata | Pydantic 冻结快照，tuple 集合，拒绝未知字段，JSON 可往返 |
| [engine.py](../backend/app/chunking/engine.py) | ChunkingEngine、TokenCounter 及两个计数实现 | 按章节分组、段落/句子/空白/字符边界切分；不下载 tokenizer |
| [adapter.py](../backend/app/chunking/adapter.py) | ParseResult/TextBlock 到 ParsedDocument；Markdown 结构通道 | 不修改旧 blocks；不猜测已丢失的布局 |
| [document_service.py](../backend/app/services/document_service.py) | 新上传选择引擎、验证结果、子片向量化、状态与日志 | 默认 rag3；ready 文档直接返回；Embedding 数量不匹配时写入前失败 |
| [vector_store.py](../backend/app/services/vector_store.py) | Chroma/Local 两种后端的结构 metadata 往返 | JSON 字符串适配 Chroma 标量约束；还原到 RetrievedChunk.extra |

`ParsedDocument` 包含文档 ID、文件名、页数、block、source 与 parser_version。每个 `DocumentChunk` 携带 chunking_version、标题、section_path、父 ID、页范围、table/formula metadata 和原 block 字符区间。父片与子片分别连续编号，子片恰好引用一个父片。

结果身份采用规范 JSON 的 SHA-256：输入文档、完整配置、parser/chunking/engine/tokenizer 身份参与 input_id；每片内容与关系参与 chunk_id；完整结果与统计参与 chunk_set_id。时间不放入身份，耗时单独记录。`ChunkSet.verify(document)` 检查结果完整性与输入身份，不能代替未来的索引数量/维度/激活验证，也不是密码学签名。

### R4.3 处理解析兼容和运行开关

旧 Markdown 解析会删除 `#`，因此单靠旧 TextBlock 无法恢复标题层级。实现采用 `ParseResult.structured_blocks` 可选通道：`parse(..., structured=True)` 对 Markdown 保留 ATX/setext 标题及 fenced code；旧 blocks 文本和旧位置参数保持兼容。PDF 沿用逐页文本；DOCX 沿用既有扁平输出，未伪装成版式级抽取。

配置来自启动环境：`DOCUMENT_CHUNKING_ENGINE` 默认 `rag3`，显式 `rag4` 启用新上传路径；RAG4 独立使用 `RAG4_CHUNKING_VERSION`、`RAG4_CHILD_MAX_TOKENS=256`、`RAG4_PARENT_MAX_TOKENS=1024`。这些不是管理后台 RAG3 的动态 chunk_size/overlap 配置。恢复 rag3 并重启，只改变之后处理的文档，不会重建已 ready 的文档。

无 tokenizer 时采用 `unicode-codepoint-v1`，按 Unicode 字符计数，保证可重复而不承诺真实模型 token 上限。注入 tokenizer 后固定其身份；运行中报错直接失败，避免同一结果混用计数口径。父片预算不小于子片预算，Phase 1 不做重叠。表格、公式、代码独立分组；表格/公式 metadata 可透传，不代表已经自动提取出结构。

### R4.4 测试与审查中的问题及修正

| 发现 | 原因与修正 | 验证方式 |
| --- | --- | --- |
| 非单调 token 计数拒绝可容纳文本 | BPE 合并可能令更长文本 token 更少；增加全文检查和二分未命中时的前缀搜索，每片重新计数 | 合并 token 与前缀搜索回归用例 |
| Markdown `C#` 标题变成 `C` | 结束井号规则过宽；只移除前面带空白的 closing sequence | 标题保真回归 |
| fenced code 缩进丢失 | 普通清洗会压缩空白；代码保留缩进，切分时保留边界空白 | 父片与子片拼接还原原代码 |
| 集成测试 helper 导入错误 | 测试引用了错误的 mock embedding 函数名 | 修正后双向量后端集成测试通过 |
| Embedding 返回数量不足可被 zip 静默截断 | 集成层增加数量相等校验，禁止不完整输入写索引 | 数量不匹配失败测试 |

旧 `split_blocks` 实际允许输出长度达到 `chunk_size + overlap`，回归金样保留此行为，没有按新引擎的严格预算要求重写旧函数。独立测试/审查与主线程集成完成后，由主线程统一运行全量后端回归。

## R5. 当前运行链路与数据安全边界

```text
上传 -> 保存原文件/Document(pending) -> parsing
  -> rag3: ParseResult.blocks -> split_blocks
  -> rag4: 可选结构解析 -> adapt_parse_result -> ChunkingEngine -> verify
  -> 子片文本 Embedding -> 数量校验 -> 向量写入 -> ready / failed

问答 -> 查询向量 -> 用户 + 当前 Embedding 版本 Collection
  -> Reranker -> LLM -> SSE 正文与引用
```

RAG4 上传仅索引 child chunks，稳定 chunk_id 避免使用旧 `doc_id:chunk_index` 覆盖旧片；旧路径仍保持原 ID。复杂结构随向量保存，引用 page 继续映射 page_start。上传路径仍不保存完整父片；Phase 2.1 独立准备服务现可持久化并读取完整父片，尚无公共 HTTP 查询 API。

`usage_logs` 的 `document_chunking` 记录耗时和成功/失败；引擎日志记录文档、版本、tokenizer、ChunkSet ID、片数和耗时。上传异常处理更新文档为 failed，并保留既有索引。独立准备服务已有任务表，但没有进程崩溃恢复或跨数据库/向量库事务；因此“捕获异常后写 failed”不能扩大为“任何故障都会自动恢复”。

当前保护范围：已 ready 文档不会通过该函数重建，切分失败不会删除既有文档索引，向量数量不匹配在写入前阻断。尚未覆盖的风险是向量写入中途失败可能留下新文档部分记录，failed 重试缺少 generation 清理，检索也没有索引任务的 active 门禁。这些是 Phase 2 的明确前置工作。

## R6. 验证记录与复现方式

| 验证时间/来源 | 范围 | 结果 | 能证明什么 |
| --- | --- | --- | --- |
| 2026-09-14 基线记录 | 后端、训练管线 | 82 passed；2 passed | 当时版本的功能回归及离线数据/指标逻辑 |
| 2026-09-14 基线记录 | 前端 lint/build | 成功 | 当时类型检查和构建通过；未作为本次重新运行结果 |
| 2026-09-16 Phase 1 实施记录 | 新增两份切分测试 | 74 passed，23.37s | 引擎、兼容、双向量后端、PDF、SSE、故障保护 |
| 2026-09-16 Phase 1 实施记录 | 全量后端 | 156 passed，102.09s | 82 项原测试加 74 项新测试，无失败或跳过 |
| 2026-09-16 本次文档核对 | pytest collect-only | 后端收集 156 项；训练管线收集 2 项 | 当前提交仍能发现对应测试；不是一次新的通过结果 |
| 2026-09-16 Phase 2.1 实施 | 全量后端实际运行 | 170 passed，130.64s | 原 156 项回归及新增 14 项持久化/隔离/并发/失败测试通过 |
| Phase 2.2 实施 | 全量后端 + 后补失败测试 | 201 passed，177.52s；另 2 passed，6.18s | 全量回归加新增 SQL 发布失败测试；当前合计 203 项，非同一次全量执行 |
| Phase 2.2 真实联调 | SiliconFlow/MySQL/Chroma | 7 模型 HTTP 200；实际 staging validated | MySQL 5.7.44 迁移重放、真实 4096 维向量回读、baseline 保留；不代表质量/性能验收 |
| 2026-09-17 Phase 2.3 | 全量后端 | 223 passed，226.08s | 新增 20 项激活/回滚/检索/变更门禁测试及全部既有回归 |
| 2026-09-17 Phase 2.3 | MySQL 8.4.9/3307 + SiliconFlow + Chroma | BGE 1024 维，激活/查询/回滚成功 | Qwen8B 当次超时；显式选择另一可用模型完成合成数据联调，业务模型未切换 |
| 2026-09-17 Phase 2.4 | 全量后端 | 235 passed，267.91s | 12 项批量 checkpoint/重试/取消/输入门禁测试及原有回归 |
| 2026-09-17 Phase 2.5 | 修复资源清理后全量后端 | 245 passed，283.44s | 10 项恢复用例及全部回归；原 PDF/SSL 句柄耗尽失败已消除 |

在仓库根目录执行以下 PowerShell 命令可复现测试；已有环境无需重新安装。

```powershell
conda activate rag4-py3.11
Set-Location E:\RAG4\project\backend
python -m pytest -o addopts='' -q --tb=short
python -m pytest tests/test_chunking_integration.py tests/test_chunking_engine.py -o addopts='' -q --tb=short
Set-Location E:\RAG4\project
python -m pytest training/tests -q
```

如果只核对数量，在对应测试命令中增加 `--collect-only`。完整依赖安装见 [project README](../README.md)，本地模型与训练依赖分别见 `requirements-local-models.txt` 和 [训练说明](../training/README.md)。Phase 1 没有新增依赖或数据库 schema 迁移。

未获得本轮验收证据的项目：扫描版 OCR、真实模型训练、冻结语料 Recall/MRR/nDCG 提升、10 并发与生产时延、前端 E2E、容器部署、备份恢复。旧文档的 6 秒解析/4.3 秒检索不能用于宣称当前 RAG4 性能。另有已记录的 Chroma/posthog telemetry 签名兼容日志，功能测试通过；本次未调整依赖。

## R7. Phase 2 交接与后续记录要求

本节的交接表保留 Phase 1 完成时的历史安排，其中多数索引能力现已完成。2026-10-12 起当前任务以 R17 和开发计划第 3.4 节为准，不按此表重新建设已有模块。

下一阶段入口已经存在：`adapt_parse_result(...) -> ParsedDocument`、`ChunkingEngine.split(document, config) -> ChunkSet`、`ChunkSet.verify(document)`。先完成一个安全重建闭环，再扩展批量执行。

| 顺序 | 下一步工作 | 验收门槛 |
| --- | --- | --- |
| 1 | 定义 ChunkSet/父片不可变存储、document_index_jobs、active version 和增量迁移 | 旧数据可继续读取，源/parser/chunking/tokenizer/embedding 版本固定，错误/耗时可追踪 |
| 2 | 将候选版本写入独立 staging 索引 | 构建期间查询继续使用旧 active，新旧数据不混写 |
| 3 | 校验来源、身份、切片数、向量数与维度，再激活 | 校验失败不发布；切换原子化且可追溯 |
| 4 | 实现回滚、重试、取消、删除与并发一致性 | 失败注入下旧版本仍可查询；重复操作幂等；部分数据不可见 |
| 5 | 备份恢复演练通过后开放历史文档批量重建 | 有迁移/恢复说明及测试证据，再标记 Phase 2 完成 |

后续顺序遵循当前开发计划：Phase 3 图谱与混合证据 → Phase 4 Agent/工具 → Phase 5 证据门禁/产物 → Phase 6 研究工作区 → Phase 7 冻结评测、微调与上线门禁。历史图谱方案里的 MySQL 邻接表选型只是旧提案；当前规划包含 MemoryGraphStore/Neo4jGraphStore，二者均未实现，不从旧提案推导新功能已经存在。

每次阶段结束更新本文，至少记录：起点与交付提交、目标与边界、关键变更和文件入口、实际故障与修正、测试命令及结果、未验证内容、回退操作、下一阶段前置条件。暂未提交时写“工作区变更”；没有测过的指标写“未验证”；计划中出现的名称不能直接进入完成清单。

## R8. 上轮文档整理记录（511cbbd）

本次只调整文档：补充本文 RAG4 过程记录；根 README 更新 Phase 1 状态并添加入口；project README 更新测试数量与切分模块说明；本地项目概览标注初始化前历史范围；基线记录补充发布确认。正文保留原 RAG3 开发经历与故障分析，并把历史分支、测试数、性能数字和图谱提案限定在当时范围，避免覆盖掉有价值的演进记录。

文档核对：五份改动文档中的 42 个本地文件链接均可解析，代码围栏成对；修正文末空白后执行 `git diff --check`。本次不修改业务代码、数据库或模型配置。

---

## R9. Phase 2.1 开发记录

本轮从干净的 `511cbbd` 开始，核对文档服务、ChunkSet 校验、数据库会话/模型、向量实现与测试夹具。选择先完成准备任务和父片存储，避免在缺少持久化证据时直接切换在线索引。

新增 `models/index_job.py` 与 `services/index_job_service.py`。实现用户级幂等请求、源文件摘要/参数冻结、条件更新抢占、临时源文件快照、结构/身份校验、完整 ChunkSet 持久化及重新读取校验。成功状态和结果在同一事务提交；源变化、解析异常和落库异常保留既有文档/索引。解析前复制并验证临时文件，消除了先检查原路径再解析原路径的时间窗口。

修改文档删除流程以清理附属记录，并注册新模型；独立测试覆盖父子片恢复、版本不冲突、重复键冲突、跨用户拒绝、数据篡改、并发抢占及并发建任务、失败注入和删除清理。错误存储采用分类码，避免原始异常内容含密钥或原文。

新增仅建表的 MySQL 增量脚本；没有执行历史含 DROP DATABASE 的初始化脚本，也没有访问业务数据库。SQLite 自动测试创建新表；MySQL 实例迁移、备份恢复和大文档容量尚未验证。无新增依赖。详细调用、状态和回退说明见 [切分准备接口](index_preparation.md)。

后续入口为 `load_chunk_set`。下一切片需固定 Embedding 配置并写入独立 staging，再验证完整性；active version、批量重建、取消/租约恢复和在线回滚仍未实现。旧上传开关和检索保持原状。

验证：backend 目录执行 `python -m pytest -o addopts='' -q`，结果 **170 passed in 130.64s**；新增测试 14 项。新增模型和服务 compileall 通过。未重新运行前端与训练测试，因为没有修改相应代码。

## R10. Phase 2.2 开发与真实模型联调

在上一切片未提交的工作区继续开发，保留所有已有修改。先按用户授权读取本地凭据，以合成文本检查硅基流动说明中的全部 7 个模型，全部 HTTP 200。实际连接 MySQL 后确认服务版本为 5.7.44-log，修正了将客户端 8.4.9 当成服务版本的认知。

新增 `models/index_build.py` 与 `services/index_build_service.py`：保存远程 EmbeddingSpec、独立 staging namespace、状态和错误阶段/耗时；验证每条向量的数量、维度、有限值、非零值后写入，通过 Local/Chroma 新增的 `read_records` 回读全部记录，逐条核对 ID、文本、metadata 和向量值，再事务发布 validated manifest。没有接入在线索引切换，失败的部分写入保持隔离，重试分配新 namespace。

文档删除与候选发布在 MySQL 上共享文档行锁；删除同时清理构建记录。SQLite 不具备相同的跨进程行锁语义，限制已记录。尚无批量、取消、租约恢复、候选 GC 或 active version。

新增 `003_index_builds.sql` 及真实验证脚本 `scripts/validate_index_staging.py`。首次真实迁移测试发现脚本错误拆分 SQL 注释分号，修正为先移除整行注释后执行；随后两份增量迁移均重复执行通过，真实 Qwen3-Embedding-8B → Chroma 构建 validated，baseline 记录未变化。创建的两个 scratch 数据库及临时目录均保留，未修改业务库，具体名称见 [联调记录](model_connectivity_validation.md)。

测试命令：backend 下 `python -m pytest tests/test_index_builds.py -o addopts='' -q --tb=short` 首批 31 passed / 53.52s；全量 `python -m pytest -o addopts='' -q --tb=short` 为 201 passed / 177.52s。全量启动后补充的 SQL 发布失败测试单独执行 `python -m pytest tests/test_index_builds.py -k sql_publication -o addopts='' -q --tb=short`，2 passed / 6.18s；当前合计 203 项均有通过记录。compileall、git diff --check 通过，无新增依赖。

下一切片建立用户级完整索引版本、文档覆盖集合和 active 指针，激活前重新验证候选及文档状态，查询绑定对应模型配置，并保留旧版本可回滚。单个文档 validated 不能直接替换整个用户知识库。

补充环境核对：用户指出双实例后，分别连接确认 3306=MySQL 5.7.44、3307=MySQL 8.4.9；RAG3 原 `.env` 使用 3307。选定 3307 为 RAG4 主开发实例，新增显式端口配置并在独立验证库重跑成功（validated、4096 维、3625ms）。3306 保留为兼容性环境，两个实例的已有业务库均未改动。详见 [双实例选型记录](model_connectivity_validation.md)。

## R11. Phase 2.3 用户级激活与回滚（2026-09-17）

从现有未提交工作区继续，核对实际入口 rag_service.retrieve。原候选仅覆盖单文档，因此新增 IndexVersion 完整用户清单，要求所有文档 ready、每份恰有一个候选且 EmbeddingSpec 一致。新增 records_sha256，以文本/metadata/float32 向量完整摘要识别构建完成后的篡改；旧无摘要候选必须重建。

新增 ActiveIndex 的 CAS 修订号和 IndexSwitch 审计，同事务切换与记录。激活、回滚前重新验证；查询一次固定一个版本，使用冻结模型配置，在现有 Reranker 和引用接口前合并结果。模型密钥仍由当前安全配置提供，并检查 endpoint 绑定；未激活保持原检索。新增、删除等文档变化会显式报错直到重建或停用，没有隐式切换/忽略文档。

新增 20 项测试覆盖完整覆盖/重复/跨用户拒绝、不同模型隔离、实际版本回滚、并发 CAS 唯一胜者、篡改拒绝、SQL 审计失败回滚、现有检索与引用、上传/删除/凭据 endpoint 变化门禁。backend 执行 `python -m pytest -o addopts='' -q --tb=short`：223 passed / 226.08s；compileall 和 git diff --check 通过。无新增依赖。

真实脚本扩展到 004 迁移重放和激活/真实查询/回滚/停用。MySQL 3307 上首次及重试因 Qwen3-Embedding-8B 超时停在 embedding，失败记录保留；直接探测 BGE 成功后显式选择 Pro/BAAI/bge-m3，1024 维链路完整通过。没有把超时当成功，也未修改业务模型配置。新增验证资源见 [真实验证记录](model_connectivity_validation.md)。

下一切片仍属 Phase 2：上传/删除与 active 版本的增量衔接、批量调度/恢复和迁移上线门禁。当前每次查询回读全部候选，适用于正确性验证，不作为生产性能结论。没有实现 Graph/Agent/前端。

## R12. Phase 2.4 批量重建与失败恢复（2026-09-17）

保留前轮工作区修改，新增 IndexRebuild 与 create_rebuild/run_rebuild/get_rebuild/cancel_rebuild。将准备、候选构建、完整版本组装串成可查询的同步任务。冻结源摘要/文件名/集合与两类配置，启动和完成前校验；每份文档成功后持久化候选 ID，失败重试重新验证已完成结果并跳过模型计算。失败文档使用新子任务键与 namespace，历史结果不覆盖。

取消在文档边界协作处理，远程请求不强杀；最终 SQL CASE 根据最新取消标志决定 ready/cancelled，防止晚到取消被 ready 覆盖。任务只生成待激活版本，base_revision 保留供显式 CAS 激活，批量工作不自动改 active。

新增 12 项 Local/Chroma 测试，首轮 12 passed / 33.02s，覆盖重试不重复向量化、取消、输入变化、权限、上传后完整重建和修订号冲突。增加 005 迁移并扩展真实脚本。MySQL 3307 验证库中本次真实批量任务 ready，1 个 checkpoint，5077ms，显式激活/停用通过，baseline 1 条记录保留。首次完整脚本的查询阶段曾返回 EmbeddingError，未把该次整条链路写成成功。

当前恢复仅处理受控失败，不接管崩溃后 running；无自动后台队列、跨任务增量复用、HTTP/UI 或 GC。下一切片应继续补租约/恢复和业务库迁移门禁，而非进入 Graph/Agent。接口见 [批量重建](index_rebuild.md)。

最终全量命令 `python -m pytest -o addopts='' -q --tb=short`：235 passed / 267.91s；compileall 与 git diff --check 通过。真实批量任务显式激活后再次调用查询，返回 1 条合成资料证据，随后停用成功。首次完整脚本查询失败仍保留在记录中，不将重试成功解释为外部模型持续稳定。

## R13. Phase 2.5 显式中断恢复（2026-09-17）

从现有未提交工作区继续，选择独立续接代替重置同一个 running 任务。新增 recover_rebuild 和 RebuildRecovery：条件更新持久化取消原任务，同一事务复制已提交 checkpoint/冻结请求/base_revision 并建立唯一续接关联。旧进程即使仍运行，也只能完成旧 namespace 或旧 checkpoint，数据库取消标志阻止其发布 ready；新任务有独立 ID，重复/并发恢复返回同一个目标。

恢复操作新增 index_recovery 耗时/成败日志。没有实现进程存活检测、心跳/租约和自动调度；恢复为显式服务调用。失败任务仍用原重试接口，主动取消的任务不被恢复。没有绕过源校验或激活 CAS，也没有重新声明整个 Phase 2 已完成。

新增 10 项测试，首轮 10 passed / 27.02s，覆盖模拟未捕获中断、checkpoint 复用、旧工作线程迟到、并发唯一续接、事务失败回滚、权限与主动取消。MySQL 3307 现有独立验证库执行 006 两次，复用之前真实 BGE 向量 checkpoint，续接 ready / 125ms / 无新增模型调用，active 不变；MySQL 两线程并发恢复也只产生一个目标。

真实验证脚本追加了 scratch 数据库中的中断快照模拟，明确不是强杀业务进程。没有修改业务库、没有删除历史任务/向量、没有新增依赖。下一切片继续完善 Phase 2 的调度或上线迁移门禁；接口见 [中断恢复](rebuild_recovery.md)。

本轮全量首次运行发现两个既有 PDF/SSL 用例因 Too many open files 失败（243 passed / 2 failed，286.25s）。定位到 Chroma 0.5.23 按路径缓存 System，原夹具每测试创建新目录却未停止实例，测试数量增加后累积耗尽 Windows 文件句柄。已在测试 teardown 中停止并移除本用例新增的 System，保留运行前已有实例，不提高系统限制、不删除用户文件或改动生产工厂。恢复运行日志补充后的独立恢复测试为 10 passed / 27.39s。

修复后重跑完整命令 `python -m pytest -o addopts='' -q --tb=short`：**245 passed / 283.44s**，此前两项故障已通过。compileall 和 git diff --check 通过，新增文档 7 个本地链接有效；真实 MySQL index_recovery 日志查询也通过。本轮没有新增依赖。

## 历史附录：RAG3 v1.0 开发记录

> 原文版本：v1.0，原更新日期：2026-07-26。以下第 1–8 节是导入的 RAG3 历史记录，不是当前 RAG4 验收清单。
>
> 原“零外部依赖”应理解为不需要外部模型 API/业务数据库，仍依赖 Python 包与本地测试设施；“当前”“已完成”“待办”和旧 ADR 均限定在原记录时期。原图谱设计没有在当前仓库实现。

---

## 目录

1. [项目现状速览](#1-项目现状速览)
2. [开发阶段回顾](#2-开发阶段回顾)
3. [功能清单：已完成 / 待办](#3-功能清单已完成--待办)
4. [运行时业务逻辑](#4-运行时业务逻辑)
5. [已知限制与技术债](#5-已知限制与技术债)
6. [未来扩展路线](#6-未来扩展路线)
7. [知识图谱：实现方案设计](#7-知识图谱实现方案设计)
8. [附录：关键决策记录](#8-附录关键决策记录)

---

## 1. 项目现状速览

| 维度 | 现状 |
|------|------|
| **代码规模** | 后端 42 个文件 / 4,225 行 Python；前端 29 个文件 / 3,368 行 TS·TSX；文档 5 篇 / 2,614 行 |
| **接口** | 20 个，与 `api_document.md` 逐条对齐 |
| **测试** | 77 个 pytest 用例，全部通过，零外部依赖 |
| **端到端验证** | 浏览器脚本 10 节点全通过，控制台零错误 |
| **真实模型验证** | 已接入硅基流动完成全链路联调 |
| **提交** | 9 个提交，均在 `claude/doc-development-project-xaub55` 分支 |
| **交付物** | 可运行系统、README、DDL v1.3、变更记录、2.4 万字演讲文稿、44 页 PPT、4 分钟演示视频 |

### 验收状态

| 验收项 | 状态 | 说明 |
|--------|------|------|
| 功能完整性 | ✅ 达标 | PRD 定义的全部功能均已实现并验证 |
| 接口一致性 | ✅ 达标 | 20 个接口逐条对齐，另有 4 个必要补充接口 |
| 自动化测试 | ✅ 达标 | 77 用例，覆盖认证/权限/文档/问答/后台/服务层 |
| 文档解析耗时 | ✅ 优于指标 | 实测 6 秒（指标：100 页内 30 秒） |
| **检索时延** | ❌ **未达标** | 实测 4.3 秒（指标：< 2 秒），归因与优化路径见 §5.1 |
| 扫描版 OCR | ⚠️ 未验证 | 代码路径完整，但演示环境未装 OCR 引擎 |
| 并发能力 | ⚠️ 未压测 | 架构支持，但未做 10 并发的实测验证 |

---

## 2. 开发阶段回顾

整个开发在一个连续会话中完成，共经历六个阶段。这里如实记录每个阶段做了什么、
发现了什么，包括走过的弯路——因为弯路本身是这份文档最有价值的部分。

### 阶段一：需求解析与架构设计

**输入**：`requirements_document.md`（PRD v1.1）、`api_document.md`（v1.0）、`init_db.sql`（v1.1）

**做的事**：
- 逐条拆解 PRD 中标记为 `[S-x]`（安全）、`[M-x]`（中优先级）、`[I-x]`（改进）的硬性要求，
  形成实现检查表
- 确定分层结构：`core`（基础设施）/ `models` / `schemas` / `api` / `services` / `utils`
- 确定三个抽象点：模型层（可换服务商）、向量库层（可换 Milvus）、存储层（MySQL / SQLite 双兼容）

**发现的第一个问题**：DDL 里 `usage_logs` 表没有任何字段能把一条失败日志关联回具体文档，
而接口文档要求 `GET /admin/stats` 返回带 `doc_id` 和 `file_name` 的 OCR 失败队列。
→ 新增 `ref_id` 字段，DDL 升至 v1.2，理由写入 `db_changelog.md`。

### 阶段二：后端实现与测试

**顺序**：基础设施 → 数据模型 → 服务层 → 路由 → 测试

**关键取舍**：
- 选同步 SQLAlchemy 而非异步——瓶颈在外部 API（8 秒）不在数据库（毫秒级），
  异步只会让全库染上 `async/await` 增加调试成本
- 选 SSE 而非 WebSocket——问答是单向推送，SSE 基于普通 HTTP，过反向代理的坑少得多
- 测试全部零外部依赖：SQLite 临时库 + `DEV_MOCK_AI` 开关，克隆即可 `pytest`

**过程中修掉的两个真实缺陷**：

| 缺陷 | 现象 | 根因 | 修法 |
|------|------|------|------|
| 消息顺序颠倒 | 一问一答显示顺序随机 | `DATETIME` 只精确到秒，同秒写入的两条记录排序不确定，而 UUID 做次级排序键无意义 | ID 改为「纳秒时间戳十六进制 + 随机后缀」，`ORDER BY created_at, id` 即稳定，零 DDL 改动 |
| 中文 TXT 乱码 | GBK 短文本被识别成韩文 | `charset_normalizer` 对短中文样本误判为 EUC-KR | 改为「UTF-8 严格解码优先 + 候选编码可读性打分」，同分时优先中文编码 |

**产出**：77 个测试用例全部通过。

### 阶段三：前端实现

React 18 + TypeScript + Vite + TailwindCSS。SSE 用 `fetch` + `ReadableStream` 手写解析
（浏览器原生 `EventSource` 只支持 GET 且无法自定义请求头，带不了 JWT）。

**产出**：`tsc --noEmit` 与 `vite build` 均通过。

### 阶段四：浏览器实测 —— 发现 3 个缺陷

77 个测试全绿之后，用真实 Chromium 完整走了一遍产品。结果：

| # | 严重度 | 缺陷 | 根因 | 为什么测试没发现 |
|---|--------|------|------|------------------|
| 1 | 严重 | **首轮提问的回答完全不显示** | 新建会话后 `navigate` 触发历史消息重新拉取，把正在流式渲染的占位气泡覆盖掉，后续 chunk 找不到目标消息 | 后端行为与数据完全正确，坏的是前端状态时序 |
| 2 | 中 | 运行监控柱状图高度为 0 | 父容器 `items-end` 使列高塌缩为内容高度，柱体百分比高度失去参照 | 纯 CSS 渲染问题 |
| 3 | 轻 | 控制台两个 404 | 缺 favicon | 不影响功能 |

**沉淀**：把浏览器验证固化为 `frontend/e2e/smoke.mjs`（`npm run e2e`），
覆盖 10 个节点并全程截图。

### 阶段五：真实模型联调 —— 发现 4 个缺陷

接入硅基流动（DeepSeek-V4-Flash + Qwen3-Embedding-8B + bge-reranker-v2-m3）后：

| # | 缺陷 | 根因 | 修法 |
|---|------|------|------|
| 4 | Rerank 从未成功 | 模型名硬编码为 Cohere 取值，换服务商必然失败，且失败被降级逻辑静默吞掉 | 新增 `rerank.model` 配置项 |
| 5 | 回答被截断甚至为空 | 推理型模型的 `reasoning_content` 思考内容同样计入 `max_tokens`，服务商默认值（常见 512）被思考吃光 | 主生成显式设 `max_tokens=4096`；空正文时推 `error` 帧而非落库空消息 |
| 6 | 主回答流被中途掐断 | 标题生成与主流并发，同一 Key 触发服务商并发限制 | 改为主流结束后顺序生成（接口文档允许标题在「即将结束时」推送） |
| 7 | 问题改写与标题生成必然超时 | 推理模型生成 15 字标题耗时 **19.9 秒**，而预算是 3 秒 / 8 秒 | 新增 `llm.aux_model` 辅助任务模型配置，留空则复用主模型 |

**第 7 条不是 bug，是设计缺口**——3 秒的改写预算在 PRD 写作时是合理的，
推理模型普及后不再成立。配置小模型后实测：改写 2.4 秒、标题 2.1 秒，全部成功。

### 阶段六：交付物制作

演讲文稿（2.4 万字）、演示 PPT（44 页）、演示视频（4 分 07 秒，中文配音）。

视频制作中同样遇到并解决了三个工程问题：真实模型生成耗时波动导致音画错位
（改为按实际画面时长补静音对齐）、Playwright 录制画布固定导致移动端画面留灰边
（分开录制后居中裱底）、精简版 ffmpeg 无法合成 mp4（改用完整静态构建）。

### 阶段小结：三重验证

| 验证层 | 能发现什么 | 发现数 |
|--------|-----------|--------|
| 自动化测试 | 逻辑正确性、权限边界、数据一致性 | 开发期修掉 2 个 |
| 浏览器实测 | 状态时序、渲染、交互 | 3 个 |
| 真实依赖联调 | 外部服务的真实行为（延迟、格式、限流、截断） | 4 个 |

**结论：三者缺一不可。测试全绿只是及格线，真的跑起来才是交付线。**

---

## 3. 功能清单：已完成 / 待办

### 3.1 已完成（DONE）

#### 用户与权限

- [x] 邮箱密码注册，主流后缀白名单校验（前后端各一次）
- [x] bcrypt 哈希存储密码，拒绝明文
- [x] JWT 登录，有效期 7 天
- [x] 登录失败区分「邮箱未注册」/「密码错误」
- [x] `token_version` 主动失效机制 `[S-2]`：改密后所有旧 Token 立即失效
- [x] 用户自行修改密码（改密后换发新 Token，当前设备不被登出）
- [x] 密码重置申请，同邮箱 10 分钟限一次 `[M-4]`
- [x] RBAC：普通用户 / 管理员两级角色，路由级守卫
- [x] 账号禁用后 Token 立即不可用，且无法再登录

#### 知识库

- [x] 多文件上传，单文件 ≤ 50MB、单次 ≤ 10 个
- [x] 四种格式解析：PDF（PyMuPDF + pdfplumber 兜底）、DOCX（含表格）、TXT、Markdown
- [x] 字符集自动识别（UTF-8 / GBK / Big5），中文优先的可读性打分
- [x] 扫描版 PDF 按页判定（单页有效字符 < 40）并触发 OCR
- [x] OCR 引擎自动探测：PaddleOCR 优先 → Tesseract 回退 → 均无则明确失败并入失败队列
- [x] 三级边界切分（段落 → 句子 → 字符），重叠可配，强制 `overlap < chunk_size`
- [x] Qwen3-Embedding-8B 向量化，批大小 16
- [x] 向量 Metadata 五要素强制写入 `[S-3]`
- [x] 每用户独立 Chroma Collection（`col_user_{user_id}`）物理隔离
- [x] 上传接口立即返回，后台线程池异步解析
- [x] 五状态机流转 + `updated_at` 可观测 `[M-1]`
- [x] 删除文档同步清理向量、物理文件、元数据（有测试守护）
- [x] 文档列表分页、状态过滤、文件名搜索

#### 智能问答

- [x] 多轮对话 Query Rewrite（可配辅助模型）
- [x] 密集检索 Top-N（可配，默认 20）
- [x] 云端 Rerank Top-K（可配，默认 4~5），兼容 Cohere 与阿里云百炼响应结构
- [x] 系统提示词幻觉遏制（严格依据资料 / 资料不足明说 / 强制引用标记）
- [x] SSE 流式输出，四类事件：`chunk` / `title` / `done` / `error`
- [x] 首轮提问自动生成 15 字以内标题并实时推送
- [x] 引用溯源 `[I-3]`：PDF 标页码、TXT·MD 标片段序号
- [x] 前端 `[n]` 角标可点击 + 引用卡片 + 原文弹窗
- [x] 纯模型对话模式 `[S-4]`：跳过检索但保留历史上下文，`citations` 存 NULL
- [x] 三级超时降级 `[M-6]`，Rerank 降级时前端显示明确告警
- [x] 空正文保护：模型未产出内容时推 `error` 帧而非显示空白气泡
- [x] 用户可随时「停止生成」

#### 对话历史

- [x] 消息持久化（含引用 JSON），时间有序 ID 保证时序稳定
- [x] 会话列表按最近活跃排序、标题模糊搜索、分页
- [x] 最新回答前 60 字预览 `[I-2]`
- [x] 手动重命名（就地编辑）
- [x] 逻辑删除
- [x] 越权访问统一返回 404 而非 403

#### 管理后台

- [x] 用户列表（含文档数、最后登录时间），邮箱模糊搜索
- [x] 角色切换、启用禁用，两条防呆规则（不能降级/禁用自己）
- [x] 密码重置申请列表 + 一键生成临时密码（仅显示一次）
- [x] 系统配置热更新：LLM / 辅助模型 / Embedding / Rerank / 切片 / 检索参数
- [x] API Key 三重保护 `[S-1]`：AES-256-GCM 加密存储、响应脱敏、留空不修改
- [x] 运行监控：8 项指标 + 每日趋势图 + 文档处理失败队列
- [x] 配置 5 秒 TTL 缓存 + 写入主动失效

#### 工程与交付

- [x] 77 个 pytest 用例，零外部依赖
- [x] 端到端浏览器冒烟脚本（`npm run e2e`）
- [x] `DEV_MOCK_AI` 离线模式，无 Key 亦可跑通全链路
- [x] 向量库抽象层 + 本地兜底实现（无 chromadb 时自动降级）
- [x] MySQL / SQLite 双兼容
- [x] README（含实测配置表、部署清单、故障排查）
- [x] DDL v1.3 + 变更记录（每处改动附理由）
- [x] 演讲文稿、演示 PPT、演示视频及其可复现脚本

### 3.2 待办（TODO）

按优先级排序，标注预估工作量与依赖。

#### P0 —— 影响验收

| 项 | 说明 | 预估 | 依赖 |
|----|------|------|------|
| **检索时延优化至 < 2 秒** | 当前 4.3 秒。首选同区域部署（零代码改动），其次本地 Embedding 模型 | 1–3 天 | 需要目标环境 |
| **扫描版 PDF OCR 实测** | 代码路径完整但未在装有 OCR 引擎的环境验证，SLA（100 页 < 120 秒）未确认 | 1 天 | 需装 PaddleOCR |
| **并发压测** | PRD 要求 ≥ 10 并发，架构支持但未实测 | 1 天 | 需压测工具 |

#### P1 —— 工程完善

| 项 | 说明 | 预估 |
|----|------|------|
| 配置自检 | 管理员保存配置后自动跑一次探测调用，把各环节成败与耗时直接反馈在界面上。缺陷 4 那类「配错模型名」的问题就能在保存时暴露，而不是潜伏到用户提问 | 1 天 |
| 前端单元测试 | 当前只有端到端冒烟，缺组件级测试（Vitest + Testing Library） | 2–3 天 |
| 结构化日志 | 当前用标准 logging，建议改 JSON 结构化并接入日志平台 | 1 天 |
| 请求限流 | 防止单用户刷爆模型额度 | 1 天 |
| 数据库迁移工具 | 引入 Alembic，替代手工维护 DDL 与变更记录 | 1 天 |
| Docker Compose | 一键拉起 MySQL + 后端 + 前端 | 1 天 |
| CI 流水线 | 提交即跑 pytest + tsc + build | 0.5 天 |

#### P2 —— 功能增强

| 项 | 说明 | 预估 |
|----|------|------|
| 混合检索 | 向量检索 + BM25 关键词融合。纯向量对精确匹配（数字、人名、专有名词）不敏感 | 3–5 天 |
| 知识库分组 | 按课题分组，提问时指定检索范围 | 3 天 |
| 更多格式 | PPTX、HTML、EPUB、LaTeX | 2–3 天 |
| 矛盾检测 | 检索到结论冲突的片段时主动提示用户 | 3 天 |
| 答案导出 | 导出为 Markdown / Word，带完整引用 | 2 天 |
| 多模态 | 利用论文中的图表信息 | 2 周+ |

#### P3 —— 平台化

| 项 | 说明 | 预估 |
|----|------|------|
| **知识图谱** | 见 §7 完整设计方案 | 3–6 周 |
| 协作知识库 | 课题组共享 + 细粒度权限 | 2 周 |
| 私有化部署 | 模型、向量库、数据库全本地化 | 2 周 |
| 向量库迁移 Milvus | 抽象层已就位，新增实现类即可 | 3 天 |

---

## 4. 运行时业务逻辑

### 4.1 文档入库链路

```
用户选择文件
   │
   ▼
POST /api/v1/docs/upload
   │  ① 校验：数量 ≤10、单文件 ≤50MB、扩展名白名单、内容非空
   │  ② 落盘：{UPLOAD_DIR}/{user_id}/{doc_id}{ext}
   │         └─ 文件名用 doc_id 而非原始名，杜绝路径穿越与重名覆盖
   │  ③ 写 documents 表，status=pending
   │  ④ 立即返回（不等待解析）
   ▼
后台线程池（默认 4 worker）
   │
   ├─ status=parsing ──► 解析
   │     PDF  ─► 逐页提取，页码随文本一起保留
   │           └─ 单页有效字符 <40 ─► 渲染为图像 ─► OCR
   │                                    └─ 引擎缺失 ─► ParseError
   │     DOCX ─► 段落 + 表格
   │     TXT  ─► 字符集识别（UTF-8 严格 → 候选打分）
   │     MD   ─► 去排版符号，保留标题文字
   │
   ├─ 切分：读取 system_configs 的 chunk_size / overlap
   │     段落边界 → 句子边界 → 字符硬切，全局连续 chunk_index
   │
   ├─ status=vectorizing ──► Embedding API（批大小 16）
   │
   ├─ 写入 Chroma col_user_{user_id}
   │     每条 Metadata 必含：doc_id / user_id / file_name / page / chunk_index
   │
   └─ status=ready  或  status=failed（写 usage_logs，带 ref_id=doc_id）
```

**关键点**：任一环节抛错都会把状态置为 `failed` 并写入失败日志，
不会让文档永远停在中间态。前端通过 `updated_at` 判断是否卡滞。

### 4.2 问答链路

```
POST /api/v1/chat/query  {session_id, query, enable_rag}
   │
   ├─ 校验会话归属（不属于本人 → 404）
   │
   ├─ 加载历史（最近 N 轮，N 可配）
   │
   ├─ 用户消息立即落库（保证异常时提问不丢失）
   │
   ├─ enable_rag = true？
   │   │
   │   ├─ 是 ─► Query Rewrite（辅助模型，超时 3s → 降级用原问题）
   │   │      └─► 问题向量化 ─► Chroma 检索 Top-N（仅本人 Collection）
   │   │           └─► Rerank Top-K（超时 3s → 降级，done 帧带 warnings）
   │   │                └─► 构造背景资料块 + RAG 系统提示词
   │   │
   │   └─ 否 ─► 纯模型系统提示词（仍带历史上下文）
   │
   ├─ 流式调用 LLM（max_tokens=4096，超时 30s）
   │   └─ 逐段 yield ─► SSE event: chunk
   │
   ├─ 正文为空？ ─► SSE event: error，不落库空消息，结束
   │
   ├─ 首轮提问？ ─► 辅助模型生成标题（超时 8s → 回退问题前 15 字）
   │                └─► SSE event: title
   │
   ├─ 助手消息落库（citations：RAG 模式存数组，纯模型模式存 NULL）
   │
   └─ SSE event: done  {message_id, citations, warnings}
```

**降级矩阵**：

| 环节 | 超时 | 降级后果 | 用户是否感知 |
|------|------|----------|-------------|
| Query Rewrite | 3s | 用原问题检索 | 否（精度略降） |
| Rerank | 3s | 用向量检索 Top-K | 是（黄色告警） |
| LLM 生成 | 30s | 推 error 帧 | 是（提示重试） |

### 4.3 权限与隔离链路

```
请求 ─► 提取 Authorization: Bearer <JWT>
        │
        ├─ 签名/过期校验失败 ─► 401
        ├─ 用户不存在 ─────► 401
        ├─ status != 1 ─────► 403（账号已禁用）
        ├─ Token.token_version < DB.token_version ─► 401（密码已变更）
        │
        └─ 通过 ─► 业务层强制附加 user_id 过滤
                   ├─ 文档：documents.user_id == 当前用户
                   ├─ 会话：chat_sessions.user_id == 当前用户
                   └─ 向量：只打开 col_user_{当前用户}
                   
                   越权 ─► 统一 404（不用 403，避免资源 ID 被枚举）
```

### 4.4 配置生效链路

```
管理员保存配置
   │
   ├─ API Key 类字段 ─► AES-256-GCM 加密 ─► 存 config_value（enc::v1:: 前缀）
   ├─ 其他字段 ────► 直接存
   │
   ├─ 校验：overlap < chunk_size，否则 400
   │
   └─ invalidate_cache()
        │
        ▼
   下一次问答/入库读取配置
        │
        ├─ 缓存有效（< 5 秒）─► 直接用
        └─ 缓存失效 ─► 查库 ─► 补齐缺失的默认键 ─► 回填缓存
             └─ Key 类字段解密后仅在内存中使用，任何响应都不返回明文
```

### 4.5 数据流转全景

```
                    ┌──────────────┐
   原始文件 ────────►│ 本地文件系统 │  {UPLOAD_DIR}/{user_id}/{doc_id}{ext}
                    └──────────────┘
                            │ 解析
                            ▼
   文本块 ──切分──► 切片 ──向量化──► ┌──────────┐
                                    │  Chroma  │  col_user_{user_id}
                                    └──────────┘
                                          │ 检索
   提问 ──改写──► 向量化 ─────────────────┘
                            │
                            ▼ Top-N
                      ┌──────────┐
                      │  Rerank  │
                      └──────────┘
                            │ Top-K
                            ▼
                    背景资料 + 提示词 ──► LLM ──► 流式回答 + 引用
                            │                        │
                            ▼                        ▼
                    ┌──────────────┐        ┌──────────────┐
                    │  usage_logs  │        │chat_messages │
                    │（耗时/Token）│        │（含引用JSON）│
                    └──────────────┘        └──────────────┘
```

---

## 5. 已知限制与技术债

### 5.1 检索时延未达标（最重要）

**现状**：向量检索 2.4 秒 + Rerank 1.9 秒 ≈ 4.3 秒，PRD 指标是 < 2 秒。

**归因**：
1. **网络往返是大头**——测试环境在容器内经代理出网，再到服务商还有公网往返。
   2.3 秒的 Embedding 调用里绝大部分是网络时间而非计算时间。
2. Embedding 与 Rerank 都是云端 API，每次提问各发一次 HTTP 请求。

**优化路径（按性价比）**：

| 方案 | 预期收益 | 成本 |
|------|---------|------|
| 与模型服务同区域部署 | 最大，可能直接达标 | 零代码改动 |
| 本地 Embedding 模型（如 bge-small） | 向量化压到毫秒级 | 需要 GPU |
| 查询向量缓存 | 重复问题直接命中 | 半天开发 |
| Top-N 从 20 降到 10 | 减少 Rerank 输入 | 配置项，已可调 |

**可观测性**：每次外部调用的耗时都写入 `usage_logs`，管理后台可查——
这个数字是可测量、可归因、可优化的。

### 5.2 其他限制

| 限制 | 影响 | 缓解 |
|------|------|------|
| 扫描版 OCR 未实测 | SLA 未确认 | 装 PaddleOCR 后按 100 页样本实测 |
| 并发未压测 | 10 并发指标未确认 | 用 locust 或 k6 压测 |
| 无请求限流 | 单用户可刷爆模型额度 | P1 待办 |
| 前端缺组件测试 | 重构风险 | P1 待办 |
| 手工维护 DDL | 迁移易出错 | 引入 Alembic |
| 单机部署 | 无横向扩展 | Chroma 换 Milvus + 无状态化 |
| 登录失败区分邮箱/密码 | 邮箱可被枚举 | 对公网开放前改为统一提示 + 失败次数限制 |
| 加密密钥存环境变量 | 密钥管理递归问题 | 生产接 KMS / Vault |

### 5.3 刻意保留的设计取舍

这些不是债，是**被想过之后选择保留**的：

| 取舍 | 理由 |
|------|------|
| 同步 SQLAlchemy | 瓶颈在外部 API 不在数据库，异步只增加调试成本 |
| 逻辑删除会话 | 便于审计追溯 |
| 越权返回 404 | 防止资源 ID 枚举 |
| 密码重置走人工流程 | 无邮件服务，资源约束下的合理选择 |
| 切片参数不回溯历史 | PRD 明确要求，且回溯需要全量重建向量 |

---

## 6. 未来扩展路线

### 短期（1–2 个月）

- 检索时延优化至达标
- 配置自检功能
- 混合检索（向量 + BM25）
- 前端组件测试 + CI 流水线
- Docker Compose 一键部署

### 中期（3–6 个月）

- 知识库分组与检索范围指定
- 更多文档格式（PPTX / HTML / EPUB / LaTeX）
- 矛盾检测与提示
- 答案导出（带完整引用）
- **知识图谱一期**（见 §7）

### 长期（6 个月以上）

- 知识图谱二期：GraphRAG 融合检索
- 协作知识库：课题组共享 + 细粒度权限
- 多模态：论文图表的理解与引用
- 私有化部署方案
- 向量库迁移 Milvus / Qdrant

### 领域迁移

当前架构不是学术专用的。把知识库内容替换掉，即可迁移到：

| 领域 | 知识库内容 | 需额外做的 |
|------|-----------|-----------|
| 企业知识管理 | 内部文档、规章、会议纪要 | 组织架构级权限 |
| 法律检索 | 法条、判例、司法解释 | 法条引用关系图谱、时效性标注 |
| 医疗辅助 | 诊疗指南、文献 | 合规审查、免责声明、术语标准化 |
| 智能客服 | 产品手册、工单历史 | 多轮引导、工单系统对接 |

迁移成本低的原因：模型层与向量库层都做了抽象，切换服务商或存储只需改配置或加实现类。

---

## 7. 知识图谱：实现方案设计

> **状态：未实现，本节为设计方案。**
> 当前系统的检索完全基于向量相似度，不含任何图结构。下面记录的是完整的落地设计，
> 供后续迭代直接使用。

### 7.1 为什么需要知识图谱

纯向量 RAG 有三个结构性短板，它们不是调参能解决的：

**短板一：无法回答聚合型问题。**
「我库里所有讨论过注意力机制的论文，各自的实验数据集是什么？」
——这需要跨多篇文档做结构化聚合，而向量检索只会返回最相似的几个片段。

**短板二：无法追溯多跳关系。**
「A 方法基于 B 理论，B 理论最早由谁提出？」
——答案分散在两篇文档里且没有词面重叠，向量检索一跳就断了。

**短板三：无法呈现全局结构。**
用户想知道「我这 50 篇文献大致分几个流派、彼此什么关系」，
向量检索给不出全局视图。

知识图谱把「实体 + 关系」显式建模，正好补上这三块。

### 7.2 数据模型设计

#### 实体（节点）

| 类型 | 说明 | 关键属性 |
|------|------|----------|
| `Document` | 文档 | doc_id、file_name、user_id、上传时间 |
| `Section` | 章节 | 标题、层级、所属 doc_id、页码范围 |
| `Chunk` | 切片 | chunk_index、page、文本（复用现有切片） |
| `Concept` | 概念/术语 | 名称、别名集合、定义摘要 |
| `Method` | 方法/模型 | 名称、提出年份、别名 |
| `Dataset` | 数据集 | 名称、规模 |
| `Metric` | 评价指标 | 名称、单位 |
| `Author` | 作者 | 姓名、机构 |
| `Paper` | 外部论文（被引用但未上传） | 标题、作者、年份 |

#### 关系（边）

| 关系 | 起点 → 终点 | 来源 |
|------|------------|------|
| `CONTAINS` | Document → Section → Chunk | 解析阶段结构化产出 |
| `MENTIONS` | Chunk → Concept/Method/Dataset | LLM 抽取 |
| `PROPOSES` | Document → Method | LLM 抽取 |
| `BASED_ON` | Method → Method/Concept | LLM 抽取 |
| `EVALUATED_ON` | Method → Dataset | LLM 抽取 |
| `ACHIEVES` | Method → Metric（带数值属性） | LLM 抽取 |
| `CITES` | Document → Paper | 参考文献解析 |
| `AUTHORED_BY` | Document → Author | 元数据解析 |
| `SIMILAR_TO` | Concept → Concept（带相似度） | 向量聚类 |

**关键约束**：每条 `MENTIONS` 边必须携带 `chunk_id`——
这样图谱推理出的每一个结论都能回溯到原文，
**溯源能力不能因为引入图谱而丢失**，这是本产品的红线。

### 7.3 三条构建路径

三条路径成本与可靠性递减，建议按顺序落地。

#### 路径一：结构化关系（零模型成本，最可靠）

从现有解析流程直接产出，不需要任何额外的模型调用：

- `Document -CONTAINS-> Section -CONTAINS-> Chunk`：
  Markdown 的标题层级、PDF 的书签/大纲、DOCX 的样式层级都能直接给出
- `Document -AUTHORED_BY-> Author`：PDF 元数据、DOCX 属性
- `Document -CITES-> Paper`：解析参考文献区块（正则 + 结构模板）

**价值**：即便只有这一层，也能支撑「按章节检索」「按作者聚合」「引用网络可视化」。

#### 路径二：LLM 实体关系抽取（主力）

对每个切片调用一次 LLM，用**受约束的 JSON 输出**抽取三元组：

```
输入：切片文本 + 已知实体表（用于对齐，避免重复造实体）
输出：{
  "entities": [{"name": "多头注意力", "type": "Method", "aliases": ["Multi-Head Attention"]}],
  "relations": [{"head": "多头注意力", "rel": "BASED_ON", "tail": "自注意力机制",
                 "evidence": "原文片段"}]
}
```

**工程要点**：

1. **复用已有的辅助模型配置**（`llm.aux_model`）——抽取是高频短任务，
   用小模型成本可降一个数量级。这一点已经在阶段五的教训里验证过了。
2. **增量抽取**：只对新上传文档的切片抽取，不全量重跑。
3. **异步低优先级**：放进独立队列，不阻塞文档「已就绪」状态——
   用户上传完应该立刻能问答，图谱慢慢建。
4. **实体对齐**：抽取时把已有实体表传给模型做对齐；
   落库前再用 Embedding 相似度做一次去重（阈值 0.92），避免
   「自注意力」「Self-Attention」「self attention」变成三个节点。
5. **置信度**：每条边记录来源模型与置信度，低置信度边可在检索时降权或过滤。

#### 路径三：向量聚类补边（低成本增强）

对已有的 `Concept` 节点向量做聚类，为同簇概念补 `SIMILAR_TO` 边。
用于「相关概念推荐」和图谱可视化时的社区划分。

### 7.4 存储选型

| 方案 | 优点 | 缺点 | 建议 |
|------|------|------|------|
| **MySQL 邻接表** | 零新增依赖，与现有事务一致，运维简单 | 多跳查询需递归 CTE，深度 > 3 时性能差 | ✅ **一期首选** |
| Neo4j / NebulaGraph | 原生图查询，多跳性能好，生态成熟 | 新增独立服务，运维与备份成本 | 二期视规模引入 |
| 复用 Chroma metadata | 零新增 | 无法表达关系，只能做属性过滤 | ❌ 不可行 |

**一期表结构建议**（与现有 DDL 风格保持一致）：

```sql
CREATE TABLE `kg_entities` (
    `id`         VARCHAR(64)  NOT NULL COMMENT '实体唯一ID',
    `user_id`    INT          NOT NULL COMMENT '所属用户（图谱同样按用户隔离）',
    `type`       VARCHAR(32)  NOT NULL COMMENT 'Concept|Method|Dataset|Metric|Author|Paper',
    `name`       VARCHAR(255) NOT NULL COMMENT '规范名称',
    `aliases`    JSON                  COMMENT '别名数组',
    `summary`    TEXT                  COMMENT '定义摘要',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_kg_ent_user_type` (`user_id`, `type`),
    KEY `idx_kg_ent_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `kg_relations` (
    `id`         BIGINT       NOT NULL AUTO_INCREMENT,
    `user_id`    INT          NOT NULL,
    `head_id`    VARCHAR(64)  NOT NULL COMMENT '起点实体',
    `rel`        VARCHAR(32)  NOT NULL COMMENT '关系类型',
    `tail_id`    VARCHAR(64)  NOT NULL COMMENT '终点实体',
    `doc_id`     VARCHAR(64)           COMMENT '来源文档',
    `chunk_id`   VARCHAR(64)           COMMENT '来源切片——溯源用，不可为空的业务约束',
    `confidence` FLOAT        NOT NULL DEFAULT 1.0,
    `props`      JSON                  COMMENT '关系属性，如 ACHIEVES 的数值',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_kg_rel_head` (`user_id`, `head_id`, `rel`),
    KEY `idx_kg_rel_tail` (`user_id`, `tail_id`, `rel`),
    KEY `idx_kg_rel_doc` (`doc_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**注意**：图谱同样按 `user_id` 隔离，与现有的三层隔离策略保持一致。
删除文档时需级联清理 `doc_id` 对应的边，以及清理因此变成孤儿的实体——
这一点必须写测试守护，否则会重演「向量残留」那类问题。

### 7.5 与 RAG 的融合方式（GraphRAG）

图谱建好之后，检索链路从「一路」变成「三路召回 + 融合」：

```
用户提问
   │
   ├─ 路 A：向量检索（现有）──────────► Top-N 切片
   │
   ├─ 路 B：图谱检索（新增）
   │        ① LLM 从问题中抽取实体
   │        ② 图中定位实体节点
   │        ③ 沿关系扩展 1–2 跳，取子图
   │        ④ 子图每条边回溯到 chunk_id ──► 相关切片
   │
   ├─ 路 C：BM25 关键词检索（可选）────► 补充精确匹配
   │
   ▼
融合去重（按 chunk_id）
   │
   ▼
Rerank 精排 ──► Top-K ──► LLM 生成
                            │
                            └─► 引用列表同时给出：
                                 · 文本引用（现有）
                                 · 关系引用（新增）：
                                   「A 基于 B」出自《X》第 3 页
```

**三类问题的路由策略**：

| 问题类型 | 主力路径 | 示例 |
|---------|---------|------|
| 事实型 | 向量检索 | 「自注意力机制的作用是什么」 |
| 关系型 | 图谱检索 | 「A 方法基于哪些理论」 |
| 聚合型 | 图谱查询 + 摘要 | 「所有用到 BLEU 指标的方法有哪些」 |

可以先用一个轻量分类器（或直接让辅助模型判断）做路由，
也可以三路全跑然后融合——后者简单可靠，代价是延迟增加。

**全局摘要能力**：对图谱做社区发现（Leiden 算法），
为每个社区生成摘要，用于回答「我这批文献大致分几个方向」这类全局问题。
这是微软 GraphRAG 的核心思路，值得借鉴。

### 7.6 分阶段落地计划

| 阶段 | 内容 | 工作量 | 交付价值 |
|------|------|--------|---------|
| **一期** | 路径一（结构化关系）+ MySQL 存储 + 文档结构可视化 | 1 周 | 章节导航、引用网络图 |
| **二期** | 路径二（LLM 抽取）+ 实体对齐 + 异步队列 | 2 周 | 实体检索、关系问答 |
| **三期** | GraphRAG 融合检索 + 关系引用 | 2 周 | 关系型问题的准确率提升 |
| **四期** | 社区发现 + 全局摘要 + 图谱可视化界面 | 2 周 | 全局视图、研究方向概览 |

**建议**：一期与二期之间做一次效果评估——
构造 30 道关系型问题，对比「纯向量」与「向量 + 图谱」的准确率。
如果提升不明显，说明当前的文献规模还不足以体现图谱价值，可以推迟后续阶段。
**不要为了做图谱而做图谱。**

### 7.7 成本与风险

| 风险 | 说明 | 应对 |
|------|------|------|
| **抽取成本** | 每个切片一次 LLM 调用，一份 100 页文档约 200 切片 | 用辅助小模型；异步低优先级；只对新文档增量抽取 |
| **抽取质量** | LLM 会抽出错误或幻觉三元组 | 强制 `evidence` 字段回溯原文；置信度过滤；人工抽检 |
| **实体爆炸** | 同一概念多种写法造成节点冗余 | Embedding 相似度去重 + 别名合并 |
| **维护复杂度** | 图谱与向量库需保持一致 | 删除文档时级联清理，写测试守护 |
| **收益不确定** | 小规模文献库可能感知不到提升 | 一期后先评估再决定是否继续 |

---

## 8. 附录：关键决策记录

以 ADR（Architecture Decision Record）风格记录，便于后续接手者理解「为什么是这样」。

### ADR-01：同步 SQLAlchemy 而非异步

- **背景**：FastAPI 原生支持异步，社区默认推荐异步 ORM
- **决策**：使用同步 SQLAlchemy
- **理由**：性能瓶颈在外部 API（LLM 生成 8 秒）而非数据库（毫秒级）；
  FastAPI 会把同步路由自动放进线程池，不阻塞事件循环；同步代码调试成本显著更低
- **代价**：极高并发场景下线程池可能成为瓶颈
- **重新评估条件**：单实例并发超过 100 时

### ADR-02：SSE 而非 WebSocket

- **决策**：问答流式输出用 SSE
- **理由**：单向推送场景；基于普通 HTTP 无需协议升级；断线自动重连；过反向代理坑少
- **代价**：无法在流中反向发消息（当前不需要）

### ADR-03：向量物理隔离而非逻辑隔离

- **决策**：每用户独立 Chroma Collection
- **理由**：逻辑隔离依赖每次查询都不写错过滤条件，只要漏一处就是跨用户泄露；
  物理隔离下别人的数据根本不在检索范围内
- **代价**：用户数极多时 Collection 数量膨胀
- **重新评估条件**：用户数超过一万

### ADR-04：时间有序 ID 而非改 DDL

- **背景**：`DATETIME` 只精确到秒，同秒写入的消息排序不确定
- **决策**：ID 改为纳秒时间戳前缀 + 随机后缀
- **理由**：零 DDL 改动；`ORDER BY created_at, id` 即稳定；对 MySQL 与 SQLite 同样有效
- **代价**：ID 长度增加（仍远小于 VARCHAR(64) 上限）

### ADR-05：新增辅助任务模型配置

- **背景**：推理型主模型生成 15 字标题耗时 19.9 秒，而预算是 8 秒
- **决策**：新增 `llm.aux_model`，留空则复用主模型
- **理由**：主回答质量与辅助任务速度是两个正交诉求，不该由同一个模型承担；
  向后兼容，不配置则行为完全不变
- **数据**：配置小模型后改写 2.4 秒、标题 2.1 秒，成本亦下降

### ADR-06：知识图谱一期用 MySQL 而非图数据库

- **决策**：邻接表存图，不引入 Neo4j
- **理由**：一期只做 1–2 跳查询，递归 CTE 足够；避免新增独立服务的运维成本；
  与现有事务保持一致
- **重新评估条件**：需要 3 跳以上查询，或边数超过千万级

---

> **文档维护约定**：每完成一个 TODO 项，将其移入 DONE 并标注完成日期；
> 每做出一个影响架构的决策，追加一条 ADR。
# 当前状态（2026-10-13）

Phase 1/2 维护基线保留；Phase 3–5 新增单一文献比较场景的后端闭环。研究任务可以持久化、单步执行、暂停/恢复/取消，证据和产物具有版本与来源定位。真实实验暴露的数值误判已用独立门禁阻断，但最新在线尝试仍有响应协议失败；人工质量验收、前端工作区和正式训练未完成。详见本文 R19、[接口与边界](research_backend_mvp.md)、[实验报告](research_comparison_report.md)。下文“最新”及测试数字如来自旧轮次，均按对应日期理解。



## R19：Phase 3–5 文献比较后端与真实失败修复（2026-10-13）

### 工作范围与依据

按阶段继续 1–5，并遵循此前“先证明研究价值”的范围冻结：核对 git 状态及真实模型/索引接口，保留未提交文献试点和用户修改；只补 Phase 2 只读快照入口，不追加队列、租约、GC。采用 codebase-design 的小接口/深模块思路，领域模型、证据、图谱、工具、编排、存储和配置适配分开，模型/向量依赖可注入；不新增依赖。实现与完整文件清单见 [后端切片](research_backend_mvp.md)。

### 实现过程和验证发现

1. 定义来源绑定的证据、Citation、关系、实体/提及及最多两跳图谱接口。MemoryGraphStore 校验来源后原子替换；按所有者/语料隔离。HybridEvidenceEngine 合并向量/局部关系，图谱故障回退。
2. 增加固定 3–5 篇比较计划、严格工具和 checkpoint；CAS 领取及迟到结果拒绝、控制与预算先于外部调用。SQL payload 摘要校验；单步 HTTP/CLI 显式执行，不伪装为自主后台调度。
3. 接来源/模型冻结和现有 verified 索引；查询检查原文件 SHA、chunk set、endpoint 和向量来源，工具结束再检查新鲜度。暂停/取消不依赖模型或向量服务。
4. 增加准确原文核验、机器支持判定、比较表/缺口/冲突和 quote-specific 页码来源。当前模型判断明确 machine_review_only，产物可为 partial。
5. 初版 runtime fixture 提前替换配置导致上传缺 chunk_size；调整 fixture 顺序并通过 Local/Chroma 相关测试。初版父片贪心展开导致 q12 已选证据丢失；改 evidence-floor-v2 并补性质测试，保留选定子片。
6. 真实网络试验暴露连接/读超时；caller-owned HTTP 连接复用、每调用明确 deadline、简短模型协议和最多一次显式重试。失败全部留下 ledger，没有把超时无限续跑。
7. 真实旧核验器误判 38.2 受到 38.5 支持；加入独立数字门禁、严格唯一排版等价引用定位和回归测试。旧版本身份保持可读，但不能跳过新核验继续 compose。修复回放没有额外 API，也不冒充独立语义审计。
8. MySQL 隔离测试先因缺本地 .env、再因保护规则将外键 ON DELETE CASCADE 误作删除语句失败；修正输入/保护判断，新库 DDL、中文 LONGTEXT 和 checkpoint CAS 通过。未删除失败测试库、未修改业务数据库。

### 实测而非完成声明

三篇官方论文、原文摘要与 CC BY 4.0 出处，在线 Embedding/抽取/核验，七次尝试、缓存向量条件、SQLite 版本回滚、MySQL 有限测试均见 [真实实验报告](research_comparison_report.md)。共 31 模型请求/9 网络失败/33406 已报 Token，另列诊断调用；费用及失败用量未知。第 6 次旧成功表有数值错误，第 7 次严格 schema 失败未产物。当前修复表仅 3/6 机器支持、9 缺口，不通过人工质量门槛。

有界父片固定候选回放平均锚点 41.67%→47.92%，完整证据 5/16→6/16，q09/q12 未改善。真实关系在首轮检索之后抽取，不能声称图谱多跳收益。既有 Phase 1 页级解析未升级为版式抽取；Phase 2 未达到生产验收；Phase 6/7 没有新实现。

### 测试与交付记录

后端 Python 3.11，在 project/backend：

```powershell
python -m pytest -o addopts='' -q --tb=short --show-capture=no
python -m pytest tests/test_literature_pilot.py tests/test_research_evidence.py tests/test_research_agent.py tests/test_research_runtime.py -o addopts='' -q --tb=short --show-capture=no
```

最终全量：**432 passed / 500.17s**（无失败、无跳过）。最后增补引用来源/历史兼容/暂停不依赖向量服务，均纳入本次最终全量；此前 425/427/429 项通过为阶段记录，不替代最终结果。compileall、git diff --check、公开 JSON 解析和 8 份文档本地链接/围栏检查通过。整理时将历史记录的一处本地密码改为省略标记；公开新增代码及结果不含凭据。

无新依赖、前端或正式训练；研究迁移仅应用隔离测试，Phase 2 结构门禁不包含 008。业务原文件/索引/active 未被实验覆盖，artifacts 保留且不纳入结果包，本轮未提交推送。下一步处理 FiD 引用和 REALM 严格协议，人工核对 20 题/比较表，再决定最小前端路径；不自动延伸索引基础设施。


## R20：引用编号、真实响应超限与上下文缺口（2026-10-13）

按用户选定的三项优先级继续。先检查 git 状态保留已有改动，使用 diagnosing-bugs 建立抽取/工具边界反馈：三个用例先失败，新增协议与安全诊断后通过。历史第 7 次响应未保存，不假设其具体原因。本轮在线重跑明确得到 REALM claims:too_long；新增五条候选用例先失败，将 wire 候选上限八与最终四个 facet 分离后通过，九条输入仍失败。

新增 protocol.py、test_research_citations.py、diagnose_evidence_gaps.py；修改 artifacts/model/tools、研究 API 配置和试点脚本。来源引用编号避免模型抄写引文，目录不扩大上下文；严格字段/未知 ID/数字/语义校验保留。JSON 模式显式设置，历史协议与默认 RAG3 不变。诊断不含未识别字段、模型原文、错误消息或凭据。

受限真实试验及复制 checkpoint 续接共 9 请求/1 网络失败/20203 已报 Token，最后完成三篇论文比较。在线 6/12 机器支持并不可靠：二次 AI 来源复核撤下两条 REALM 条件/支持不足，展示版仅 4 条、8 缺口；原始决定保留。该复核不是人工验收或生产语义核验自动修复。q09 的缺失父片需另加 1363 字符而只剩 83；q12 的 DPR FAISS 锚点未入候选父片。诊断使用 AI 标签，仅离线，不改变生产选择。

完整文件清单、模型/恢复预算、失败、署名及结果链接见 [引用修复记录](research_citation_fix.md)。相关 Agent/runtime/新组 35 passed / 24.84s；最终 backend `python -m pytest -o addopts='' -q --tb=short --show-capture=no`：**440 passed / 470.62s**，无失败/跳过。compileall、git diff --check、公开 JSON、文档链接/围栏及凭据检查通过。没有新依赖、调度基础设施、前端、训练、业务库迁移或 GitHub 推送；所有失败目录与原用户修改保留。


## R21：GitHub 交付检查（2026-10-14）

按用户要求整理并提交 Phase 3–5 文献比较后端、真实文献试点、引用协议修复、回归测试与进度记录。提交前 main 与 origin/main 同为 476127b，无远程分叉；采用普通提交和非强制推送。既有 R18–R20 的“未提交”属于各轮历史状态，不改写实验与测试记录。

交付前核对 61 个项目变更文件；最新测试记录的受测代码 SHA 全部与当前文件匹配，重新收集 440 项测试通过。最近一次全量为 440 passed / 470.62s，本次未改变受测代码，不重复全量。公开 JSON、凭据扫描和差异检查通过。artifact 截图、原始 PDF、实验数据库、向量、原始失败目录和 .env 不纳入提交；用户本地截图保留。

GitHub 同步不代表生产上线、业务库迁移或人工质量验收通过。仍保留部分产物、8 项缺口及 q09/q12 的未改善记录，不把后续前端/Neo4j/训练写成完成。具体提交编号与远程结果以 main 的 Git 历史为准。
