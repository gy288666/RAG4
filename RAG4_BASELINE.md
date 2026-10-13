# RAG4 基线记录

> 记录日期：2026-09-14

> 最近代码交付：2026-09-16，`4b0e1dd feat: implement RAG4 structured chunking engine` 已按用户请求推送至 GitHub main。下文 Phase 1 中“未提交/推送”描述的是开发完成、发布之前的时点；发布后的过程与当前进度见 [开发过程记录](project/docs/development_process.md)。

## 当前基线

RAG4 当前以 `project/` 下导入的 RAG3 代码作为可运行基线。模型运行时、训练脚手架与 Phase 1 结构化切分已经接入，默认仍使用 RAG3 切分；Research Agent、知识图谱和混合证据引擎尚未实现，这些能力仍以根目录的 `RAG4_DEVELOPMENT_PLAN.md` 为设计目标。

## 目录与入口

- 后端：`project/backend/`，FastAPI 入口为 `app.main:app`。
- 前端：`project/frontend/`，Vite + React + TypeScript。
- 需求/API/部署文档：`project/docs/` 与 `project/deploy/`。
- 模型训练：`project/training/`，含硬负样本、Embedding、Reranker、LoRA-SFT 和排名评测入口。
- 后端测试：`project/backend/tests/`；训练数据管线测试位于 `project/training/tests/`。

## 已验证结果

- Node.js `v24.15.0`、npm `11.12.1`。
- `npm ci` 成功；安装后报告 3 个 audit vulnerabilities（2 moderate、1 high）。
- `npm run lint` 成功。
- `npm run build` 成功，产物输出到 `project/frontend/dist/`。
- 使用独立 Conda `rag4-py3.11` 环境（Python 3.11.15，按项目 requirements 安装，含 Chroma 0.5.23 与 pytest 8.3.4）执行后端 82 个测试成功；训练数据管线 2 个测试成功。

## 环境阻断

系统 Python 3.13 创建的 `project/backend/.venv` 安装依赖时会在 `chroma-hnswlib==0.7.6` 处因缺少 MSVC 编译工具失败；RAG4 不使用该环境。项目使用独立的 Conda `rag4-py3.11` 环境运行基线：

## 运行基线

前端：

```powershell
cd project/frontend
npm ci
npm run lint
npm run build
```

后端（固定 Python 3.11）：

```powershell
cd project/backend
conda create -n rag4-py3.11 python=3.11 -y
conda activate rag4-py3.11
python -m pip install -r requirements.txt
python -m pytest -q
```

本地模型推理另装 `requirements-local-models.txt`，正式训练另装
`project/training/requirements.txt`。Phase 1 的 ChunkingEngine 已在下节记录；
历史前端/训练检查仍是 2026-09-14 结果，不代表本次重新执行。

## 2026-09-16：Phase 1 结构化切分

修改前检查：工作区干净，分支 main，HEAD 为 `b59204b feat: integrate versioned local model fine-tuning`。本次基于此提交修改工作区，未提交/推送，也未修改用户已有文件变更。真实计划与基线文档位于仓库根目录。

### 新增接口

- `app.chunking.ParsedDocument` / `ParsedBlock`：文档身份、文件名、页数、结构类型、来源、parser_version。
- `DocumentChunk`：带版本身份的文本、编号、标题/章节、父子关系、PDF 页范围、表格/公式 metadata、原 block 字符定位和 token_count。
- `ChunkSet` / `ChunkStats`：父片/子片、完整配置、确定性 input_id/chunk_set_id、统计；`verify(document=None)` 校验 hash、关系、编号、预算及可选输入来源。
- `ChunkingEngine.split(document, config)`：可直接供后续索引任务调用，结果支持 JSON 往返。
- `TokenCounter` / `TokenizerTokenCounter` / `CharacterTokenCounter`：注入现有 tokenizer 或使用确定性 Unicode 字符计数 fallback，身份写入结果。
- `adapt_parse_result(...)`：兼容旧 ParseResult/TextBlock；`parse(..., structured=True)` 给 Markdown 增加可选标题/代码结构，旧 blocks 内容保持不变。
- 上传默认 `DOCUMENT_CHUNKING_ENGINE=rag3`；显式 rag4 后只索引子片。两种向量后端保存版本、ChunkSet ID 和结构 metadata，旧检索/SSE 引用兼容。已 ready 文档不会被上传处理函数重建。

详细字段、使用代码、配置、来源/offset 语义和回退操作见 [`project/docs/rag4_chunking.md`](project/docs/rag4_chunking.md)。

### 实际文件清单

新增：

- `project/backend/app/chunking/__init__.py`
- `project/backend/app/chunking/models.py`
- `project/backend/app/chunking/engine.py`
- `project/backend/app/chunking/adapter.py`
- `project/backend/tests/test_chunking_engine.py`
- `project/backend/tests/test_chunking_integration.py`
- `project/docs/rag4_chunking.md`

修改：

- `project/backend/app/core/config.py`
- `project/backend/.env.example`
- `project/backend/app/services/parser_service.py`
- `project/backend/app/services/document_service.py`
- `project/backend/app/services/vector_store.py`
- `project/backend/tests/conftest.py`
- `RAG4_DEVELOPMENT_PLAN.md`
- `RAG4_BASELINE.md`

