# R46：真实三论文有界恢复完成与来源复核

日期：2026-11-08。承接R45恢复入口，在R44失败任务的新副本上通过浏览器真实登录/核对/确认恢复，未改变原SQLite、JSON、PDF或索引，未续跑R37旧任务。没有因任务能运行就扩建索引/队列。

## 本轮结果

从R44 `failed/revision4` 经受保护retry接口准备为 `pending/revision5`，保留原DPR成功检索、证据束、2次工具尝试和完整失败快照；预算仍13工具/8生成/6000字符。随后只从失败的FiD检索继续，最终 **completed/revision25**，累计工具12/13、生成6/8、retry_events=1。余下10步骤全部成功，三份文档核验报告和最终比较表已持久化。

独立窗口限制2次查询Embedding、6次Completion，HTTP重试0、首败即停。实际8请求均200：Embedding用量332 tokens，Completion用量31318 tokens，总计31650 reported tokens；金额费用未知，不把token数视为金额。HTTP耗时合计136301ms，剩余步骤窗口186714ms（首个重试步骤started_at到compose finished_at），不等于含启动/人工复核的整轮墙钟耗时。旧R44失败请求不计入该新窗口用量，也不从任务预算中抹除。

模型仍Qwen/Qwen2.5-7B-Instruct，原text格式、facet-handles-v5、preceding-children-v1和explicit-row-v1不变。无需重新抽取PDF、重算文档Embedding或重跑DPR查询。原任务/数据库/向量与副本向量摘要、active均保留；新副本任务变化是此次显式恢复的预期结果，不能再要求副本自身parent_task_unchanged=true。

## 质量观察：执行完成，语义门槛未通过

抽取12条，机器核验放行4条、8缺口；REALM数值结果因遗漏CC-News被条件门禁阻止。DPR/FiD各1条、REALM2条机器支持。本轮新REALM报告通过批次身份/条件覆盖检查，R37历史ValueError没有复现，但旧响应缺失，不能据此宣布原根因修复。

使用PDF技能、Poppler渲染原始DPR第2/4页、FiD第3页、REALM第2/8页并核对引用，主Agent复核原放行4条：DPR方法、FiD方法和REALM数据集可由绑定引用支持；REALM方法中“优化边缘似然训练检索器”的部分不在所选PDF8引用中。在线核验器仍放行，是引文覆盖不足的错误接受。该事实在论文别处存在，不能替代原引用本身的覆盖。

原SQL、核验报告和Artifact完整保留；另交付[保守审阅稿](../backend/evaluation/results/research_recovery_reviewed_20261108.md)，暂留3条/9缺口。复核者仍是Agent，**不是独立人工支持率或金标准**。DPR数据集和REALM局限还存在疑似误拒，不能只提高拒绝率就算修复。

冻结一组相同REALM方法陈述、不同引文的正负诊断Claim：原PDF8绑定为负例，使用已有PDF2机制引用生成候选正例并重算Claim ID。两者经现有 `frozen_corpus/load_claim_file` 校验范围/原文区间/身份成功；未追加模型请求、未附到原Task，不当作新线上成果。来源与许可、期望标签限制见审阅稿。

## 新增/修改入口

- `scripts/serve_research_acceptance.py`：提取acceptance_options/acceptance_paths；新增显式retry-copy、简单快照文件名及独立2/6请求上限，旧新建模式默认保留。输出目录不能与输入相等/嵌套/包含输入，数据库只读backup到全新目录；恢复仍由浏览器调用生产retry API完成，服务启动不自动恢复。
- `frontend/e2e/research-paper.mjs --allow-live --retry-copy`：只针对R44实验副本，真实登录、核对恢复条件、确认pending，验证预算/原成功步骤/BundleRef/失败快照保留后逐步执行。超时只读GET观察，不重发POST；完成/首败停止，独立保存审计及截图。
- `tests/test_acceptance_options.py`：11项路径/预算/模式边界回归；结合原预算守卫和恢复/执行回归验证。
- `evaluation/results/research_recovery_method_{negative,positive}_20261108.json`：两份可供现有claim-file诊断CLI使用的严格Claim数据，无APIKEY；没有修改生产核验协议或训练逻辑。
- README、计划、基线、开发过程和MVP状态同步；无新依赖、业务库操作、迁移或默认策略切换。

## 实际命令与测试

```powershell
cd E:\RAG4\project\backend
& C:/Users/gy/.conda/envs/rag4-py3.11/python.exe -m pytest tests/test_acceptance_options.py tests/test_acceptance_guard.py tests/test_research_explicit_retry.py tests/test_research_run_revision.py -o addopts='' -q --tb=short

cd E:\RAG4\project\frontend
node --check e2e/research-paper.mjs
node e2e/research-paper.mjs --allow-live --retry-copy
```

后端相关 **59 passed /53.51s**，其中新增11项；首次路径/预算预检24项先通过才开始在线窗口。Node语法检查、真实浏览器恢复和来源保全断言通过；诊断两Claim的离线来源校验通过。没有更改生产TS/界面，所以不重复构建或全部浏览器组；R45的121项/37浏览器场景/8合成HTTP组为历史记录，不混称本轮执行。未跑后端全量、业务MySQL部署或正式微调。

完整任务/比较表/审计/原PDF渲染保存在忽略目录 `backend/data/research-paper-retry-20261108/`，浏览器截图和调用记录在 `frontend/e2e/shots/research-paper-retry/`；公开摘要见 [R46验证记录](../frontend/e2e/results/research_real_recovery_20261108.json)。原R44/37实验保持原状。输出目录已存在，不能重复本命令覆盖或追加请求；新请求必须是另一个明确有界窗口。本轮不再发模型请求。

## 下一片

现在可以把主线从连通性/恢复转回研究质量：使用冻结的REALM引用覆盖正负对，以及DPR数据集、REALM局限疑似误拒正例，定位核验失败原因。保留未改动的模型/提示词基线，不继续盲目叠提示词、切模型或扩建索引。任何策略修改先离线回归，再用同一小组有限请求验证，不能把同一陈述换引文后直接复用旧supported verdict。

完整研究工作区、生产调度、人工语义质量、独立评测冻结和正式训练仍未验收。R40–R46尚未提交或推送。
