# R33：真实文献比较端到端与有界恢复

记录日期：2026-11-01。执行目录沿用启动时的20261031名称。质量门槛仍未通过，当前交付是可复核的后端开发切片。

## 本轮解决的问题

R32六条冻结案例符合开发预期，但没有验证新任务中的检索、抽取、逐篇核验和产物是否协同工作。本轮对DPR、FiD、REALM三篇论文重新发起研究任务，保留机器实际生成的12条声明，不沿用旧比较表来替代新抽取。

首轮REALM核验60秒ReadTimeout，前两篇核验报告已经持久化。新增显式恢复入口，仅在新SQLite副本重做最后失败的一篇核验，复用成功检查点，随后合并和生成产物；不扩大任务预算。

## 实际修改及接口

- `project/backend/scripts/resume_research_comparison.py`：独立CLI入口，参数为`--source-run`和`--output`，凭据只从环境`RAG4_EVAL_API_KEY`读取；新目录拒绝覆盖。
- `require_recoverable(task)`：只接收v2计划中唯一的末篇网络核验失败；其他未执行步骤只能是合并/产物。必须保留其余全部文档报告，且原Completion和步骤预算足够。
- `copy_database(source, destination)`：SQLite只读源连接backup到新文件，目标存在即拒绝。原JSON、SQL和向量不改。
- `credential_base(spec)`：检查点不得把已有硅基流动凭据重定向到其他域名或HTTP。该试点入口固定绑定`https://api.siliconflow.cn/v1/chat/completions`。
- `project/backend/tests/test_research_checkpoint_recovery.py`：11项新测试，覆盖可恢复状态、错误类别、待执行付费步骤、模型/步骤预算、running状态、报告缺失、源库保留、目标拒绝覆盖与提供商绑定。
- 本文、README、开发计划、基线和开发过程记录，以及4个公开结果文件。

沿用既有ResearchTask、VerificationBatch、CompletionSpec和ArtifactComposer，无新领域模型、数据库迁移或依赖。RAG3默认行为、生产API及研究实现本轮未改。

## 执行方式与预算

在`project/backend`使用Conda `rag4-py3.11`；运行前在当前进程设置上述环境凭据，不写入命令、日志、SQL或版本库。

```powershell
python scripts/evaluate_research_comparison.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --cached-run data/literature-pilot-v1/run-qwen8b-20261012-attempt2 --cached-report-sha256 ff2d80b89c5e506bd4d8b0a9f3eb933e0972efb426d6107c19665cefe779b88e --output data/research-context-e2e-20261031 --model Qwen/Qwen2.5-7B-Instruct --plan-version research-comparison-v2 --extraction-protocol source-handles-v2 --verification-protocol facet-handles-v5 --verification-context-policy preceding-children-v1 --context-policy local-window-v3 --candidate-policy source-role-v3 --max-output-tokens 4096
python scripts/resume_research_comparison.py --source-run data/research-context-e2e-20261031 --output data/research-context-e2e-recovery-20261031
```

上述目录已有数据，重放必须选全新输出路径。原运行未打开自动重试；恢复是单独显式动作，不把首轮失败涂改为成功。原任务限额13步、8次Completion；查询Embedding独立限额。文档向量仅在字节/ID/文本绑定校验后复用，未重新调用文档Embedding。

| 项目 | 首轮 | 显式恢复后累计 |
| --- | --- | --- |
| 任务状态 | failed，REALM ReadTimeout | completed |
| 工具步骤 | 9 | 12 / 原预算13 |
| Completion请求/预留 | 6，5成功1超时 | 7，6成功1超时 / 原预算8 |
| 查询Embedding | 3批，每批4输入 | 仍3批，无新增 |
| 新抽取声明 | 12，三篇各4条 | 原声明不变 |
| 机器支持/缺口 | 未合并 | 6 / 6，产物partial |

首轮187639ms，超时60007ms；恢复唯一新增Completion成功59476ms。已报Completion Token 36365、查询Embedding Token 498，合计36863；失败请求用量及实际费用未知，不能把已报数当总账单。两份成功报告保持完全相等。原隔离库完成激活、切换、回滚、停用演练，最后active为None；恢复不做任何索引切换。业务库未访问或迁移。

