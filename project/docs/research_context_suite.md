# R32：新窗口六例复测与端到端入口（2026-10-31）

本轮完成R31遗留的方法正例，并用同一组DPR/FiD六例验证preceding-children-v1。核验提示词、模型、引文、案例预期和生产研究实现不改。六例均为既有论文上的Agent开发案例，不是人工标注或盲测。

## 六请求实际结果

先核对R31全部研究模块清单、文件摘要、原任务摘要及复核脚本摘要，再冻结与R30相同的六个Claim。只改变显式上下文策略；每条独立新SQLite副本，4096输出上限、60秒超时、不重试，合计六次请求，全部成功。

| 案例 | 开发预期 | 最终状态 | 指定分项 |
| --- | --- | --- | --- |
| DPR：带NQ开发集/1,000样本条件的比较 | 支持 | supported | 符合 |
| DPR：省略条件并扩成所有数据集 | 不支持 | insufficient | 符合 |
| DPR：SQuAD缺段落时的明确局限 | 支持 | supported | 符合 |
| DPR：局限推出不能处理任何开放域数据集 | 不支持 | insufficient | 符合 |
| FiD：编码器独立、解码器联合处理 | 支持 | supported | 符合 |
| FiD：把背景方法的权重/参数限制归到FiD | 不支持 | insufficient | 符合 |

最终和预先指定分项均6/6符合开发预期，三个正例均支持，三个负例均拒绝。R31连接超时的方法正例在本次独立新请求中取得判断，旧失败不改写。各窗口实际1777、1777、1525、1525、2868、1241字符，均在6000上限内，源引用不扩大。

本次15258已报Token，货币费用未知；旧R30仅引用块六例为8118Token。本次上下文增加了观察用量，不能把单次Token差异或模型耗时当作固定成本/延迟改善。调用账本、原文、分项理由、窗口身份和来源见 [六例复测结果](../backend/evaluation/results/research_context_suite_20261031.json)。

离线评分实跑返回 `development_expectations_met`、退出0、额外模型调用0；quality_gate_passed仍为false。6/6只说明这组开发样本符合预期，不能证明人工支持率≥90%、普遍无回归、稳定网络、拒答质量或新研究任务端到端通过。

## 实际改动

扩展 `evaluate_cross_paper_claims.py`，增加显式verification-context-policy和与旧control-tests互斥的control-report。新control-report要求完整研究模块清单、摘要、源任务及复核脚本均匹配，不能用缺项清单绕过冻结。旧默认及旧控制入口保留，预算仍为六次，案例在调用前保存，不把预期传入模型。

扩展既有 `evaluate_research_comparison.py` 的运行入口：显式plan-version、context-policy、candidate-policy、verification-protocol、verification-context-policy和输出Token上限。原默认仍v1、父片策略、向量候选、numeric-model-v2、cited-chunk-v1及2048输出上限；单次网络恢复仍需明确传原retry标志。

v2计划沿用runtime预算准入，Completion模型请求上限绑定TaskBudget；查询Embedding设置有限上限并记录。检索器按选择包装词法/来源角色Adapter，与线上runtime一致。无效协议/上下文组合在凭据、缓存读取和数据库创建前拒绝，配置错误仍退出2。运行报告明确quality_gate_passed=false及所选策略和调用上限，不能将task completed等同质量验收。

这次**没有执行新的端到端研究任务**，仅打通下一步入口和前置检查。既有缓存报告摘要ff2d80b89c5e506bd4d8b0a9f3eb933e0972efb426d6107c19665cefe779b88e、成功状态及4096维配置已离线核对；没有新增查询Embedding、文档Embedding或训练调用。

## 测试与命令

相关最终 **44 passed /2.22s**，本轮新增10项：两种控制入口/两种窗口的六调用保留、控制来源/实现清单/复核脚本漂移拒绝，以及端到端CLI旧默认、显式新设置、无效组合和访问前拒绝。此前40 passed /2.35s，之后增加端到端入口参数覆盖。

本轮生产研究模块摘要与R31完整后端549 passed /265.06s时一致，仅改试点/诊断脚本与测试，未重复执行完整后端，不将新增用例记为已全量运行。源码与命令见 [本轮工程测试](../backend/evaluation/results/research_context_suite_tests_20261031.json)。

在 `project/backend`、rag4-py3.11环境：

```powershell
python -m pytest tests/test_research_pilot_options.py tests/test_cross_paper_experiment.py tests/test_verification_context.py tests/test_verification_claim_file.py tests/test_verification_single_replay.py tests/test_context_experiment.py -o addopts='' -q --tb=short --show-capture=no
python scripts/evaluate_cross_paper_claims.py --task data/research-citation-handles-20261013-resume2/task.json --database data/research-citation-handles-20261013-resume2/research.sqlite --vectors data/research-citation-handles-20261013-attempt1/vectors --control-report evaluation/results/research_context_attribution_20261031.json --verification-context-policy preceding-children-v1 --output data/new-context-suite
python scripts/evaluate_cross_paper_claims.py --score-report evaluation/results/research_context_suite_20261031.json
```

下一切片的受控端到端入口如下，**本轮未执行**：

```powershell
python scripts/evaluate_research_comparison.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --cached-run data/literature-pilot-v1/run-qwen8b-20261012-attempt2 --cached-report-sha256 ff2d80b89c5e506bd4d8b0a9f3eb933e0972efb426d6107c19665cefe779b88e --output data/new-research-context-pilot --model Qwen/Qwen2.5-7B-Instruct --plan-version research-comparison-v2 --extraction-protocol source-handles-v2 --verification-protocol facet-handles-v5 --verification-context-policy preceding-children-v1 --context-policy local-window-v3 --candidate-policy source-role-v3 --max-output-tokens 4096
```

三篇v2计划有11固定步骤/6固定Completion调用，预算13步骤/8 Completion调用和4查询Embedding请求；新目录隔离SQLite及版本演练，业务库和active不动，凭据只放RAG4_EVAL_API_KEY进程环境。本次诊断预算六次已用尽，后续新任务需另行明确预算并保留失败，不借旧预算隐藏重试。

实际文件为上述两份脚本、两份测试、两份结果JSON，以及本页/根计划/基线/README/开发过程/接口说明。无生产默认切换、依赖、迁移、前端或训练，旧索引/任务/比较表及用户artifacts保留。本轮尚未提交或推送。


后续更新（2026-11-01）：R33已执行本文预备的新端到端入口，并在新副本显式恢复末篇网络失败；机器产物仍有语义错误，见 [实际执行和来源复核](research_context_end_to_end.md)。本文“未执行”描述保留为R32历史状态。
