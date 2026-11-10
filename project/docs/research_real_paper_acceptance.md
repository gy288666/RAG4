# R44：真实论文有预算验收与未完成核验提示修正

日期：2026-11-06。承接R40–R43未提交变更。保留用户artifacts、R37失败任务与已成功核验报告，使用现有DPR/FiD/REALM PDF和保留索引的**新SQLite/向量副本**，浏览器真实登录、预览、创建一个新任务，未恢复旧任务或更改其预算。

## 本轮范围与结果

先测试验收专用的提供商白名单/预算守卫，再运行一次真实硅基流动窗口：最多3次查询Embedding HTTP请求、8次Completion请求，HTTP自动重试0，首个工具失败停止。凭据只从进程环境或用户已授权的本地提示文件载入，不打印、不写SQL/报告、不传命令行；未读取业务.env或访问业务MySQL。

实际浏览器创建 `research_18e5ac69ce68573054a1ac4e`，冻结三篇真实PDF、comparison-v2/local-window-v3/source-role-v3、facet-handles-v5/preceding-children-v1/explicit-row-v1。使用当前创建页的text响应格式；不是对R37 json_object输出做严格单变量对比。模型配置为Qwen/Qwen2.5-7B-Instruct，但**本轮未进入生成请求**，不能宣称该模型当前连接或语义质量通过。

| 观察 | 实际结果 |
| --- | --- |
| 浏览器登录/版本选择/目标/预览/新任务创建 | 真实HTTP完成，无API拦截或登录态注入 |
| DPR查询Embedding | HTTP200 /5244ms，返回166 total_tokens，检索步骤完成 |
| FiD查询Embedding | ConnectTimeout /5042ms，无usage；工具含来源/上下文开销8057ms |
| 请求总数 | 2次Embedding（1成功1失败），0次Completion；停止后未追加请求 |
| 新任务 | failed /revision4，工具2次、生成模型0次，1/11步骤成功 |
| 新研究成果 | 0声明/0引用，12待核验单元格；没有完整Artifact或语义审阅对象 |
| 费用 | 未返回货币费用，失败请求usage未知；不能将0次生成等同于总费用0 |

只说明当前窗口中Embedding存在一次成功和一次连接超时，不能判定APIKEY无效、所有模型不通、代理有错或全站不可用。未修改系统代理、网络默认值、生产超时或默认策略。R37历史ValueError根因仍未知。

审计确认旧任务payload、原task.json、原SQLite文件、原向量和副本向量摘要、active状态均未改变。PDF来源绑定在创建/执行/部分稿读取时继续验证。完整新检查点、请求用量/耗时/错误类型和执行源码SHA保留于忽略目录 `backend/data/research-paper-browser-20261106/`；浏览器截图和汇总在 `frontend/e2e/shots/research-paper/`。公开摘要见 [R44验收记录](../frontend/e2e/results/research_paper_acceptance_20261106.json)。

## 由真实失败发现并修复的问题

失败后原页面将没有完整核验报告的单元格渲染成“未检出证据”。本例尚未完成检索/抽取，不能据此推断论文缺少证据。新增浏览器回归先失败（预期12个“未完成核验”，实际0），随后修正 `ResearchPage`：对于部分稿的 `unverified_documents`，未支持的单元格显示“未完成核验”，原因明确“尚无完整核验报告，不能据此判断论文是否报告相关内容”。

有已保留核验报告的文献继续按其原状态显示，已有受支持引用不删改。只调整用户可见解释，不重写Task、VerificationReport或Artifact。新增场景使用一致的0引用/12缺口响应，防止把未运行流程测试成语义失败。

## 新增代码与接口

- `backend/scripts/research_acceptance_guard.py`：`AcceptanceTransport`，仅允许HTTPS硅基流动两个指定POST端点，锁内保留独立全局请求配额，失败也计数；记录状态/白名单usage/耗时，不存正文、Authorization或错误原文。
- `backend/scripts/serve_research_acceptance.py`：显式 `--allow-live`，新目录、只读SQLite backup和向量副本、固定回环服务；复制环境登录口令只在新副本设置。共享HTTP Client和零重试Transport仅作用于本脚本，不修改生产Adapter。验收结束保存审计和新任务，不删除旧数据。
- `frontend/e2e/research-paper.mjs`：必须显式 `--allow-live`，浏览器驱动当前用户路径；只读GET观察处理浏览器超时，不重发POST，失败停止。Node退出码0只表示观察/保全断言通过，**task_completed=false才是本轮研究结果**。
- `backend/tests/test_acceptance_guard.py`：13项，端点范围、非法预算、网络失败消耗配额、用量白名单、敏感信息不入账本、并发配额。
- `frontend/src/pages/ResearchPage.tsx` 与 `frontend/e2e/research.mjs`：未完成核验标签及新增回归；未改其他生产逻辑、依赖、schema、Graph或训练代码。

## 命令与验证

```powershell
cd E:\RAG4\project\backend
& C:/Users/gy/.conda/envs/rag4-py3.11/python.exe -m pytest tests/test_acceptance_guard.py tests/test_live_fixture_safety.py tests/test_research_run_revision.py -o addopts='' -q --tb=short

cd E:\RAG4\project\frontend
node e2e/research.mjs
npm run lint
npm run build
```

后端 **31 passed /31.76s**，新增13项；前端**13场景通过**（新增1项先红后绿），类型检查/生产构建通过。真实失败页面与修正后的回归截图已检查。未重跑全量后端、R43模拟HTTP7组或完整创建/执行浏览器组，保留历史记录，不混称本轮全量。

本轮在线命令如下；**不要直接重跑**：原输出目录存在会拒绝覆盖，新的显式预算窗口必须使用新目录并记录原因，本轮首败即停。

```powershell
cd E:\RAG4\project\frontend
node e2e/research-paper.mjs --allow-live
```

默认Python/Chrome沿用R43；`RAG4_ACCEPTANCE_OUTPUT`可指定全新输出目录，`RAG4_EVAL_API_KEY`可在内存设置。此脚本不纳入默认测试命令或生产启动；计数上限不是货币金额上限。

## 限制与下一切片

R45后续：已补网络失败的严格恢复准入、失败快照保留和两步确认界面，并通过离线/隔离HTTP回归，见 [恢复记录](research_explicit_retry.md)。本轮未在线恢复R44、未续跑R37，以下为R44当轮边界。

真实研究任务未完成，未产生可逐条做语义复核的新结论，人工支持率/缺口金标准仍未验收。浏览器失败路径已被真实验证，不把网络失败当作成功研究成果，也不把模拟模型断言充作语义证据。

下一片先基于这份已终止、来源和预算均保留的失败检查点，设计显式恢复入口的离线准入/并发回归：确认旧执行已结束，不重置预算，不自动重试、不续跑预算耗尽历史任务；在线恢复另开明确有限窗口。不能因本次连接超时扩建索引或调度平台。R40–R44尚未提交或推送。
