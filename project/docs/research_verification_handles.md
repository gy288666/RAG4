# 核验来源编号与检索缺口对照（2026-10-14）

按“优先解决核验引文抄写失败，再验证语义质量和检索缺口”推进。本轮消除了新协议中必须由模型抄写引文的步骤；真实验证仍不足以通过语义质量门槛，两个检索缺口未改善。没有切换默认研究协议或 RAG3 行为。

## 实现与兼容

新增显式可选 `CompletionSpec.verification_protocol = source-handles-v4`，研究任务创建 API 同名字段可指定。旧任务仍默认 numeric-model-v2，source-checks-v3 保留用于回放。

`verification_sources(claim)` 将该结论已有引用分为最长 800 字符、连续且不重叠的原文窗口，尽可能沿段落/句子边界。source_id 绑定协议、claim_id、原引用及字符偏移。既不规范化原文，也不扩大引用或检索范围。

模型返回 `HandleJudgment / HandleAssessment / HandleCheck`，每项检查包含 status、reason、最多四个 support_ids。服务端解析这些编号，并在 `SourceCheck` 中保存编号和实际 support_quote。多个编号还原为原文的连续包含区间，上限 1600 字符，不能拼接成不存在的句子。空、重复、跨结论、未知或区间超限编号均不能支持结论；返回自抄 support_quote 属于协议错误。

ArtifactComposer 再次按结论重建编号并校验文本映射，v4 supported 必须具有有效编号。新增字段为空时不改变旧 SourceCheck 序列化；旧 v2 产物身份及真实 v3 报告往返均有回归测试。模型调用 ledger 记录协议，SQL checkpoint 延续原有预算/CAS/失败保护；没有新增依赖、迁移、训练或前端。

## 真实语义核验结果

固定原 R20 任务、原文/切片/索引和 Qwen/Qwen2.5-7B-Instruct，JSON 模式、输出上限 8192、连接 5 秒/读取 60 秒。本轮预定最多两次请求，不额外重试。

| 运行 | 范围 | 结果 | 耗时与用量 |
| --- | --- | --- | --- |
| subset | 原 v2 判 supported 的六条结论 | 1 supported，5 insufficient；无引文抄写或陌生编号导致的拒绝 | 29991ms；4866 输入 + 1290 输出 = 6156 Token |
| full | 原任务全部十二条结论 | ReadTimeout，无新核验报告 | 60885ms；用量未知 |

获支持的是 DPR 双编码器方法结论。相比上一轮该结论因模型改写引文而被拒，新协议能在不放宽原文校验的情况下正确还原来源。其余五条为空编号选择，不能把这些拒绝算成语义正确：其中包含先前 AI 来源复核认为有依据的结论，也包含 REALM 的两条问题陈述。本轮没有人工 gold，完整十二条也未验证成功，质量门槛保持未通过。

首轮对子项空编号的处理只保留标准错误码，未保存模型原始理由，无法事后推断具体语义原因。已修复为错误码加原理由（遵守长度上限），并补测试；未伪造或改写首轮记录。完整请求的超时发生在此修复后。两次合计 2 请求、1 网络失败、6156 已报 Token；失败用量与货币费用未知。

新记录保存在 [模型回放账本](../backend/evaluation/results/verification_handles_20261014.json)，原任务、数据库、向量和旧展示表未被覆盖。仍为机器复核，论文作者/许可见 [来源说明](research_corpus_sources.md)。

## 检索缺口：范围不是本次主因

新增 `evaluate_evidence_scope.py` 和显式范围文件 `literature_scope_diagnostic_v1.json`。范围只根据问题文字中的论文名指定：q09 为 DPR/FiD，q12 为 DPR/REALM。证据选择完成之后才读取锚点用于评分，不将预期答案或锚点传给检索器。

固定历史 Top-10 候选，不新增 Embedding、不补取被过滤的候选，最多 10 项/6000 字符，沿用 evidence-floor-v2。不同范围的实际上下文长度可能不同；本次实际完全相同。

| 问题 | 全部文档 → 显式两篇 | 实际上下文字符 | 结论 |
| --- | --- | --- | --- |
| q09 编码输入比较 | 1/2 → 1/2 锚点覆盖 | 5917 → 5917 | 原父片扩展预算缺口仍在 |
| q12 索引更新比较 | 2/3 → 2/3 锚点覆盖 | 5950 → 5950 | 原 DPR 候选召回缺口仍在 |

这只是冻结候选过滤对照，不是新的带过滤条件向量检索，也不能证明实时检索无益。结果见 [范围对照账本](../backend/evaluation/results/evidence_scope_20261014.json)。本轮没有修改生产检索算法或扩大索引基础设施。

## 文件与复现

修改 app/research/artifacts.py、model.py、protocol.py、app/api/v1/research.py、scripts/reverify_research_claims.py、tests/test_research_runtime.py。新增 tests/test_verification_handles.py、tests/test_evidence_scope_replay.py、scripts/evaluate_evidence_scope.py、evaluation/literature_scope_diagnostic_v1.json 及上述结果文件。同步根计划、基线、README、开发记录和后端说明，保留上一轮未提交内容及用户 artifacts。

在 `project/backend`、Python 3.11 环境运行：

```powershell
python -m pytest tests/test_verification_handles.py tests/test_evidence_scope_replay.py tests/test_research_verification_checks.py tests/test_research_runtime.py -o addopts='' -q --tb=short --show-capture=no
python scripts/reverify_research_claims.py --task data/research-citation-handles-20261013-resume2/task.json --database data/research-citation-handles-20261013-resume2/research.sqlite --vectors data/research-citation-handles-20261013-attempt1/vectors --output data/verification-handles-new --protocol source-handles-v4
python scripts/evaluate_evidence_scope.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --retrieval-report data/literature-pilot-v1/run-qwen8b-20261012-attempt2/report.json --report-sha256 ff2d80b89c5e506bd4d8b0a9f3eb933e0972efb426d6107c19665cefe779b88e --scopes evaluation/literature_scope_diagnostic_v1.json --output data/scope-replay-new
```

线上回放需通过进程环境提供 RAG4_EVAL_API_KEY；脚本不读取或输出凭据文件。输出目录必须是新的，数据库只复制后读取，不恢复执行旧任务。六条子集实际调用使用重复 `--claim-id` 明确列出旧 supported 的编号。

初始编号协议用例 **3 failed / 5.49s**；接通后相关 41 项通过 / 6.22s。新增边界与范围回放后，相关 **32 passed / 28.12s**；此后还增加了两种存储下 API 协议冻结的参数化覆盖，由最终全量回归验收。

## 下一步边界

优先解决长批次核验的有界执行和语义稳定性，避免一次十二条在 60 秒内失败。任何按文档分组的方案必须显式计入任务调用预算与 checkpoint，不做隐藏重试。检索方面应分别验证 q09 的局部上下文分配与 q12 的候选召回，保持等预算并保留原通过样本。人工支持率、缺口识别和真实跨文档收益仍待验收；Phase 1–5 没有因此被标记为全部完成。

最终全量：在 `project/backend` 执行 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`，**466 passed / 521.87s**，无失败或跳过。本轮新增 15 项回归覆盖（含 API 参数化新增两项）。编译、差异空白、公开结果 JSON 和凭据模式检查通过；语义质量门槛仍未通过。
