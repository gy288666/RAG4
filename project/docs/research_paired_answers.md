# R56：真实20题双组答案与待审阅包（2026-11-10）

本轮实际执行相同问题、语料、模型和生成提示下的双组问答，共40次请求，取得39份可用正文。RAG3为20/20；RAG4为19/20，q19发生RemoteProtocolError，原始失败保留且没有重试。运行状态为incomplete，不是质量验收通过。

## 实验边界与预算

本轮只比较历史RAG3切分与RAG4结构切分策略。复用2026-10-12已保存的Qwen/Qwen3-Embedding-8B检索Top-10；验证题目、来源PDF、实际重新切分的chunk ID/正文/页码/区间与缓存一致。没有新建向量库、访问业务SQL、修改上传或active指针。此处RAG4不含父片展开、Hybrid融合、图谱、ResearchAgent、多步核验或生产Reranker，因此不能将结果解释为完整RAG4 Agent与线上RAG3的端到端比较。

两组采用现有 `app/services/prompts.py` 的 `RAG_SYSTEM_PROMPT` 和相同来源格式，测试与 `build_context_prompt` 校验一致。不把题目类别、expected_answer或标注证据锚点发送给模型。不同组仅有旧/新切分检索上下文变化，但两种切分策略也存在重叠差异，不能单独归因于父片或结构边界。

首次请求前写入并冻结manifest：

| 项目 | 实际设置 |
| --- | --- |
| Completion | 沿用最近真实三论文任务的Qwen/Qwen2.5-7B-Instruct，硅基流动 |
| 参数 | temperature=0.2；max_tokens=4096；非流式正文 |
| 次数 | 全部20题×2组，共40；每题1次，无重试 |
| 超时/执行准入 | 单次HTTP超时30秒，连接5秒；600秒后不再发起新请求；连续3次失败停止后续准入；401/403/429立即停止 |
| 上下文 | Top-10，原文字符总数最多6000，不含来源标题开销 |
| 顺序 | 逐题交替先执行RAG3/RAG4，减少固定顺序影响 |
| 新增Embedding | 0，使用冻结的历史检索结果 |

HTTP超时按连接/读取阶段生效，600秒是新请求准入期限，不是操作系统强制杀进程期限。不是40次失败后无限续跑。服务商模型内部版本和随机种子未固定；同参复跑不保证逐字一致，也没有重复采样的统计置信度。

## 实际结果

- 总耗时241,324ms，包含失败请求；不包含历史向量构建，不作为线上端到端延迟。
- 40次尝试、39次可用，q19/RAG4/slot37为连接协议错误，19,160ms，未取得正文和用量；不能推断服务商是否已经计费。
- 服务商已报告prompt_tokens=75,320、completion_tokens=7,016、total_tokens=82,336。失败请求用量未知，货币费用未知，不能把这个总数当作全部计费总量。
- 独立人工评分0，语义正确率和引用支持率未知，不能报告缺口4/4通过。
- 生成过程中未改变执行代码；结束后复验执行代码、三份PDF、原缓存报告和原三论文任务摘要全部一致。

完整请求/原文证据/回答/错误/用量/耗时保存在已忽略的 `backend/data/literature-answers-20261110/`，输出目录不可覆盖。公开 [逐题结果](../backend/evaluation/results/literature_answers_20261110.json) 保留39份原始正文、1次失败、实际输入来源索引/文档/PDF页码及来源身份；不把模型生成的参考来源清单当权威页码。另见 [来源及测试核对](../backend/evaluation/results/literature_answers_checks_20261110.json)。

## 可审阅交付与R55入口

`backend/data/literature-answer-review-20261110/` 已生成：

- `review.md`：全部20题双组原文及每个实际输入片段，正文和引用以代码围栏呈现，模型文本不会变成可执行HTML。
- `answer-00.json` 至 `answer-39.json`：绑定manifest和原报告摘要的独立产物；失败也保留。
- `rag3-annotation-pending.json`、`rag4-annotation-pending.json`：分别20份和19份真实正文，绑定各自artifact摘要。`abstained=null`和空claims表示待标注，明确不能直接通过R55类型或评分；没有猜测模型是否拒答、自动拆分声明或仅挑正确声明。

