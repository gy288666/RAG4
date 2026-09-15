# RAG4 开发计划：证据驱动的学术 Research Agent

> 文档版本：v2.1
> 编写日期：2026-09-13  
> 基线项目：RAG3（React 18 + TypeScript + FastAPI + SQLAlchemy + Chroma）  
> 产品形态：个人学术资料 Research Agent  
> 建议周期：个人 AI 辅助开发 7–8 周；最小可演示版本 5 周

---

## 1. 项目定位

RAG4 不再只是“带知识图谱的 RAG 问答系统”，而是一个**证据驱动的学术 Research Agent**。它面向需要处理论文、报告、实验记录和课程资料的学生与研究人员，把“用户提一个问题、系统返回一段回答”升级为“用户提出研究目标、Agent 规划步骤、调用资料工具、核验证据并交付研究产物”。

RAG4 的核心任务不是替用户假装完成研究，而是减少资料整理、证据定位、文献对比和研究记录中的重复劳动，并让每个关键结论都能回到来源。

四个升级共同形成研究任务闭环：

1. **结构感知切分**提供完整、可定位的文献证据；
2. **知识图谱**连接跨文档实体、方法、数据集和指标；
3. **Agent 编排**把复杂目标拆成可观察、可停止、可恢复的研究步骤；
4. **前端重构**把任务计划、执行进度、证据、关系和最终产物放在同一个研究空间中。
5. **模型实验闭环**用人工标注与 hard negative 持续改进召回、精排和结构化生成，但模型切换必须可评测、可回滚。

RAG4 的一句话价值主张：

> 把自己的研究资料交给一个会规划、会检索、会核验证据，并能生成可追溯研究产物的个人学术 Agent。

### 1.1 目标用户

- 本科生与研究生：课程论文、毕业设计、开题调研和文献阅读；
- 科研人员：主题梳理、方法比较、数据集与指标追踪；
- 知识工作者：内部报告、规范文档和项目资料的证据化整理。

### 1.2 典型任务

```text
“比较这 12 篇论文中的切分策略，按方法、数据集、指标和局限生成综述。”
“找出支持与反对 GraphRAG 的证据，并标出原文和页码。”
“根据知识库生成开题调研提纲；证据不足的章节明确列为待补资料。”
“总结本周新增文献，更新研究笔记，但不要覆盖我已有的人工结论。”
```

### 1.3 产品边界

RAG4 是受控的协作型 Agent，不是无人监督的“自动科研系统”。它可以自主规划和调用只读研究工具；涉及写入笔记、覆盖产物、批量重建索引或调用外部网络数据时，必须经过清晰的权限与确认机制。

---

## 2. RAG3 基线与主要问题

### 2.1 可继承能力

RAG3 已具备以下基础，应优先复用：

- PDF、DOCX、TXT、Markdown 上传与解析；
- 基于 Chroma 的用户级向量隔离；
- Embedding、向量检索、Rerank、LLM 生成链路；
- SSE 流式回答与引用；
- 用户、管理员、配置、运行监控；
- 外部模型超时与降级；
- Docker Compose、Nginx、MySQL 和 HTTPS 部署资料；
- 切片大小、Top-N、历史轮数的初步参数实验。

### 2.2 当前不足

#### 切分层

- 主要按字符长度切分，对模型 Token 上限缺乏直接控制；
- 重叠通过截取上一片尾部字符实现，可能从句子中间开始；
- 标题、章节路径、列表、表格等结构信息没有成为切片元数据；
- 检索粒度和生成上下文粒度相同，精确召回与上下文完整性互相牵制；
- 参数变更只影响新文档，没有切分版本和批量重建机制。

#### 检索层

- 主要依赖向量相似度和 Rerank；
- 对跨文档关系、实体对比、多跳问题支持有限；
- 引用展示能定位切片，但不能解释多个证据之间的关系；
- 当前实验以单跳事实题为主，准确率饱和，不能充分区分策略优劣。

#### 前端层

- 整体仍偏通用后台，研究场景辨识度不足；
- 聊天、原文证据、文档上下文之间切换成本较高；
- 知识库页面更像文件管理器，缺少文档阅读与研究信息；
- 缺少文档详情、切片检查、实体详情和关系探索；
- 管理配置较多，但普通用户看不到系统如何形成答案。

#### 任务执行层

- 当前交互以单轮问答为中心，无法表达“比较—验证—整理—交付”这类多步骤研究目标；
- 系统没有显式任务状态，用户无法看到正在做什么、为什么调用某个工具以及下一步是什么；
- 检索、生成、引用和导出之间缺少统一编排，失败后通常只能重新提问；
- 没有步骤级暂停、恢复、取消和人工确认机制；
- 对“证据不足”和“工具失败”的处理仍停留在回答层，不能形成可继续执行的待办项。

---

## 3. 目标、非目标与成功条件

### 3.1 本期目标

1. 在不破坏 RAG3 基础问答的前提下，引入结构感知、父子切片和版本化重建。
2. 从文档切片中抽取实体、关系和来源证据，构建用户私有知识图谱。
3. 建立向量检索与图谱检索融合的混合证据引擎。
4. 实现可观察的 Research Agent 循环：理解目标、制定计划、调用工具、核验证据、生成产物。
5. 支持文献综述、跨文档对比、主题证据地图和研究笔记四类核心任务。
6. 重构主要前端页面，形成“目标—计划—执行—证据—产物”的连续体验。
7. 建立能比较 RAG3 与 RAG4 的检索质量、回答质量和任务完成质量评测。
8. 保留离线 Fake Adapter、自动化测试与 Docker 部署能力。
9. 建立远程/本地模型 Adapter、模型与索引版本、训练数据和离线评测闭环，优先完成 Reranker 微调。

### 3.2 本期非目标

- 不构建跨用户共享的公共知识图谱；
- 不做自动投稿、自动发表或无人监督的完全自主研究；
- 不让 Agent 随意执行 Shell、安装软件或访问用户知识库之外的数据；
- 不在第一版开放任意自定义工具和任意提示词驱动的工作流；
- 不代替用户给出最终学术判断，也不伪造引用、实验或调研数据；
- 不追求百万节点级分布式图计算；
- 不把知识图谱做成手工绘图或流程编辑器；
- 不在第一版支持所有复杂数学公式、图片和表格语义理解；
- 不用“图谱节点数量”代替真实检索与回答质量指标；
- 不宣称现有实验结果可以代表真实生产环境。

### 3.3 成功条件

RAG4 只有同时满足以下条件才算完成：

- 原有核心功能保持可用；
- 每个图谱节点和关系均能追溯到文档切片；
- 每个 Agent 任务都有明确目标、计划、步骤状态、工具调用记录和最终产物；
- 用户可以暂停、取消任务，并在关键写入操作前确认；
- Agent 的关键结论能够追溯到 EvidenceBundle 中的来源证据；
- 多跳问题相对 RAG3 基线取得可测量提升；
- 不可回答问题不会被图谱或 LLM 强行补全；
- 删除文档会同步清理文件、向量、实体提及和失去来源的关系；
- 用户能在一次交互内从答案定位到关系和原文；
- 至少四类核心研究任务能在固定评测集上稳定完成；
- 前后端测试、构建、迁移和部署流程可复现。
- 任一微调模型只有在冻结测试集上通过质量、延迟和失败率门禁后才能切换；Embedding 切换不得混用旧索引。

---

## 4. 总体架构

