# RAG4 Phase 1：结构化切分接口

实现位置：`backend/app/chunking/`。这是纯计算模块，无数据库、向量写入、模型下载或 active version 副作用。RAG3 的 `app.services.chunking_service.split_blocks` 保持原样。

## 直接调用（Phase 2 的入口）

```python
from app.chunking import ChunkingConfig, ChunkingEngine, ChunkSet
from app.chunking.adapter import adapt_parse_result
from app.services.parser_service import parse

legacy_result = parse(path, file_name, structured=True)
document = adapt_parse_result(
    legacy_result, document_id=document_id, file_name=file_name,
)
config = ChunkingConfig(
    chunking_version="rag4-structured-v1",
    child_max_tokens=256,
    parent_max_tokens=1024,
)
chunks = ChunkingEngine().split(document, config)
assert chunks.verify(document)
snapshot_json = chunks.model_dump_json()
assert ChunkSet.model_validate_json(snapshot_json).verify(document)
```

应用已有 tokenizer 时，使用 `TokenizerTokenCounter(tokenizer, identity="model@immutable-revision")` 传入 `ChunkingEngine(token_counter=...)`；也可以实现 `TokenCounter` 的 `identity` 与 `count(text) -> int`。tokenizer 必须确定性，identity 必须包含词表/配置版本；适配器调用 `encode(..., add_special_tokens=False)`，调用者需给模型特殊 token 预留余量。引擎不下载 tokenizer。

缺省 `unicode-codepoint-v1` 使用 Python `len(text)` 计数，是可重复的字符预算估算，不能保证任何特定模型的真实 token 上限。已注入 tokenizer 在执行中失败时中止并记录错误，不在同一结果中混用计数器。BPE 计数非单调时不假设每个前缀递增；在无法二分找到合法前缀时执行确定性前缀搜索，最终每片重新计数。

## 数据契约

所有模型均基于项目已有 Pydantic 2.10.4，冻结字段、拒绝未知字段、嵌套集合用 tuple，可 JSON 往返。没有新增依赖。

| 接口 | 含义 |
| --- | --- |
| `ParsedDocument` | document_id、file_name、page_count、blocks、SourceInfo、parser_version；page_count=0 表示未知 |
| `ParsedBlock` | block_id、text、kind、heading_level、section_path、page_start/end、可选 TableMetadata/FormulaMetadata |
| `DocumentChunk` | chunk_id、document_id、text、chunk_index、chunking_version、title、section_path、parent_chunk_id、is_parent、page_start/end、table_metadata、formula_metadata、source_locator、token_count |
| `SourceLocator` / `SourceSpan` | 稳定 source URI 和原 block 中的 Unicode 字符区间 `[char_start, char_end)`；页码从 1 开始，未知为 None |
| `ChunkSet` | chunk_set_id、input_id、文档及各版本身份、完整配置、parent_chunks/child_chunks、统计与 verify 方法 |
| `ChunkStats` | 输入 block 数、父子片数、分别累计的 token 数；父子计数互相独立，不能相加当作原文 token 数 |

父片、子片分别连续从 0 编号。父片无 parent ID，子片恰好关联一个父片。不跨章节聚合；表格/公式/代码独立成组。标题层级由显式 heading block 或 block.section_path 提供，不猜测 PDF 字体或普通文本标题。子片优先段落、句子、空白、字符边界；Phase 1 不做重叠，父片提供上下文。普通正文只裁去切分边界空白；代码块保留缩进及换行。超长表格/公式允许按文本拆分，每片保留整个来源对象的 metadata，而不是声称已定位到单个单元格或公式语法节点。

input_id 由完整输入文档、配置（含 chunking_version）、算法版本和计数器身份计算。chunk_id 再包含各片内容、位置、来源与父关系，chunk_set_id 包含全部结果和统计。SHA-256 使用排序键的规范 JSON；不包含时间戳。`verify()` 校验内容 hash、编号、引用、统计和预算；传入原 ParsedDocument 时同时验证 input_id。它是完整性校验，不是数字签名，也不能证明第三方 tokenizer 正确。版本更新需更换显式版本，算法语义变化同时提升 engine version。

