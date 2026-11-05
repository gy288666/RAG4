# R36：来源绑定的实验行与确定性条件门禁

2026-11-01。**已在显式策略下拦截真实REALM结果的CC-News条件遗漏，不依赖模型是否批准。** 旧默认和旧产物身份保持不变；这是一项原文条件检查，不代表全部语义问题或Phase 1–5质量验收已解决。

## 本轮用户收益

R33/R34/R35中，7B、候选提示词和72B都曾批准同一条不完整结果。当前引文数字38.5/52.0来自`REALM (X = CC-News)`；原声明只写REALM。现在开启`explicit-row-v1`时，服务器必须从精确引文定位唯一实验行并检查其中显式条件，条件缺失或未知直接保留为待核验，模型无法覆盖这一结论。

本轮零付费模型调用，没有继续盲换模型、训练或扩建索引。

## 领域模型与稳定接口

词汇定义见根目录[CONTEXT.md](../../CONTEXT.md)。采用domain-modeling与codebase-design技能，计算集中在一个无副作用的接口：

```python
audit = audit_result_conditions(corpus, claim)
audit.validate_source(corpus, claim)
```

实现位于`project/backend/app/research/result_conditions.py`：

- `ConditionAssignment`：行中显式命名条件，保存symbol及条件值的原始Citation，不推断别名或默认值。
- `ExperimentRow`：语料/文档、行标签、行区间、数值区间、条件区间和解析完整性。`selector_version=vertical-assignment-row-v1`参与确定性row_id。
- `ResultConditionAudit`：绑定corpus_id、claim_id和可选实验行，记录passed/missing/unknown/not_applicable、原因、缺失条件及警告；策略版本explicit-row-v1参与audit_id。通过不代表语义得到支持。
- `ResultConditionPolicy`：默认model-only-v1；只有显式选择explicit-row-v1才启用新门禁。

所有快照不可变、可JSON序列化。Citation使用原Chunk的Unicode字符区间，结束位置不包含在内；source、label、values和条件值均可重建校验。内容摘要是完整性检查，不是签名或事实证明。

## 解析及判定规则

本切片只识别“标签行后紧跟若干纯数值行”的竖排表格；条件必须是完整的括号内`symbol = named-value`赋值，可包含多个逗号分隔赋值。数值支持十进制/科学计数法等价，不进行单位换算；Recall@5中的5不冒充测量值。

1. 先验证Claim身份与精确来源。
2. 声明数值必须匹配唯一行；多个候选行或未定位行均为unknown。
3. 该行必须有完整可解析的显式赋值；缺失/无法解析时unknown。
4. 必须保留所有命名条件值；缺少任何一个为missing。完整名称匹配，不把CC-NewsExtra当CC-News；大小写/NFKC兼容，英文句末标点不会丢失名字。
5. 识别到局部否定或显式符号赋值相反时保持unknown；不做开放域语义推断。
6. 即使passed，也仍需原有模型核验。这里不证明数据集/指标/列对齐、单位、因果关系或其他语义断言。

不支持的表格布局、跨行条件、未登记别名、缺失上下文和歧义都不能靠数字匹配获得通过。当前主要处理ASCII命名条件/阿拉伯数字，不保证覆盖中文数词、任意远距离否定或翻译后的来源别名。现有普通数字范围校验也继续保留。

## 核验到产物的接入

- `CompletionSpec.result_condition_policy`冻结任务选项；`JsonResearchModel`暴露该选项并在非默认调用账本中记录。
- `EvidenceVerifier`在模型请求前执行条件检查；missing/unknown转为insufficient，同时保存原文审计记录。没有增加隐藏请求。
- `VerificationReport`保存policy和condition_audits。默认序列化省略新字段，保留历史身份。
- `VerificationBatch.validate_scope`检查策略、Claim/语料/文档范围、唯一性和内容身份，并要求已支持结果具备通过的审计；合并步骤保留全部记录。
- `ArtifactComposer`重新从原文计算审计并比较，不相信传入的passed；冻结任务的compose工具禁止降级为旧策略来绕过检查。
- `POST /api/v1/research-tasks`接受显式`result_condition_policy`并持久化，非法选项沿用现有400响应。
- `evaluate_research_comparison.py`增加`--result-condition-policy explicit-row-v1`；不传参数时仍是旧策略。