```text
资料层
文档 → Parser → ChunkingEngine
                     ├─ Embedding → Chroma
                     └─ GraphBuilder → Neo4j

任务层
用户目标 → ResearchAgent
             ├─ GoalInterpreter：明确目标、范围和产物
             ├─ TaskPlanner：生成有限步骤计划
             ├─ ToolRunner：调用允许的研究工具
             ├─ EvidenceVerifier：核验证据覆盖与引用
             └─ ArtifactComposer：生成笔记、对比表或综述
                       │
                       ▼
工具层
             ┌─────────────────────────────┐
             │ search_evidence             │
             │ explore_graph               │
             │ inspect_document            │
             │ compare_documents           │
             │ save_research_note          │
             └─────────────────────────────┘
                       │
                       ▼
证据层
HybridEvidenceEngine → EvidenceBundle
  ├─ 向量检索
  ├─ 图谱检索
  ├─ 父级上下文展开
  ├─ 合并、去重和 Rerank
  └─ 来源、置信度和降级信息

交互层
SSE / WebSocket → 计划、步骤、工具调用、证据、确认请求、最终产物

实验反馈层
显式标注/评测失败 → hard negative 构建 → 训练 → 离线评测 → 注册模型版本
                                                     └→ 灰度切换/回滚
```

架构原则：

- ResearchAgent、切分、图谱和混合证据分别设计为深模块；
- 调用者只依赖小而稳定的接口；
- 外部模型与 Neo4j 通过 Adapter 注入；
- 在线服务只依赖 EmbeddingModel/RerankerModel 等小接口，训练框架留在离线路径；
- 模型版本、索引版本、数据版本和代码提交必须共同记录，禁止“覆盖同名权重”；
- 模块接口同时作为测试表面；
- Agent 只通过 ToolRegistry 调用工具，不直接依赖 Chroma、Neo4j、文件系统或数据库；
- Agent 计划必须有最大步骤数、Token 预算、超时和取消信号；
- 任务状态先持久化再执行下一步，崩溃后可从最后一个安全检查点恢复；
- 图谱只提供有来源的证据，不直接充当事实真相；
- 任何外部依赖失败都应明确降级，而不是静默制造完整假象。

---

## 5. 核心模块设计

### 5.1 `ResearchAgent` 模块

`ResearchAgent` 是任务编排的唯一外部 seam。聊天页、任务页和自动化测试都通过同一个接口启动或继续任务，不直接操作模型与工具。

建议外部接口：

```python
class ResearchAgent:
    def start(self, request: ResearchRequest) -> ResearchTask: ...
    def continue_task(self, task_id: str, command: TaskCommand) -> ResearchTask: ...
    def get_state(self, task_id: str) -> ResearchTask: ...
```

`ResearchRequest` 只暴露调用者真正需要知道的内容：

```python
@dataclass(slots=True)
class ResearchRequest:
    user_id: int
    goal: str
    document_scope: list[str]
    output_type: Literal["answer", "comparison", "review", "research_note"]
    constraints: ResearchConstraints
```

内部实现负责：目标解析、计划生成、步骤执行、工具选择、错误恢复、证据验证和产物生成。不要把每个内部阶段暴露为控制器可随意组合的浅接口。

Agent 循环采用有限状态机：

```text
created
  → planning
  → running
  → waiting_confirmation ─┐
  → verifying             │
  → composing             │
  → completed             │
                          └→ running

任意执行态 → paused / cancelled / failed
```

每轮最多执行一个工具调用，然后保存任务状态。默认最大 12 步；达到预算仍无法完成时，返回已获得证据、未完成原因和建议的下一步，禁止无限循环。

### 5.2 `ResearchToolRegistry` 模块

Agent 只能调用注册过的研究工具。工具接口统一返回结构化结果，禁止返回无法验证的自由文本作为事实来源。

第一版工具：

| 工具 | 用途 | 权限 |
|---|---|---|
| `search_evidence` | 从指定文档范围检索证据 | 自动执行 |
| `explore_graph` | 查找实体、邻居和有来源的关系路径 | 自动执行 |
| `inspect_document` | 读取指定页、章节或父切片 | 自动执行 |
| `compare_evidence` | 对多个 EvidenceBundle 做结构化对比 | 自动执行 |
| `list_knowledge_gaps` | 标记证据冲突、缺失和待补资料 | 自动执行 |
| `save_research_note` | 保存 Agent 产物，不覆盖人工内容 | 执行前确认 |

统一接口：

```python
class ResearchTool:
    name: str
    input_schema: dict

    def execute(self, context: ToolContext, arguments: dict) -> ToolResult: ...
```

`ToolResult` 必须包含 `status`、`data`、`evidence_ids`、`warnings` 和 `elapsed_ms`。工具异常被转换为可恢复错误，由 Agent 决定降级、重试一次或结束任务。

### 5.3 `ResearchTaskStore` 模块

该模块集中处理任务、步骤和产物的持久化，避免任务状态散落在聊天消息、缓存和日志中。

建议接口：

```python
class ResearchTaskStore:
    def create(self, task: ResearchTask) -> None: ...
    def load(self, user_id: int, task_id: str) -> ResearchTask: ...
    def save_checkpoint(self, task: ResearchTask) -> None: ...
```

任务必须记录：用户目标、文档范围、当前计划、步骤状态、工具输入摘要、证据 ID、预算消耗、确认记录、最终产物和失败原因。敏感原文不重复写入任务日志，只保存证据引用。

### 5.4 `ChunkingEngine` 模块

建议外部接口：

```python
class ChunkingEngine:
    def split(
        self,
        document: ParsedDocument,
        config: ChunkingConfig,
    ) -> ChunkSet: ...
```

调用者只需要理解输入文档、配置和切分结果。标题识别、句子聚合、Token 计算、父子关联和边界重叠均隐藏在实现内部。

关键数据结构：

```python
@dataclass(slots=True)
class DocumentChunk:
    id: str
    doc_id: str
    text: str
    chunk_index: int
    parent_id: str | None
    level: Literal["child", "parent"]
    page_start: int | None
    page_end: int | None
    section_path: list[str]
    token_count: int
    chunking_version: str
```

### 5.5 `KnowledgeGraph` 模块

建议外部接口：

```python
class KnowledgeGraph:
    def index_document(
        self,
        user_id: int,
        doc_id: str,
        chunks: list[DocumentChunk],
    ) -> GraphBuildResult: ...

    def retrieve(
        self,
        user_id: int,
        query: str,
        limit: int,
    ) -> GraphEvidence: ...

    def get_subgraph(
        self,
        user_id: int,
        entity_id: str,
        depth: int,
    ) -> GraphView: ...

    def remove_document(self, user_id: int, doc_id: str) -> GraphCleanupResult: ...
```

生产使用 `Neo4jGraphStore` Adapter；测试使用 `InMemoryGraphStore` Adapter。图谱抽取模型也使用接口注入，测试时用确定性假实现，避免测试依赖外部模型。

### 5.6 `HybridEvidenceEngine` 模块

建议外部接口：

```python
class HybridEvidenceEngine:
    def search(
        self,
        user_id: int,
        query: str,
        options: RetrievalOptions,
    ) -> EvidenceBundle: ...
```

`EvidenceBundle` 统一返回：

- 文本切片；
- 父级上下文；
- 图谱关系路径；
- 来源文档与页码；
- 各阶段耗时；
- 降级与风险警告。

