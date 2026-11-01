# R28：按结论类别核验来源（2026-10-31）

本轮继续计划第3.4节的三篇论文比较，不扩建索引平台、图谱或前端。R26 留下两个明确错误：REALM 方法描述因为缺失无关数据集/模型变体而被误拒；无来源的“需要进一步研究组件贡献”在 entailment 分项被误支持，仅因另一分项失败才没有展示。

## 复现与实现

离线复放已保存的真实报告，两项检查均失败：method.conditions 实际 insufficient、预期 supported；limitation.entailment 实际 supported、预期不支持。这是原语义问题的复现，不能靠测试替身证明修复。

新增显式可选 `verification_protocol="facet-handles-v5"`，报告版本 `exact-facet-handles-v5`，模型操作 `verify_facets`。旧 v2/v3/v4 的提示词、默认值和行为保留；没有静默升级历史任务。

新增不可变 `FacetRequirements` 与 `requirements_for(facet)`，服务器按已校验的 facet 选择规则，策略版本固定 `facet-scope-v1`：

| 类别 | 条件规则 | 检查目标 |
| --- | --- | --- |
| method | method_scope | 已陈述机制、训练/推理阶段及范围；不要求无关结果标签 |
| dataset | dataset_scope | 数据集名称、用途和已陈述 split；无表头数值表不能证明名称 |
| result | experiment_conditions | 具体行、数据集、指标、split、单位、模型变体和预训练语料；遗漏实质条件仍拒绝 |
| limitation | explicit_limitation_scope | 有明确来源的局限及范围；已完成调查不能证明尚待研究 |

三项 attribution、conditions、entailment 均继续必填。规则没有增加自动通过或不适用豁免；每项支持仍须有绑定到当前结论的来源编号。精确区间、数字检查、模型预算和产物复查均保留。复合结论要求每一断言得到支持，不能只支持第一句。

来源编号继续使用既有 v4 的稳定区间命名；它只代表原文身份。新的核验策略由 v5 报告版本标识，参与产物身份计算。旧任务/报告/产物序列化仍作回归验证。新协议已接入创建 API、逐文档报告范围验证、合并、SQL checkpoint 和 ArtifactComposer。

## 有限真实对照

新增 `scripts/evaluate_verification_facets.py`，最多四次模型请求，不重试，不抽取新结论，不生成新的全量比较表。复制 SQLite 到新目录，核对原任务、来源绑定与语料身份。实际论文组每次调用前后都重新验证源快照；原任务/索引/active 和业务数据库不写入。

固定两组、每组四条，分别调用 v4、v5：论文组复用真实方法、缺失条件的结果、虚构未来工作，并加入由同一引用重新表述的已完成调查方法；迁移诊断组为明确标记的合成来源，包含正确方法、错误阶段、明确局限、混合真假断言。合成组不是新的真实论文证据。

案例在第一次调用前保存并计算摘要；expected 和 required_checks 仅在返回后评分，EvidenceVerifier 只向模型传递 Claim 和服务器规则。既计最终 verdict，也独立检查指定分项，避免“碰巧因另一理由拒绝”被算作语义正确。案例由 Agent 编写，是开发诊断而非人工标注或独立 holdout；不根据本次返回继续修改提示词或增加请求。

实际执行四请求，三个成功、一个 ReadTimeout；预算已用尽，不重试。逐请求耗时、用量、完整来源、预期与分项结果见 [公开对照账本](../backend/evaluation/results/research_facet_comparison_20261031.json)。成功请求合计11000已报Token，失败请求用量和货币费用未知。

| 组别 | 协议 | 最终判断符合开发预期 /4 | 判断与指定分项均符合 /4 |
| --- | --- | --- | --- |
| 真实论文诊断 | v4 | 2 | 0 |
| 真实论文诊断 | v5 | ReadTimeout，62303ms | 不可评分 |
| 合成迁移诊断 | v4 | 4 | 4 |
| 合成迁移诊断 | v5 | 4 | 4 |

v4 对两个正例均因条件误拒；两个负例虽然最终拒绝，缺失预训练条件的结果被错误支持 conditions，虚构未来工作被错误支持 entailment。因此最终拒绝数不能替代逐项语义检查。v5 只在合成案例通过，无法证明它改善了真实论文问题，也没有整体质量提升证据。

新的具体线索：v4 为两个方法描述给出的拒绝理由均提到“精确匹配和零样本检索召回@5”，这是同一批另一条结果结论的内容。它提示可能存在批内跨结论干扰；尚未通过单变量实验确认，不能仅归因为条件规则不够细。后续逐条对照应先检验这一点，而不是继续增加核验协议。

旧比较表不覆盖，不切换默认协议，不标记误拒/误支持已修复。下一步入口是 `reverify_research_claims.py --protocol facet-handles-v5 --claim-id ...`，先在新预算、新目录中逐条区分真实判断与长批次超时，再验证独立样本及新抽取。当前模型输出、facet 分类和条件适用仍须人工复核；只按 facet 选提示词不能保证语义正确。本次未完成全部二十题回答/拒答或端到端新任务。

## 文件、测试与回滚

新增 `app/research/verification_policy.py`、`tests/test_verification_facets.py` 和上述评测脚本；修改 model.py、artifacts.py、tasks.py、创建 API、原复核脚本及 runtime/批次测试。更新本页、计划、基线、README、开发过程与后端接口说明。无新依赖或数据库迁移。

新契约测试首次 **8 failed /1 passed /4.56s**，新协议实现后与旧核验测试合计 **30 passed /3.45s**；加入 API/批次覆盖后相关 **55 passed /44.68s**，随后增加两项产物伪造和分项诊断测试。最终全量 **509 passed /501.85s**，无失败/跳过，新增15项，详见 [测试与源码摘要](../backend/evaluation/results/research_facet_tests_20261031.json)。测试验证策略路由、保留来源门禁和历史兼容，不验证模型语义准确率。

在 `project/backend` 的 `rag4-py3.11` 环境：

```powershell
python -m pytest tests/test_verification_facets.py tests/test_verification_handles.py tests/test_research_verification_checks.py tests/test_research_verification_batches.py tests/test_research_runtime.py -o addopts='' -q --tb=short --show-capture=no
python scripts/evaluate_verification_facets.py --task data/research-citation-handles-20261013-resume2/task.json --database data/research-citation-handles-20261013-resume2/research.sqlite --vectors data/research-citation-handles-20261013-attempt1/vectors --output data/new-facet-comparison
python -m pytest -o addopts='' -q --tb=short --show-capture=no
```

模型凭据仅从 `RAG4_EVAL_API_KEY` 进程环境读取。新 output 不得已存在；该脚本没有恢复或隐式追加预算。回滚只需继续使用默认协议，保留全部新旧数据。Phase 1–5 最终质量验收、剩余题召回、四道拒答题和人工审阅仍未完成。本轮尚未提交或推送。


后续R29已完成四次逐条真实对照，v5对两个正反例符合预期，v4仍有方法误拒；本页批量实验与超时记录保持原样。最新入口见 [R29逐条记录](research_single_verification.md)，仍非人工验收或生产默认切换。
