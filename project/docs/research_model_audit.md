# R35：仅替换核验模型的四次诊断

2026-11-01。**Qwen/Qwen2.5-72B-Instruct仍错误接受两条REALM声明，FiD正例因连接超时未判断，不晋级、不修改默认模型。** 此轮结果不能解释为“所有大模型都无效”，也不是整套系统的准确率。

## 范围和实际修改

承接R34，保持四条原始Claim、精确引文、前文窗口、旧research-operator-v1提示词、facet-handles-v5协议、JSON格式、4096输出Token和60秒超时不变，仅改变model_id。语义预期来自Agent来源复核，不是人工标注集。

- `project/backend/scripts/evaluate_claim_audit.py`：在既有有界诊断入口增加`--model-id`、`--control-report`、`--model-catalog`三项配套参数。默认配对提示词模式保持8次上限；model-only模式四条各一次，最多4次、不重试。
- `treatment_spec(source, version, model_id)`：复制冻结CompletionSpec，只覆写显式版本/模型。本次版本保持原值，所以模型之外的设置全部相等。
- `model_treatment(...)`：在凭据读取和输出创建前核对候选在提供商清单中且不同于旧模型、四条声明相等、研究模块清单和源码摘要相等、四份旧提示词控制结果完整、原模型/提示词摘要相等。`main`另核对源任务原始字节摘要及端点绑定。不能用修改过的提示词或来源伪装成模型单变量实验。
- 报告保存完整treatment_completion、提供商清单摘要、控制报告摘要、历史控制评分、每次调用状态/用量/耗时/提示词摘要和原声明。
- `project/backend/tests/test_model_audit.py`：新增11项契约回归，覆盖只改变模型、控制结果复用、候选不存在/相同模型、声明/实现清单/源码变化、控制缺失/失败、提示词和模型不一致。源码完整性单元测试使用隔离清单，不要求未来无关代码永久等于历史字节；真实试验仍严格检查实际源码摘要。
- 新增本说明、两份公开结果JSON并更新计划、README、开发过程和基线。

无新生产接口、领域模型、依赖或数据库迁移；生产研究实现与R34不变。不是新核验协议、调度或前端功能。

## 模型可用性与真实执行

实际GET `https://api.siliconflow.cn/v1/models`返回HTTP 200，共98个模型，包含Qwen/Qwen2.5-72B-Instruct。仅“列出”不等于调用成功或价格已确认；后续三次Completion成功才证明本次可调用。选择同系列72B尽量减少模型代际变化；不假设免费，不推断账单金额。APIKEY只在进程环境内使用，公开结果没有凭据。

在`project/backend`，Conda环境rag4-py3.11，使用已在进程环境配置的`RAG4_EVAL_API_KEY`：

```powershell
python scripts/evaluate_claim_audit.py --source-record evaluation/results/research_context_e2e_20261101.json --task data/research-context-e2e-recovery-20261031/task.json --database data/research-context-e2e-recovery-20261031/research.sqlite --vectors data/research-context-e2e-20261031/vectors --output data/research-model-audit-20261101 --model-id Qwen/Qwen2.5-72B-Instruct --control-report evaluation/results/research_claim_audit_20261101.json --model-catalog data/research-model-selection-20261101/models.json
```

输出目录已存在，重放须使用新路径。旧库只读backup到新SQLite，保留源任务、旧报告和向量。控制是R34先前的单条请求，不是同步随机对照，提供商行为漂移仍可能影响比较。

| 固定声明 | R34的7B旧提示词控制 | 本轮72B，旧提示词 |
| --- | --- | --- |
| REALM方法：缺训练目标引文 | 错误接受 | 仍错误接受 |
| REALM结果：遗漏CC-News | 无效ID被机械拒绝，不能算语义识别正确 | 仍错误接受 |
| DPR数据集 | 支持 | 支持 |
| FiD论文报告定性SOTA | 因额外条件要求而拒绝 | ConnectTimeout，未判断 |

4次Completion请求，3成功1ConnectTimeout，无重试；另有1次模型清单GET。有效结果中只有DPR正例符合开发预期，两个错误接受未解决、一个案例无判断。已报10637 Token，失败请求用量及实际费用未知。无Embedding、新抽取、激活、产物替换或业务库访问。脚本原生退出1表示存在执行失败，不能把超时计为拒绝或无退化。

## 测试与可复核记录

```powershell
python -m pytest tests/test_model_audit.py tests/test_claim_audit.py tests/test_research_pilot_options.py tests/test_verification_facets.py tests/test_research_verification_batches.py tests/test_research_checkpoint_recovery.py -o addopts='' -q --tb=short --show-capture=no
```

先19 passed /4.55s；扩展相关范围55 passed /7.93s，隔离测试源码清单后最终**55 passed /7.89s**，新增11项，无失败/跳过。本轮仅诊断脚本/测试变化，生产研究模块摘要与R34相等，因此未重复历史577项完整回归。模型实验失败与工程测试通过分别记录，不混为质量通过。

- [提供商清单、四次请求、来源和控制摘要](../backend/evaluation/results/research_model_audit_20261101.json)
- [测试范围及源码摘要](../backend/evaluation/results/research_model_audit_tests_20261101.json)

源任务JSON、向量文件摘要及实际执行源码摘要已再次离线核对。R34/R33原始机器判断、失败证据和四条展示稿不改。

## 下一切片：可检查的断言与实验条件

停止继续盲换模型和叠加提示词。下个切片先为结果声明建立类型明确、绑定原始字符区间的实验行/条件表示，区分表格值、模型变体和预训练来源；以本轮真实CC-News遗漏为首个红灯，支持完整条件正例并保守处理歧义。只有来源和必需条件均可核对才允许该条件检查通过；无法判定必须保持unknown，不能依赖模型的supported字符串。先用离线真实引文和单元/集成测试验证，保留旧默认与旧Artifact身份，不直接改写历史判断。

方法声明的逐断言支持、抽取引用匹配、20题与比较表人工验收仍待完成。前端、Neo4j、生产调度和正式微调未新增，Phase 1–5仍未完整验收。本轮代码未提交或推送。


后续R36（2026-11-01）：已实现绑定原文的实验行/条件检查，真实CC-News遗漏在显式策略下被拦截，未声称解决全部语义问题。见 [R36记录](research_result_conditions.md)。
