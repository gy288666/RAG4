# R31：可追踪的核验前文窗口（2026-10-31）

R30发现FiD背景方法被误归给本文：所引子片与父片都从“However,it…”开始，指代对象在前两个子片中。本轮实际补充有来源的核验前文，保留原始引文区间、旧默认与全部历史结果；不新增核验协议或逐条生产计划。

## 接口与领域数据

新增 `app/research/verification_context.py`：

- `ContextPart`：preceding/cited角色及既有Citation（规范chunk ID、Unicode字符起止偏移、精确原文）。冻结ChunkSet保留PDF定位；不会伪造跨片引文。
- `VerificationContext`：确定性context_id、策略、corpus_id、claim_id、document_id、最多三段来源、字符数与警告。身份绑定实际内容，源校验时按冻结语料重建并比较，拒绝伪造或不同选片。
- `build_context(corpus,claim)`：同篇文档中至多两个紧邻前序子片，加当前引用的上下文。支持越过父片边界；不跨文档检索，不跳过超预算近邻去借更远材料。

单个窗口最多6000个Unicode字符，包含段间换行。引用块不超过4000时保留整块，否则保留精确引文；预算不足或重复文本导致父片锚点不唯一时明确记录警告并保留被引内容。父片引用按与原文区间相交的子片确定锚点；不能凭重复文本猜偏移。总模型输入仍受既有90000字符上限控制，这不是模型token保证。

`CompletionSpec.verification_context_policy` 可选 `cited-chunk-v1`（旧默认）或 `preceding-children-v1`（仅允许facet-handles-v5）。新字段在旧默认序列化中省略，保持历史任务/配置身份可读。创建API接入该选项，复核CLI也可显式选择；默认不改变。

模型收到扩展context和独立context_sources，发布支持仍只能选择原引文目录的support_ids。前文可以帮助识别指代，不能变成新的支持编号或取代引文中缺失的事实。新策略的VerificationReport保存context_policy和窗口，逐篇批次校验策略匹配，合并时完整保留，ArtifactComposer重验窗口及支持编号。报告字段默认省略，旧v2/v3/v4/v5和旧产物身份保持兼容。

## 工程验证

首个新增测试因模块缺失收集失败（1 error /0.53s）；实现后相关35项通过。扩展真实任务批次测试发现合并遗漏context_policy/contexts（1 failed、65 passed /25.05s），修复后批次、来源、预算、历史兼容、API和SQL恢复相关最终 **70 passed /26.06s**。

覆盖跨父片前文、精确偏移、稳定ID、字符上限、重复文本降级、父引用锚点、文档隔离、上下文编号不能当support_ids、篡改窗口拒绝、报告/产物往返、默认序列化、API策略冻结和报告合并。测试替身只验证契约，不证明语义准确。

最终完整后端 **549 passed /265.06s**，无失败/跳过。本切片新增17项回归，同时覆盖R29/R30此前只做相关测试的23项；比R28最近一次全量增加40项。源码及命令见 [完整测试记录](../backend/evaluation/results/research_context_tests_20261031.json)。

## 四请求真实对照

固定R30的FiD归属负例和本文方法正例，每条分别使用旧/新上下文；都使用相同v5提示词、同一模型、温度0、4096输出上限、60秒超时及原引用。案例在请求前保存，预期不传给模型，原对照与任务摘要核对，新的SQLite副本和输出目录只保存本次结果。

| 案例 | 旧cited-chunk-v1 | 新preceding-children-v1 |
| --- | --- | --- |
| 归属负例 | supported，仍错误接受 | insufficient，attribution不支持 |
| 方法正例 | supported | ConnectTimeout，未获判断 |

本轮四请求预算用尽，三成功、一连接超时，5209已报Token，失败用量/货币费用未知，不重试；完整调用、原引用和窗口见 [真实对照账本](../backend/evaluation/results/research_context_attribution_20261031.json)。负例的新窗口实际1241字符，由584字符前文、104字符前文、549字符所引子片及四个换行字符构成。原support_ids目录及所引549字符不扩大。新拒绝不是因模型选择了非法上下文编号，而是模型未选支持编号并报告未建立FiD归属与完整语义支持。

这次观察到负例改善，但新窗口下的方法正例尚未取得判断；不能声明无退化、统计因果或整体质量通过。旧引文、旧比较表、旧实验和失败保留，默认策略不切换，不把此子集拼接为新全量比较表。失败正例的2868字符窗口在源码及冻结来源不变时离线重建并单独标注，不冒充成功的语义判断。

## 文件、复现与回滚

新增领域模块、`tests/test_verification_context.py`、`scripts/evaluate_context_attribution.py` 和其测试。修改model.py、artifacts.py、tasks.py、tools.py、创建API、原复核CLI及runtime/批次/复核测试；更新计划、基线、README、开发过程、本页与接口说明，以及公开结果。无依赖或数据库迁移，现有研究JSON checkpoint保存新字段，未修改向量或active指针。

在 `project/backend` 的rag4-py3.11环境：

```powershell
python -m pytest tests/test_context_experiment.py tests/test_verification_context.py tests/test_verification_facets.py tests/test_verification_handles.py tests/test_research_verification_batches.py tests/test_research_runtime.py tests/test_verification_single_replay.py -o addopts='' -q --tb=short --show-capture=no
python scripts/evaluate_context_attribution.py --task data/research-citation-handles-20261013-resume2/task.json --database data/research-citation-handles-20261013-resume2/research.sqlite --vectors data/research-citation-handles-20261013-attempt1/vectors --control-report evaluation/results/research_cross_paper_20261031.json --output data/new-context-comparison
python -m pytest -o addopts='' -q --tb=short --show-capture=no
```

R29/R30旧对照脚本仍校验当时的实现摘要，源码不同应新建对照，不能绕过冻结检查。R31从历史账本复用Claim及原引用，另行封存本轮源码，保留全部旧记录。

创建新任务可显式组合plan_version=research-comparison-v2、verification_protocol=facet-handles-v5、verification_context_policy=preceding-children-v1；这不会增加模型调用次数，但上下文和Token用量可能增加，仍需质量/延迟验证。

回滚继续旧默认策略，保存已产生的窗口、任务、版本与产物，不删研究表或重写旧数据。下一切片先完成正例与其余案例的新窗口验证，再做受控端到端比较；不继续增加协议或索引设施。Phase1–5人工质量门槛、四道拒答题与新任务验收仍未完成，本轮尚未提交或推送。


后续R32已用同六例完成新窗口复测，方法正例支持、误归属负例拒绝，全部符合本组开发预期；旧ConnectTimeout保留，不声明人工质量通过。现有端到端试点入口已准备但尚未执行，详见 [R32记录](research_context_suite.md)。