`project/backend/app/services/chunking_service.py` 未修改。没有新增依赖、SQL schema 迁移、Graph/Agent/前端功能。沿用已固定的 Python 3.11 和 Pydantic 2.10.4；安装仍使用现有 requirements.txt。

### 本次实际验证

以下测试在 `E:\RAG4\project\backend` 执行，使用独立临时 SQLite/Chroma 目录和 Mock AI，不访问业务数据库，不需要外部模型 API。

修改前运行原有测试，退出码 0（82 项）。最终验证命令：

```powershell
& 'C:\Users\gy\.conda\envs\rag4-py3.11\python.exe' -m pytest tests/test_chunking_integration.py tests/test_chunking_engine.py -o addopts='' -q --tb=short
# 74 passed in 23.37s

& 'C:\Users\gy\.conda\envs\rag4-py3.11\python.exe' -m pytest -o addopts='' -q --tb=short
# 156 passed in 102.09s (0:01:42)
```

仓库根目录另执行 `git diff --check` 与对新增模块/改动服务的 `python -m compileall -q`，均退出码 0。Git 提示 LF/CRLF 转换，不是检查失败。

覆盖：普通段落/句子、超长中英文/无标点、标题层级与章节路径、父子关系、实际 PDF 页码、table/formula metadata、原文 span 回溯、版本/参数/tokenizer/parser/source 身份、可重复 JSON、篡改检测、空/异常输入、tokenizer 错误和非单调 token 计数、代码缩进、旧 split_blocks 金样。集成测试同时实际使用 LocalVectorStore 和 Chroma，验证 RAG3 默认输出/ID、RAG4 上传与检索/SSE、开关回退、ready 保护、切分失败保留既有索引、Embedding 数量不匹配拒绝写入。

测试开发中修复了测试 helper 名称错误，以及审查发现的非单调计数错误、Markdown C# 标题尾字符误删和代码缩进丢失；最终无失败或跳过测试。Chroma 0.5.23 在当前环境有既存 posthog telemetry 错误日志（capture 签名不兼容）；数据写入/查询测试通过，本次未改动该依赖。

### 限制与下一阶段

- 字符 fallback 不是目标模型真实 token 数；生产 tokenizer 需由调用者提供并固定版本，上传默认仍是 fallback。
- PDF/DOCX 的标题/表格/公式自动结构抽取未实现；Markdown 适配不是完整 AST。模型与引擎可承载/透传结构，不伪造已丢失信息。
- 完整父片存在于返回的 ChunkSet，尚无持久化及父片读取 API；上传只持久化子片及其 metadata。
- 只提供新上传算法开关回退，没有历史索引 active version/原子激活/版本回滚。向量写入中途失败的新文档可能留下部分记录；跨 SQL/向量库事务和失败 generation 清理由 Phase 2 实现。已有 ready 文档不重处理，不以新结果覆盖旧索引。
- 未做真实检索质量单变量评测；Graph、ResearchAgent、EvidenceVerifier、ArtifactComposer、研究工作区均未实现。

Phase 2 具体入口为 `adapt_parse_result` → `ChunkingEngine.split` → `ChunkSet.verify(document)`。前置工作：定义不可变 ChunkSet/父片存储、document_index_jobs 与 active version 的增量 schema；固定 source/parser/chunking/tokenizer/embedding 组合；独立 staging 写入并校验数量/维度/身份；验证后原子切换检索指针，旧版本保留并可回滚。并发、失败、取消、删除、重试测试和备份恢复演练通过后，才能开放历史文档批量重建。没有执行包含 DROP DATABASE 的初始化脚本。

## Phase 2.1：切分准备持久化（2026-09-16）

起点 `511cbbd`，本轮工作区新增 `DocumentIndexJob`、`StoredChunkSet` 及 `index_job_service.create_job/run_job/get_job/load_chunk_set`。完整父子片可持久化恢复；任务记录源 SHA-256、切分配置、结果身份、状态、错误分类及耗时。所有权校验、用户级幂等键、条件更新抢占、临时源文件快照和事务发布保护已实现。默认上传/检索没有切换，旧 ready 状态和向量在准备失败时保留。

新增 MySQL 建表脚本 `project/docs/migrations/002_chunk_preparation.sql`，无新增依赖。没有执行真实数据库迁移；MySQL 与备份恢复仍未验证。回退代码时保留新增表即可。

实际在 `E:\RAG4\project\backend` 执行：

```powershell
& 'C:\Users\gy\.conda\envs\rag4-py3.11\python.exe' -m pytest -o addopts='' -q
# 170 passed in 130.64s (0:02:10)
```

新增 14 项测试覆盖完整父子片恢复、幂等/版本隔离、权限与篡改检测、源文件变化/解析/空结果/落库失败、并发创建/执行和删除清理。模型及服务 compileall 通过。测试使用临时 SQLite/向量目录和 Mock AI，未访问用户业务数据库。

当前仅完成 Phase 2 首个垂直切片。新任务 succeeded 不代表索引激活；尚无公共 HTTP 接口、后台调度、租约恢复、向量 staging、批量重建或 active version。后续从 `load_chunk_set` 开始冻结 Embedding 并构建独立 staging，通过完整性验证后再接入激活/回滚。详细契约见 [切分准备说明](project/docs/index_preparation.md)。

## Phase 2.2：独立 staging 与真实模型验证

