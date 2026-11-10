# R55：20 题冻结审阅与离线评分（2026-11-10）

本轮交付可运行的逐题来源核对、冻结审阅包和引用/缺口子门槛评分，不宣称完成真实研究质量验收。没有新增模型协议、索引设施、依赖或数据库迁移。R40–R54 和用户已有文件保留，本轮未推送 GitHub。

## 核对结论

`evaluation/literature_pilot_v1.json` 的三篇论文、20 题及 8/6/2/4 分类已核对。实际 PDF 的 SHA-256、页数和全部标注锚点通过现有解析器校验。标签仍为 `ai_draft`，没有改为人工确认。

近期三论文任务的 12 个比较字段不是这 20 题的逐题答案，所有者审阅也不是独立人工评分。此次未提供逐题答案，因此报告为 `incomplete`、20 题缺答、0 题独立审阅、引用支持率未知。0/4 是本次已确认缺口题的计数，不是模型实测拒答失败率。原真实任务和历史错误保持原记录。

## 接口与文件

- `app/evaluation/acceptance.py`：`Submission`、`Answer`、`Claim`、`Citation`、`Review`、`Judgment` 领域类型；`prepare()` 和 `score()` 离线入口。
- `scripts/evaluate_literature_acceptance.py`：命令行导出 `pack.json`、`review.json`、`report.json`；输出目录必须不存在。
- `tests/test_literature_acceptance.py`：合成输入验证门槛及失败保护；测试人工判断仅用于单元测试，不是实际人工标注。
- 公开真实核对报告：`evaluation/results/literature_acceptance_20261110.json`。完整题目/原文审阅包位于已忽略的 `data/literature-acceptance-20261110-verified/`。

冻结包包含原始题目文件摘要、结构化题目与 AI 参考答案、实际解析文本摘要、执行代码摘要、运行 ID、答案和引用。任何输入或执行代码变化都产生不同包摘要，旧审阅不能复用于新包。不会改写原始题目文件、PDF、任务或 active version。

`Submission` 格式示例（正式输入需覆盖所有 20 题）：

```json
{
  "schema_version": "literature-answers-v1",
  "pilot_sha256": "原始题目文件的64位SHA-256",
  "run_id": "实际运行标识",
  "answers": [{
    "question_id": "q01",
    "artifact_id": "原始导出产物标识",
    "artifact_sha256": "原始产物文件的64位SHA-256",
    "text": "实际回答，不填写参考答案代替运行结果",
    "abstained": false,
    "claims": [{"id": "原始声明标识", "text": "实际事实陈述",
      "citations": [{"document_id": "dpr", "page": 2, "quote": "实际引用原文"}]}]
  }]
}
```

每条发布的事实须列出声明及引用，不能只挑正确声明；拒答使用 `abstained: true`、空 `claims` 和解释缺口的正文。引用按 NFKC 与空白等价检查文档/PDF 页/原文存在性，不把字符串存在当成语义支持。原始 artifact 摘要是提交者声明，执行器不自动读取这些历史导出，正式审阅必须核对原产物，防止漏列错误声明。

## 复现与评分

在 `E:\RAG4\project\backend`、`rag4-py3.11` 环境执行，使用新目录。以下准备命令不填入任何模型答案：

```powershell
python scripts/evaluate_literature_acceptance.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --output data/literature-acceptance-new
python scripts/evaluate_literature_acceptance.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --answers data/answers.json --output data/literature-review-new
```

第二条命令生成与答案绑定的 `review.json` 模板。独立审阅者逐题填写 `answer_correct`、每条 `claim_support`、拒答题的 `gap_correct` 和非空理由，填写审阅者、带时区的时间及 `independent_human_attested`。不能把 AI 填写的判断自报为人工。随后按相同原始输入评分，另用新输出目录：

```powershell
python scripts/evaluate_literature_acceptance.py --pilot evaluation/literature_pilot_v1.json --sources data/literature-pilot-v1 --answers data/answers.json --review data/literature-review-new/review.json --output data/literature-scored-new
python -m pytest tests/test_literature_acceptance.py tests/test_literature_pilot.py -o addopts='' -q --tb=short
```

退出码：Python 子门槛通过为 0，未完成或不通过为 2；非法输入抛错，已有目录拒绝覆盖。PowerShell 启动器可能将非零程序结果包装为命令失败，需查看 JSON 状态。

子门槛要求 20 题实际答案齐全、逐题审阅完整且回答正确；16 道可答题不能全部/部分以拒答规避覆盖；每条声明都有判断；引用支持率用整数比较至少 90%；4 道缺口题必须全部正确拒答。缺失/重复/未知题号、错声明 ID、来源或摘要不匹配拒绝；空理由、未填写或未声明独立人工审阅记为未完成。审阅独立性仅为声明，本工具不能认证人的身份或独立性。

`subgate_passed` 只代表上述子门槛；`quality_gate_passed` 始终保持 false。完整产品验收还须三论文比较表覆盖、同条件 RAG3 对比修复至少两个预登记跨文档失败且事实/拒答不回归、运行预算/用量/耗时记录。开发 20 题已长期用于调试，不能当作独立盲测或微调收益证明。

## 测试和下一步

最终相关测试结果见公开核对报告。覆盖完整/待审/空答案、阈值、错误拒答、错误回答、摘要绑定、源 PDF 变更、页码/原文、重复/外来题号及声明、严格布尔类型、审阅时间和目录保护。未运行全量项目测试；本轮只新增独立离线评测模块，既有线上行为未切换。

下一交付应运行同条件 RAG3/RAG4 的真实 20 题答案并保留失败、成本和原始导出，再进行独立人工审阅。执行前冻结预算；继续使用现有模型配置和已保留语料，不能用手写或 AI 参考答案冒充系统输出。与此同时保留已知 REALM 训练目标错误引用作为必须复核的比较表案例。没有证据时不追加提示词协议、索引功能或训练任务。
