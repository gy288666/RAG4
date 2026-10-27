# R26：方法来源召回与核验续接（2026-10-20）

按照开发计划第 3.4 节继续三篇论文比较，完成一个有限切片：补 q12 方法来源、保留 q09 上下文收益，从复制断点完成剩余 REALM 核验。默认 RAG3、研究任务策略、旧索引和产物均保留。**工程闭环完成，研究质量验收仍未通过。**

## 来源角色排序

q12 原缺失证据是 DPR 第 3 页自己的离线索引方法。原向量候选没有这段；R25 BM25 补充选中了第 9 页介绍其他论文的相关工作。后者虽包含索引、预训练等关键词，不能用于证明 DPR 自身的方法。

新增显式 `candidate_policy="source-role-v3"`，复用原受限 BM25 Adapter。在索引问题、且同一文档候选没有索引文字时，优先考虑带第一人称和操作描述的段落，降低带第三人称及作者引用的背景段落次序。速度、延迟、性能问题仍用原 BM25 次序。该提示只影响候选排序，不能证明来源归属，也不能绕过核验器。

实现没有论文名、页码、chunk ID、FAISS 或答案锚点等特例。仍只替换同篇最后一个不相关命中；不替换已有索引证据、不挤掉其他文档。候选不超过十项，上下文不超过 6000 字符，来源保留 lexical 通道。默认 `vector-v1` 和既有 `lexical-fusion-v2` 行为保留，新策略冻结在任务中，可通过创建 API 显式选择。

来源角色提示目前识别英语代词、作者引用与少量操作词；中文论文没有相应角色规则。这里只验证了三篇英文论文，不能推断其他语言或领域已有同等收益。

### 同预算六路对照

原三篇 PDF、解析/切分、封存 Top-10 向量候选保持一致；增加两路 source-role 策略，先完成全部候选选择，再定位 AI 锚点评分。Pilot 文件在开始读取以获得问题文本，排序函数不接收其证据标签。没有新增 Embedding、生成调用或索引写入。

| 候选 / 上下文 | 平均锚点覆盖 | 全证据题 /16 | q09 | q12 |
| --- | --- | --- | --- | --- |
| vector-v1 / parent-floor-v2 | 47.92% | 6 | 1/2 | 2/3 |
| vector-v1 / local-window-v3 | 51.04% | 7 | 2/2 | 2/3 |
| lexical-fusion-v2 / parent-floor-v2 | 47.92% | 6 | 1/2 | 2/3 |
| lexical-fusion-v2 / local-window-v3 | 51.04% | 7 | 2/2 | 2/3 |
| source-role-v3 / parent-floor-v2 | 50.00% | 7 | 1/2 | 3/3 |
| source-role-v3 / local-window-v3 | 53.13% | 8 | 2/2 | 3/3 |

同上下文策略下，唯一锚点指标变化是 q12：2/3→3/3；全部二十题无锚点退化。q12 新窗口实际 5900 字符，包含 DPR 第 3 页 880:1683 的原文区间。q09 新窗口保持 5919 字符。十六道有证据题评分，四道证据不足题没有被计为回答正确。

这是已用于调试的开发集，标签仍为 AI 草稿；不是 holdout 或人工语义支持率。两个跨文档题锚点补齐，不等于两个跨文档答案通过验收。原 R25 三轮正负实验不覆盖，新增全量 120 行、引用来源区间及源码摘要见 [六路结果](../backend/evaluation/results/research_source_role_retrieval_20261020.json)。

剩余未完整覆盖题为 q03、q08、q10、q11、q13、q14、q15、q16，其中 q14 为 1/2，其余为零锚点覆盖；四道证据不足题仍未做回答/拒答验证。本轮只解决指定召回缺口，不把 53.13% 写成检索或研究任务已全部达标。

## 独立预算续接

R25 四次请求预算保持用尽状态，原两份成功报告及失败保留。本轮为新实验显式设定两次请求预算，使用 SQLite backup 复制其断点；没有在原目录扩大预算。

`reverify_research_batches.py` 新增互斥的 `--continue-from` 和 `--resume`。前者必须指定全新 output 与 1–6 范围内的 `--new-request-budget`，核对原抽取 SHA、父任务 JSON 与 SQL 一致性。新账本保存父报告/任务摘要、旧上限、继承调用数、新预算和逐次执行源码摘要。`--resume` 不接受新预算，且仍受保存的总上限约束。

本次旧调用四次、新预算两次、累计上限六次；不算新的完整端到端任务。复制任务保留已完成检索/抽取及 DPR/FiD 报告，实际仅请求 REALM：