在 Phase 2.1 工作区继续开发，新增 `IndexBuild`、冻结的 `EmbeddingSpec` 和 `create_build/run_build/get_build`。Local/Chroma 增加完整 `read_records` 回读接口。只在独立命名空间写入，验证 ID/数量/文本/来源/维度/向量值后保存 validated manifest；写入、验证或 SQL 发布失败保持旧索引可用。重复执行不会重复调用模型，重试使用新的 namespace。MySQL 发布与删除使用文档行锁。

新增 `003_index_builds.sql`、`scripts/validate_index_staging.py` 和 33 项测试，无新增依赖。API Key 仅在执行期间传入，没有持久化到模型配置或 manifest。

本次实际测试（backend 目录）：

```powershell
python -m pytest tests/test_index_builds.py -o addopts='' -q --tb=short
# 首批 31 passed in 53.52s
python -m pytest -o addopts='' -q --tb=short
# 201 passed in 177.52s
python -m pytest tests/test_index_builds.py -k sql_publication -o addopts='' -q --tb=short
# 全量收集后补充的 2 项：2 passed, 31 deselected in 6.18s
```

上述命令使用 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe`。当前 203 项用例均有通过记录，但不是一次 203 项全量执行。compileall 和 git diff --check 通过。

用户授权后的真实检查：硅基流动本地说明中的 7 个模型全部 HTTP 200。MySQL 实际服务为 5.7.44-log（8.4.9 为客户端版本）。在独立新建验证库两次执行 002/003 迁移，完成 MySQL ChunkSet → 项目远程 Adapter → Qwen3-Embedding-8B → Chroma → 回读验证：1 条合成切片、4096 维、validated、3750ms，baseline 未变化。数据库密码和 API Key 均未写入仓库。具体模型、耗时和保留的验证资源见 [真实验证记录](project/docs/model_connectivity_validation.md)。

当前限制：仅单文档、远程 Embedding；没有 active 指针、用户级完整索引覆盖、批量重建、取消/租约恢复、失败 namespace GC 或模型权重指纹固定。validated 只证明构建完成时验证通过，激活前须重新校验；SQLite 跨进程删除并发语义未保证。未升级业务库，未执行备份恢复演练。回退代码可保留新增表和隔离 namespace；在线路径未切换。

下一入口：从 `IndexBuild` 的 validated manifest 构造用户级候选版本，核对文档集合与模型配置，再实现 active version 原子切换和旧版本回滚。接口说明见 [staging 文档](project/docs/index_staging.md)。

### 本机双 MySQL 实例修正

实际连接确认 3306 为 MySQL 5.7.44-log，3307 为 MySQL 8.4.9；RAG3 原 `.env` 使用 3307。选定 3307 为后续 RAG4 主开发实例，3306 保留为兼容性验证环境。验证脚本新增 RAG4_TEST_MYSQL_PORT，默认 3307。3307 独立验证库已完成迁移重放和真实模型链路：validated、4096 维、3625ms、baseline 保留。业务库和应用连接配置未修改；详细资源与证据见 [双实例记录](project/docs/model_connectivity_validation.md)。

## Phase 2.3：用户级版本激活与回滚（2026-09-17）

新增 `IndexVersion`、`ActiveIndex`、`IndexSwitch` 和 `index_version_service`，提供完整文档覆盖检查、冻结模型配置、CAS 修订号切换、同事务审计、旧版本回滚和显式停用。`rag_service.retrieve` 接入 active 查询，未激活保持原路径；引用和 Reranker 接口保留。候选新增完整记录摘要，激活和每次 active 查询回读验证；旧无摘要候选须新建 build。

新增 `004_active_indexes.sql` 和 20 项测试。本轮最终在 backend 使用独立 Conda 环境执行：

```powershell
& 'C:\Users\gy\.conda\envs\rag4-py3.11\python.exe' -m pytest -o addopts='' -q --tb=short
# 223 passed in 226.08s (0:03:46)
```

compileall 和 git diff --check 通过。未修改前端/训练代码，无新增依赖。变更仍未提交。

真实验证：MySQL 8.4.9/3307 独立验证库重复执行 002–004，通过 BGE 1024 维 Embedding → Chroma → 激活 → 查询 → 切换/回滚 → 停用，baseline 未变。Qwen8B 在此前两次尝试超时，已保留 failed/embedding/ModelRuntimeTimeout 记录；显式改用 BGE 仅用于此次验证，业务模型配置未动。详见 [实际联调记录](project/docs/model_connectivity_validation.md)。

限制：当前为后端服务接口，无管理 HTTP/UI；要求所有文档 ready 且完整覆盖，同版本仅一种模型。上传/删除/重命名后 active 版本失配会报错，需重建或显式停用；没有自动增量合并。每次查询全量回读仅适合当前规模验证，不承诺生产性能。原文件磁盘外部修改与跨系统外部写入的原子隔离未实现。批量、租约恢复、取消、GC、业务库迁移和备份恢复门禁仍待后续完成，Phase 2 未整体完成。

接口与下一切片入口见 [激活与回滚](project/docs/index_activation.md)：下一步处理 active 版本与文档增量变化、批量任务及恢复，不进入 Graph/Agent/前端。

## Phase 2.4：批量重建与受控失败重试（2026-09-17）

新增 IndexRebuild、index_rebuild_service 及 005_index_rebuilds.sql。冻结完整源快照/配置/active revision，逐文档持久化 checkpoint，失败重试跳过已完成候选并为未完成文档创建新尝试；协作取消不强杀外部请求。最终生成待激活版本，仍须显式 CAS 激活，旧数据及 active 指针不会被批量任务自动覆盖。新增 12 项测试，无新增依赖。

在 `project/backend` 使用 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe` 执行 `-m pytest -o addopts='' -q --tb=short`，最终 **235 passed in 267.91s**。相关模块 compileall 和 git diff --check 通过。