实际恢复脚本在调用后追加了提供商绑定检查，未再产生模型请求。执行时原脚本已按执行摘要归档到本地恢复目录`resume_script_executed.py`；公开结果分别记录执行摘要和最终测试源码摘要。实际端点本来就是获授权的硅基流动端点。

## 来源复核：工程完成不等于答案正确

逐条检查12条声明的原始引文，保存机器判断，不改原正式Artifact或假装修好核验器。检查者是开发Agent，不是人工标注者，不作为盲测/人工质量通过依据。

- DPR方法、FiD方法、REALM数据集和REALM局限，4条与所引来源一致，进入单独展示稿。
- 机器接受的REALM方法引文来自PDF第8页概率示例/消融，没有支持声明中的边缘似然训练目标；撤回展示。这里只否定当前引文支持，不能据此说论文没有该方法。
- 机器接受的REALM结果38.5/52.0对应PDF第7页Table 2的`REALM(X=CC-News)`，原声明漏掉该条件，普通REALM行是38.2/38.5；撤回展示，不偷偷改写原声明。
- DPR数据集引文列有五个数据集，FiD结果引文明言论文所报的两个基准SOTA，核验仍拒绝，记录为疑似误拒，未经独立复核不恢复展示。
- DPR结果引文有absolute EM 1–12的数字，模型否认该数字不准确；中文提升百分比仍须区分绝对百分点和相对提升。
- DPR局限选错方法段，FiD数据集引文不完整；FiD局限把背景方法归给自己，虽然最终拒绝，模型声称无参数数量的理由仍不准确。

原始机器产物6条支持仍保留；另存展示稿4条、8个单元格待确认。没有以展示稿冒充新版本正式Artifact。关系抽取为0，不能声称本轮证明图谱增益。

## 可核对结果

- [完整执行与恢复账本](../backend/evaluation/results/research_context_e2e_20261101.json)：首轮失败、显式恢复、全部调用/用量、原声明及原机器产物。
- [12条来源复核](../backend/evaluation/results/research_context_source_review_20261101.json)：机器判断与Agent复核并列，标明撤回和疑似误拒。
- [单独展示稿](../backend/evaluation/results/research_context_reviewed_comparison_20261101.md)：4条展示结论及精确来源，未经人工验收。
- [测试与完整性记录](../backend/evaluation/results/research_context_recovery_tests_20261101.json)：源码摘要、执行摘要及离线检查。

PDF、SQLite、向量和包含解析内容的本地运行目录不提交。公开JSON不含APIKEY或数据库凭据。原报告/任务摘要、成功报告、向量字节、SQL/JSON相等、所有Claim身份/精确引文、上下文重建和Artifact重建均离线验证通过。

## 测试与边界

```powershell
python -m pytest tests/test_research_checkpoint_recovery.py tests/test_research_pilot_options.py tests/test_research_verification_batches.py -o addopts='' -q --tb=short --show-capture=no
```

最终24 passed /3.62s，无失败或跳过；本轮新增11项。生产研究模块摘要与R31一致，未重复历史完整后端549 passed /265.06s。契约测试通过不能证明语义质量通过。

恢复CLI只覆盖本次最后一篇网络失败及剩余原预算，不能当通用队列、可靠调度或任意损坏检查点修复。异常输入/语义错误不能用此入口绕过。默认策略仍保留旧配置，撤销试点只需停止调用新入口，不影响旧库/旧索引。尚无新前端、Neo4j、生产调度或正式微调。

## 下一入口与停止条件

下一切片直接围绕本次12条新声明修复claim–citation匹配和必要实验条件核验，优先解决REALM两条错误接受及DPR/FiD疑似误拒；保留此轮原始失败，预期独立复核后冻结。先做针对性契约回归，再以明确调用上限验证语义收益和误拒，不新增核验协议来替代质量证据，不扩展索引基础设施。比较表、20题、独立人工验收和使用路径尚未完成，Phase 1–5不能标为全部验收通过。


后续R34（2026-11-01）：已对四条原声明完成有界配对提示词诊断，未解决两条错误接受，不切换默认，见 [R34记录](research_claim_audit.md)。
