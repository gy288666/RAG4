# 分批核验、上下文分配与候选召回（2026-10-20）

本轮实现可保存、可恢复的逐文档核验，并对上下文与召回分别做四路对照。工程恢复能力通过测试；真实回放保存两篇报告，第三篇仍连接超时。q09 的 AI 锚点覆盖补齐，q12 尚未解决，人工研究质量验收仍未通过。

以上为 R25 历史结果。后续 R26 已在独立预算副本中完成第三篇核验、生成部分表，并用可选来源角色排序补齐 q12 开发锚点；语义质量仍未验收。最新结果见 [R26 续接记录](research_continuation.md)，本页原实验和失败不覆盖。

## 1. 按文档核验与合并

新增 `research-comparison-v2` 计划，显式通过创建任务 API 的 `plan_version` 选择，旧任务和默认仍是 v1。每篇论文执行 `verify_document`，最多四条结论、一次模型调用、一份 `VerificationBatch`；所有批次成功之后，`merge_verification` 校验范围和计数并合并报告，不调用模型。最后才允许 ArtifactComposer 生成产物。

| 文档数 | 固定步骤 | 固定模型调用 | 缺省预算（步骤/模型预留） |
| --- | --- | --- | --- |
| 3 | 11 | 6 | 13 / 8 |
| 5 | 17 | 10 | 19 / 12 |

自定义预算不足时拒绝创建，不静默扩容。失败和重试均预先消耗预算；成功批次已保存，显式 resume 只重跑失败步骤。暂停、取消和迟到结果保护沿用原 CAS。存量 v1 计划和序列化保持兼容，无数据库迁移。

创建任务可显式组合：

```json
{
  "plan_version": "research-comparison-v2",
  "verification_protocol": "source-handles-v4",
  "context_policy": "local-window-v3",
  "candidate_policy": "lexical-fusion-v2"
}
```

以上是可选参数，还需传原有 index_version_id、document_ids 和 goal。三项策略可以分别对照，不因选择新计划自动升级证据或核验协议。

### 真实回放及失败

复用 R20 原三篇论文的已完成检索/抽取 checkpoint 和十二条结论，创建新任务、新 SQLite 副本；不重新计作端到端抽取成功。Qwen/Qwen2.5-7B-Instruct、source-handles-v4、JSON 模式，输出上限 4096，连接 5 秒/读取 60 秒。预定最多四次新请求，失败自动停止，恢复由另一次明确的 `--resume` 执行。

| 请求 | 文档 | 状态 | 耗时 | 已报 Token |
| --- | --- | --- | --- | --- |
| 1 | DPR | ReadTimeout | 62175ms | 未知 |
| 2 | DPR（显式恢复） | 成功，3/4 机器支持 | 31686ms | 3450 |
| 3 | FiD | 成功，1/4 机器支持 | 20198ms | 3547 |
| 4 | REALM | ConnectTimeout | 5040ms | 未知 |

四次共 6997 已报 Token；失败请求用量及货币费用未知。DPR、FiD 两份报告已保存，REALM 失败后仍在；没有不完整的合并报告或新比较表。**拆批并没有消除模型/网络超时**，实际验证的是成功结果能持久保留。预算用完后没有继续重试、换模型或增加超时。

脚本 `scripts/reverify_research_batches.py` 有总请求上限、逐文档调用账本、恢复前状态历史、源码摘要和原任务摘要。局部数据位于 `data/research-verification-batches-20261019`，公开记录见 [分批核验账本](../backend/evaluation/results/research_batch_verification_20261020.json)。初始代码摘要对应初次请求；后续词法/上下文调整未用于这些核验模型调用。结果仍是机器判断，不能当作 4/8 人工支持率。三篇论文的作者、官方来源和 CC BY 4.0 许可见 [语料来源](research_corpus_sources.md)。

## 2. 上下文：预留空间和原文窗口

默认 `parent-floor-v2` 保留原行为。显式 `local-window-v3` 在非索引类问题中预留 20% 字符给上下文扩展；索引类问题保留完整子片优先策略，避免挤掉精确证据。父片可完整放入时仍选完整父片，放不下时尝试包含已选子片和一个相邻子片的连续原文窗口。

`EvidenceItem.context_start/context_end` 是原始父片字符偏移，`text` 返回实际提供给模型的区间。它不是新索引切片，不修改 ChunkSet。窗口必须包含全部已选子片；重复文本无法唯一映射时退回子片。编号、原文偏移进入身份，BundleRef 保存并恢复这些信息。旧默认选项和旧引用序列化不增加字段，保持旧身份可读。

抽取目录、旧引文兼容路径及关系抽取均将窗口局部偏移映射回原父片；成品页码按实际引用裁剪。上下文计数使用窗口实际文字，评测也按裁剪后的来源区间评分，不能借用窗口外父片文字。

## 3. 候选：受限词法补充

