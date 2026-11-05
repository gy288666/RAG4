# R34：固定声明的成对核验与候选版本拒绝晋级

2026-11-01。承接R33新任务的四个具体问题，先复现再对照。**未修复REALM两条错误接受，不切换默认提示词，质量门槛仍false。** 本轮没有扩大索引设施，也没有反复增加核验协议。

## 复现与假设

使用diagnosing-bugs流程。冻结R33原声明、原引文、原语料、Qwen/Qwen2.5-7B-Instruct及上下文设置；两条REALM错误接受、DPR数据集和FiD结果两条疑似误拒，开发预期来自上轮Agent来源检查，未经独立人工标注。

```powershell
cd project/backend
python scripts/evaluate_claim_audit.py --source-record evaluation/results/research_context_e2e_20261101.json --score-original
```

原始机器报告0/4符合开发预期，程序原生退出2，未访问凭据、SQL或模型。这里0/4是专门选择的失败案例，不能外推为整套系统准确率。

排名假设：(1)多声明批次使模型漏核某条；(2)理由复述规则而没有检查所有断言和表格条件；(3)抽取已选错引文。配对请求将声明数固定为一条，仅改变显式提示词版本。历史批次与本轮单条另行比较，不把两种变化合并宣称收益。

## 实际修改与接口

- `project/backend/app/research/model.py`：`prompt_for(spec, operation)`选择候选提示词；显式`CompletionSpec.version='research-facet-audit-v2'`才对`verify_facets`启用。仅允许facet-handles-v5组合，其他旧版本/操作仍使用原提示词。无额外模型请求。每次调用增加实际`prompt_sha256`账本字段。
- 候选提示词要求区分示例/消融/训练目标，逐断言查证，读取表格行修饰条件和完整数据集列表，并区分论文定性结果声明与数值比较。没有内置论文名称、Claim ID或预期答案。
- `project/backend/scripts/evaluate_research_comparison.py`：增加显式`--operator-version`，默认仍research-operator-v1。候选未获晋级；不推荐用于默认或质量验收。
- `project/backend/scripts/evaluate_claim_audit.py`：四条原始声明配对诊断，最多8请求、不重试。核对源任务摘要、SQL/JSON、Claim身份、引用和源语料，读取原库后backup到新SQLite；不改旧任务或索引。提供离线原报告评分入口。
- `score`新增无效support ID的独立统计。最终拒绝因机械来源校验造成时，不算语义匹配成功；`semantic_matched`仍只表示开发预期符合，不等于人工语义正确率。
- `project/backend/tests/test_claim_audit.py`：8项新回归，覆盖旧提示词/序列化兼容、候选准入、真实HTTP请求提示词与账本摘要、有限调用、历史失败复现、歧义来源拒绝、机械拒绝不计语义成功及CLI显式开关。
- 2份公开结果JSON和本轮开发文档。无新依赖、数据库迁移或默认配置切换。

## 真实对照

进程环境中读取获授权的硅基流动凭据，不写入命令/输出/数据库。下列输出目录已经存在，重放必须选新目录。

```powershell
python scripts/evaluate_claim_audit.py --source-record evaluation/results/research_context_e2e_20261101.json --task data/research-context-e2e-recovery-20261031/task.json --database data/research-context-e2e-recovery-20261031/research.sqlite --vectors data/research-context-e2e-20261031/vectors --output data/research-claim-audit-20261101
```

| 固定声明 | 原提示词，单条 | 候选提示词，单条 |
| --- | --- | --- |
| REALM方法：引文未支持训练目标 | 仍错误接受 | 仍错误接受 |
| REALM结果：遗漏CC-News条件 | 无效证据ID被服务器拒绝；模型理由仍声称完全匹配 | 仍错误接受，理由甚至提及CC-News但没检查声明是否包含它 |
| DPR数据集：引文完整列名 | 支持 | 支持 |
| FiD定性结果：论文报告两个基准SOTA | 因要求未声明的数值条件而拒绝 | 支持 |

8/8请求执行成功，已报27022 Token；请求耗时之和105531ms，不能当墙钟运行时间；费用未知。无Embedding、重新抽取、激活或自动重试。脚本退出2表示候选未满足开发预期，不是执行异常。

最终与指定分项匹配均为2/4；剔除无效ID造成的拒绝后旧版1/4、候选2/4。两个正例上的表现不能抵消两个错误接受，更不能说明整体提升。原报告、原声明与4条展示稿不变。候选不晋级、不接入生产API默认，也不把本次机器判断拼成一份新的可信比较表。

执行后只强化了离线评分，不再调用模型。执行原脚本已按摘要保留在本地`evaluate_script_executed.py`；公开账本分别保存执行源码摘要与最终离线评分源码摘要，原始报告不覆盖。

## 测试与证据

完整后端：`python -m pytest -o addopts='' -q --tb=short --show-capture=no`，**577 passed /233.94s**。该轮收集发生在新增“机械拒绝不算语义成功”用例之前；此后生产模型源码未变，最终新增用例及相关回归另测。

最终相关：`python -m pytest tests/test_claim_audit.py tests/test_research_pilot_options.py tests/test_verification_facets.py tests/test_research_verification_batches.py -o addopts='' -q --tb=short --show-capture=no`，**33 passed /2.35s**。本轮新增8项，最终收集总数应为578，不把577项全量冒称为578项已全量运行。无失败/跳过的工程回归不等于语义验收通过。

- [固定声明、8次请求、原报告及离线分解](../backend/evaluation/results/research_claim_audit_20261101.json)
- [测试命令、范围和源码摘要](../backend/evaluation/results/research_claim_audit_tests_20261101.json)

## 下一切片与停止条件

本轮已达到8请求上限，不追加重试，也不再靠提示词叠加声称解决语义错误。下一切片保持这四条声明和默认旧提示词，仅替换核验模型，以不超过4次独立请求判断更强模型能否识别两条错误接受并保留两个正例；模型清单需实际确认，不假设可用或免费。若仍失败，先引入可检查的逐断言/实验条件表示，再评估训练。未经独立来源确认的开发预期不进入人工质量门槛。抽取引用匹配仍未修复，需在核验能力可用后以新抽取任务验证，不能用这轮固定声明替代端到端。

Phase 1–5仍只有最小后端工程闭环，完整质量、20题/比较表、图谱增益和用户使用路径均未验收。研究工作区、Neo4j、生产调度、正式训练本轮未实现。此次修改尚未提交或推送；回退只需保留旧operator版本，旧任务和旧索引不受影响。


后续R35（2026-11-01）：已按上述入口完成模型单变量对照；72B仍错误接受两个REALM声明，FiD连接超时，未切换模型。下一步收敛到可检查的来源条件表示，见 [R35记录](research_model_audit.md)。