`search_evidence` 工具和兼容的普通问答链路只消费 `EvidenceBundle`，不直接了解 Chroma、Neo4j 或 Rerank 的内部细节。

### 5.7 计划、执行与验证规则

计划不是模型生成的一段说明文字，而是后端可验证的数据结构：

```python
@dataclass(slots=True)
class ResearchStep:
    id: str
    objective: str
    tool_name: str
    dependencies: list[str]
    status: Literal["pending", "running", "done", "blocked", "skipped"]
    success_criteria: list[str]
    evidence_ids: list[str]
```

规划约束：

- 每一步只能有一个明确目标和一个主要工具；
- 步骤必须声明成功条件，不允许只写“进一步分析”；
- 后续步骤只能引用已有步骤的结构化结果；
- 计划可以在证据不足时修订，但最多重规划两次；
- 新增外部范围、改变产物类型或执行写入操作时需要用户确认。

完成任务前执行证据门禁：

1. 每个核心结论至少关联一个有效证据 ID；
2. 对比结论必须覆盖被比较的每个对象；
3. 存在冲突证据时必须显式展示，不得静默选择；
4. 证据无法支持的内容进入 `knowledge_gaps`，不得混入结论；
5. 引用页码、原文片段与文档归属必须通过后端校验。

### 5.8 `TrainableModelRuntime` 模块

模型能力作为跨模块基础设施，而不是塞进 `ResearchAgent` 的训练逻辑。在线侧只暴露
两个稳定接口：

```text
EmbeddingModel.embed_documents(texts) / embed_query(text)
RerankerModel.rank(query, passages, top_k)
```

每种接口至少有两个 Adapter：

- `remote`：兼容当前云端 Embedding 与 Rerank API，保留 RAG3 基线；
- `local`：加载项目训练得到的 Sentence Transformers 模型；
- 测试使用 Fake Adapter，不下载模型、不依赖 GPU。

模型身份由 `task_type + provider + model_id + version` 确定。Embedding 的版本同时
决定 Chroma Collection 命名空间；修改 provider、model 或 local_path 时必须提交
新的 version。Reranker 可独立切换，不需要重建向量。训练目录提供：

- 基于显式相关性标签的 hard negative 构建；
- Embedding 三元组/对比学习，可选 LoRA；
- CrossEncoder Reranker 二分类训练，可选 LoRA；
- GraphExtractor 与 ArtifactComposer 的通用 LoRA-SFT；
- Recall@K、MRR 和 nDCG 离线评测。

训练数据不得默认采集普通用户聊天。优先使用冻结评测集、公开数据与明确授权、完成
脱敏的数据；生产反馈只能记录显式赞同/纠错和候选证据 ID。

---

## 6. 切分逻辑详细设计

### 6.1 从字符切分升级为 Token 感知

使用与目标模型匹配或近似的 tokenizer 计算 Token 数量。配置由 `chunk_size_chars` 升级为：

```text
child_max_tokens = 320
child_overlap_sentences = 1
parent_max_tokens = 1000
min_chunk_tokens = 80
chunking_strategy = structure_parent_child_v1
```

为了兼容现有配置，可以保留旧字段读取，但新文档统一写入新策略版本。

### 6.2 结构感知优先级

按以下优先级组织内容：

1. 文档标题；
2. 一级至三级章节标题；
3. 段落；
4. 列表项；
5. 表格；
6. 句子；
7. 最后的 Token 硬切分。

切片不能跨越明显的一级章节；对于较短的相邻段落，应在同一章节内聚合。

### 6.3 父子切片

- 子切片用于 Embedding 与召回，长度较小，定位更准确；
- 父切片用于传给 LLM，保留章节上下文；
- 检索命中子切片后，根据 `parent_id` 获取父切片；
- 多个子切片命中同一父切片时，只保留一次，避免上下文重复。

### 6.4 表格与公式

第一版策略：

- Markdown 表格保持整表，不按单行拆分；
- 过长表格按表头重复的方式分组；
- 公式保留原始文本与所在段落；
- 图片只保存占位与页码，暂不进行图像语义理解；
- 后续版本再评估布局模型和多模态解析。

### 6.5 版本与重建

新增切分版本机制：

- 每个文档记录 `chunking_version`；
- 管理端展示当前版本与待重建数量；
- 修改切分配置不会悄悄污染旧索引；
- 用户或管理员显式触发重建；
- 重建采用新版本写入成功后再切换，失败时保留旧索引；
- 重建过程中限制重复任务，保证幂等。
- `chunking_version` 与 `embedding_version` 分开管理；前者改变文档结构，后者改变向量空间；
- Collection 由 `user_id + embedding_version` 唯一确定，完整写入并验证后再原子切换活动版本。

---

## 7. 知识图谱详细设计

### 7.1 图谱对象

第一版建议支持有限、明确的实体类型：

- `Person`：作者、研究人员；
- `Organization`：机构、实验室、公司；
- `Method`：方法、模型、算法；
- `Dataset`：数据集；
- `Metric`：指标；
- `Material`：材料或实验对象；
- `Concept`：领域概念；
- `Document`：来源文档。

关系类型也应控制范围，例如：

- `PROPOSED_BY`
- `USES`
- `EVALUATED_ON`
- `OUTPERFORMS`
- `PART_OF`
- `RELATED_TO`
- `MENTIONED_IN`

未知关系先映射到 `RELATED_TO` 并保留原始谓词，避免关系类型无限膨胀。

### 7.2 数据模型

#### Entity

```text
id
user_id
canonical_name
display_name
entity_type
aliases
created_at
updated_at
```

#### Relation

```text
id
user_id
source_entity_id
target_entity_id
predicate
confidence
status: extracted | verified | rejected
created_at
```

#### Mention

```text
id
user_id
entity_id
doc_id
chunk_id
page
source_quote
char_start
char_end
```

#### RelationEvidence

```text
relation_id
doc_id
chunk_id
page
source_quote
extractor_model
extractor_version
```

`Mention` 与 `RelationEvidence` 是可信性的核心。没有来源切片和原文片段的关系不得进入检索上下文。

### 7.3 图谱抽取流程

```text
文档切分完成
  ↓
按父切片调用实体关系抽取模型
  ↓
JSON Schema 校验
  ↓
实体名称规范化与别名合并
  ↓
关系去重与置信度计算
  ↓
写入节点、关系和来源证据
  ↓
文档 graph_status = ready / partial / failed
```

抽取模型必须返回原文引用；后端验证引用是否真实存在于输入切片中。验证失败的关系进入拒绝队列，不写入正式图谱。

### 7.4 删除与重建

删除文档时：

1. 删除该文档的 Mention；
2. 删除该文档提供的 RelationEvidence；
3. 没有其他证据的关系被删除；
4. 没有 Mention、没有关系的孤立实体被删除；
5. 操作日志记录删除数量与失败原因。

---

## 8. 混合证据检索设计

### 8.1 检索模式

```text
vector：仅向量检索，用于兼容与基线比较
hybrid：向量 + 图谱，作为 RAG4 默认模式
graph：主要用于图谱页面探索，不作为普通问答默认模式
```

普通问答与 Agent 共用同一证据引擎。区别在于普通问答通常调用一次，Agent 可以根据计划进行多轮检索、缩小文档范围、检查冲突并补充原文上下文。

### 8.2 查询流程