新增无依赖 BM25 Adapter，仅在选择 lexical-fusion-v2 且问题明确涉及索引时启用。中文概念映射是公开的小词表，不含论文答案或 FAISS 等预期锚点。排名仅使用用户 query 和所选文档的子片文本，不调用模型，不写索引。

首轮全量交错词法/向量候选会挤掉有效向量证据；保留失败结果后，改为：当某篇已有候选却没有索引相关文字时，仅补充该篇的词法候选；容量已满时替换同篇最后一个不相关命中，保留其他文档候选。通用比较问题原样返回向量候选。最多十个候选，词法来源明确记录 lexical，所有者和文档范围继续校验。

该补充没有带来本次整体覆盖收益。q12 的 DPR 候选被替换成另一段含 index 的材料，仍未召回所需的具体方法证据，**q12 保持未解决**。词法相符不是语义相关，不能据此默认切换。

## 4. 三轮开发实验及最终结果

全部使用同三篇 PDF/摘要、解析与切分、封存 Top-10 向量候选、最多十项/6000 字符；无新 Embedding 或生成调用。候选选择全部完成后才读取 AI 标签评分。开发集已有二十题、十六题有锚点，四题证据不足题不计为回答正确。

| 实验 | 改动与观察 |
| --- | --- |
| 2026-10-19 首轮 | 不预留窗口预算；窗口不改善 q09；广泛交错词法导致平均覆盖下降至 36.46% |
| 2026-10-20 第二轮 | 预留 20%，保留向量前缀；q09 补齐，但 q12 退化，未通过回归门槛 |
| 2026-10-20 第三轮 | 索引问题保留子片优先，同篇受限替换；q09 补齐、q12 恢复原 2/3，最终无锚点覆盖退化 |

最终四路对照：

| 候选 / 上下文 | 平均锚点覆盖 | 全证据题（/16） | q09 | q12 |
| --- | --- | --- | --- | --- |
| 向量 / 原父片 | 47.92% | 6 | 1/2 | 2/3 |
| 向量 / 新窗口 | 51.04% | 7 | 2/2 | 2/3 |
| 词法补充 / 原父片 | 47.92% | 6 | 1/2 | 2/3 |
| 词法补充 / 新窗口 | 51.04% | 7 | 2/2 | 2/3 |

q09 实际上下文 5917→5919 字符，都在 6000 上限内。三轮全量逐题与原文区间、负面结果及源码摘要保留在 [检索对照账本](../backend/evaluation/results/research_retrieval_ablation_20261020.json)，原报告在 data 的相应新目录中保留。预留比例、词法限制是在这份开发集上调整的，不是独立 holdout；零锚点退化不能证明零答案回归或人工引用支持率通过。默认策略不变。

## 5. 文件、验证与后续入口

修改 `app/research/tasks.py`、`agent.py`、`tools.py`、`runtime.py`、`evidence.py`、`artifacts.py`、研究 API 和 runtime 测试。新增 lexical.py、两份脚本、三份测试模块和上述两份结果记录。计划、基线、README 与开发过程同步更新。无新依赖、训练、前端或业务库迁移；用户 artifacts 保留。

在 `project/backend`、rag4-py3.11 环境：

```powershell
python -m pytest tests/test_research_verification_batches.py tests/test_research_context_windows.py tests/test_research_lexical.py tests/test_research_runtime.py -o addopts='' -q --tb=short --show-capture=no
python scripts/reverify_research_batches.py --task data/research-citation-handles-20261013-resume2/task.json --database data/research-citation-handles-20261013-resume2/research.sqlite --vectors data/research-citation-handles-20261013-attempt1/vectors --output data/new-batch-replay
python scripts/evaluate_research_retrieval.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --retrieval-report data/literature-pilot-v1/run-qwen8b-20261012-attempt2/report.json --report-sha256 ff2d80b89c5e506bd4d8b0a9f3eb933e0972efb426d6107c19665cefe779b88e --output data/new-retrieval-ablation
python -m pytest -o addopts='' -q --tb=short --show-capture=no
```

线上脚本只从 RAG4_EVAL_API_KEY 进程环境读取密钥。明确恢复时沿用同一 output，添加 `--resume`，请求上限不变；当前实验已用尽四次上限，不再执行。初始四个批次用例和三个窗口用例先失败，再实现；最终相关 **27 passed / 61.84s**。涵盖失败恢复不重复成功批次、暂停、合并完整性、超四条拒绝、预算准入、窗口偏移、伪造来源和 API 策略冻结。

下一步入口是失败的 REALM 单文档核验及 q12 的具体方法证据召回。需要在新实验中明确新的调用预算，记录网络与语义两类失败；不能把当前缺失批次标为完成。候选改进须保留已通过的 q09 和事实题，再检查人工支持与拒答；Phase 1–5 仍未全部验收。

最终全量：在 `project/backend` 执行 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`，**483 passed / 749.89s**，无失败、无跳过。本轮新增17项覆盖；编译和差异空白检查、公开JSON与凭据模式检查通过。源码摘要见 `project/backend/evaluation/results/research_batching_tests_20261020.json`。该结果不替代人工语义验收。