下一步在新标注文件中逐项列出所有事实声明、实际引用原文与页码，判断拒答；保留原答案正文与产物摘要并对照原产物，不能重写答案后仍沿用旧摘要。之后用R55准备工具校验原文引用、生成独立人工审阅模板。R55不会认证人工身份或自动确认产物声明完整性，独立审阅须覆盖原始整份回答。q19仍缺可用正文，即使其余答案审完，RAG4本次运行也不能全部通过；后续重跑须另定预算、新目录，并保留本次失败作为统计分母。

## 开发观察：不是人工金标

从实际输出发现以下失败候选，登记供下一次改动回归，尚未作独立评分：

1. q09：两组都错误地把DPR表述为问题/段落拼接。RAG4还把实际FiD的第4条输入来源归给DPR；该输入明确写着FiD的passage/title/question拼接。需要修复主体归属，不能仅看引用编号存在或字符串重合。
2. q12：两组的DPR索引生命周期描述超出已提供来源；RAG3声称预训练/微调都固定索引，所引片段不能建立该结论。不得把REALM有刷新机制反推DPR的所有阶段。
3. q20：RAG3先承认无Qwen3信息，随后用DPR的NQ 41.5替代回答；RAG4明确无法判断。仅可作为缺口题改进候选，不能据此认定4/4或总体收益。
4. q03：两组都未回答100词/无重叠的已知细节，保留为共同的证据覆盖缺口，不能把拒答当作正确事实题答案。

q09/q12是在本轮之后为**下一次**实验登记的失败案例，不追溯声称本轮已完成“预登记的两个跨文档失败修复”。优先修复归属与超出证据的推断，保留RAG3默认路径；不通过增加索引设施、放宽核验或追加提示协议掩盖错误。

## 文件、测试与复现

新增 `scripts/evaluate_literature_answers.py`（freeze_inputs/run）、`scripts/export_literature_answer_review.py`（export_review）和 `tests/test_literature_answers.py`；没有新增生产接口、依赖或数据库迁移。密钥沿用用户授权的进程环境或本地笔记，仅存在内存，不写请求manifest、结果或日志。

在 `E:\RAG4\project\backend` 的Python 3.11环境执行；以下输出目录必须不存在，真实复跑会产生新的模型调用：

```powershell
python scripts/evaluate_literature_answers.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --cached-report data/literature-pilot-v1/run-qwen8b-20261012-attempt2/report.json --report-sha256 ff2d80b89c5e506bd4d8b0a9f3eb933e0972efb426d6107c19665cefe779b88e --model-task data/research-paper-retry-20261108/research_18e5ac69ce68573054a1ac4e.json --task-sha256 d7a8c66148929a7f7d27724f4c2c60ad70e84f4497d88af2ce33384851b4e4fe --output data/literature-answers-new
python scripts/export_literature_answer_review.py --run data/literature-answers-20261110 --output data/literature-review-new
python -m pytest tests/test_literature_answers.py tests/test_literature_acceptance.py tests/test_literature_pilot.py -o addopts='' -q --tb=short
```

最终 **66 passed /12.16s**，包括新增23项及R55/旧检索评测回归。首轮合成PDF过短导致结构片不足10条，调整为足够长的合成文档；随后修复Windows测试读取UTF-8问题。全部HTTP测试为合成响应、0外部请求。覆盖无标签泄漏、与旧提示格式一致、来源变更、40次上限、错误保留、无重试、超时/连续失败/授权错误停止、运行中和摘要冲突拒绝导出、待标注不能评分及原始产物保全。未声称后端全量或端到端Agent验收。

R40–R56工作区改动与用户artifacts保留，尚未提交/推送。
