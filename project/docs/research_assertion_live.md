# R50：逐断言真实返回边界与严格 JSON 诊断

日期：2026-11-08。承接 [R49](research_assertion_coverage.md)。本轮实现可复现的真实协议诊断和安全 JSON 错误分类，但**没有完成新协议语义验收**，不接入 Task/API，不切换默认模型或格式。

## 固定控制与实际请求

新增 coverage-v1：REALM 原错误覆盖引用、REALM 覆盖训练目标引用、DPR 数据集正例、FiD 归属负例。REALM 原句人工固定两个连续范围，不改写表述；DPR/FiD 各一个完整范围，不自动拆句。前序上下文、原始引用、Qwen/Qwen2.5-7B-Instruct 和 statement-ranges-v1 固定。

不仅比较整句 verdict，还核对 6 个预定断言的独立结果；整句恰好不足不能掩盖另一个断言误拒，遗漏判断不能计成正确负例。预期仍是主 Agent 来源审阅草稿，不是独立人工金标准。

| 执行 | 实际请求 | 返回与停止原因 | 可用语义判断 |
| --- | --- | --- | --- |
| 固定四例窗口，原 text 格式 | 首例 1 次，其余 3 例未执行 | HTTP200，随后 JSONDecodeError；guard 耗时 36331ms，已报3031输入/662输出=3693 tokens | 0 |
| 显式单例 json_object 格式探测 | 同一首例 1 次 | ReadTimeout，guard 耗时61272ms，usage 未返回 | 0 |

首个失败按预设“技术错误即停”终止。随后先补离线严格解析测试和安全诊断，再明确限定一个单例格式探测；不是自动重试，也没有把四例窗口继续跑完。两次实际请求的 prompt SHA256 均为 `f2ae92c87d367c51c6e4d83a05004385f3e83c1613847ed5847cb148849788c5`，user payload SHA256 均为 `821994c5a75da8f80ee74e0dc9fb1557f4b517474f8414461be6af2440a3b265`。请求选项仅显式将 text 改为 json_object，模型/提示词/来源/断言范围不变；第二次还有新增的本地错误诊断，不改变请求内容。

本轮总共 2 次 Completion、0 Embedding、0 自动重试。**3693 只是已报告部分**，超时用量及总费用未知。两个报告的诊断逻辑都返回 2（未完成），不是语义不匹配的 3，更不是质量通过。未获得有效判断，不能报告新协议准确率、误接受为零、JSON 模式有效或 FiD 无退化。

首个模型返回内容未留存，只能确认 JSON 解析失败，不能补写其代码围栏、附加解释、缺引号或其他具体形状。第二次超时也不能证明 JSON 模式导致超时、模型不支持该模式或提供方根因；未修改超时、代理、模型或继续追加请求。

## 实际修改的接口与文件

- `backend/scripts/compare_verification_scope.py`：新增 coverage-v1、coverage_plan、coverage_expected、coverage_outcome；将完整计划/输入在首次请求前落盘；缺失原子判断记 missing；开发门禁同时检查整句和逐断言结果。
- 同脚本增加显式 `--coverage-case`、`--response-format` 及 select_coverage_case/comparison_spec。默认矩阵、任务 CompletionSpec 和 response_format 保持原值；单例模式仅允许 coverage-v1，配额按实际选定矩阵计算。
- `backend/app/research/model.py`：新增安全返回阶段/JSON 特征诊断。失败账本 response_error 只记录固定阶段/代码、格式前缀标签、字符数、错误位置/行列；区分 provider_json、provider_envelope、model_json 与 http_response，不保存原文、字段名、异常文本或认证信息。
- `backend/tests/test_assertion_live_comparison.py` 新增8项，覆盖固定配额/范围、单例准入、原子误判/缺失门禁及格式覆盖不改其他配置；`test_model_json_diagnostics.py` 新增10项，覆盖围栏/解释/畸形/空/数组前缀、HTTP体JSON、重复字段、非对象、非文本及成功账本兼容。
- 两份公开JSON、本页和根 README/计划/基线及 development_process/research_backend_mvp 同步真实结果。

严格解析行为保持：不剥离围栏、不提取正文中的 JSON、不修复语法、不接受重复字段或非对象，不静默切换响应格式。成功账本不新增错误字段，旧任务和既有序列化身份不被重写。新诊断只适用于新失败；不能回填首个已发生失败的格式细节。

## 测试与复现命令

新增控制测试最初6红、单例/格式接口2红，JSON诊断9红/1绿，完成后全部通过。最终在 `E:\RAG4\project\backend`，Conda `rag4-py3.11`：

```powershell
python -m pytest tests/test_model_json_diagnostics.py tests/test_assertion_live_comparison.py tests/test_assertion_coverage.py tests/test_verification_assertion_comparison.py tests/test_verification_support_context.py tests/test_verification_scope_comparison.py tests/test_verification_context.py tests/test_verification_facets.py tests/test_verification_handles.py tests/test_research_verification_checks.py tests/test_research_verification_batches.py tests/test_research_runtime.py tests/test_failed_partial_export.py tests/test_verification_claim_file.py tests/test_response_contract_diagnostics.py tests/test_result_condition_integration.py tests/test_result_conditions.py tests/test_research_citations.py -o addopts='' -q --tb=short
# 221 passed /65.62s；新增18项，未跑全量或前端
```

本轮实际两条在线命令如下。复现必须另选不存在的输出目录，不能覆盖保留输入；不应因本轮失败直接无界重跑。

```powershell
python scripts/compare_verification_scope.py --source-run data/research-paper-retry-20261108 --task-name research_18e5ac69ce68573054a1ac4e.json --output data/research-assertion-live-20261108 --experiment coverage-v1 --allow-live --fail-on-draft-mismatch
python scripts/compare_verification_scope.py --source-run data/research-paper-retry-20261108 --task-name research_18e5ac69ce68573054a1ac4e.json --output data/research-assertion-json-probe-20261108 --experiment coverage-v1 --coverage-case realm_method_negative --response-format json_object --allow-live --fail-on-draft-mismatch
```

公开原计划、来源/输入摘要、错误/请求账本及原始报告摘要见 [真实诊断](../backend/evaluation/results/research_assertion_live_20261108.json)，最终源码摘要和测试范围见 [检查记录](../backend/evaluation/results/research_assertion_live_checks_20261108.json)。原任务、SQLite 和全部向量在两个窗口均前后摘要相等；原机器 Artifact/审阅稿、新 R49 回放不改，没有产生新的正式产物。

无新增依赖、数据库迁移、业务 MySQL 操作、索引激活、模型训练或 GitHub 推送；用户 artifacts 和此前工作区修改保留。回退为停止显式 coverage-v1/格式探测调用，历史接口不依赖它；保留失败账本，不删记录或改写旧任务。

## 当前限制与下一入口

R49 的范围/发布契约仍有本地证据，真实新协议尚未获得有效判断，三个控制样本未执行。下一片停止追加模型诊断设施，先核对既有阅读台和产物，补实际缺失的逐结论来源审阅/撤下记录能力，用现有数据推进用户研究闭环。任何后续在线尝试仍须预先限定单例/预算并使用现有安全阶段信息；不能因本轮失败启用默认或反复宣称已验证。Task 联合报告/持久化接入、批量效应及独立人工质量仍未完成。