| 新请求 | 结果 | 模型耗时 | 已报 Token |
| --- | --- | --- | --- |
| 1 | ConnectError，保存失败 | 5896ms | 未知 |
| 2，显式恢复 | 成功 | 23043ms | 4777 |

没有额外收费模型探测或隐藏重试；只读未鉴权网络探测得到 401 后，才使用剩余一次模型预算。与 R25 合计六请求、三成功、三网络失败、11774 已报 Token；失败请求用量及货币费用未知。

最后完成三个批次、无模型调用的合并和产物生成。DPR/FiD 成功批次与父任务逐字段相等，父报告/任务文件摘要未变。新实验记录为 `data/research-verification-continuation-20261020`，父实验仍在 `data/research-verification-batches-20261019`；不触碰业务数据库或 active version。

结果和完整调用账本见 [续接结果](../backend/evaluation/results/research_continuation_20261020.json)，新部分产物见 [比较表](../backend/evaluation/results/research_continuation_comparison_20261020.md)。旧展示表未覆盖。

### 语义结果与限制

十二条旧抽取结论中四条获得机器支持，八项列为缺口，产物为 `partial`。REALM 四条均未显示：缺失 CC-News 条件的结果和“需要进一步研究”的无来源推断被挡住，但不能据此宣称 verifier 已正确理解它们。

具体审阅发现：REALM limitation 的 entailment 分项仍错误标为 supported，只因 conditions 分项失败才最终拒绝；有效的 REALM 方法描述又因缺少与方法本身无关的数据集/模型变体被误拒。新策略也没有重新抽取或重新回答二十题，所以检索收益与这张复用旧抽取的比较表必须分开评价。

下一切片应区分方法、结果、局限所需的适用条件，针对真实误拒与错误 entailment 建立正反例，再做有限的新抽取/核验和独立样本复核。不能将未知状态当作支持，也不能用机械全拒绝满足安全指标。人工支持率 ≥90%、4/4 缺口识别、真实答案无回归仍未验收；不启动训练或扩建索引基础设施。

## 接口、文件与验证

实际改动：`app/research/lexical.py`、`tasks.py`、`runtime.py`；`scripts/evaluate_research_retrieval.py`、`reverify_research_batches.py`；`tests/test_research_lexical.py`、`test_research_runtime.py`，新增 `test_research_continuation.py`；本页、根计划/基线/README、开发过程和后端接口说明，以及上述公开结果。无新依赖、业务迁移、前端或正式训练。

Phase 2 继续复用已有 `index_version_service.load_version_snapshot`：前置条件是来源所有者一致、ready 准备结果、已验证 builds 和完整 manifest，研究任务显式绑定保留版本。本轮不需要新增索引平台或激活该版本；需要回滚时继续原版本切换接口，保留所有数据。

在 `project/backend` 的 `rag4-py3.11` 环境执行：

```powershell
python -m pytest tests/test_research_continuation.py tests/test_research_lexical.py tests/test_research_runtime.py tests/test_research_verification_batches.py tests/test_research_context_windows.py -o addopts='' -q --tb=short --show-capture=no
python scripts/evaluate_research_retrieval.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --retrieval-report data/literature-pilot-v1/run-qwen8b-20261012-attempt2/report.json --report-sha256 ff2d80b89c5e506bd4d8b0a9f3eb933e0972efb426d6107c19665cefe779b88e --source-role --output data/new-source-role-run
python scripts/reverify_research_batches.py --task data/research-citation-handles-20261013-resume2/task.json --database data/research-citation-handles-20261013-resume2/research.sqlite --vectors data/research-citation-handles-20261013-attempt1/vectors --continue-from data/research-verification-batches-20261019 --new-request-budget 2 --output data/new-continuation-run
python -m pytest -o addopts='' -q --tb=short --show-capture=no
```

模型脚本仅从进程环境读取 `RAG4_EVAL_API_KEY`；示例新目录是复现入口，不表示继续当前已用尽预算的实验。首个红灯为缺少 fork_checkpoint 导致导入失败，接着来源角色用例失败（11 passed / 1 failed）；实现后相关最终 **38 passed / 66.59s**。覆盖副本与父文件保留、来源谱系、有限预算、排序确定性/意图门控、已有证据保留、API 策略冻结及旧批次/窗口行为。全量同命令 **494 passed / 738.80s**，无失败、无跳过。新增十一项（来源角色三项、断点副本六项、Local/Chroma API 两项），详见 [测试与源码摘要](../backend/evaluation/results/research_continuation_tests_20261020.json)。

工程回滚仍用原默认策略；实验失败记录、新旧 SQLite 和产物全部保留。本页保留 2026-10-20 的开发结果；R25–R26 改动纳入 2026-10-26 GitHub 同步批次，见开发记录 R27。