MySQL 3307 独立库 002–005 迁移重放通过；BGE 1024 维真实批量任务 ready，1 个 checkpoint、5077ms，显式激活、后续真实查询与停用成功，baseline 保留。首次完整脚本曾在查询阶段返回 EmbeddingError，后续单独验证成功；失败没有被改写为成功，详见 [真实记录](project/docs/model_connectivity_validation.md)。

当前为同步完整重建服务，只支持受控失败后的重试；没有后台调度、进程崩溃 running 接管、跨任务增量复用、HTTP/UI 或 GC。上传/删除后仍需显式重建激活或停用旧 active。后续继续 Phase 2 租约/恢复与上线迁移门禁。接口见 [批量重建](project/docs/index_rebuild.md)。变更未提交或推送。

## Phase 2.5：显式中断恢复（2026-09-17）

新增 recover_rebuild、RebuildRecovery 和 006_rebuild_recovery.sql。恢复会在同一事务持久化取消旧 running 任务、复制冻结请求和已提交 checkpoint、创建独立续接任务并记录唯一关联。重复/并发调用返回同一目标；旧执行者迟到只能写自己的记录，不能覆盖续接结果或发布 ready。保留旧 base_revision，active 切换仍需显式 CAS。index_recovery 日志记录操作耗时与成败。

新增 10 项恢复测试覆盖模拟中断、checkpoint 复用、迟到执行者、并发、恢复事务失败、权限和主动取消。首轮 10 passed / 27.02s，补充运行日志后 10 passed / 27.39s。全量初跑 243 passed / 2 failed：既有 PDF/SSL 测试因 Chroma System 缓存未释放造成文件句柄耗尽；已修复测试 teardown，停止并移除本用例新增实例，无生产行为或依赖变更。

MySQL 3307 的独立合成验证库重放 006 两次，通过 checkpoint 续接 ready、并发唯一目标和恢复运行日志校验。复用此前真实 BGE 向量，本次没有额外模型调用，active 指针未变化。未强杀业务进程、未修改业务库或删除历史验证数据。

当前是显式恢复，不判断进程存活，没有自动超时/心跳/租约、后台队列、增量复用或 GC；旧远程调用可能继续，但其结果隔离。接口见 [中断恢复](project/docs/rebuild_recovery.md)。下一切片仍在 Phase 2，继续处理调度或迁移上线门禁。

修复测试句柄释放后，最终在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest -o addopts='' -q --tb=short`：**245 passed in 283.44s (0:04:43)**，无失败或跳过。compileall、git diff --check 和新增文档本地链接校验通过。MySQL 还验证了 index_recovery 成功日志（201ms）；本轮变更仍未提交/推送。

## Phase 2.6：只读迁移结构门禁（2026-09-17）

新增 `schema_preflight.inspect_schema(engine)`、`SchemaIssue`、`SchemaReport` 和 CLI `scripts/check_index_schema.py`，与 ORM 对照 002–006 八张表和外键依赖主键。缺表返回有序迁移建议；字段、主键、唯一键、索引和外键漂移阻止通过。MySQL 检查 InnoDB/表 collation/显式字段 collation。只读，无自动迁移或业务数据改写，无新增依赖。修正 database.init_db 的历史初始化脚本指引。

首轮新增 9 项测试 **9 passed in 3.57s**，覆盖空库、完整库只读 SQL、部分迁移、字段与约束漂移。MySQL 首次检查因反射增加 CHARACTER SET 误报两项 VARCHAR 类型，修正规范化并补第 10 项回归测试；后续合成库检查 ready=true（68ms），rag_high 返回八张缺表及 002–006（51ms），与真实状态一致。CLI 缺少密码和不可连接端口均返回退出码 2，错误消息不包含密码或连接详情。

接口、运行命令及边界见 [结构门禁](project/docs/schema_preflight.md)。不检查业务行、默认值、权限或备份可恢复性；尚未完成专用业务库迁移、自动调度或完整上线验收。Graph/Agent/研究前端没有新增实现。本轮与此前 Phase 2 变更仍未提交/推送。

最终在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest -o addopts='' -q --tb=short`：**255 passed in 274.98s (0:04:34)**。相关模块 compileall 和 git diff --check 通过。

## Phase 2.7：合成关系库备份恢复演练（2026-09-18）

新增 `scripts/rehearse_index_migration.py` 及 10 项测试，使用现有 MySQL 8.4 mysql/mysqldump，无新增 Python 依赖。随机创建三个独立库，执行 baseline 备份、002–006 迁移、准备任务与 ChunkSet 持久化、迁移后备份、两版本恢复、数据摘要比较、结构门禁和恢复库迁移重放。拒绝非测试库与非空恢复目标；备份损坏或客户端失败时停止，保留现场。报告包含阶段、UTC 起始时间、总耗时、备份和迁移文件 SHA-256。

