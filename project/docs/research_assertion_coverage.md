# R49：逐断言覆盖、单请求核验与保守产物

日期：2026-11-08。承接 [R48 对照](research_verification_assertions.md)，新增可直接调用的显式后端接口。没有接入 ResearchTask/HTTP 默认路径，没有自动拆句、改写旧任务或切换模型。研究质量验收仍未通过。

## 领域与实际行为

新增 `backend/app/research/assertions.py`，领域词汇同步根 `CONTEXT.md`：

| 类型/接口 | 契约 |
| --- | --- |
| StatementAssertion | 原声明的 Unicode 字符起止位置（右开区间）及精确原文，含独立 assertion_id |
| AssertionPlan | corpus_id/claim_id、完整原声明和 1–8 个连续区间；版本 statement-ranges-v1 参与身份 |
| build_assertion_plan(corpus, claim, ends) | 调用方提供经过审阅的结束位置；必须从 0 连续覆盖到原句末，不修剪逗号、空白或标点，不补主语 |
| AssertionCoverageVerifier.verify(corpus, claims, plans) | 每条声明恰有一个计划；最多 20 个声明、合计最多 20 个断言，只执行一次 generate，不重试 |
| AssertionReview | 保留计划、精确来源上下文及逐断言 attribution/conditions/entailment 检查；缺失判断不足，未知/重复身份拒绝 |
| compose_assertion_review(...) | 使用调用方已持有的旧核验报告，新增审阅只能限制原结论，不能提升旧报告已拒绝的声明 |
| AssertionPublication | 同时保留 baseline、reviews 和新的 Artifact；自身身份绑定三者，可从冻结来源重建核对 |

计划校验同时核对 Claim 的精确引文、所属文档和确定性身份。完整覆盖不证明划分语义合理；断言保留整句作为归属/否定/条件背景，不能被当作脱离上下文的新结论。当前不自动定位分句边界，必须由调用方明确提供。

新模型操作 `verify_assertions` 用一次请求发送完整原声明、断言区间/身份、原声明的来源编号目录、facet 要求和来源上下文。模型只能返回 assertion_id 和三项编号检查；不会复制引文或生成新的分句。来源仍严格限制在原引用内，前序上下文不能扩大支持范围。任意断言不足/未判断，整句不能受支持；有效反证可使整句 contradicted。

调用须显式配置 facet-handles-v5 及 preceding-children-v1 或 cited-support-v2；新操作在账本额外记录 assertion_protocol=statement-ranges-v1、提示词摘要、耗时和用量。它没有成为 CompletionSpec/API 的新默认 verification_protocol，也没有改变旧提示词。`protocol.py` 仅为新 assertion_id 字段提供安全错误路径。

## 发布与预算边界

```python
plan = build_assertion_plan(corpus, claim, (cut, len(claim.statement)))
reviews = AssertionCoverageVerifier(model).verify(corpus, (claim,), (plan,))
publication = compose_assertion_review(
    corpus, goal, document_ids, titles, (claim,), existing_report, reviews
)
publication.validate_source(corpus, (claim,))
```

`existing_report` 是调用方已有的报告；本接口不会为了获得它重新请求模型。发布先复查原报告/引用，验证全部新审阅的范围、来源及身份，再生成独立的新报告和产物。原报告和原 Artifact 保留。新产物不偷偷把较弱分句替换进原比较表，引用仍是完整原 Claim 的精确来源。

这是审阅既有结论的显式入口；**未接入任务执行器，不会自动消耗或增加 ResearchTask 预算**。调用方必须预留这一生成调用，使用 JsonResearchModel 的有限 max_calls；多断言/多声明只用一次调用。新任务若未来要同时获得整句与断言判断，必须在同次请求内设计联合报告，不能先跑旧核验再隐式附加一次调用。若请求过大，沿用现有输入限制并报错，不切成隐藏多请求。

必须保留整个 AssertionPublication；只取内部旧格式 Artifact 会丢掉断言审阅来源。它目前不是任务检查点或 HTTP 响应格式，不应冒充正式任务已采用新策略。身份摘要是完整性检查，不是签名，也不证明语义真伪。

