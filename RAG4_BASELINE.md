# RAG4 基线记录

> 记录日期：2026-09-14

> 最近代码交付：2026-09-16，`4b0e1dd feat: implement RAG4 structured chunking engine` 已按用户请求推送至 GitHub main。下文 Phase 1 中“未提交/推送”描述的是开发完成、发布之前的时点；发布后的过程与当前进度见 [开发过程记录](project/docs/development_process.md)。

## 当前基线

RAG4 以 `project/` 下导入的 RAG3 代码作为可运行基线，默认仍使用 RAG3 切分。2026-10-13 已新增文献比较场景的来源内存图谱、混合证据、SQL ResearchAgent 任务/工具及核验产物最小后端；质量验收、Neo4j、通用自主规划与研究工作区尚未完成。当前边界见文末最新记录和 `project/docs/research_backend_mvp.md`；下文旧轮次的“未实现”保留为历史状态。

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

## 发布与开发范围调整（2026-10-12）

Phase 2.1–2.16 已提交并推送到 GitHub main，提交 `476127bb23c7745e46410b80c49b11561f1693e8`；推送后本地 HEAD 与远程 main 核对一致。该提交包含 75 个文件，不含独立任务的 artifacts 截图，也未进行业务库迁移或生产部署。前述各轮“尚未提交”是当时状态。

按用户要求收紧近期计划：现有索引能力冻结为维护基线，当前全量回归和隔离文献手动闭环作为有限收尾；下一切片转为 3–5 篇真实论文、20 题开发回归、RAG3/结构切分对照及失败案例。随后按 Phase 3–6 顺序完成最小混合证据、研究任务、带核验的比较表和用户操作路径。引用支持、证据缺口与已知失败案例改善作为验收目标；指标尚无新实测结果。

队列、租约、GC、Neo4j 和正式训练改为有实测阻塞或明确运行需求时触发，采用第 3.4 节记录的最小范围与退出条件。受控实验串行运行不等于系统已有全局并发保护。首批 20 题用于开发回归，不充当独立训练测试集；现有 experiment 脚本会修改全局配置和删除实验账号文档，不直接在业务环境运行。

本轮修改 8 份文档：`RAG4_DEVELOPMENT_PLAN.md`、`README.md`、本基线、`project/docs/development_process.md`、`project/docs/phase2_acceptance.md`、`project/docs/rebuild_quota.md`、`project/docs/rag4_chunking.md`、`project/training/README.md`。同步消除当前入口的过时状态描述，保留明确标注的历史记录。仅调整计划和说明，没有新增应用代码、数据库迁移、依赖或模型调用；没有将新评测集、Graph、Agent 或前端功能标记为已完成。

验证采用修改文档的本地文件链接、代码围栏配对与 `git diff --check` 检查；不对纯文档变更重复运行后端测试。当前 378 项完整回归与真实论文质量验证仍列为下一切片待执行，历史测试结果不变。本轮计划修订尚未提交或推送。

## 真实文献检索试点（2026-10-12）

按收紧后的计划推进实际验证。开工 git status 为前轮 8 份文档修改及独立 artifacts 截图，全部保留。先在原发布基线执行后端全量 `python -m pytest -o addopts='' -q --tb=short`，**378 passed in 465.54s (0:07:45)**；此时新增试点测试尚未加入。没有创建索引队列、租约或新业务表。

新增文件：

- `project/backend/app/evaluation/__init__.py`、`literature.py`：Pilot/Paper/Question/Evidence 与 Candidate/Span 类型、PDF 摘要/页数校验、唯一锚点定位、现有切分器适配、向量值校验与跨切片原文覆盖指标。
- `project/backend/scripts/evaluate_literature.py`：明确参数和凭据环境变量、80 次调用预算/30 秒超时/每批一次尝试、现有 RemoteEmbeddingAdapter 和 LocalVectorStore、独立输出及失败报告；不写业务 SQL、管理员配置或 active。
- `project/backend/evaluation/literature_pilot_v1.json`、`README.md`：三篇官方来源、许可及 SHA-256 固定，20 题 AI 草稿与复现契约；27 个证据区间已定位，尚未人工语义复核。
- `project/backend/evaluation/results/literature_pilot_20261012.json`、`parent_expansion_diagnostic_20261012.json`：两次尝试、逐题候选位置/分数、完整原始报告摘要、源码/输入身份和离线父片诊断；不包含密钥或向量正文。
- `project/backend/tests/test_literature_pilot.py`：19 项离线功能和失败保护测试。
- `project/docs/research_corpus_sources.md`、`literature_pilot_report.md`：原论文与许可依据、AI 标签范围、真实结果及失败分析。同步更新开发计划、根 README、Phase 2 验收和开发过程记录，不把试点写成 Graph/Agent 已完成。

