# 引用、响应协议与上下文缺口修复

日期：2026-10-13，接开发记录 R19。保留当时代码、实验结果和所有用户修改；没有业务库迁移、active 切换或 GitHub 推送。

## 本轮实际改动

新增 `source-handles-v2` 抽取协议。系统把已选证据分为连续、不重叠、最多 1600 字符的原文片段，优先使用段落/句子边界，生成绑定语料、chunk set、切片和字符区间的引用 ID。片段覆盖原上下文，不增加检索内容或预算。模型只输出陈述及引用 ID；系统还原准确原文和页码。未知 ID、跨语料 ID或重复字段仍拒绝，不从模型改写的引文构造来源。

保留 `literal-quote-v1` 和历史任务读取。新 HTTP 研究任务默认使用引用编号；`response_format` 默认 `text`，由使用者显式选择 `json_object`，避免假定所有兼容服务支持该选项。实验明确启用 JSON 模式。官方接口说明见 [硅基流动 Chat Completions](https://docs.siliconflow.cn/docs/api/chat-completions-post)；JSON 模式保证格式，不替代字段与语义校验。

模型配置、调用 ledger 和任务快照记录协议/输出模式。修正旧提示中“缺证据就省略字段”的歧义，要求省略整条候选、不输出缺字段对象。新增安全 schema 诊断：只存固定字段路径、位置和错误代码；不存异常消息、模型原文、未知字段名或凭据。旧文字引用拒绝细分为不存在、歧义、未知证据和重复字段类型。

实际文件：

- 新增 `project/backend/app/research/protocol.py`、`tests/test_research_citations.py`、`scripts/diagnose_evidence_gaps.py`。
- 修改 `app/research/artifacts.py`（引用目录、严格引用选择、有界候选）、`model.py`（协议、JSON 模式、重复 JSON 键拒绝）、`tools.py`（安全诊断）、`app/api/v1/research.py`（显式配置）、`scripts/evaluate_research_comparison.py`（冻结实验参数）、`tests/test_research_agent.py`（更具体的拒绝原因断言）。
- 新增下文结果包，同步 README、开发计划、基线、开发过程和后端接口说明。没有新依赖。

## 从失败到验证

先跑三个引用/诊断用例得到 **3 failed**，建立真实抽取/工具边界的反馈信号；随后修复并回归。之前第 7 次历史响应没有保存，只知道 ValidationError，不能倒推它的具体字段错误。

本轮重跑三篇论文后，DPR/FiD 各得到四类候选，REALM 出现明确的 `response_schema_invalid:extract_cited:claims:too_long`。这次观测证明超过四条候选会使整个步骤失败；原始不合规响应依旧不保存，测试使用受控五条候选复现同一约束，不冒充原始响应。

修复将 **wire 候选上限 8** 与 **最终最多四个 facet** 分开。每个 facet 按响应顺序保留首个来源有效候选，记录重复/超量警告；没有按 AI 标签或最终答案挑选候选。输入超过八条、字段缺失或类型不对仍失败；每条仍需独立核验，不能据第一条推断最优或完整。新增用例先红后绿，保护九条超限仍被拒绝。

复制 SQLite checkpoint 到新目录作显式续接，原失败数据库、任务 JSON 和报告不覆盖。第一次续接 ConnectTimeout；再做一次受限续接，仅执行剩余抽取、核验、compose，最终 completed。每次外部调用都计入预算，没有默认或无限重试。没有重新生成已完成的查询/文档向量。

| 运行 | 模型请求 | 结果 |
| --- | --- | --- |
| 新协议完整尝试 | 6 | 三次查询、DPR/FiD 抽取成功；REALM 候选数量超限 |
| 第一次有界续接 | 1 | ConnectTimeout，失败保留 |
| 一次显式网络失败续接 | 2 | REALM 抽取、全部候选核验成功；比较表完成生成 |

合计 **9 次请求、1 次网络失败、20203 已报告 Token**；失败请求用量及货币费用未知。完成任务累计 10 次工具尝试、6 次生成调用预留。这是 checkpoint 恢复成功，不是一次无中断成功运行，且修复前后改变了候选接收规则，不能当作单变量质量对照。

## 原文复核后的部分产物

在线核验对 12 候选判定 6 条支持、6 项缺口。二次 AI 来源复核又发现两条 REALM 不足：38.5/52.0 对应 CC-News 预训练条件，陈述省略该条件；另一条“仍需研究编码器/检索器贡献”的局限超出所引用段落。**这两条不能作为可靠研究结论交付。** 在单独复核版撤下，原模型决定原样留作失败证据。

目前复核版展示 **4 条、8 项缺口、partial**；它是本 Agent 对原文的二次 AI 审阅，不是新的外部模型核验、人工金标准或生产 verifier 自动修复。其余四条也需要人工审阅。引用完全可定位和数字全部出现，并不保证实体归属、表格条件或论断成立；生产语义核验仍存在误判，90% 人工支持率尚未通过。

- [所有尝试、失败及用量](../backend/evaluation/results/citation_protocol_fix_20261013.json)
- [二次来源复核记录](../backend/evaluation/results/citation_source_audit_20261013.json)
- [部分比较表](../backend/evaluation/results/citation_comparison_20261013.md)
- [带来源区间的产物](../backend/evaluation/results/citation_comparison_artifact_20261013.json)

公开结果仅涉及三篇已记录许可的论文。Markdown 导出附作者/出版来源/CC BY 4.0，结构化 artifact 保留 canonical 身份；后者与加署名的导出正文不同。凭据、原始 PDF、向量和实验 SQLite 不提交。

## 上下文缺口定位

`diagnose_evidence_gaps.py` 使用固定旧 Top-10 和同一 6000 字符预算，对 q09/q12 的 AI 锚点做离线检查，**不把标签或预期答案送入生产检索/模型**。

- q09：缺 DPR 第 3 页编码器锚点；候选父片中存在该位置，但最终只剩 83 字符，完整展开需另加 1363 字符。属于有界上下文不足，不擅自突破预算或丢掉已选证据。
- q12：缺 DPR 第 3 页 FAISS 锚点；Top-10 及其父片都未包含。属于锚点检索缺口，不应继续放大父片解决。

[逐锚点诊断](../backend/evaluation/results/evidence_gap_diagnosis_20261013.json) 记录身份、原文位置、父片成本、预算及代码摘要。只能说明短锚点位置，尚未核对所有语义等价证据；q09/q12 未被标为改善。

复现（backend 中，已有 source/cache 必须通过摘要校验，输出为新目录）：

```powershell
python scripts/diagnose_evidence_gaps.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --retrieval-report data/literature-pilot-v1/run-qwen8b-20261012-attempt2/report.json --report-sha256 ff2d80b89c5e506bd4d8b0a9f3eb933e0972efb426d6107c19665cefe779b88e --output data/evidence-gap-diagnosis-new
```

在线试点沿用此前缓存命令，新增 `--extraction-protocol source-handles-v2 --response-format json_object`；凭据仅从进程环境注入，所有输出目录必须不存在。恢复试验是显式复制 checkpoint 的研究实验，不新增业务自动恢复接口或队列。

## 最终测试和后续

新增八个有意义用例：引用编号抽取、安全 schema 诊断、引用拒绝原因、目录来源覆盖及确定性、未知 ID 和数字错配、JSON 模式/重复键、有界多候选、九条超限。新组及原 Agent/runtime **35 passed / 24.84s**；全量（backend、Python 3.11）：

```powershell
python -m pytest -o addopts='' -q --tb=short --show-capture=no
```

**440 passed / 470.62s**，无失败/跳过。语法、差异、公开 JSON 与文档本地链接检查通过。此前 432 项是 R19 历史结果，不替代本轮。

下一切片先改善语义核验的实验条件/方法归属和 facet 约束，再用独立来源审阅检验；q12 优先做文档范围内检索对照，q09 在固定预算下评估证据组合。没有以缺口为理由扩建索引平台、Neo4j、正式微调或前端。
