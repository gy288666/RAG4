# R38：安全的核验返回诊断

2026-11-04。**已实现并验证安全返回分类；R37历史ValueError的精确根因仍未确定。** 独立1次REALM复测ConnectTimeout，未收到响应，没有重试或把R37任务改成成功。原失败任务与两条方法的部分稿均保留。

## 本轮完成的代码

- `app/research/protocol.py`：新增`ResponseContractError`（继承ResponseSchemaError/ValueError）和`check_response_ids`。诊断仅来自服务器白名单code、operation、collection及非负整数计数，不保存返回ID、模型理由、原文或原异常消息。
- `app/research/artifacts.py`：四种已有核验协议均区分重复ID、未知ID及二者同时出现，记录expected/received/unique/unknown/missing数量。仍严格拒绝坏身份；缺失判断保持旧有`judge_did_not_verify_claim`/insufficient行为，不补造判断。
- `app/research/tasks.py`：VerificationBatch将原先合并的ValueError拆为scope、verdict coverage、counters、protocol、policy、condition scope与condition coverage。没有更改通过标准，旧`scope`错误文案保持兼容。
- `app/research/tools.py`：保留已分类错误，其余文档核验内部ValueError标为`unclassified_document_validation`；不把未知错误猜测成ID或网络错误。诊断随ToolResult.warnings保存到SQL检查点，任务继续保持failed。
- `scripts/reverify_research_claims.py --validate-document-batch`：独立最多一次请求后，还验证完整原文档的VerificationBatch。必须恰好选择该原文档的全部Claim；跨文档、空集合、部分或改写声明均拒绝。默认旧复测入口不变。
- `tests/test_response_contract_diagnostics.py`：27项新回归，覆盖四协议、身份计数、7类批次约束、未分类错误、SQL持久化、隐私、旧缺失判断及完整文档范围。

没有新任务/报告字段、数据库迁移、依赖、核验协议、模型切换或身份容错放行。成功产物/旧部分稿的序列化与身份保留。错误响应才增加安全warnings和明确error_type，API原有错误码仍保留。

## 安全诊断示例

```text
response_contract_invalid:verify_facets:assessments:unknown_claim_ids
response_contract_counts:verify_facets:expected=3,missing=1,received=3,unique=3,unknown=1
```

这是格式示例，不是本次实际模型返回。不会记录究竟哪个未知ID或模型文本。重复与未知同时出现时使用duplicate_and_unknown_claim_ids；计数不代表语义质量。白名单以外的路由、code、count字段或非整数不会被写入诊断。

## 独立复测及其限制

R37原任务已用满8次预算；本轮是另建SQLite副本、单独1次诊断，不恢复该Task、不改其预算、不重跑检索或抽取，不把该请求混入原8次。

已在进程环境设置APIKEY后，于`project/backend`执行：

```powershell
$diagnosticTask = Get-Content data/research-condition-repair-20261104/task.json -Raw | ConvertFrom-Json
$diagnosticSelection = @()
foreach ($diagnosticClaim in ($diagnosticTask.claims | Where-Object { $_.document_id -eq 'realm' })) {
    $diagnosticSelection += @('--claim-id', $diagnosticClaim.claim_id)
}
python scripts/reverify_research_claims.py --task data/research-condition-repair-20261104/task.json --database data/research-condition-repair-20261104/research.sqlite --vectors data/research-condition-e2e-20261104/vectors --output data/research-response-diagnostic-20261104 --protocol facet-handles-v5 --max-output-tokens 4096 --verification-context-policy preceding-children-v1 --validate-document-batch @diagnosticSelection
```

输出路径已有内容，重放必须另选新目录。模型、提示词摘要、四条原始声明、引用、上下文和结果条件策略均保持冻结设置；源任务与R37部分稿身份核对不变。

实际仅1请求，**ConnectTimeout /5548ms**，没有响应、判断或新产物，reported token为0只表示未得到usage，不等于实际费用为0。没有再次请求。未进入新的身份/批次校验路径，因此不能说原ValueError已复现或已修复，也不能用测试模型判断代替真实输出。

随后只读GET `/v1/models`两次：默认读取环境和显式不读取环境均返回200，分别4494/5428ms；未发现http/https/all代理配置，未修改系统代理，未保存代理地址或凭据。两次顺序探测既不证明代理故障，也不证明chat接口稳定；本轮没有根据它们修改网络默认配置。

## 回归测试

新回归先19 failed /1 passed，复现旧通用错误与无诊断；实现分类后出现1 failed /83 passed，旧批次测试依赖scope错误文案，已保留该兼容前缀，不修改测试来掩盖行为差异。

最终：

```powershell
python -m pytest tests/test_response_contract_diagnostics.py tests/test_verification_single_replay.py tests/test_research_verification_batches.py tests/test_failed_partial_export.py tests/test_verification_handles.py tests/test_verification_facets.py tests/test_result_condition_integration.py tests/test_research_verification_checks.py -o addopts='' -q --tb=short --show-capture=no
```

**99 passed /10.43s**，新增27项。该范围覆盖所有修改的核验错误路径、工具/SQL持久化、旧产物身份和部分导出；未重复8分钟历史完整套件。当前收集678项，不称678项已全量运行。R37的641 passed /524.75s是历史完整结果，不能替代本轮测试。

- [独立请求、连接探测及来源摘要](../backend/evaluation/results/research_response_diagnostic_20261104.json)
- [测试命令与最终源码摘要](../backend/evaluation/results/research_response_diagnostic_tests_20261104.json)

## 下一交付与阶段边界

本轮停止追加模型请求；新增分类会在下一次正常核验返回时记录准确约束，历史缺失的响应不追认。短期交付转向把R37已保留的失败部分稿接入用户授权的只读查看路径，提供来源、缺口和failed标识，以支撑计划3.4节的实际研究操作入口。该接口必须验证用户/语料/检查点范围，不修改Task，不调用模型，不改变默认条件策略；CLI探针不能直接当作生产授权路径。

方法语义误判、ValueError历史精确根因和独立人工质量验收仍未解决；不标记Phase 1–5全部完成。后续安全诊断只随有预算的合法执行捕获，不启动无限重试、模型更换或索引扩建。业务库、默认策略、旧数据/向量、前端、Neo4j和正式训练本轮未改，代码尚未提交或推送。


后续R39（2026-11-04）：已完成失败部分稿的授权只读接口，真实隔离HTTP验证和来源/状态不写回检查通过；没有声称R37历史根因已修复。见 [接口记录及下一读取路径](research_partial_artifact_api.md)。