## 测试与冻结回放

新增 `backend/tests/test_assertion_coverage.py` 共 **31 项**，初次因缺少模块红灯，完成后全绿。覆盖连续 Unicode 范围/版本身份、空/缺失/重叠/伪造范围、来源与身份错配、未知/重复返回、跨来源编号、未判断、反证、只限制不提升、原句/引用保留、发布重建、防删审阅、范围总额和失败无重试。

使用真实 JsonResearchModel + httpx.MockTransport 检查实际请求结构：两断言共享一次 HTTP 请求和一次账本预留；max_calls=1 时第二次调用在发请求前被拒绝。另验证多声明也是一次 generate。这是协议/预算测试，不是线上模型质量测试。

在新 SQLite 副本上，用 R48 的预测/训练单句判断构造了**显式受控回放**。保留 R46 原复合声明及完整来源，按同一引用窗口的精确位置/文本把旧支持编号重新绑定到父声明；把 R48 单句判断对应至本次区间时记录了表述差异（逗号/句号、显式 REALM 主语），不是对新分句重新获得的模型判断。一次 fixture generate 后，旧报告 supported=1，新产物 supported=0、引用为空，保留完整原报告与审阅；新产物身份为 `assertion_publication_c853c1f124f03de30a141e2011af9235a55fc914f9fa453a2af7ef5240670094`。

回放说明聚合和发布契约能拦截这组判断，**不能证明真实模型在新同批协议下也会正确拒绝**。本轮付费 Completion/Embedding 均 0。原任务、SQLite 和全部向量摘要相等；旧机器产物和保守审阅稿均不改。公开记录含变换说明、来源摘要及完整发布封装：[受控回放](../backend/evaluation/results/research_assertion_coverage_replay_20261108.json)。本地回放副本在 `backend/data/research-assertion-coverage-replay-20261108/`。

在 `E:\RAG4\project\backend`，Conda `rag4-py3.11` 执行：

```powershell
python -m pytest tests/test_assertion_coverage.py tests/test_verification_assertion_comparison.py tests/test_verification_support_context.py tests/test_verification_scope_comparison.py tests/test_verification_context.py tests/test_verification_facets.py tests/test_verification_handles.py tests/test_research_verification_checks.py tests/test_research_verification_batches.py tests/test_research_runtime.py tests/test_failed_partial_export.py tests/test_verification_claim_file.py -o addopts='' -q --tb=short
# 140 passed /66.81s
python -m pytest tests/test_response_contract_diagnostics.py tests/test_result_condition_integration.py tests/test_result_conditions.py tests/test_research_citations.py -o addopts='' -q --tb=short
# 63 passed /7.12s
```

两组不重叠，共 **203 项相关测试通过**；未重跑后端全量或前端。精确源码摘要与测试范围见 [检查记录](../backend/evaluation/results/research_assertion_coverage_checks_20261108.json)。无依赖、迁移、业务 MySQL 操作、模型训练或 GitHub 推送，用户 artifacts 和原工作区修改保留。

## 文件、回退和下一入口

本轮实际修改：新 assertions.py、test_assertion_coverage.py、两份公开 JSON、本页；model.py 增加新操作/版本账本，protocol.py 增加错误字段，根 CONTEXT.md 新增三条词汇；根 README/开发计划/基线及 development_process/research_backend_mvp 更新交接。原 RAG3 上传、切分、检索、聊天和引用接口未改。

回退为停止调用这个显式接口；旧任务与默认路径不依赖它，全部新发布封装继续保留，不删数据或剥离审阅。下一片在隔离环境用固定正负对、有界预算验证真实新协议，重点看是否逐项判断及是否出现同批干扰；同时必须保留已有 FiD 归属负例，避免为了此一例而失去前序上下文。未验证前不接生产 Task/API、不新增自动拆句、不晋级模型，不把本轮契约通过写成原 REALM 语义误判已修复。