## 解析兼容

`ParseResult` 在旧字段后增加可选 `structured_blocks` 和 `parser_version`，旧位置参数兼容。`adapt_parse_result` 优先使用结构通道，否则逐个 TextBlock 转成 paragraph，保留页码、OCR 标志和原文，不修改旧对象。直接从旧 TextBlock 列表接入时先包装 `ParseResult(blocks=blocks)`。

`parse(..., structured=True)` 目前对 Markdown 追加 ATX/setext 标题和 fenced code 结构；legacy blocks 的内容不变。它是轻量兼容器，不是完整 Markdown AST。PDF 保留已有逐页输出，DOCX 保留既有扁平文本；已经丢失的布局、标题样式、表格和公式不伪造。结构化解析器可通过 `ParsedBlock` 或 `ParseResult.structured_blocks` 提供丰富 metadata。

## 上传开关与回退

默认配置：

```dotenv
DOCUMENT_CHUNKING_ENGINE=rag3
RAG4_CHUNKING_VERSION=rag4-structured-v1
RAG4_CHILD_MAX_TOKENS=256
RAG4_PARENT_MAX_TOKENS=1024
```

设 `DOCUMENT_CHUNKING_ENGINE=rag4` 并重启后，新上传使用 RAG4；当前上传路径使用字符 fallback。两个 RAG4 budget 独立于后台 RAG3 的 chunk_size/overlap。恢复为 rag3 并重启即可让后续上传回到原算法，无数据库迁移。非法配置会明确失败；父预算必须不小于子预算。

上传只将 child chunks 向量化，RAG4 使用新 chunk_id；默认 RAG3 保留 `doc_id:chunk_index`。VectorRecord 增加可选 chunking_version、chunk_set_id、chunk_metadata_json，复杂结构存成 JSON 字符串满足 Chroma 标量限制。两种向量后端都将其还原到 RetrievedChunk.extra.chunking；旧引用 page 使用 page_start，chunk_index/SSE 契约不变。父片完整内容当前只存在 ChunkSet 返回值中，尚未持久化或提供父片查询 API。

ready 文档调用 process_document 会直接返回，不因开关变化被重写。Embedding 数量不匹配在写入前失败；切分失败记为 failed 并保留既有其他文档索引。错误和耗时记录在 `usage_logs.document_chunking`；引擎日志包含 document/version/tokenizer/chunk_set/片数/elapsed_ms。日志不打印正文。失败不会删除旧版本数据。

**本开关不是索引版本激活/回滚。** 现有 Collection 仅隔离 Embedding 版本；不要用上传函数对历史同一文档构造多份切分版本。现有向量写入没有跨 SQL/Chroma 事务，中途写入失败的新文档可能留下部分记录，失败重试也没有 generation 级清理；完整 staging、可见性门禁和原子发布属于 Phase 2，不能以本功能宣称已经实现。

## Phase 2 前置条件

1. 设计增量 schema：不可变 ChunkSet/父片快照、document_index_jobs、active version，明确 user/document/version 组合和并发幂等键。
2. 冻结 parser/chunking/tokenizer/embedding 版本组合，独立 staging collection 写入；校验 ChunkSet 来源与 hash、child 数量、向量维度及元数据完整性。
3. 验证完成后才原子激活，检索只读 active；失败保留旧 active，回滚恢复旧指针。补取消、重试、删除、并发和故障注入测试。
4. 先完成备份和迁移恢复演练，再开放历史文档批量重建。不要执行带 DROP DATABASE 的 `docs/init_db.sql` 做迁移。

本次未实现 Graph、HybridEvidenceEngine、ResearchAgent、EvidenceVerifier、ArtifactComposer 或前端工作区；未对真实语料 Recall/MRR/nDCG 宣称提升。