语料是 DPR（ACL 2020，13 页）、FiD（ACL 2021，7 页）、REALM（PMLR 2020，10 页），PDF 与本地完整原文/向量位于 `E:\RAG4\project\backend\data\literature-pilot-v1`，受现有忽略规则保护。许可与作者出处留在来源注记及定义文件中；下载模型与文献不等于正式训练。该试点只对照纯检索，真实文献 SQL staging/激活/回滚闭环及人工标注验收仍待完成。

固定模型 Qwen/Qwen3-Embedding-8B、4096 维；RAG3 600/60，RAG4 子预算 600/父预算 1800/无重叠/字符 fallback，同一批问题向量。RAG3 254 子片，RAG4 272。Top-10 标注锚点覆盖均值 **33.33%→41.67%**，全证据题数均 **5/16**；q01 出现锚点退化。四道证据不足题只保存检索明细，未测拒答，不计为正确；没有生成答案或验证引用。短锚点不等同于完整语义支持，默认路径保持原有设置，没有达到新的质量切换门槛。

首轮 `run-qwen8b-20261012` 保留 failed / rag4_embedding / ConnectError，60587ms、19 次调用；RAG3 成功结果保留。第二轮 `run-qwen8b-20261012-attempt2` 同参数，剩余调用预算 61，**succeeded / 125176ms / 35 次调用**。两轮合计 54 次、1 次失败，服务返回 total_tokens 合计 117219，货币费用未知。此前许可来源核对和本轮请求都未涉及用户私有文献；API Key 只在进程内读取，没有写入输出或仓库。

额外的离线父片诊断只复用既有候选排名，不新增 API 调用：覆盖均值 51.04%、全证据题 7/16，q01/q09 的指定锚点补全；但 q01 上下文 4467→12709 字符，预算不等价，尚未接入在线检索。下一切片由这些具体失败驱动有预算的父片展开、等价证据复核与文档范围覆盖，不据此扩展 Neo4j、租约或训练平台。

在 `E:\RAG4\project\backend` 的 `rag4-py3.11` 环境运行：

```powershell
python -m pytest tests/test_literature_pilot.py -o addopts='' -q --tb=short
python -m pytest tests/test_literature_pilot.py tests/test_chunking_engine.py tests/test_services.py -o addopts='' -q --tb=short
python scripts/evaluate_literature.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --output data/literature-pilot-v1/run-new
```

前两项实际结果 **19 passed / 3.79s**、**108 passed / 8.03s**。第三项是复现命令，运行前由进程设置 RAG4_EVAL_API_KEY；本轮实际使用相同 run 接口分别写入上述两个新目录，第二轮扣减首轮调用预算。代码准备时修复了导入路径和歧义锚点，没有降低校验要求；测试最终全通过。没有新增依赖或修改已有业务实现，本轮未重跑新增后的 397 项全量，尚未提交或推送。


## 2026-10-13：Phase 3–5 文献比较后端切片

保留默认 RAG3 和既有手动索引。新增 EvidenceCorpus/Bundle、GraphStore/MemoryGraphStore、来源实体与两跳探索、HybridEvidenceEngine；ResearchTask/Step、工具注册与 ResearchAgent；SQL checkpoint/CAS 和所有者 HTTP/单步 CLI；EvidenceVerifier/ArtifactComposer 和结构化引用。文件与接口清单见 [后端切片](project/docs/research_backend_mvp.md)。仅新增 research_tasks 迁移 008，不新增依赖。

真实三篇论文的 SQLite 版本激活/回滚闭环通过，文档向量复用、查询/模型在线；MySQL 8.4.9/3307 隔离新增表、中文往返、过期 revision 拒绝通过，未迁移业务库。七次在线尝试共 31 请求、9 网络失败、报告 33406 Token，货币/失败请求用量未知。旧核验器曾错误接受 38.2 对 38.5；当前独立数字门禁拒绝该结论，保存的语义判断离线回放得到 3/6 机器支持、9 缺口、partial 产物。最新在线第 7 次严格响应 schema 失败保留，不能标记质量通过。

固定旧 Top-10、6000 字符父片回放：平均锚点覆盖 41.67%→47.92%，全证据 5/16→6/16；q01 改善，q09/q12 未改善。先保留子片后展开父片避免初版挤掉证据。真实关系未证明图谱收益。20 题仍待人工标注审核，90% 支持率及缺口题未验收。