1. 识别问题中的实体、时间、比较关系和指代；
2. 执行子切片向量检索；
3. 对识别出的实体执行图谱邻居与有限深度路径检索；
4. 将图谱路径映射回 RelationEvidence；
5. 合并文本证据，按 `chunk_id` 去重；
6. 通过 `RerankerModel` 接口精排（远程基线或本地微调版本）；
7. 用命中子切片定位父切片；
8. 控制总 Token 预算；
9. 返回统一证据包。

### 8.3 图谱触发条件

以下问题优先增加图谱检索权重：

- “A 与 B 有什么区别”；
- “某方法由谁提出、使用了什么数据集”；
- “哪些文档同时提到了某概念”；
- “某模型如何影响另一个方法”；
- 需要跨文档连接两个以上实体的问题。

纯事实定位问题仍以向量检索为主，避免所有问题都承担图谱查询成本。

### 8.4 降级策略

- Neo4j 不可用：自动回退向量检索，并返回 `graph_unavailable`；
- 实体抽取失败：不影响文档向量入库，文档状态为 `ready_with_graph_warning`；
- Rerank 超时：保留原有向量排序，并记录警告；
- 图谱路径没有来源证据：丢弃该路径；
- 证据不足：明确返回“现有资料不足”，不让模型补全事实。

---

## 9. 后端数据与迁移计划

### 9.1 MySQL 新增字段

`documents` 建议新增：

```text
chunking_version VARCHAR(64)
chunk_count INT
graph_status VARCHAR(32)
graph_updated_at DATETIME NULL
graph_error TEXT NULL
```

可新增 `document_index_jobs` 表记录切分、向量化和图谱构建任务：

```text
id, user_id, doc_id, job_type, status, progress,
strategy_version, error, started_at, finished_at
```

### 9.2 Research Agent 数据表

新增 `research_tasks`：

```text
id, user_id, goal, output_type, document_scope_json,
status, current_step_id, plan_version, step_budget,
token_budget, created_at, updated_at, completed_at, error
```

新增 `research_steps`：

```text
id, task_id, sequence, objective, tool_name,
arguments_json, status, success_criteria_json,
evidence_ids_json, warnings_json, elapsed_ms,
started_at, finished_at
```

新增 `research_artifacts`：

```text
id, task_id, user_id, artifact_type, title,
content_markdown, citation_map_json, version,
created_at, updated_at
```

新增 `task_confirmations`，记录需要人工确认的操作及结果，不保存账号凭据或完整敏感内容。

模型实验建议新增：

```text
model_versions:
id, task_type, provider, model_id, version, base_model,
dataset_version, code_commit, artifact_uri, metrics_json, status, created_at

index_versions:
id, user_id, embedding_version, chunking_version, status,
document_count, activated_at, created_at

retrieval_judgments:
id, dataset_split, query_id, candidate_id, label, source,
is_authorized, created_at
```

`retrieval_judgments` 只保存显式评测标签或授权反馈，不把普通聊天日志自动转成训练数据。

### 9.3 Chroma Metadata

新增：

```text
chunk_id
parent_id
level
section_path
page_start
page_end
token_count
chunking_version
embedding_model_version
```

### 9.4 迁移原则

- 数据库迁移只新增字段和表，不直接破坏 RAG3 数据；
- 旧文档显示为“待升级索引”；
- 后台分批重建，不阻塞应用启动；
- 迁移脚本支持 dry-run；
- 重建失败可继续使用旧向量索引；
- 模型和索引使用不可变版本号，切换活动版本不覆盖旧产物；
- 上线前备份 MySQL、Chroma 和 Neo4j 数据卷。

---

## 10. 后端接口计划

保留现有接口，新增以下接口。

### 10.1 Research Agent 任务

```text
POST /api/v1/research/tasks
GET  /api/v1/research/tasks
GET  /api/v1/research/tasks/{task_id}
GET  /api/v1/research/tasks/{task_id}/events
POST /api/v1/research/tasks/{task_id}/pause
POST /api/v1/research/tasks/{task_id}/resume
POST /api/v1/research/tasks/{task_id}/cancel
POST /api/v1/research/tasks/{task_id}/confirm
GET  /api/v1/research/tasks/{task_id}/artifact
```

创建任务请求：

```json
{
  "goal": "比较选定论文的 RAG 切分策略并生成研究笔记",
  "document_scope": ["doc-1", "doc-2"],
  "output_type": "comparison",
  "constraints": {
    "max_steps": 10,
    "require_citations": true,
    "allow_note_write": false
  }
}
```

事件流必须区分 `plan_created`、`step_started`、`tool_completed`、`evidence_added`、`confirmation_required`、`artifact_completed` 和 `task_failed`，前端不能靠解析自然语言猜测任务状态。

### 10.2 文档与切片

```text
GET  /api/v1/docs/{doc_id}
GET  /api/v1/docs/{doc_id}/content
GET  /api/v1/docs/{doc_id}/chunks
POST /api/v1/docs/{doc_id}/reindex
GET  /api/v1/docs/{doc_id}/index-job
```

### 10.3 知识图谱

```text
GET  /api/v1/graph/search?q=&type=
GET  /api/v1/graph/entities/{entity_id}
GET  /api/v1/graph/subgraph?entity_id=&depth=1&limit=100
GET  /api/v1/graph/documents/{doc_id}
POST /api/v1/graph/documents/{doc_id}/rebuild
```

### 10.4 兼容聊天

扩展现有聊天请求：

```json
{
  "session_id": "...",
  "query": "...",
  "enable_rag": true,
  "retrieval_mode": "hybrid",
  "doc_ids": []
}
```

扩展 SSE `done` 事件：

```json
{
  "message_id": "...",
  "citations": [],
  "graph_paths": [],
  "retrieval_summary": {
    "vector_hits": 8,
    "graph_hits": 3,
    "reranked_hits": 5,
    "elapsed_ms": 1860
  },
  "warnings": []
}
```

所有接口必须通过当前用户身份确定 `user_id`，不得接受前端传入的任意用户 ID。

---

## 11. 前端体验与视觉计划

### 11.1 设计 Brief

```text
产品：证据驱动的个人学术 Research Agent
受众：学生、研究者、知识工作者
目的：把研究目标转成可观察步骤，找到证据、理解关系并交付研究产物
设备：桌面端优先，兼容平板和移动端
情绪：安静、严谨、编辑感、可信
骨架风格：暖纸手账
借用特征：瑞士网格的左对齐与秩序、杂志排版的文本层级
```

### 11.2 设计 Tokens

```text
页面底色：#F7F4EC
主要文字：#27251E
次级文字：#6F6A60
品牌藏青：#17324D
引用朱红：#A6452D
成功苔绿：#496B52
标题字体：Noto Serif SC / Source Han Serif SC
正文字体：Noto Sans SC / Microsoft YaHei
字阶：12 / 14 / 16 / 20 / 28 / 40
圆角：6px 与 10px；层级依靠留白、底色和 1px 边框
```

约束：色板不超过五类主色，图标统一使用线性 SVG，不使用 Emoji，不使用大面积渐变，不生成等宽卡片海。

### 11.3 信息架构

```text
Research Agent
├── 概览
├── 新建研究任务
├── 研究任务
│   └── 任务工作区
├── 快速问答
├── 文献库
│   └── 文档详情
├── 知识图谱
├── 研究笔记
└── 设置

管理员
├── 用户管理
├── 模型与检索配置
├── 索引任务
└── 运行监控
```

### 11.4 概览页

目标：让用户回来后能立即继续研究。

内容优先级：

