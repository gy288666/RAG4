# R30：跨论文核验与来源归属阻塞（2026-10-31）

按既定顺序扩展R29的两个REALM案例，固定六条DPR/FiD真实来源正反例，检验遗漏条件、明确局限、复合断言和归属错误。案例仍由Agent编写，论文已在现有语料中；这是跨论文开发验证，不是外部盲测或人工验收。没有修改核验提示词或新增协议。

## 实际代码与测试

原复核脚本新增互斥的 `--claim-file` / `--claim-id`。文件只接受一条既有Claim结构，必须匹配任务文档范围、冻结原文区间和确定性身份，不能带预期标签或伪造引用。原默认、输出上限与调用前后来源守卫保留。

新增 `scripts/evaluate_cross_paper_claims.py`：核对冻结实现摘要，先保存六个案例及字节摘要，再每条调用一次v5。子调用只接收Claim文件，不接收expected/required_checks；新目录复制SQLite、4096输出上限、60秒超时、不重试。所有成功/失败和模型账本分别保留。

新增两份测试覆盖诊断Claim范围与来源、变更身份、保留原引用、冻结六条案例、请求预算、失败保留、实现漂移拒绝及离线评分。最终相关 **45 passed /5.65s**，新增13项；此前39 passed /4.11s为增加评分退出状态之前的结果。

本轮生产研究模块与R28全量通过时摘要一致，只修改诊断脚本和测试，未重跑完整后端。R28的 **509 passed /501.85s** 是历史验证结果，不能写成当前新增用例已全量通过。测试和源码摘要见 [工程验证记录](../backend/evaluation/results/research_cross_paper_tests_20261031.json)。

## 六请求结果

六请求均成功，共8118已报Token，货币费用未知；冻结案例、原文、要求的分项、完整模型输出和调用设置见 [公开评测账本](../backend/evaluation/results/research_cross_paper_20261031.json)。没有追加请求或隐式重试。

| 案例 | 开发预期 | 实际最终判断 | 指定分项 |
| --- | --- | --- | --- |
| DPR：NQ开发集、1,000样本、优于BM25 | 支持 | supported | conditions支持 |
| DPR：删除设置并扩成所有数据集/不受条件影响 | 不支持 | insufficient | conditions不支持 |
| DPR：没有给定段落时SQuAD许多问题缺上下文 | 支持 | supported | conditions/entailment支持 |
| DPR：上述局限推出DPR不能处理任何开放域数据集 | 不支持 | insufficient | entailment不支持 |
| FiD：编码器独立处理、解码器联合处理 | 支持 | supported | attribution/conditions支持 |
| FiD：把“知识全存权重、需数十亿参数”归给FiD本身 | 不支持 | **supported，错误接受** | **attribution错误支持** |

最终及指定分项均为5/6符合开发预期，三个正例均通过，三个负例中错误接受一条。指定分项通过不代表每个分项都可靠；例如DPR复合负例的conditions仍支持，但entailment拒绝了整体结论。不能用最终拒绝数量推断全部分项语义正确。

这次错误接受是新的具体阻塞。R29的两个正反例通过并未证明可靠归属；本轮不能据此接入生产逐条计划、切换默认或宣布Phase1–5质量验收完成。旧比较表不覆盖，诊断子集不拼接成全量产物。

## 离线定位与自动门禁

失败引用从“However, it…”开始；当前核验上下文就是所引子片，缺少it的指代对象。其父片也从这句话开始。离线读取前两个子片，发现其中介绍了Roberts等人（2020）的生成式方法，以及不依赖外部知识的背景方法；三个子片均在PDF第1页。相关原始Chunk、父片、前文及定位区间已存入账本的 `offline_failure_inspection`，没有额外模型调用。

因此，单纯展开父片不能补齐这次前文。下一切片应在冻结语料范围内补充有定位、可追踪的前序上下文，同时保留原引用支持区间；是否能纠正归属还须重新验证，不能只靠文件名、方法名启发式或新增提示词协议宣布修好。

六次实际推断完成后，脚本追加了离线评分入口和明确退出状态：1为请求/解析不完整，2为开发预期或指定分项不符，0仅表示开发案例符合预期，始终不等同人工质量通过。案例重新生成与请求前冻结内容完全一致；原请求脚本摘要和评分后脚本摘要分别保留，提示词、模型、来源及已完成推断未改。

实际运行 `--score-report` 对保存报告得到 `expectation_mismatch`、**退出码2**、额外模型调用0；原报告不写入。这样不能将“六次HTTP成功”误记为语义全通过。

## 复现与后续入口

在 `project/backend`、rag4-py3.11环境：

```powershell
python -m pytest tests/test_cross_paper_experiment.py tests/test_verification_claim_file.py tests/test_verification_single_replay.py tests/test_single_claim_experiment.py tests/test_verification_facets.py tests/test_verification_handles.py -o addopts='' -q --tb=short --show-capture=no
python scripts/evaluate_cross_paper_claims.py --task data/research-citation-handles-20261013-resume2/task.json --database data/research-citation-handles-20261013-resume2/research.sqlite --vectors data/research-citation-handles-20261013-attempt1/vectors --control-tests evaluation/results/research_single_tests_20261031.json --output data/new-cross-paper-run
python scripts/evaluate_cross_paper_claims.py --score-report evaluation/results/research_cross_paper_20261031.json
```

在线模式要求新的输出目录，凭据仅在RAG4_EVAL_API_KEY进程环境中；评分模式不需要凭据。最后一条当前应退出2，是已记录归属错误的可重复反馈，不应改预期让它变绿。

实际修改包括原复核脚本、新评测脚本、两份测试及本页/根计划/基线/README/开发过程/接口说明和两份结果JSON。无新依赖、业务库迁移、索引激活、前端或训练。所有旧数据、实验和用户artifacts保留，本轮尚未提交或推送。


后续R31已实现有定位的前序核验窗口：该归属负例在新窗口下拒绝，旧窗口仍误接受；新窗口的方法正例连接超时。R30旧案例和语义红灯不改，默认未切换；最新实现与限制见 [R31记录](research_verification_context.md)。
