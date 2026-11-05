# R37：新任务条件门禁、可选关系修复与失败部分稿

2026-11-04。**新研究任务未完成：REALM文档核验返回后发生ValueError，8次Completion预算已用完。** 已保留两轮失败状态，在不增加模型请求的情况下导出DPR/FiD两条方法结论与10个缺口；没有把部分稿标成成功研究任务，质量验收仍false。

## 实际运行与预算

保持R36生产门禁及旧research-operator-v1提示词，用三篇真实论文重新检索、抽取和核验，显式选择explicit-row-v1。文档向量经过ID/文本/来源匹配后复用，缓存文件摘要与R33封存相等；查询Embedding是真实新请求。

```powershell
cd project/backend
python scripts/evaluate_research_comparison.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --cached-run data/literature-pilot-v1/run-qwen8b-20261012-attempt2 --cached-report-sha256 ff2d80b89c5e506bd4d8b0a9f3eb933e0972efb426d6107c19665cefe779b88e --output data/research-condition-e2e-20261104 --model Qwen/Qwen2.5-7B-Instruct --plan-version research-comparison-v2 --extraction-protocol source-handles-v2 --verification-protocol facet-handles-v5 --verification-context-policy preceding-children-v1 --result-condition-policy explicit-row-v1 --context-policy local-window-v3 --candidate-policy source-role-v3 --max-output-tokens 4096 --retry-network-once
```

凭据仅从进程环境读取，未出现在命令/日志/SQL/公开结果中。以上目录均已存在，重放必须选择全新路径。

| 阶段 | 实际结果 | 预算与保留状态 |
| --- | --- | --- |
| 新检索 | 三篇成功，3批共12个输入 | 文档向量不重新调用Embedding |
| 首次DPR抽取 | ReadTimeout 60008ms | 按预先显式选项恢复一次 |
| 第二次DPR抽取 | 模型返回成功，但relations.1.predicate不在白名单 | 首轮failed，5步/2次Completion；没有保存有效claims |
| 修复后的新副本续接 | 三篇各抽取4条声明，DPR/FiD报告成功提交 | 复用3份原检索检查点，不重新查询 |
| REALM文档核验 | 模型返回成功，随后通用ValueError；未提交报告 | 总11/13步、8/8次Completion，停止请求 |
| 离线部分导出 | 保留成功报告，其余明确不足 | 原任务仍failed，0新增模型/Embedding请求 |

累计8次Completion：传输返回成功7次、ReadTimeout 1次；其中一次成功响应未通过抽取校验，另一次未提交文档核验，不能把HTTP成功当工具或任务成功。已报Completion Token 35419，加查询Embedding 498，共35917；失败请求用量、实际费用未知。原隔离库激活演练最后停用到None，续接和导出不切换索引，业务库未访问。

## 本轮真实阻塞与生产代码修复

首轮诊断明确为`response_schema_invalid:extract_cited:relations.1.predicate:literal_error`。当时模型响应原文未保留，不能复原其具体内容；回归测试使用同一校验路径构造有来源的有效声明和无效可选关系，不冒充原始返回。

`app/research/artifacts.py`现在保持CitedAnalysisDraft的声明结构、8个候选上限、2个关系上限与容器约束，随后逐条验证CitedRelation。非法谓词、缺失/多余字段会拒绝该关系并记录安全诊断；不修正谓词、不发第二次模型请求，也不丢弃合法声明。必要声明缺字段、关系超限或错误容器仍严格失败。RAG3旧问答/切分接口不改。

这是一次新的请求续接，不是从丢失的响应中恢复声明；不能将新模型输出的变化全部归因于该修复。

## 新增与扩展接口

- `scripts/evaluate_research_comparison.py::condition_summary(task)`：明确审计状态、被条件门禁阻止的Claim ID、未审计和未产生verdict的结果声明。只统计最终报告或保留批次中的一类，防止重复计数。passed不推断语义质量。报告task_policies补齐result_condition_policy。
- `scripts/resume_research_comparison.py --repair-optional-relations`：仅接收本次首篇抽取的可选predicate白名单错误，要求全部检索已成功、没有成功抽取成果，并要求原预算覆盖剩余全部工作。新SQLite副本只读复用向量/检索，原任务、报告和成功步骤不改；本例最多新增6次Completion/8步，自动网络重试为0。默认末篇网络恢复模式保留。
- `scripts/export_research_partial.py::partial_verification(task, corpus)`：仅为没有最终报告/产物的failed任务导出。原成功批次严格校验并保留；其余所有声明为insufficient，即使某条字面条件检查passed/not_applicable也绝不推断语义支持。
- 导出时重建必要条件审计，使用现有ArtifactComposer检查来源和产物身份。comparison.md必须带失败任务说明；不把Artifact附到原Task、不改变其状态、不标为完成。

