# 真实文献检索试点 v1

本目录固定 DPR、FiD、REALM 三篇正式论文及 20 道中文问题：8 事实、6 比较、2 多跳、4 证据不足。来源、作者、出版信息、CC BY 4.0 许可依据及比较限制见 [来源注记](../../docs/research_corpus_sources.md)。标注是 AI 草稿，尚待人工复核；多跳题的预期答案包含明确标识的工程推断，不是原论文实测。

`literature_pilot_v1.json` 固定官方 URL、PDF 摘要、页数、证据页和短锚点。机器定位时允许空白、大小写和 Unicode NFKC 连字差异，但映射回原解析文本的字符区间；一页出现多次的歧义锚点会被拒绝。页码为 PDF 文件内从 1 开始的页序，不是会议印刷页码。

## 实际范围

2026-10-12 的首轮只比较现有 `split_blocks` 与 `ChunkingEngine` 的纯证据检索。复用同一 PDF 解析输出、Embedding 模型、问题向量和 LocalVectorStore 余弦检索；字符预算 600，旧重叠 60，新父片预算 1800，新子片不重叠。策略包含重叠差异，不能把结果变化归因于单独的父片效果。PDF 当前按页扁平解析，没有伪造标题、表格或版式结构；首轮没有 Reranker、LLM 回答、父片展开或 Graph/Agent。2026-10-13 新增的独立实验见下文，不改写首轮结果。

主要指标是 `anchor_span_recall`：Top-K 所有命中的原文区间合并后，完整覆盖了多少标注锚点。按文档、页及字符范围比较，避免不同 chunk ID 造成不可比；重复命中不增加覆盖，跨页同词不算命中。另记录满足全部所需锚点的题数。短锚点覆盖不能证明引用支持结论，不报回答正确率或 nDCG。4 道证据不足题保留检索结果，但排除正例覆盖指标，拒答能力标为未评测。

## 复现

在 backend、Python 3.11 环境执行。PDF、向量及完整原文候选放在已有忽略规则覆盖的 `backend/data`，不要放进业务上传目录或 artifacts 中。先下载三份官方 PDF 到新目录：

```powershell
$pilotSourceDir = Join-Path (Get-Location) 'data/literature-pilot-v1'
New-Item -ItemType Directory -Path $pilotSourceDir -ErrorAction Stop
$pilotDefinition = Get-Content evaluation/literature_pilot_v1.json -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($pilotPaper in $pilotDefinition.papers) {
    Invoke-WebRequest -Uri $pilotPaper.pdf_url -OutFile (Join-Path $pilotSourceDir $pilotPaper.file_name)
}
```

已存在资料时跳过下载；执行器在任何模型调用前核对 PDF SHA-256、页数和全部锚点。官方文件变化会拒绝旧版本，不覆盖或悄悄接受新的文献。

由当前终端或启动进程注入 `RAG4_EVAL_API_KEY`，不写入定义、结果或源码。首轮默认沿用项目的 Qwen/Qwen3-Embedding-8B / 4096 维；服务地址固定为硅基流动。每批 16，超时 30 秒，最多 80 次调用，每批仅一次尝试，无自动重试。输出目录必须不存在：

```powershell
python scripts/evaluate_literature.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --output data/literature-pilot-v1/run-new
python -m pytest tests/test_literature_pilot.py -o addopts='' -q --tb=short
```

运行会保存输入快照、解析摘要、执行代码摘要、模型身份与预算、切片/原文区间、向量、逐题候选与分数、用量、耗时和最终状态。只使用独立实验目录，不加载或修改业务数据库、管理员配置或 active 指针。失败保留报告和已有候选；模型响应维度错误或非有限/零向量拒绝，不能静默忽略。失败目录不会被成功尝试覆盖。

重跑须使用新目录并记录与旧尝试的关系及剩余预算。v1 实测首轮网络连接失败后，只进行了同模型/同参数的第二轮，两轮共同受 80 次总预算约束。Token 用量按服务返回值记录，货币费用未知，不由耗时推算。

## 后续入口

先人工核对标注与失败上下文，再用一类跨文档证据覆盖失败驱动最小 HybridEvidenceEngine；不能仅据短锚点数值认定需要图谱或模型训练。当前试点不是独立测试集，不能用于证明微调收益。索引激活/回滚的既有合成验收和本试点的纯检索验证是两种证据，本试点不声称完成真实文献的数据库发布闭环。

## 2026-10-13：有界证据与研究任务实验

以下是新实验；不改变上文首轮纯检索口径。接口见 [后端切片](../../docs/research_backend_mvp.md)，结果见 [真实执行报告](../../docs/research_comparison_report.md)。

```powershell
python scripts/evaluate_bounded_evidence.py --help
python scripts/evaluate_research_comparison.py --help
python scripts/replay_research_verification.py --help
```

所有输出目录必须新建且不存在。`evaluate_bounded_evidence.py` 固定旧候选，无模型调用，仅比较同预算父片开关；`evaluate_research_comparison.py` 要求原缓存报告 SHA，隔离 SQLite，核对文档与缓存，在线生成查询及模型抽取/核验，凭据由进程环境 `RAG4_EVAL_API_KEY` 注入。默认模型和预算可从 help 核对；换模型/超时须新目录并明确记录，不作同条件质量对比。`--retry-network-once` 是显式最多一次网络重试，不是默认无限恢复。

当前修复回放的命令（源文件和原任务须先保留）：

```powershell
python scripts/replay_research_verification.py --task data/research-comparison-20261013-attempt6/task.json --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --output data/research-verification-replay-new
```

这是当前数字门禁加旧语义判断的离线回放，不是新的在线核验。公开结果位于 `results/*20261013*`：有界覆盖 41.67%→47.92%、全证据 5/16→6/16；七次在线尝试全部记录，第 6 次旧表存在已知数字错误，第 7 次严格 schema 失败。当前安全部分产物来自单独修复回放，3/6 机器支持、9 缺口，人工门槛未通过。真实关系尚无检索收益证明。

公开 JSON 不含凭据、完整 PDF 或向量；Markdown 导出加出版署名，结构化 artifact JSON 保留 canonical 身份，二者正文不完全相同。MySQL 结果仅证明隔离新增表和 CAS，不代表业务上线。完整失败目录留在已忽略的 `data`，不覆盖、删掉或提交。


## R20：引用编号与缺口诊断

新增实验支持 `--extraction-protocol source-handles-v2 --response-format json_object`，均写入配置/ledger。历史 literal-quote-v1/text 可显式复现。输入最多八条候选，输出仍最多四个 facet；有界接收不是绕过字段/来源/数字/模型核验。当前 [引用修复记录](../../docs/research_citation_fix.md) 提供真实失败、checkpoint 续接和二次 AI 来源复核。在线原始 6/12 机器支持，复核版 4 条、8 缺口；未通过人工门槛，不能当作训练金标签。

`diagnose_evidence_gaps.py --help` 只对原检索候选做 AI 锚点离线诊断，摘要核对和全新输出目录必须满足；无 API/SQL、不向生产传标签。q09 为预算缺口，q12 为候选召回缺口，未标为修复。20261013 的 citation_* 与 evidence_gap_diagnosis_* 是新结果，不覆盖旧七次试验或数字门禁回放。
