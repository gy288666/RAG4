# R29：真实结论的逐条核验对照（2026-10-31）

继续 R28 的单变量线索：同批另一结论的指标进入了方法描述的拒绝理由。本轮只检验两条真实结论在逐条调用下的表现，没有追加核验协议、索引平台、图谱或前端。

## 实际修改

- `scripts/reverify_research_claims.py` 新增显式 `--max-output-tokens`，支持2048/4096/8192，默认仍8192；`verification_spec` 校验覆盖参数并保留其他冻结设置。增加 `frozen_corpus`，在模型调用前后核对语料身份及来源绑定，变化即拒绝生成新产物。
- 新增 `scripts/evaluate_single_claims.py`，固定四次请求：两条原始结论 × v4/v5。先核对任务、原对照摘要、全部研究实现源码及原结论；每次独立新目录、新SQLite副本、最多一个模型调用。保存每次失败、子报告摘要与完整调用账本，没有隐式重试。
- 新增 `tests/test_verification_single_replay.py`、`tests/test_single_claim_experiment.py`，覆盖冻结设置、无效参数、来源变化、四次上限、失败保留、单条范围及来源/代码谱系拒绝。
- 更新本页、计划、基线、README、开发过程、后端接口说明和公开结果。没有修改本轮生产研究模块、依赖、数据库迁移或旧产物。

## 固定条件和预算

原始输入为 R20 完成任务的两条 REALM 结论，保持源文件、引用、上下文、原文目录、模型、提示词、temperature=0、60秒超时和4096输出上限；每次只发送其中一条结论。原 R28 结果和四次预算不改，本轮新实验也只允许四次请求，没有重试。

所有代码与来源摘要在请求前核对，`expected` 只在返回后评分，不发送给模型。v4/v5之间提示词不同，因此只在同协议内讨论“逐条 vs 批量”；不能把 v5 的成功同时归因于两项变化。R28真实v5超时，无可评分的批量语义结果。

## 结果与解释

本轮四请求全部成功，6012已报Token，货币费用未知；模型耗时分别为10862、12182、15761、9794ms。原任务文件摘要保持一致。完整引用、分项状态、用量、设置和谱系见 [逐条对照账本](../backend/evaluation/results/research_single_comparison_20261031.json)。

| 结论 | R28批量v4 | 本轮单条v4 | 本轮单条v5 |
| --- | --- | --- | --- |
| 有来源的方法描述 | conditions不足，误拒 | conditions仍不足，误拒 | 三项支持，最终supported |
| 无来源的“需进一步研究组件贡献” | entailment误支持，因其他项失败才拒绝 | entailment不足，最终拒绝 | entailment不足，最终拒绝 |

v4 的两条单条判断中一条符合预期（1/2），v5两条均符合预期（2/2），指定分项也分别为1/2、2/2。相比R28只在合成案例通过，本次获得了两条真实来源的 v5 正反例反馈，方法误拒在这次单条调用中不再出现。

方法描述在单条v4下仍被拒绝，否定了“仅由同批另一结论造成方法误拒”的解释；局限结论的分项改善与批内干扰假设相容，但每格只有一次调用，模型随机性、请求组成和token数仍有影响，不能据此证明因果或广泛质量提升。案例及预期仍为Agent开发判断，未通过人工支持率门槛。

本次没有把逐条策略接入生产计划：三至五篇、每篇至多四条的逐条调用可能明显增加步数、费用和等待时间，需要先验证独立正反例，再决定如何在已有任务预算和checkpoint下执行。不能在verify_document内部隐式循环模型或借旧预算继续调用。默认仍numeric-model-v2，不将两个诊断子集产物拼接为“全部核验过”的比较表，旧表不覆盖。

## 测试与复现

在 `project/backend`、rag4-py3.11环境：

```powershell
python -m pytest tests/test_verification_single_replay.py tests/test_single_claim_experiment.py tests/test_verification_facets.py tests/test_verification_handles.py -o addopts='' -q --tb=short --show-capture=no
python scripts/evaluate_single_claims.py --task data/research-citation-handles-20261013-resume2/task.json --database data/research-citation-handles-20261013-resume2/research.sqlite --vectors data/research-citation-handles-20261013-attempt1/vectors --batched-report evaluation/results/research_facet_comparison_20261031.json --output data/new-single-comparison
```

最终相关 **32 passed /3.61s**，本轮新增10项工程测试。此前先26通过/3.93s，再29通过/3.05s；后者覆盖了新增来源守卫。上轮完整后端 **509 passed /501.85s** 是R28历史结果，本轮生产研究模块摘要均未变化，仅改诊断脚本与测试，未重复运行全量或把新增用例写成已全量通过。

复现时凭据只放进程环境 `RAG4_EVAL_API_KEY`；要求新的输出目录，原数据保留。下一切片先验证独立来源正反例，尤其遗漏实验条件的结果、明确局限和混合真假断言，再决定逐条或小批策略；不增加核验协议。Phase1–5的人工支持率、四道拒答题、剩余召回和新端到端比较仍未验收，本轮尚未提交或推送。


后续R30跨论文扩展验证为5/6，FiD归属负例被错误接受并已定位前文缺口，尚未修复；R29的两个案例通过不能代表普遍可靠。最新阻塞、离线门禁与入口见 [R30记录](research_cross_paper_verification.md)。