任务配额预留规则不变：即使某条结果在模型调用前被阻止，也不声称相同预留预算自动允许更多调用；实际HTTP请求以调用账本为准。

## 实际原文回放

脚本`project/backend/scripts/audit_result_conditions.py`不读取APIKEY；只读旧库并backup到新SQLite，验证SQL/JSON一致、源语料和向量后执行：

```powershell
cd project/backend
python scripts/audit_result_conditions.py --task data/research-context-e2e-recovery-20261031/task.json --database data/research-context-e2e-recovery-20261031/research.sqlite --vectors data/research-context-e2e-20261031/vectors --output data/research-result-conditions-20261101-verified
```

该输出路径已经存在，重放须选新目录，不覆盖旧数据。实际结果：

| 输入 | 条件检查 | 后续行为 |
| --- | --- | --- |
| R33 REALM原结果声明 | missing：CC-News | 模型调用前insufficient，回放产物不展示该声明 |
| 同一引文、显式补充X=CC-News的对照声明 | passed | 只验证条件，未做语义核验、未以supported发布 |
| R33 DPR结果 | unknown：不能唯一定位本切片支持的实验行 | 不冒充条件通过 |
| R33 FiD定性结果 | not_applicable：无测量数值 | 仍依赖语义核验，不生成新的支持判断 |

真实实验行及值映射回PDF第7页；所有子区间、源任务JSON和向量摘要核对通过。生成的blocked_artifact只是单条拦截回放的部分产物，不是一次新抽取/新端到端任务，也没有替换原正式Artifact。

## 测试和修改文件

新增`tests/test_result_conditions.py`与`tests/test_result_condition_integration.py`，扩展`tests/test_research_verification_batches.py`和`tests/test_research_runtime.py`。覆盖真实反例/完整条件对照、重复行、未知布局、多个条件、否定、子串、科学计数法、精确CRLF区间、伪造/缺失/外部审计、旧Artifact身份、API冻结、SQL重载、合并和发布重验，共新增31项。

全量命令`python -m pytest -o addopts='' -q --tb=short --show-capture=no`：**619 passed /521.81s**。全量收集/导入早于最后标点用例和批次范围加固；最终收集620项，未宣称620项已全量运行。

最终相关命令：

```powershell
python -m pytest tests/test_result_conditions.py tests/test_result_condition_integration.py tests/test_research_verification_batches.py tests/test_research_pilot_options.py -o addopts='' -q --tb=short --show-capture=no
```

**42 passed /5.69s**，覆盖最终代码。此前含真实API/local+Chroma的相关范围**62 passed /56.64s**。开发中修复了句末数值识别；修正CRLF测试与既有切分去尾空白约定、无效参数与既有400响应约定的预期，未改变旧接口来迁就测试。原文回放在最终代码上重新执行，模型/Embedding请求均0。

除上述新模块/脚本/测试，实际修改包括`app/research/model.py`、`artifacts.py`、`tasks.py`、`tools.py`、`app/api/v1/research.py`、试点CLI，以及根词汇表、计划、基线、README和开发记录。没有新增依赖、迁移、前端或训练。

- [原文回放、行来源及单条拦截结果](../backend/evaluation/results/research_result_conditions_20261101.json)
- [测试范围和最终源码摘要](../backend/evaluation/results/research_result_condition_tests_20261101.json)

## 回滚边界与下一入口

默认仍model-only-v1。停止新任务选择explicit-row-v1即可保留原行为；既有任务继续按其冻结配置运行，不能直接编辑旧报告或覆盖旧索引。旧版本程序未必能解析新strict任务的额外字段：二进制回滚前须保留这些任务与导出记录，不能宣称旧程序自动兼容新策略数据。当前没有在业务库创建或迁移此类任务。

下一切片在隔离的新三论文任务中显式选择该策略，保持原13工具步/8次Completion预算，记录阻止的错误、unknown造成的缺口与部分产物；不把本轮条件正例冒充完整语义支持。REALM方法的训练目标误归属、抽取引用匹配、20题/比较表人工验收仍未解决。当前检查不替代通用PDF表格结构抽取或EvidenceVerifier语义能力，也没有宣称Phase 1–5全部完成。本轮尚未提交或推送。


后续R37（2026-11-04）：已运行上述新任务，修复可选关系边界后仍因REALM返回ValueError未完成，预算不追加；已导出明确失败的部分稿，见 [本轮执行](research_condition_end_to_end.md)。
