# RAG4 基线记录

> 记录日期：2026-09-14

## 当前基线

RAG4 当前以 `project/` 下导入的 RAG3 代码作为可运行基线。模型运行时与训练脚手架已经接入；Research Agent、知识图谱和混合证据引擎尚未实现，这些能力仍以根目录的 `RAG4_DEVELOPMENT_PLAN.md` 为设计目标。

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