MySQL 8.4.9 / 3307 两次实测通过：首轮 8972ms，测试库前缀 `rag4_restore_5112562c7d9b`，产物 `C:\Users\gy\AppData\Local\Temp\rag4_restore_uagkglq_`；补充摘要追踪和拒绝覆盖后，最终脚本 5717ms，测试库前缀 `rag4_restore_64743df4a608`，产物 `C:\Users\gy\AppData\Local\Temp\rag4_restore_rdpvoyaj`。每组有 source/before/after 三个库，均保留。恢复前后七张 baseline 表以及十五张迁移后表的行数和数据摘要分别一致；最终 report.json 保存完整结果。没有操作现有业务库或调用远程模型。

在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest tests/test_migration_drill.py tests/test_schema_preflight.py tests/test_index_jobs.py -o addopts='' -q --tb=short`：**34 passed in 30.82s**。此前工具与门禁测试 20 passed / 3.90s。compileall 和 git diff --check 通过。本轮未重跑全量，255 项全量通过是上一轮记录。

范围仅合成关系数据，不含 Chroma、上传文件、完整业务状态或线上大库一致性；正式专用库迁移未执行。下一步入口是配套文件与向量恢复验证，随后才能准备上线迁移。详见 [演练说明](project/docs/migration_restore_drill.md)。本轮变更未提交或推送。

## Phase 2.8：停写文件和 Chroma 配套恢复（2026-09-18）

新增 `app/services/offline_snapshot.py` 的 capture/verify/restore 接口、`scripts/rehearse_offline_restore.py` 和 10 项测试。外部保存 manifest SHA-256，校验全部相对路径/文件摘要/长度及空目录；拒绝链接、重叠路径、已有目标、缺失/多余/损坏文件。失败目标保留且不返回成功，不覆盖旧数据或自动切换应用目录。

独立 seed 子进程创建 SQLite、中文上传文件、真实 Chroma baseline 和候选索引，通过真实准备/构建/版本服务激活；Embedding 使用三维 Fake Adapter。进程退出后才复制目录，恢复到新路径，再由 verify 子进程重映射合成文档路径、验证原文及 active 清单/向量来源、查询、停用 active 并检查 baseline。源数据库摘要不变，没有业务库修改和远程模型调用。

独立脚本首轮通过：15267ms，目录 `C:\Users\gy\AppData\Local\Temp\rag4_offline_restore_fb901kfk`；最终版本通过：10655ms，目录 `C:\Users\gy\AppData\Local\Temp\rag4_offline_restore_yd4j_u22`，UTC 起始 `2026-09-18T16:55:51.518657+00:00`。最终外部清单摘要 `94c3e1f4997ff0639eb93ba84245b0587c003f3d34dd43286e7198e73afaa5a8`，report.json、bundle、source、restored 均保留。

在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest tests/test_offline_snapshot.py tests/test_index_versions.py -o addopts='' -q --tb=short`：**30 passed in 61.11s**，其中包含真实 Chroma 子进程恢复集成测试。compileall 和 git diff --check 通过。未重跑全量；255 passed 仍为 Phase 2.6 的历史全量记录。无新增依赖，未提交或推送。

捕获要求调用方先停止所有写入者；摘要前后检查不是在线一致性保证。此次仅合成 SQLite 配套恢复，尚未与 MySQL dump 组成统一生产恢复流程。下一步是独立 MySQL 库中的 SQL/上传/Chroma 同窗口备份恢复与版本复核，详见 [配套恢复说明](project/docs/offline_restore.md)。

## Phase 2.9：MySQL/上传文件/Chroma 组合恢复（2026-09-22）

新增 `scripts/rehearse_mysql_restore.py`，复用 SQL 备份、文件快照和索引服务；扩展 `rehearse_offline_restore.worker`，通过环境传入限定为随机演练库名称的 MySQL URL，并在空库执行 baseline 建表及 002–006 迁移。原 SQLite 演练清除该环境变量，保持独立。`restore_pair` 在 SQL 导入前要求空演练库、有效的可信包摘要和 dump，失败保留现场，不覆盖业务目录或 active 配置。

真实 MySQL 8.4.9/3307 演练通过，**32882ms**：`rag4_restore_665566bc97f6_source` 与 `rag4_restore_665566bc97f6_after`，目录 `C:\Users\gy\AppData\Local\Temp\rag4_mysql_restore_onsvwirc`。十五张表导入后摘要一致；恢复库路径重映射后 active 指针、来源清单、向量、查询及 baseline 停用回退通过，源库/文件最终摘要不变。外部 manifest SHA-256 `6e6d91fdd009e434e0e1b7dfcf22dcecb9d9139c55f1890f14cf343d59a2c6a7`，SQL dump SHA-256 `64b77b300be234302ee5c5ba1ad9995f1c1e8b556232f81fe17736a0d743283b`。完整报告及所有数据保留。

新增 7 项组合恢复测试覆盖 SQL/文件/清单损坏、非空库阻止恢复、dump 摘要绑定、SQL 失败保留及子进程凭据不进入参数。首轮四组相关测试 36 passed / 1 failed（26.10s）：测试构造 SQLAlchemy URL 时漏了用户名，导致未序列化密码；已修复该测试夹具。没有实际凭据泄露或恢复失败。