1. 进行中任务、阻塞原因与“继续研究”；
2. 最近打开的文档；
3. 待处理、失败或待重建的文档；
4. 最近生成的研究产物和新发现的实体关系；
5. 使用量统计作为次要信息，不占据首屏中心。

布局使用非对称 7:5 网格，不使用四个等宽统计卡片。

### 11.5 新建研究任务

新建任务不直接暴露复杂 Agent 参数，而是引导用户明确四件事：

1. 想解决什么研究问题；
2. 使用哪些文档或知识库范围；
3. 需要什么产物：回答、对比表、综述或研究笔记；
4. 是否允许保存笔记，以及最大执行范围。

系统在启动前展示简短的目标复述和预计步骤。若问题过于宽泛，只追问会实质改变执行范围的信息，不把所有任务都变成冗长表单。

### 11.6 任务工作区

桌面端采用三栏工作区：

```text
目标与计划  |  执行过程与产物  |  证据、原文与关系
```

- 左栏展示目标、文档范围、步骤、状态、预算和暂停/取消；
- 中栏展示当前步骤、Agent 说明、结构化中间结果和最终产物；
- 右栏展示本步骤使用的证据，可切换原文与知识图谱；
- 点击计划步骤能查看工具、输入摘要、结果、耗时和警告；
- `waiting_confirmation` 状态必须明确展示即将发生的写入及影响；
- 失败时保留已完成步骤，允许从安全检查点恢复；
- 最终产物中的引用点击后定位到右栏原文，不跳出任务上下文。

移动端先保证查看任务和证据，创建复杂任务与图谱探索不作为首期核心体验。

### 11.7 快速问答页

桌面端采用三栏工作区：

```text
会话与范围  |  对话与输入  |  证据与关系
```

- 左栏支持选择全知识库或指定文档；
- 中栏保持对话主线，输入框始终可见；
- 右栏默认显示本轮证据；
- 点击引用定位到原文，并高亮对应片段；
- 点击关系路径切换到图谱视图；
- 回答生成时分阶段显示“检索资料、分析关系、组织回答”；
- 降级警告使用可理解文案，不直接暴露内部异常名称。

移动端将证据栏改为底部抽屉，保留回答与证据的连续跳转。

快速问答继续支持 RAG3 用户习惯，但复杂问题可通过“转为研究任务”带上当前问题、文档范围和已有证据进入 Agent。

### 11.8 文献库与文档详情

文献库支持：

- 文件名、类型、标签、状态与更新时间筛选；
- 上传、重试、重建索引和删除；
- 显示切分版本、实体数量和图谱状态；
- 状态说明使用进度时间线，而不是只显示彩色 Badge。

文档详情页采用三栏：目录、正文、研究侧栏。侧栏展示当前段落对应的切片、实体、关系和引用次数。管理员或调试模式可显示切片边界与 Token 数量。

### 11.9 知识图谱页

推荐使用 Cytoscape.js：

- 中央：关系图画布；
- 左侧：实体搜索、类型筛选、文档范围；
- 右侧：实体详情、关系、原文证据；
- 节点颜色只区分实体类型；
- 节点大小可表示提及次数，但必须有图例；
- 默认只加载局部子图，避免一次绘制全库；
- 点击边必须显示 RelationEvidence；
- 支持“以此实体提问”，将实体带入聊天页。
- 支持“围绕此实体创建研究任务”，自动带入当前实体、关系证据和文档范围。

图谱的目标是帮助探索与验证，不是制造炫酷动画。禁止 3D 旋转、持续漂浮和无意义粒子效果。

### 11.10 研究笔记

- 区分用户手写内容与 Agent 生成内容；
- Agent 默认新建版本或追加建议，不静默覆盖人工内容；
- 每个段落保留任务 ID 和引用映射；
- 支持将证据不足项转为后续研究任务；
- 第一版导出 Markdown，DOCX/PDF 放入后续版本。

### 11.11 管理端

新增：

- 切分策略和版本；
- 父子切片 Token 配置；
- 实体抽取模型配置；
- 图谱任务成功率、失败队列与重试；
- 混合检索各阶段耗时；
- 旧索引待升级数量。
- Embedding/Reranker 的 provider、模型目录、版本和活动状态；
- 模型版本对应的冻结评测指标、索引重建进度与一键回滚入口；
- Agent 任务成功率、平均步骤数、暂停/取消和失败原因；
- 工具调用延迟、错误率及任务预算消耗；
- 不展示普通用户完整研究内容和原文。

涉及全局切分策略变更时，界面必须明确提示“仅影响新文档”或提供显式重建选项。

---

## 12. 评测与实验计划

### 12.1 建立 RAG3 基线

开发前冻结一份基线：

- 固定测试文档、模型和参数；
- 保存 RAG3 每道题的检索结果、答案、引用、耗时与成本；
- 记录软件版本和外部模型版本；
- 修复当前虚拟环境，确保自动化测试实际可运行。

### 12.2 评测集结构

证据问答集第一版至少 60 题：

| 类型 | 数量 | 目的 |
|---|---:|---|
| 单跳事实题 | 15 | 验证基本召回与精确回答 |
| 跨文档多跳题 | 15 | 验证知识图谱与证据融合 |
| 对比题 | 10 | 验证多个实体与多个来源 |
| 总结题 | 10 | 验证父切片上下文完整性 |
| 不可回答题 | 10 | 验证拒答与幻觉控制 |

测试文档需包含标题层级、长段落、表格、相似实体和有意设计的干扰信息。

另建立至少 20 个端到端 Agent 任务：

| 类型 | 数量 | 验证重点 |
|---|---:|---|
| 多文档对比 | 5 | 范围覆盖、对比维度、引用完整性 |
| 主题综述 | 5 | 计划质量、证据聚合、知识缺口 |
| 支持/反对证据地图 | 5 | 冲突证据识别、关系追溯 |
| 研究笔记生成 | 5 | 产物结构、引用映射、写入确认 |

### 12.3 指标

检索指标：

- Recall@K；
- MRR；
- nDCG；
- 正确文档命中率；
- 正确切片命中率；
- 图谱路径命中率。

回答指标：

- 答案正确率；
- 引用准确率；
- 引用覆盖率；
- 无依据陈述比例；
- 不可回答题正确拒答率。

工程指标：

- P50/P95 检索延迟；
- P50/P95 首 Token 延迟；
- 单问题 Token 和费用；
- Neo4j、Rerank、LLM 的失败与降级率；
- 文档索引吞吐和失败率。

Agent 指标：

- 任务完成率；
- 步骤成功率与平均重规划次数；
- 核心结论证据覆盖率；
- 文档范围遵守率；
- 错误工具选择率；
- 正确触发人工确认率；
- 暂停、恢复和取消成功率；
- 单任务耗时、Token 和费用；
- 人工评分：产物可用性、结构清晰度和继续研究价值。

### 12.4 实验矩阵

至少比较：

1. RAG3 字符切分 + 向量检索；
2. Token 结构切分 + 向量检索；
3. 父子切片 + 向量检索；
4. 父子切片 + 向量检索 + Rerank；
5. 父子切片 + 混合检索 + Rerank。

每次只改变一个主要变量，保留原始明细，报告不仅写平均值，也展示失败案例。

模型微调实验按以下顺序增加，且每一步都与未微调基线做单变量对照：

