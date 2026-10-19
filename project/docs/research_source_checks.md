# Phase 1–5 优化：逐项来源核验（2026-10-14）

本轮交付一个贯穿已冻结切片、版本来源、研究任务和产物的质量切片。Phase 1–5 的最小文献比较后端已具备，完整阶段验收仍未完成。本轮没有追加索引调度平台或扩大研究任务范围。

## 问题与设计

R20 的真实任务保存了 12 条抽取结论，旧核验器判定 6 条 supported。二次 AI 来源审阅发现两条 REALM 结论存在问题：结果中的 38.5/52.0 属于 CC-News 预训练条件，陈述省略了条件；另一条将已经完成的 encoder/retriever 对比实验说成仍需研究。数字和原文引用正确并不等于完整语义受支持。

新增 `source-checks-v3`，一次模型调用返回每条结论的三项检查：

| 检查 | 必须核对的内容 |
| --- | --- |
| attribution | 是否属于目标论文的方法或结果，是否误用引用文献或表格其他行 |
| conditions | 数据集、划分、指标、单位、模型变体、预训练语料和其他影响解释的条件 |
| entailment | 陈述中的每个子结论是否受支持，是否把已完成研究误写为未知或局限 |

每项保存 status、reason、support_quote。支持片段必须是当前引用的非空、连续、精确子串，不能从背景上下文借用证据。任何一项不足、缺失或片段伪造，程序都不会发布该结论；重复/陌生 claim_id、缺少必填项等协议错误使工具失败。模型不再提供可直接采纳的总判定。ArtifactComposer 在渲染前再次检查支持项，避免不一致报告绕过门禁。

这些检查仍是模型判断。程序能验证原文、身份、数字和状态组合，不能证明模型对实验条件或语义的解释正确。测试替身验证协议和失败保护，不是语义准确率证据。

## 接口与回滚

- `SourceCheck`、`ClaimAssessment`、`CheckedJudgment`：类型化模型输出。
- `VerificationReport.verifier_version = exact-source-checks-v3`；assessments 保存逐项记录。
- `CompletionSpec.verification_protocol` 和创建研究任务 API 可显式选 `source-checks-v3`，调用日志记录协议版本。
- 缺省和历史任务继续 `numeric-model-v2`。不静默升级存量任务，不替换 RAG3 默认问答链路。
- 历史报告序列化不添加 assessments，原有产物身份保持不变；已提交的真实历史产物用于兼容性测试。
- 无新依赖、数据库迁移、训练、前端改动。旧产物、源文件、索引版本和用户截图保留。

## 有界真实回放

新增 `project/backend/scripts/reverify_research_claims.py`：显式输入原任务 JSON、SQLite 和向量目录，将数据库只读复制到新目录，核对完整索引/来源摘要后，最多调用一次模型。可用重复的 `--claim-id` 选择诊断子集；不重新抽取、不更新旧任务或 active version。API Key 仅从进程环境 `RAG4_EVAL_API_KEY` 读取。

在 `project/backend` 的 Python 3.11 环境运行：

```powershell
python scripts/reverify_research_claims.py --task data/research-citation-handles-20261013-resume2/task.json --database data/research-citation-handles-20261013-resume2/research.sqlite --vectors data/research-citation-handles-20261013-attempt1/vectors --output data/research-source-checks-new
python -m pytest tests/test_research_verification_checks.py tests/test_research_agent.py tests/test_research_citations.py tests/test_research_runtime.py -o addopts='' -q --tb=short --show-capture=no
python -m pytest -o addopts='' -q --tb=short --show-capture=no
```

第一轮选择原 12 条结论，Qwen/Qwen2.5-7B-Instruct、JSON 模式、输出上限 8192、连接 5 秒/读取 60 秒。单次请求 ReadTimeout，61039ms，没有新判定或 Token 用量。失败保留在 `data/research-source-checks-20261014-attempt1`。第二轮仅选择原模型判 supported 的六条，属于有偏诊断集，不作为整体质量评测。

第二轮一次请求成功，34425ms，prompt 4223 / completion 1588 / total 5811 Token。六条最终全部 insufficient；其中四条虽被模型三项判支持，但支持引文不是原文连续子串，被程序拦下。DPR/FiD 原有受支持结论也被误拒；REALM limitation 的三项模型判断依然错误。REALM result 被判不足，但理由声称原文未报告 REALM，而不是正确指出 CC-News 条件。故本轮没有证明语义质量提升，不能将“0 条发布”记作成功修复了两条语义误判。

两轮合计 **2 请求、1 网络失败、5811 已报告 Token**，失败请求用量和货币费用未知。没有继续重试或换模型刷结果。保留副本和候选报告，未覆盖 R20 展示表。完整账本见 [真实回放记录](../backend/evaluation/results/source_checks_20261014.json)，论文作者/许可见 [来源说明](research_corpus_sources.md)。新协议维持显式实验选项；后续应优先复用来源编号消除核验阶段的引文抄写，再在固定样本外检查语义稳定性。

新增 11 项协议/产物回归，先运行见到 6 项失败，再补实现和边界用例；相关 Agent、引用和 Local/Chroma runtime 合计 **46 passed / 30.84s**。旧真实产物身份、缺项/重复/外来 claim_id、虚构引文、单项不足及成品二次检查均覆盖。

## 阶段边界与下一步

| 阶段 | 现有能力及本轮关系 | 仍待验收 |
| --- | --- | --- |
| Phase 1 | 复用结构化 ChunkSet、原文区间和页码，不更改切分身份 | PDF/DOCX 版式结构抽取、真实质量对照 |
| Phase 2 | 只读验证冻结索引；回放使用数据库副本 | 生产执行/部署验收，按需求触发，暂不扩展 |
| Phase 3 | 复用所有者与文档范围隔离；未发现需改动范围检查的证据 | q09 上下文预算、q12 召回缺口；真实图谱收益 |
| Phase 4 | 新协议冻结在任务模型配置中，沿用预算、失败、CAS 和恢复 | 更灵活研究计划与生产运行验收 |
| Phase 5 | 新增逐项核验和产物二次门禁 | 人工支持率、缺口识别、跨文档任务质量门槛 |

下一切片应以 q09/q12 的具体证据缺口做等预算检索对照，并人工复核开发集；不向生产检索注入离线答案或锚点，不用提升平均覆盖率代替研究结论质量。不把 Neo4j、通用自主规划、前端工作区或正式微调标为已完成。

最终全量回归：在 `project/backend` 执行 `python -m pytest -o addopts='' -q --tb=short --show-capture=no`，**451 passed / 494.48s**，无失败、无跳过。编译检查与差异空白检查通过。测试通过不代表上述真实语义质量门槛通过。