限制：合成停写场景、Fake Embedding、真实 MySQL/Chroma；不是生产在线备份、跨主机恢复或检索质量验收。下一步补 Phase 2 受权限保护的任务管理入口和业务验收，正式专用库迁移仍未执行。无新增依赖，未提交或推送。见 [组合恢复说明](project/docs/mysql_combined_restore.md)。

修正测试夹具后，在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest -o addopts='' -q --tb=short`：**282 passed in 421.93s (0:07:01)**，无失败或跳过，覆盖此前全部后端用例与新增恢复测试。相关脚本 compileall 和 git diff --check 通过。

## Phase 2.10：用户级重建任务管理 API（2026-09-22）

新增 `app/api/v1/index_rebuilds.py`、注册路由、`index_rebuild_service.list_rebuilds` 和 `tests/test_rebuild_api.py`。POST 创建、GET 分页/详情、POST 取消均通过现有 JWT 获取用户并按所有者隔离；他人任务和不存在任务统一 404，管理员无越权例外。请求只允许 dimension/chunking；远程模型 endpoint/model/version 取管理员配置，凭据不进入请求/响应/任务快照。响应包含进度、错误分类、版本与耗时，创建/取消有 usage 事件。

创建仅 pending、不自动调度或激活；取消 running 为协作请求。仍保留 Python 执行服务，HTTP 执行/重试/恢复/激活没有实现；不新增数据库迁移或依赖，不修改 baseline 默认配置。创建尚无幂等键，重复 POST 会新增任务。详见 [管理接口](project/docs/rebuild_api.md)。

在 backend 使用 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe` 验证：

- `-m pytest tests/test_rebuild_api.py tests/test_index_rebuilds.py -o addopts='' -q --tb=short`：**29 passed in 89.41s**（API 新增 17 项；补充冻结配置和源文件错误测试前首轮 27 passed / 83.05s）。
- `-m pytest tests/test_auth.py tests/test_docs.py -o addopts='' -q --tb=short`：**22 passed in 42.61s**。
- 相关模块 compileall、git diff --check 通过。

本轮未重跑全量；282 passed 是 Phase 2.9 历史全量结果。下一切片先补可靠的执行控制与管理员凭据绑定，再开放 CAS 激活。Graph/Agent/工作区未实现。本轮与此前 Phase 2 变更仍未提交或推送。

## Phase 2.11：单任务 worker 与凭据绑定（2026-09-22）

新增 `rebuild_execution.execute_configured_rebuild(user_id, task_id, store=None)` 和 `scripts/run_index_rebuild.py`。执行前校验任务归属、账号启用、当前 remote endpoint/model/version 与冻结值相同且当前密钥非空；不匹配时领取前拒绝。使用既有 SQL CAS 领取，避免重复模型执行；failed 可显式重试，ready/running/cancelled 返回现状；成功只产生 ready，不改 active。CLI 要求显式 DATABASE_URL，避免误用默认库，不建表或迁移，输出脱敏状态与耗时。

新增 10 项测试覆盖成功和重复执行、五种配置/密钥不匹配、归属/禁用账号、模型失败后重试、并发执行和 CLI 拒绝隐式数据库。在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest tests/test_rebuild_execution.py tests/test_rebuild_api.py tests/test_index_rebuilds.py -o addopts='' -q --tb=short`：**39 passed in 114.98s**。compileall 和 git diff --check 通过。测试使用 Fake Adapter，无真实远程调用或业务库写入；本轮未重跑全量，282 passed 仍为历史记录。

没有自动队列、心跳、崩溃检测或 HTTP 长任务执行；配置及账号检查是执行前快照，不能撤销已发出的调用。进程崩溃仍需现有显式恢复；运维自行保存 worker JSON 输出。下一步为权限受控的 CAS 激活/停用 HTTP 接口。无新依赖/迁移，未提交或推送。说明见 [worker 契约](project/docs/rebuild_worker.md)。

## Phase 2.12：用户级 CAS 激活/回滚/停用（2026-09-22）

新增 `app/api/v1/index_versions.py` 并注册路由，提供 GET/PUT `/api/v1/index-versions/active`。SwitchVersionRequest 要求显式 version_id（null 为停用）及非负整数 expected_revision，禁止额外身份参数。仅操作当前 JWT 用户；管理员无越权例外。版本服务新增兼容 ValueError 的 ActiveRevisionConflict，HTTP 映射 409；缺失/他人版本 404，完整性失败 400，不回显内部异常。复用完整候选校验、SQL CAS 和同事务 IndexSwitch 审计。

修正停用路径：version_id=None 不再初始化向量后端，即使 Chroma 不可用也可解除 active 绑定。保留旧版本和向量，不保证故障后端的 baseline 查询立即恢复。创建/worker 仍不会自动激活。

新增 `tests/test_version_api.py` 共 17 项（含 Local/Chroma 参数化），覆盖 JWT、显式字段、激活回滚停用、过期请求、跨用户含管理员、损坏清单保留指针与审计、向量后端不可用时停用。在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest tests/test_version_api.py tests/test_index_versions.py -o addopts='' -q --tb=short`：**37 passed in 122.75s**。相关 compileall、git diff --check 通过。未重跑全量，282 passed 仍为 Phase 2.9 历史记录。

无新增依赖/迁移或业务库变更，未提交或推送。下一步补历史版本列表/详情和闭环验收；自动调度、前端、Graph/Agent 均未完成。详见 [版本管理 API](project/docs/index_version_api.md)。