1. 基线 Embedding + 基线 Reranker；
2. 基线 Embedding + hard-negative Reranker；
3. 领域 Embedding + 基线 Reranker；
4. 领域 Embedding + hard-negative Reranker；
5. 在证据门禁不变的条件下比较基线生成模型与 ArtifactComposer LoRA。

Reranker 以 MRR/nDCG 为主，Embedding 以 Recall@K 为主；生成模型不能只看风格评分，
还必须比较引用准确率、证据覆盖率、JSON/Markdown 结构合法率和不可回答题拒答率。

Agent 实验至少比较：

1. 单轮 RAG 直接生成产物；
2. 固定工作流生成产物；
3. Research Agent 动态规划与工具调用；
4. Research Agent + 证据门禁。

比较重点不是“回复更长”，而是任务完成率、证据覆盖、引用准确性、成本和失败可恢复性。

---

## 13. 测试策略

### 13.1 模块测试

#### ResearchAgent

- 计划步骤数、依赖和工具名称符合约束；
- 每轮只执行一个工具并保存检查点；
- 最大步骤、重规划、Token 和超时预算生效；
- 工具失败能按策略降级或终止；
- 写入工具进入等待确认，拒绝后不会执行；
- 暂停、恢复和取消保持幂等；
- 证据不足时生成知识缺口而不是编造结论；
- Fake Model 与 Fake Tool 下任务执行结果确定。

#### ResearchToolRegistry

- 未注册工具不能执行；
- 输入 Schema 和用户文档范围得到校验；
- 工具结果只引用当前用户可访问的证据；
- 异常统一转换为结构化 ToolResult；
- 只读和写入权限分级正确。

#### ChunkingEngine

- 标题与正文不错误跨章；
- 中英文句子边界；
- 超长无标点文本；
- overlap 保留完整句子；
- 表格切分时重复表头；
- 父子关联正确；
- Token 上限与最小切片合并；
- 同一输入和配置输出确定。

#### KnowledgeGraph

- JSON Schema 校验；
- 无原文引用的关系被拒绝；
- 实体别名去重；
- 同一关系多来源合并；
- 用户隔离；
- 删除文档后关系与孤立节点清理；
- Neo4j 失败时返回明确错误。

#### HybridEvidenceEngine

- 向量和图谱结果去重；
- 图谱证据映射到正确切片；
- 父切片展开不重复；
- Token 预算控制；
- Neo4j 和 Rerank 降级；
- 不可回答时证据为空或不足。

### 13.2 接口测试

- 创建、读取、暂停、恢复和取消研究任务；
- 任务事件顺序、断线重连和重复确认；
- 非任务所有者访问统一返回 404；
- Agent 不得突破创建任务时的文档范围；
- 文档详情和切片分页；
- 重建索引幂等；
- 非文档所有者访问统一返回 404；
- 图谱搜索与子图限制；
- SSE 事件顺序与新增字段；
- 旧前端请求仍兼容；
- 删除文档的跨存储一致性。

### 13.3 前端测试

- 任务创建、计划展示、步骤进度、暂停、恢复和取消；
- 确认弹窗准确描述写入目标和影响；
- 任务产物、引用、原文和关系联动；
- 问答、引用定位、关系路径跳转；
- 文档上传、失败、重试、重建和删除；
- 图谱节点、边和证据交互；
- 空状态、加载、部分失败和降级；
- 键盘导航、焦点状态和基础可访问性；
- 360px、768px、1280px、1440px 响应式截图；
- 长文件名、长实体名、无数据和大量数据。

### 13.4 端到端关键路径

```text
注册登录
→ 上传文档
→ 等待向量与图谱完成
→ 创建跨文档对比任务
→ 检查 Agent 计划和文档范围
→ 观察工具调用与证据积累
→ 查看最终对比产物
→ 从结论跳转到关系和原文
→ 确认保存研究笔记
→ 删除文档
→ 验证向量与图谱均已清理
```

---

## 14. 安全、隔离与可靠性

- Agent 工具采用显式白名单，不提供通用 Shell 和任意 Python 执行；
- 任务创建时冻结 `user_id`、文档范围、工具权限和预算，执行中不得自行扩大；
- 只读检索工具可自动执行；写入笔记、批量重建和导出操作需要确认；
- 模型输出只能提出工具调用，后端必须重新校验工具名、Schema、权限和资源归属；
- 文档内容视为不可信数据，文档中的指令不得改变 Agent 系统规则或工具权限；
- Agent 生成的产物与用户人工内容分版本保存，禁止静默覆盖；
- Neo4j 中所有节点和关系包含 `user_id`；
- 图谱查询必须从当前登录用户派生权限；
- 原文片段返回前验证文档归属；
- 图谱抽取模型的输入只包含当前用户文档；
- API Key 延续加密存储和脱敏返回；
- 文档内容和图谱信息不得写入普通应用日志；
- 对上传文件继续限制格式、数量和大小；
- 图谱查询限制最大深度、节点数和执行时间；
- 重建任务具备幂等键与并发锁；
- 任务执行具备取消信号、步骤上限、Token 预算、总超时和单工具超时；
- 崩溃恢复只从已持久化检查点继续，不重复执行已确认的写入；
- 跨 Chroma、Neo4j、MySQL 的删除采用可重试补偿流程，并记录未完成步骤。

---

## 15. 可观测性

新增日志类型：

```text
research_task
research_plan
research_step
research_tool_call
research_verification
research_artifact
chunking_run
graph_extract
graph_write
graph_query
hybrid_retrieve
index_rebuild
graph_cleanup
```

每次问答记录：

- 查询改写结果；
- 向量命中数量；
- 图谱命中路径数量；
- 合并与 Rerank 后证据数量；
- 各阶段耗时；
- Token 使用量；
- 降级原因；
- 最终引用数量。

每个 Agent 任务额外记录：

- 任务类型、状态变化和计划版本；
- 每步工具名称、耗时、结果状态和证据 ID 数量；
- 重试、重规划、确认、暂停与取消；
- 预算使用、知识缺口和完成门禁结果；
- 产物版本及引用覆盖率。

管理后台只展示统计与失败原因，不展示普通用户的完整问题和文档内容。

---

## 16. 目录结构建议