没有新生产API、数据库迁移、依赖、调度、前端、Neo4j或训练。httpx使用原有依赖，续接只增加连接复用，不增加重试。

## 显式续接及失败部分稿

```powershell
python scripts/resume_research_comparison.py --source-run data/research-condition-e2e-20261104 --output data/research-condition-repair-20261104 --repair-optional-relations
python scripts/export_research_partial.py --source-run data/research-condition-repair-20261104 --vectors data/research-condition-e2e-20261104/vectors --output data/research-condition-partial-20261104
```

续接模式在外发请求前检查准入/原预算，并绑定获授权的硅基流动端点。原输出文件和SQL不覆盖，新副本中继续运行同一任务ID；父文件SHA、成功检索步骤、BundleRef和向量字节均核对保留。导出脚本不需要APIKEY，不调用模型，不恢复任务。

部分稿只有DPR、FiD方法两条支持、10个待核验单元格。两条声明和引文与先前逐条来源检查的内容完全相等，本次原文重新校验通过；这仍是Agent复核，不是独立人工验收。REALM四条均不获得语义支持。

| 结果声明 | 在线任务的已提交检查点 | 离线部分稿 |
| --- | --- | --- |
| DPR 1%–12% | unknown：当前竖排表格选择器无法定位散文结果 | 保留不足；不是证明声明错误 |
| FiD定性结果 | not_applicable，模型语义判断不足 | 保留不足，不凭字面检查恢复 |
| REALM 38.5/52.0 | 文档核验整体失败，审计未提交 | 重新按原文定位CC-News遗漏，missing；其他结论全部未知 |

所以不能声称线上REALM门禁报告已成功提交，也不能声称完整流程或质量通过。部分稿的所有声明都有明确verdict（可能只是不可用），不代表所有声明都完成了语义检查；unverified_documents仍显式列出realm。

## 尚未定位的ValueError

实际失败响应没有保存，现有日志只有verify_document/ValueError，不能断言是模型抄错Claim ID、重复身份或其他返回约束。离线用同一来源、有效的受控wire响应检查来源/条件审计/批次范围可以通过；该探针只缩小排查范围，结果不发布为科学结论，也不替代失败响应。

下一切片先为这条返回校验路径增加安全错误分类、数量和身份检查诊断，构造未知/重复ID及其他边界回归；不保存敏感原文或把未知错误一律认作网络错误。诊断明确后再用单独有限预算验证，不继续在本轮已经用完的预算上追加请求。方法声明的引用匹配和语义问题仍未解决。

## 测试与公开证据

生产修复前回归3 failed、3 passed，准确复现可选关系连带拒绝；修复后22 passed /2.69s。续接准入、摘要、旧恢复及条件相关51 passed /5.04s。完整后端：

```powershell
python -m pytest -o addopts='' -q --tb=short --show-capture=no
```

**641 passed /524.75s**。此完整运行包含最终生产修复和续接代码；之后只新增部分导出CLI与10项测试，生产实现未再修改。最终相关：

```powershell
python -m pytest tests/test_failed_partial_export.py tests/test_optional_relations.py tests/test_extraction_repair.py tests/test_condition_summary.py -o addopts='' -q --tb=short --show-capture=no
```

**31 passed /5.17s**。本轮新增31项（摘要8、可选关系6、续接7、部分导出10）；最终收集651，不冒称全部651已全量运行。部分导出的独立测试最初发现workflow fixture未导入，补齐后通过，没有保留失败测试。

- [首轮失败与原任务](../backend/evaluation/results/research_condition_e2e_initial_20261104.json)
- [续接、部分稿、来源复核与调用账本](../backend/evaluation/results/research_condition_e2e_20261104.json)
- [可阅读的失败任务部分比较稿](../backend/evaluation/results/research_condition_partial_20261104.md)
- [测试范围及源码摘要](../backend/evaluation/results/research_condition_e2e_tests_20261104.json)

本轮实际新增/修改文件：上述三个脚本、app/research/artifacts.py、四个测试文件、四份结果文件、CONTEXT.md及README/计划/基线/后端MVP/开发过程记录。原R34–R36未提交修改与用户artifacts保留，本轮未提交或推送。

## 阶段边界与回退

可选提示不再破坏有效声明，失败任务可交付明确部分稿，属于Phase 3–5最小后端的修复。原任务仍失败，质量门槛未通过，不能标记Phase 1–5全部验收完成。默认结果条件策略仍model-only-v1；新策略任务不能通过修改冻结配置来降级，旧数据、向量和已成功报告全部保留。结构化表格支持范围、人工评测、方法断言、真实用户工作路径和研究前端仍待完成。


后续R38（2026-11-04）：安全返回诊断已实现，独立一次REALM复测连接超时，历史精确根因未确定，原失败任务与部分稿保留。见 [诊断记录及下一用户入口](research_response_diagnostics.md)。