## Phase 2.13：历史版本发现和回滚闭环（2026-09-22）

扩展 `index_version_service.py` 与 `api/v1/index_versions.py`，新增 list_versions/describe_version 及历史列表 GET `/index-versions`、详情 GET `/index-versions/{id}`。按用户过滤、限制页大小、稳定倒序；/active 固定路由优先。摘要展示模型身份、文档数、active 标记与 manifest_integrity；详情仅展开冻结文档名和 build/document/chunk_set ID，不返回 endpoint、namespace 或原始 manifest。

历史查询仅验证清单摘要和基本结构，不打开向量库，不要求当前文档集匹配；改名/删除后的历史版本仍可发现，损坏清单显示 invalid。valid 不等同于可激活，切换仍复用完整候选检查。

新增 `tests/test_version_history.py` 共 9 项，含 Local/Chroma 参数化、权限、分页、字段脱敏、历史文档变化、损坏清单和创建→worker→激活→第二版本→历史发现→回滚检索闭环。在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest tests/test_version_history.py tests/test_version_api.py -o addopts='' -q --tb=short`：**26 passed in 75.70s**。compileall 和 git diff --check 通过。模型使用 Fake Adapter，没有真实外部调用或业务库修改；未重跑全量，282 passed 仍为 Phase 2.9 历史全量记录。

无新依赖或迁移；没有前端、自动调度、Graph 或 Agent。下一步收敛 Phase 2 整体验收及部署/发布前限制，不再将历史版本查询列为缺口。本轮未提交或推送。

## Phase 2.14：清单异常语义与验收收敛（2026-09-22）

核对发现历史查询与激活分开解析版本 JSON，缺字段 KeyError 可能被 HTTP 当成 LookupError 而返回 404。新增共享 `_read_manifest`，统一验证摘要、schema、用户身份、非空文档集、EmbeddingSpec、成员必需字段、向量摘要格式和成员唯一性。历史损坏记录显示 invalid，激活返回 400；当前 active 损坏时检索失败关闭，显式停用仍可用。未修改默认 RAG3 行为、数据库结构或依赖。

新增 `tests/test_manifest_integrity.py` 14 项 Local/Chroma 回归，包括重新计算过摘要的结构损坏，断言旧 active 与切换审计不变且旧检索可用。在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest tests/test_manifest_integrity.py -o addopts='' -q --tb=short`：**14 passed in 52.27s**。

使用当前代码重新运行 `scripts/rehearse_mysql_restore.py`：MySQL/上传/Chroma 组合恢复 **passed / 29979ms**，目录 `C:\Users\gy\AppData\Local\Temp\rag4_mysql_restore_83qt_y_t`，源库 `rag4_restore_a13dbd76804e_source`、恢复库 `rag4_restore_a13dbd76804e_after`，报告和数据全部保留。模型为 Fake Adapter，业务库和业务配置未改动。

新增 [Phase 2 验收索引](project/docs/phase2_acceptance.md)，按源码入口和测试建立证据映射，明确手动闭环与生产上线之间仍有自动调度、幂等创建/配额、增量复用/GC、大规模性能、质量评测和部署迁移等缺口。没有声明生产上线或 Graph/Agent 完成。变更未提交或推送。

最终在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest -o addopts='' -q --tb=short`：**349 passed in 618.48s (0:10:18)**，无失败或跳过。该全量包含 Phase 2.10–2.14 新接口、worker、历史闭环和损坏回归。相关模块 compileall 与 git diff --check 通过。

## Phase 2.15：创建幂等性（2026-09-26 收尾）

新增 RebuildRequest / index_rebuild_requests 和 007_rebuild_requests.sql；create_rebuild 增加可选 idempotency_key，HTTP 同步支持。同用户同键同模型/切分参数返回原任务当前状态，不读取或刷新源文档/active revision；异参冲突 409，不传键保持旧创建行为。键区分大小写。任务与映射同事务，并发失败方回滚新任务后读取唯一胜出记录，恢复续接不重新绑定原创建键。

此前已完成首组测试：`tests/test_rebuild_idempotency.py tests/test_rebuild_api.py tests/test_schema_preflight.py` **38 passed / 77.44s**（当时幂等测试 11 项，后补原键与恢复关系测试为 12 项）。此前 MySQL 8.4.9/3307 组合恢复含 007 新表 **passed / 24405ms**，目录 `C:\Users\gy\AppData\Local\Temp\rag4_mysql_restore_f7boq7_l`，数据库 `rag4_restore_35b3b620b31f_source` / `_after`，全部保留。

随后在该独立合成源库追加并发验证：007 重放两次成功，两线程同键创建均返回 `rebuild_18d7ad3456b11f48248bfb95`，任务与请求映射各新增一条，顺序重试仍返回原任务。此并发验证发生在恢复演练之后，合成源库因此多出一条 pending 任务；没有修改业务库。新迁移已纳入只读门禁与演练脚本，未执行生产迁移。

2026-09-26 继续时旧测试 session 已失效，未将其未确认结果写成通过，重新执行五组相关回归。代码、API 字段描述、数据库变更记录与 [幂等契约](project/docs/rebuild_idempotency.md) 已补齐。没有新增依赖或自动调度，也没有实现任务配额、键过期和 GC。本轮未提交或推送。

最终在 backend 执行 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe -m pytest tests/test_rebuild_idempotency.py tests/test_rebuild_recovery.py tests/test_index_rebuilds.py tests/test_rebuild_api.py tests/test_schema_preflight.py -o addopts='' -q --tb=short`：**61 passed in 106.10s**。相关模块 compileall、git diff --check 通过。本轮未重跑全量，349 passed 仍为 Phase 2.14 的历史全量结果。