```text
project/
├── backend/
│   ├── app/
│   │   ├── modeling/
│   │   │   ├── interfaces.py
│   │   │   ├── registry.py
│   │   │   └── adapters/
│   │   ├── domain/
│   │   │   ├── research_task.py
│   │   │   ├── research_step.py
│   │   │   ├── chunks.py
│   │   │   ├── graph.py
│   │   │   └── evidence.py
│   │   ├── services/
│   │   │   ├── research_agent.py
│   │   │   ├── research_task_store.py
│   │   │   ├── evidence_verifier.py
│   │   │   ├── artifact_composer.py
│   │   │   ├── chunking_engine.py
│   │   │   ├── graph_builder.py
│   │   │   ├── knowledge_graph.py
│   │   │   ├── hybrid_retriever.py
│   │   │   └── rag_service.py
│   │   ├── tools/
│   │   │   ├── registry.py
│   │   │   ├── search_evidence.py
│   │   │   ├── explore_graph.py
│   │   │   ├── inspect_document.py
│   │   │   └── save_research_note.py
│   │   ├── adapters/
│   │   │   ├── llm_planner.py
│   │   │   ├── fake_planner.py
│   │   │   ├── neo4j_graph_store.py
│   │   │   ├── memory_graph_store.py
│   │   │   └── llm_graph_extractor.py
│   │   └── api/v1/
│   │       ├── research.py
│   │       ├── graph.py
│   │       └── docs.py
│   ├── tests/
│   │   ├── test_research_agent.py
│   │   ├── test_research_tools.py
│   │   ├── test_research_api.py
│   │   ├── test_chunking_engine.py
│   │   ├── test_knowledge_graph.py
│   │   ├── test_hybrid_retriever.py
│   │   └── test_graph_api.py
│   └── evaluation/
│       ├── datasets/
│       ├── run_eval.py
│       └── reports/
├── training/
│   ├── datasets/
│   │   └── build_retrieval_dataset.py
│   ├── embedding/train.py
│   ├── reranker/train.py
│   ├── sft/train_lora.py
│   ├── evaluation/evaluate_ranking.py
│   └── outputs/
├── models/                       # 本地模型产物，不提交 Git
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── research/
│       │   ├── evidence/
│       │   ├── graph/
│       │   └── document/
│       ├── pages/
│       │   ├── NewResearchTaskPage.tsx
│       │   ├── ResearchTaskPage.tsx
│       │   ├── ResearchNotesPage.tsx
│       │   ├── WorkspacePage.tsx
│       │   ├── DocumentDetailPage.tsx
│       │   └── KnowledgeGraphPage.tsx
│       ├── api/
│       │   ├── research.ts
│       │   └── graph.ts
│       └── types/
│           └── graph.ts
└── deploy/
    ├── docker-compose.yml
    └── neo4j/
```

目录只是建议，不应为了“架构好看”机械拆分。只有当模块拥有稳定接口、真实变化点或独立测试价值时才创建对应目录。

---

## 17. 八周实施里程碑

### 第 0 阶段：准备与基线（第 1–3 天）

任务：

- 从 RAG3 创建独立开发分支；
- 修复环境并运行已有测试、前端 lint、build 和 E2E；
- 固定 RAG3 检索配置、页面截图和评测结果；
- 建立 Embedding/Reranker 接口、remote/local Adapter 与模型版本配置；
- 固定第一版检索题、候选证据导出格式与数据授权规则；
- 选定两组真实文献，定义 20 个 Agent 任务及人工期望产物；
- 建立迁移、备份和回滚清单。

完成标准：

- 前后端在干净环境可启动；
- RAG3 基线可复现且没有未解释的失败；
- 基线模型与本地模型可以通过同一接口替换，Fake Adapter 测试通过；
- Agent MVP 的四类任务、范围和验收样例已经冻结。

### 第 1 阶段：结构感知切分（第 1 周）

任务：

- 定义 ParsedDocument、DocumentChunk 与 ChunkSet；
- 实现 Token 计算、结构边界和父子切片；
- 扩展 Chroma Metadata，增加切分版本与重建任务；
- 编写模块测试并与 RAG3 做单变量实验。

完成标准：

- 标题、章节、页码与父子关系可查询；
- 所有切片符合 Token 上限；
- 旧策略仍可作为基线运行；
- 实验报告包含指标与失败案例。

### 第 2 阶段：知识图谱与混合证据（第 2–3 周）

任务：

- 加入 Neo4j，定义图谱存储 seam 和两个 Adapter；
- 实体与关系抽取必须包含原文引用并通过校验；
- 实现归一化、别名、去重、删除和重建；
- 实现 HybridEvidenceEngine、父切片展开和降级；
- 建立多跳、对比和不可回答评测。
- 从基线误召回中构建 hard negative，训练第一版 Reranker 并记录 MRR/nDCG、延迟与失败案例。

完成标准：

- 每个正式关系至少有一个有效来源；
- 用户图谱严格隔离；
- 混合证据能返回文本、关系路径和警告；
- Neo4j 或 Rerank 不可用时可以明确降级。
- 微调 Reranker 未通过门禁时可以立即切回 `baseline` 版本。

### 第 3 阶段：Research Agent 内核（第 4 周）

任务：

- 定义 ResearchTask、ResearchStep、ToolResult 和状态机；
- 实现 ResearchAgent、ResearchTaskStore 和 ResearchToolRegistry；
- 首批接入只读工具：检索证据、探索图谱、检查文档和对比证据；
- 实现步骤预算、检查点、取消、失败恢复和最多两次重规划；
- 使用 Fake Planner 和 Fake Tool 完成确定性测试。

完成标准：

- 一个多文档对比任务能够按计划完成；
- 每步执行前后都有持久化状态；
- 未注册工具和越界文档调用被后端拒绝；
- 达到预算后能交付部分结果和知识缺口，而不是无限循环。

### 第 4 阶段：证据门禁与研究产物（第 5 周）

任务：

- 实现 EvidenceVerifier 和 ArtifactComposer；
- 支持回答、对比表、主题综述和研究笔记；
- 检查核心结论证据覆盖、对比对象覆盖和冲突证据；
- 实现 `save_research_note` 及确认流程；
- 建立 20 个端到端 Agent 任务评测。
- 当 ArtifactComposer 输出协议稳定后，制作 LoRA-SFT 小样本实验；模型输出仍必须通过 EvidenceVerifier。

完成标准：

- 产物引用能够定位到文档、页码和原文；
- 证据不足内容只出现在知识缺口中；
- Agent 不会静默覆盖人工笔记；
- 四类核心任务均有成功和失败样例。

### 第 5 阶段：Agent 前端工作区（第 6 周）

按逐屏方式实施：

1. 固化全局 tokens、字体、图标和页面框架；
2. 实现新建研究任务与任务工作区；
3. 实现计划、步骤、工具、确认、证据和产物联动；
4. 重构快速问答、文献库与文档详情；
5. 实现知识图谱与研究笔记页面；
6. 补充概览与管理员任务监控。

完成标准：

- 用户能看见 Agent 正在做什么、为什么做以及用了哪些证据；
- 暂停、恢复、取消和确认状态清晰；
- 结论、关系、引用和原文能连续导航；
- 关键路径 E2E 通过，主要状态具备响应式和可访问性支持。

### 第 6 阶段：整体验证与交付（第 7–8 周）

任务：

- 执行检索、问答和 Agent 完整评测矩阵；
- 仅当召回瓶颈仍存在时训练领域 Embedding，使用新版本完成独立索引重建与回滚演练；
- 修复高优先级失败案例；
- 验证部署、升级、备份、恢复和回滚；
- 更新需求、接口、数据库、安全和部署文档；
- 制作真实操作演示并整理个人开发复盘。

完成标准：

- 所有验收项均有代码、测试、截图或实验数据作为证据；
- 评测原始数据、模型版本、代码版本和配置可复现；
- README 不包含无法证明的性能与“自主科研”宣传；
- 能清楚说明 Agent 的模块接口、工具权限、失败案例和产品边界。

---

## 18. 任务优先级

### P0：必须完成

- 恢复可运行测试基线；
- 稳定模型接口、remote/local Adapter、不可变版本号与 Embedding 索引隔离；
- 结构感知父子切片；
- 图谱来源证据；
- 用户隔离；
- 文档删除与重建一致性；
- 混合证据引擎；
- Research Agent 状态机和任务持久化；
- 四个只读研究工具；
- 步骤、Token、超时和重规划预算；
- 证据门禁和知识缺口；
- 写入研究笔记的确认机制；
- 任务工作区和证据侧栏；
- 文档详情与局部图谱；
- 多跳、不可回答和 Agent 任务评测。
- 冻结评测集与显式授权训练数据规则。

### P1：建议完成

