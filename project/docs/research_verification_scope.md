# R47：引用上下文对照与不晋级决定

日期：2026-11-08。范围仅为 R46 已冻结的语义核验失败，不扩建索引、不切换模型，不改写原任务/机器产物/保守审阅稿。研究质量门槛仍未通过。

## 问题与诊断

R46 的 REALM 方法声明包含“通过优化边缘似然训练检索器”，但选中的 PDF 第 8 页引用没有覆盖该目标，机器仍判支持。DPR 数据集引用明确列出五个数据集，却在原批量核验中被拒。

先以零网络调用的载荷探针检查实际输入：DPR 数据集的 1029 字符来源包含全部五个名称，2380 字符上下文也没有丢失；REALM 方法来源 1394 字符、上下文 2510 字符。由此排除这两个样本中的传输截断假设，但尚不能确认批量干扰或上下文的因果作用。

新增显式 `cited-support-v2` 选择，仅使用精确 `claim.citation` 作为单个 cited ContextPart。保持原模型、提示词、来源编号目录、facet-handles-v5 和结果条件策略，单变量比较上下文选择。该选项需要 facet-handles-v5；历史 CompletionSpec 默认仍为 cited-chunk-v1，现有浏览器试点仍为 preceding-children-v1。

## 有限在线结果

同一冻结任务的新只读 SQLite 副本，固定四例、每例每策略一次，共 8 次 Completion、0 Embedding、0 重试，HTTP 全部 200。模型 Qwen/Qwen2.5-7B-Instruct；提示词 SHA256 为 `bc6ff0dcfc8d609a6979be214d910d88ac5f2b54b8023291f999f73aeece65d6`。已报 20352 tokens；请求耗时合计 93745ms，金额未知。

| 开发样本 | Agent 来源审阅预期 | 前序上下文 | 仅精确引文 |
| --- | --- | --- | --- |
| REALM 方法，原错误覆盖引用 | insufficient | supported（误接受） | supported（误接受） |
| 同一 REALM 声明，换为覆盖训练目标的 PDF2 引用 | supported | supported | supported |
| DPR 五数据集 | supported | supported | supported |
| FiD 局限，实际描述此前参数化方法 | insufficient | insufficient | supported（误接受） |

前序策略符合开发预期 3/4、误接受 1；仅引文策略符合 2/4、误接受 2；两者无正例误拒。**不晋级新策略。** 仅引文模式在本轮 FiD 归属负例上发生退化，保留前序上下文作为现有试点配置；保留新模式仅供显式诊断和结果复现。

这四例是主 Agent 来源审阅的开发草稿，非独立人工金标准、非总体准确率。每格只运行一次；DPR 本次逐条核验与 R46 按文档批量核验不同，不能把改善归因于上下文选择。REALM 原错误引用在两策略下均被放行，其准确根因仍未确认。REALM 局限、其他检索缺口及历史 ValueError 没有在本轮复测。

## 实际接口与文件

- `backend/app/research/verification_context.py`：扩展 VerificationContextPolicy；`build_context(corpus, claim, policy=...)` 生成确定性上下文，精确来源/策略参与身份，validate_source 重建核对。
- `backend/app/research/artifacts.py`：新策略载荷及报告溯源，ArtifactComposer 拒绝策略冒名和来源扩张；支持目录不扩大。
- `backend/app/research/model.py`：协议约束错误说明适用于两种来源上下文；默认序列化行为保留。
- `backend/scripts/reverify_research_claims.py`：允许显式选择诊断策略。
- `backend/scripts/compare_verification_scope.py`：固定四例、最多八请求、零重试；逐次保存输入摘要、上下文/来源长度、判断和调用账本，技术错误停止，不重新抽取或发布产物。
- `backend/tests/test_verification_support_context.py`、`test_verification_scope_comparison.py`、`test_research_verification_batches.py`：新增 9 个测试实例，覆盖精确引文、策略身份、防篡改、旧默认、协议限制、拒绝全部不算通过、请求失败不算质量成功及 SQL 批次合并/重载。
- 本文、根 README/计划/基线、development_process、research_backend_mvp 和公开结果同步真实交接。

公开逐项输入摘要、判断、tokens/耗时及保全断言见 [实验账本](../backend/evaluation/results/research_scope_ablation_20261108.json)。完整本地报告位于忽略目录 `backend/data/research-scope-ablation-20261108/report.json`，SHA256 `3c73c020fe0231b1bb5cfc40b6be9fc21312ca0ef3ee2433ed0172533d949ef3`。原 task SHA256 `d7a8c66148929a7f7d27724f4c2c60ad70e84f4497d88af2ce33384851b4e4fe`，原 SQLite/向量文件摘要前后相等。凭据仅在内存，不进入公开结果。

## 验证与复现

后端工作目录 `E:\RAG4\project\backend`，使用 Conda `rag4-py3.11`，无新增依赖。最终 **97 passed /57.61s**，新增 9 个测试实例，无失败或跳过；未重跑后端全量或前端。`git diff --check` 通过。

```powershell
python -m pytest tests/test_verification_support_context.py tests/test_verification_scope_comparison.py tests/test_verification_context.py tests/test_verification_facets.py tests/test_verification_handles.py tests/test_research_verification_checks.py tests/test_research_verification_batches.py tests/test_research_runtime.py tests/test_failed_partial_export.py tests/test_verification_claim_file.py -o addopts='' -q --tb=short
```

本轮唯一在线命令如下；复现需另选不存在的 output，并重新承担请求预算，不要覆盖保留输入：

```powershell
python scripts/compare_verification_scope.py --source-run data/research-paper-retry-20261108 --task-name research_18e5ac69ce68573054a1ac4e.json --output data/research-scope-ablation-20261108 --allow-live
```

回滚为停止显式选择 cited-support-v2，原默认和旧报告不变。新策略任务/报告仍需保留；旧版本程序可能不识别其策略，不能通过删字段或改写旧任务回退。本轮不访问业务 MySQL、不迁移/激活、不训练、不推送；R40–R47 仍在工作区，用户 artifacts 保留。

下一切片先增加同一引用的“检索改善预测”与“优化边缘似然训练”单断言对照，离线检查复合声明如何被放行，再决定是否需要有预算的模型验证。不能把正例覆盖或引文精确匹配当成语义成立；批量/逐条效应需独立对照，不能未经预算设计直接拆成生产多请求。