## Phase 2.16：用户重建创建配额（2026-10-10）

新增 `RAG4_MAX_OPEN_REBUILDS_PER_USER`（1–10000，默认 8）和 `RebuildQuotaExceeded(ValueError)`（limit/open_count）。pending/running/failed 计入，ready/cancelled 释放逻辑额度但保留数据。事务内无操作更新 users 行取得数据库锁，复查幂等键后统计并创建任务/映射；不触发 ORM 的账号更新时间。满额同键同参仍返回原任务，异参仍 409，真正超限返回 429 并记录创建监控。恢复同事务交换原任务与续接，沿用额度；调低上限不破坏旧任务。没有自动激活或旧索引写入。

本轮实际修改文件：

- 配置与实现：`project/backend/app/core/config.py`、`project/backend/.env.example`、`project/backend/app/services/index_rebuild_service.py`、`project/backend/app/api/v1/index_rebuilds.py`。
- 测试：新增 `project/backend/tests/test_rebuild_quota.py`（17 项），调整 `project/backend/tests/conftest.py` 固定测试环境配额，避免外部配置污染。
- 文档：新增 `project/docs/rebuild_quota.md`；更新 `project/docs/rebuild_api.md`、`project/docs/rebuild_idempotency.md`、`project/docs/phase2_acceptance.md`、`project/docs/development_process.md`、`RAG4_DEVELOPMENT_PLAN.md`、本基线及两级 README。此前已有 Phase 2 工作区变更全部保留。

在 `E:\RAG4\project\backend` 用 `C:\Users\gy\.conda\envs\rag4-py3.11\python.exe` 执行：

```powershell
python -m pytest tests/test_rebuild_quota.py tests/test_rebuild_idempotency.py tests/test_rebuild_recovery.py tests/test_rebuild_execution.py tests/test_index_rebuilds.py tests/test_rebuild_api.py -o addopts='' -q --tb=short
python -m pytest tests/test_rebuild_quota.py tests/test_auth.py tests/test_docs.py -o addopts='' -q --tb=short
python -m pytest --collect-only -o addopts='' -q
python -m compileall -q app/core/config.py app/api/v1/index_rebuilds.py app/services/index_rebuild_service.py tests/test_rebuild_quota.py tests/conftest.py
git diff --check
```

首组 **73 passed in 234.58s (0:03:54)**，当时配额测试已收集 12 项；运行过程中补充了后续 5 项，故又对最终 17 项和原认证/文档 22 项执行第二组，**39 passed in 89.16s (0:01:29)**。两组覆盖 100 个不同用例。先前测试缺配置时 12 项 setup 失败已修复；最终无失败。当前后端 **378 tests collected in 0.52s**，本轮未执行全量；349 passed 仍是 Phase 2.14 历史全量。语法检查在 backend 正确目录执行无输出通过，git diff --check 通过（现有 CRLF 提示不影响结果）。

真实 MySQL 8.4.9/3307 在全新合成库 `rag4_restore_1c3d37503d42_source` 中验证：只创建新库，baseline 表后执行 002–007 增量并通过只读结构门禁，未使用破坏性初始化脚本。四线程不同键在配额 2 下成功 2 个、拒绝 2 个；任务和映射均各 2 条。独立用户双线程同键在配额 1 下只产生一组任务/映射；恢复及取消后重新创建均通过。**passed / 8843ms**，报告和合成源文件保留于 `C:\Users\gy\AppData\Local\Temp\rag4_quota_l6h4tpm2`。临时验证脚本保留于 `C:\Users\gy\AppData\Local\Temp\rag4_quota_check_f90a88424cc85.py`，用于复核此次合成验证，不是应用运行依赖。凭据只在进程内读取，未进入报告或仓库，业务库未修改；无真实远程模型调用。

限制：该配额只限制逻辑未完成重建，不能限制模型费用、Token、实际并发或磁盘空间；恢复后旧执行者可能完成已发出的调用。直接 job/build 服务未受此配额约束，ready 历史及失败候选仍未 GC；SQLite 写锁会串行化不同用户准入，数据库锁等待失败未新增重试。多实例需保持上限配置一致。无新增依赖、表或迁移，不删除旧数据，回退旧应用可保留全部记录。

下一切片入口：`rebuild_execution.execute_configured_rebuild` 与 `index_rebuild_service.run_rebuild` 的领取事务。前置条件是明确执行槽、租约及迟到执行者隔离语义，设计失败/取消/恢复下的释放方式并先通过并发和故障注入测试，再接可靠队列。Graph、ResearchAgent 和研究工作区仍未实现。本轮未提交或推送。

收尾增强账号时间戳测试：先固定为 2000 年，再断言准入不会改动，避免同秒操作掩盖问题。单项 `python -m pytest tests/test_rebuild_quota.py::test_users_have_independent_quota_without_account_timestamp_mutation -o addopts='' -q --tb=short`：**1 passed in 9.78s**。差异检查发现新增记录末尾空行，移除后复查通过。