- 概览页；
- 实体别名管理；
- 图谱抽取失败重试；
- 管理员索引任务页面；
- 检索阶段耗时可视化；
- 文档范围筛选；
- 任务暂停、恢复和失败检查点；
- 快速问答一键转为研究任务。
- hard-negative Reranker 训练、离线 MRR/nDCG 评测与版本切换；
- 当 Recall@K 明确受限时进行 Embedding 微调和全量重建实验。

### P2：后续版本

- 用户手动纠正实体与关系；
- 图谱版本对比；
- 多模态图表理解；
- 文献自动聚类与主题演化；
- 导出图谱或研究笔记；
- 受控外部文献搜索工具；
- 用户自定义工作流模板；
- 多 Agent 分工与并行研究。
- GraphExtractor/ArtifactComposer LoRA-SFT 与偏好优化；
- 视觉语言模型处理图表、公式和扫描页，并保留页级来源；

---

## 19. 风险清单与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 图谱抽取产生幻觉 | 错误关系污染回答 | 强制原文引用验证；无证据不入图 |
| 实体重复和别名混乱 | 图谱碎片化 | 规范化名称、别名、类型与人工抽检 |
| Neo4j 增加部署复杂度 | 环境难复现 | Docker 固定版本、健康检查、数据卷与回滚 |
| 混合检索延迟增加 | 用户等待时间变长 | 条件触发图谱、并行查询、超时降级与缓存 |
| 父切片导致上下文过长 | 成本和延迟增加 | Token 预算、父片去重、动态裁剪 |
| 重建过程中索引不一致 | 搜索缺失或混用 | 新版本完整写入后原子切换 |
| 前端图谱节点过多 | 卡顿和不可读 | 默认局部子图、节点上限、按需扩展 |
| 评测题过于简单 | 得出虚假高分 | 增加多跳、总结、干扰与不可回答题 |
| AI 生成代码本人不理解 | 面试时无法解释 | 每阶段手写设计记录、亲自调试和复盘 |
| Agent 计划看似合理但无法执行 | 任务停滞或循环 | 结构化步骤、成功条件、工具白名单和步数上限 |
| 文档中的提示注入影响 Agent | 越权调用或错误结论 | 文档视为不可信数据；权限由后端固定而非模型决定 |
| Agent 产物引用不完整 | 用户误信总结 | 完成前执行证据门禁，未覆盖内容进入知识缺口 |
| 自动保存覆盖用户笔记 | 数据损失 | 写入前确认、版本化保存、默认不覆盖人工内容 |
| 任务成本不可控 | 延迟和费用过高 | 步骤、Token、工具调用和总时长预算 |
| 微调数据泄漏或未经授权 | 隐私风险与虚高评测 | 只用显式授权数据；train/dev/test 按文档或主题隔离；记录数据版本 |
| Embedding 切换后向量混写 | 检索结果不可解释或直接报维度错误 | 新版本独立 Collection；完整重建后原子切换；保留旧索引回滚 |
| 模型提升来自过拟合 | 离线很好、真实任务退化 | 冻结测试集、单变量实验、记录失败案例与线上灰度指标 |

---

## 20. Git 与开发纪律

建议按可审查的最小变更提交：

```text
chore: restore reproducible RAG3 baseline
feat(chunking): add token-aware parent-child chunks
feat(indexing): add versioned reindex jobs
feat(modeling): add local and remote embedding reranker adapters
feat(training): add hard-negative retrieval training pipeline
feat(graph): add sourced entity and relation extraction
feat(graph): add neo4j and in-memory adapters
feat(evidence): add hybrid evidence engine
feat(agent): add research task state machine and store
feat(agent): add controlled research tool registry
feat(agent): add evidence verification and knowledge gaps
feat(artifact): add cited comparison and review outputs
feat(api): expose graph and document evidence endpoints
feat(api): expose research task lifecycle and events
refactor(ui): establish RAG4 visual system
feat(ui): add research task workspace
feat(ui): add document inspector and knowledge graph
feat(ui): add versioned research notes
test: add multi-hop, unanswerable and agent task evaluation
docs: publish RAG4 experiment and deployment report
```

每个提交至少回答：

1. 为什么需要这个变化？
2. 调用了哪个模块接口？
3. 如何验证？
4. 失败时如何回滚或降级？

不要一次提交整个 RAG4，也不要让 AI 在没有测试基线的情况下大规模重写 RAG3。

---

## 21. 最终交付物

- RAG4 前后端源码；
- Research Agent 状态机、工具注册表和任务持久化实现；
- 四类核心研究任务模板与带引用产物；
- Agent 工具权限、确认机制和失败恢复说明；
- 数据库与 Neo4j 迁移文件；
- RAG3 → RAG4 升级和回滚脚本；
- 结构化切分设计说明；
- 知识图谱数据模型与接口说明；
- RAG3/RAG4 检索对照评测、Agent 任务评测、原始结果和实验报告；
- 模型训练脚本、数据说明、模型卡、模型/索引版本清单与回滚记录；
- 前端设计 tokens、页面截图和交互说明；
- Docker Compose 生产部署文件；
- 测试报告；
- README、部署指南与故障排查；
- 项目演示视频；
- 个人开发复盘：决策、失败案例、调试过程和个人贡献。

---

## 22. 面试可讲述的项目主线

RAG4 的面试价值不应是“我套了一个 Agent 框架、加了 Neo4j”，而应是：

> RAG3 的单跳问答已经可用，但面对“比较多篇论文并形成综述”时，用户仍要反复提问、人工整理，而且系统无法展示任务进度和结论依据。我先建立 RAG3 基线，把切分升级为 Token 感知的父子切片，再构建带原文证据的私有知识图谱与混合证据引擎。在此基础上，我设计了一个有限状态的 Research Agent：它把研究目标拆成有成功条件的步骤，只能调用白名单工具，每步保存检查点，完成前验证结论的证据覆盖。前端围绕目标、计划、执行、证据和产物重构。最终我用真实的多文档任务比较单轮 RAG、固定工作流和 Agent，记录任务完成率、引用准确率、成本和失败恢复情况。

这条主线能体现需求判断、深模块设计、Agent 工程、RAG 与图谱检索、权限控制、评测方法和产品表达，而不是简单堆叠模型与框架。

---

## 23. 开工顺序

立即执行顺序：

1. 修复并冻结 RAG3 测试和评测基线；
2. 先建立模型接口、版本化索引和冻结评测数据格式，不立即训练大模型；
3. 独立实现 ChunkingEngine，不同时修改图谱和前端；
4. 为单篇测试文档建立有来源的局部图谱，并完成混合证据与降级；
5. 从真实失败案例构建 hard negative，先训练和评测 Reranker；
6. 用 Fake Adapter 实现 ResearchAgent 状态机和四个只读工具；
7. 接入真实证据引擎，增加证据门禁、研究产物和保存确认；
8. 先实现任务工作区，再重构问答、文档详情和图谱页；
9. 仅在 Recall@K 仍受限时微调 Embedding 并重建独立版本索引；
10. 最后补生成模型 LoRA 实验、概览、管理监控、部署和完整评测。

第一周结束前不追求 Agent 自主循环或图谱动画；第一项可验收成果必须是**可复现的 RAG3 基线与更可靠的切分模块**。第四周结束时必须先用 Fake Adapter 证明 Agent 状态机、权限和恢复机制正确，再接入真实模型，避免把随机模型行为误当成系统能力。
