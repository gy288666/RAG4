# R48：复合声明的单断言对照

日期：2026-11-08。承接 [R47](research_verification_scope.md)，本轮只实现可复现的声明对照和开发诊断门禁；没有修改生产核验协议、默认配置、模型、提示词或索引。

## 问题、反馈循环与结果

先对 R47 冻结账本执行“REALM 原引用判断应为 insufficient”的断言，实际 supported，得到 AssertionError；这条离线复现只重放已保存判断，不声称重新运行模型。随后固定四个对照：前三个引用完全一致，第四个只换为覆盖训练目标的 PDF2 引用。新声明按原 Claim.expected_id(corpus_id) 重新计算身份，绝不继承旧 verdict。

| 对照 | 表述与来源 | Agent 开发预期 | 实际判断 |
| --- | --- | --- | --- |
| compound_original_quote | 检索改善预测，且优化边缘似然训练检索器；PDF8 | insufficient | supported（误接受） |
| prediction_original_quote | 仅检索改善预测；同一 PDF8 引用 | supported | supported |
| training_original_quote | 仅优化边缘似然训练检索器；同一 PDF8 引用 | insufficient | insufficient |
| training_covering_quote | 与上一行同表述；PDF2 覆盖训练目标 | supported | supported |

模型仍为 Qwen/Qwen2.5-7B-Instruct，facet-handles-v5、preceding-children-v1、explicit-row-v1 及提示词不变。4 次 Completion 全 HTTP200，0 Embedding、0 自动重试；报告 12615 tokens，请求耗时合计 49656ms，金额未知。没有追加请求、换模型或恢复生产任务。

这组结果支持继续调查复合陈述的覆盖遗漏：完整声明的 entailment 理由只描述预测能力，conditions 却把训练目标配给未说明目标的消融段落；独立训练断言的三个检查均判不足。**原复合声明误判仍未修复。** 每格只有一次调用，单断言显式补回 REALM 主语，表述及 Claim ID 随之改变；不能据此认定唯一根因，也没有证明通用自动拆句可以解决问题。四例预期来自主 Agent 来源审阅草稿，非独立人工金标准。

## 实际代码与接口

- `backend/scripts/compare_verification_scope.py` 新增 `assertion_cases(task, corpus, results)`，生成固定的四例；校验原两条 Claim 的所有者范围、精确引用、身份、共同完整声明及 method facet。输入声明发生变化时必须显式修订对照，不能静默复用。
- `experiment_cases(..., experiment='context-v1'|'assertions-v1')` 选择既有上下文八请求或本轮断言四请求，默认仍为旧 context-v1。请求上限按固定矩阵计算，每次独立最多一调用；请求前在内存构建完整声明/引用/预期 frozen_claims，每次结束后持久化，技术失败停止。
- `diagnostic_exit_code(record)` 区分 0（全部符合开发预期）、2（未完成/缺失/重复行）、3（执行完成但判断不符）。CLI 新增 `--fail-on-draft-mismatch`；不传时保持历史执行完成返回成功的语义。无论哪个返回码，都不会把 quality_gate_passed 改为 true。
- `backend/tests/test_verification_assertion_comparison.py` 新增 12 项：来源保留、确定性新 ID、四请求固定策略、声明变动拒绝、假身份/假引用/越范围拒绝、HTTP 成功但判断错误、未完成/缺结果/错误请求/空矩阵、重复行不能替代遗漏对照。
- 本文、公开结果、README、开发计划、基线、development_process 和 research_backend_mvp 更新真实进度。

实现前新增测试因缺失接口导入失败；实现后通过。门禁重复行用例先 1 failed /11 passed，确认会错误放行后增加唯一性检查。最终相关 **109 passed /60.20s**，新增 12 项，无失败或跳过；未重跑后端全量或前端。另在隔离副本逐条复核公开四 Claim、typed 报告/上下文身份与真实来源绑定，凭据模式检查及 `git diff --check` 通过；这些契约检查不改变语义诊断仍为 3 的结果。

## 命令与保留结果

后端目录 `E:\RAG4\project\backend`，Conda 环境 `rag4-py3.11`，无新增依赖。本轮唯一在线命令：

```powershell
python scripts/compare_verification_scope.py --source-run data/research-paper-retry-20261108 --task-name research_18e5ac69ce68573054a1ac4e.json --output data/research-assertion-ablation-20261108 --experiment assertions-v1 --allow-live
```

本轮在线调用早于新门禁实现；旧退出码 0 表示四次执行完成。新增门禁后仅离线读取同一报告，`diagnostic_exit_code(record)` 得到 **3**，不重新调用模型。未来复现可增加 `--fail-on-draft-mismatch`，必须另选不存在的输出目录。

```powershell
python -m pytest tests/test_verification_assertion_comparison.py tests/test_verification_support_context.py tests/test_verification_scope_comparison.py tests/test_verification_context.py tests/test_verification_facets.py tests/test_verification_handles.py tests/test_research_verification_checks.py tests/test_research_verification_batches.py tests/test_research_runtime.py tests/test_failed_partial_export.py tests/test_verification_claim_file.py -o addopts='' -q --tb=short
```

公开结果含四条完整 Claim、typed 核验报告/支持区间、输入和提示词摘要、用量及保全断言，见 [断言对照账本](../backend/evaluation/results/research_assertion_ablation_20261108.json)。本地原始 typed 报告 `backend/data/research-assertion-ablation-20261108/report.json` 的 SHA256 为 `c24322e8f2717aebe3d38991cdb0fa99e280e035447e60f54a5d732e591d1008`。原 R46 task SHA256 仍为 `d7a8c66148929a7f7d27724f4c2c60ad70e84f4497d88af2ce33384851b4e4fe`，原 SQLite 与向量摘要前后相等。凭据仅在进程内存；不记录认证头或原始模型报文。

回退为不选择 assertions-v1 或不用新增门禁；历史 context-v1 和生产入口不变。所有实验与旧报告继续保留。没有数据库迁移、业务 MySQL 操作、产物发布、训练或推送，R40–R48 仍为工作区修改，用户 artifacts 保留。

## 下一交付与停止扩展条件

下一片针对已复现的覆盖遗漏建立有版本的断言覆盖表示：每个断言绑定原声明字符范围，未覆盖、重叠或缺失判断均不得把整个复合声明升级为 supported；在同一次核验请求内聚合，不能绕过 ResearchTask 预算隐式增加调用。先用本轮冻结响应检验聚合和来源契约，再决定是否启用新显式协议及有界在线验收。覆盖完整不代表语义成立，不能把拆句测试当人工质量通过。

本轮不自动拆写任务、把原句改成较弱结论或复用其中正例来替换原正式产物。REALM 局限、批量干扰、独立评测冻结与人工质量仍待完成；继续保留 R46 的保守审阅稿。