最终全量 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`：**432 passed / 500.17s**，无失败/跳过；compileall、差异、公开 JSON 和文档链接检查通过，详见开发记录 R19；无业务配置/active 修改、无前端/正式微调、无新依赖，本轮未提交推送。旧任务/产物可读取历史身份，新生成必须通过当前核验；回滚可停用研究入口/worker 继续 RAG3，保留研究表与记录。后续先修复真实引用与响应协议并做人工质量验收，Phase 2 不继续无边界扩建。


## 2026-10-13 R20：来源引用编号与协议修复

新增 source-handles-v2（连续原文目录和区间绑定）、安全 schema 诊断、显式 JSON 输出、重复 JSON 键拒绝和有界候选归一；历史任务缺省仍是原协议。真实重跑查明 REALM claims 超限，保留 DPR/FiD 已完成步骤，从复制 SQLite 受限续接成功，失败连接也保留。9 请求、1 网络失败、20203 已报 Token，费用/失败用量未知。

在线 12 候选中机器通过 6；二次 AI 来源复核发现两条 REALM 条件/支持不足，展示版撤下，仅 4 条、8 缺口；不是人工质量验收或生产语义 verifier 自动修复。q09 为预算不足，q12 为候选召回缺口，没有伪装成改善。新增文件、接口配置和结果见 [修复记录](project/docs/research_citation_fix.md)。

最终 backend `python -m pytest -o addopts='' -q --tb=short --show-capture=no`：**440 passed / 470.62s**，无失败/跳过。此前 432 项为 R19 历史结果。无新依赖、业务库迁移/配置/active 改动，无前端/训练或 GitHub 推送。继续优先条件/归属核验与范围内检索。


## 2026-10-14：Phase 1–5 质量优化候选

本轮复用既有结构化切片、冻结索引和研究任务，新增 SourceCheck / ClaimAssessment / CheckedJudgment，显式可选的 source-checks-v3 核验协议，以及产物生成前的逐项复查。模型逐项报告来源归属、实验条件、完整语义和原文支持片段；未知/重复 claim_id、缺项或不受来源支持的片段不能直接变成发布结论。历史任务默认 numeric-model-v2，历史报告序列化及真实产物身份保持兼容。没有新增依赖或业务库迁移。

新增脚本 scripts/reverify_research_claims.py 在新目录中复制 SQLite 并验证冻结来源，最多一次模型请求，可指定结论子集。两次实际实验共 2 请求、1 ReadTimeout、5811 已报 Token，费用及失败用量未知。第二轮六条旧 supported 结论全部被拒，其中存在引文抄写导致的误拒，REALM 的语义误判仍在模型分项中出现。未证明质量提高，新协议不作为默认，不替换旧展示表。账本为 project/backend/evaluation/results/source_checks_20261014.json。

相关回归命令：`python -m pytest tests/test_research_verification_checks.py tests/test_research_agent.py tests/test_research_citations.py tests/test_research_runtime.py -o addopts='' -q --tb=short --show-capture=no`，结果 **46 passed / 30.84s**。新增 11 项测试覆盖契约、历史真实身份和失败保护；不能用测试替身的成功证明语义准确率。完整说明见 [逐项核验记录](project/docs/research_source_checks.md)。

最终全量回归：在 `project/backend` 执行 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`，**451 passed / 494.48s**，无失败、无跳过。编译检查与差异空白检查通过。测试通过不代表上述真实语义质量门槛通过。


## 2026-10-14：核验来源编号与范围对照

继续上一轮未提交开发，新增 source-handles-v4 / exact-source-handles-v4：verification_sources、resolve_support、HandleCheck/HandleAssessment/HandleJudgment，模型选择编号，服务端还原原文；空、重复、跨结论、未知或超长区间不支持发布。SourceCheck 保存 support_ids 与 support_quote，ArtifactComposer 重建编号映射；旧 v2 产物身份和 v3 报告序列化继续回归验证。默认仍为 numeric-model-v2。

实际两次模型请求：六条旧 supported 子集一次成功，1 supported / 5 insufficient，无引文抄写校验失败；全部十二条一次 ReadTimeout。合计 6156 已报 Token，失败用量及货币费用未知，不通过人工质量门槛。另以题目明确论文范围过滤冻结 Top-10、6000 字符预算，q09 仍 1/2、q12 仍 2/3 锚点覆盖，零额外模型调用。来源编号修复与语义/召回不足分别记录，不以全拒绝宣称准确。

修改研究模型/核验/API/协议诊断、复核脚本和 runtime 测试；新增编号与范围测试、evaluate_evidence_scope.py、明确范围配置和公开结果账本；无新依赖、业务库迁移或生产检索改动。详见 [来源编号与检索对照](project/docs/research_verification_handles.md)。

最终全量：在 `project/backend` 执行 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`，**466 passed / 521.87s**，无失败或跳过。本轮新增 15 项回归覆盖（含 API 参数化新增两项）。编译、差异空白、公开结果 JSON 和凭据模式检查通过；语义质量门槛仍未通过。
