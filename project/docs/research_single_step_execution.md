# R42：显式单步执行与状态核对

日期：2026-11-06。承接R40–R41未提交变更；保留用户 `artifacts/`。本轮在阅读台接一个可验证的执行切片，不扩展索引、计划协议或后台队列。

## 核对结论与接口

原 `ResearchAgent.step` 在执行前通过SQL revision CAS领取，工具执行不持有SQL事务；已有running步骤拒绝重复领取，暂停/取消造成revision变化后迟到工具结果不能发布。中断会留下可见的running步骤，不具备可靠自动恢复。

发现CAS不足以阻止顺序到达的旧页面请求：第一请求完成后，第二请求可能读取新revision并领取下一步。为此新增可选 `expected_revision` 检查，位于加载任务后、预算领取和上下文/模型初始化前。新浏览器每次点击都发送所见revision，旧revision返回409，无工具或生成模型预算消耗。

`POST /api/v1/research-tasks/{id}/run` 现在可接 `{ "expected_revision": 0 }`。字段必须为非负严格整数，拒绝未知字段。无请求体保持既有客户端行为；新客户端必须自行选择发送revision，旧路径没有该顺序重放保护。仍要求JWT和本人任务范围。`ResearchAgent.step(..., expected_revision=None)` 向后兼容；CLI无需变更。

## 前端行为

新增 `ResearchExecutionPanel`，显示下一步骤、工具和生成模型已用/上限、上下文预算。只有pending或running且无正在运行步骤、存在下一步且预算足够时提供“执行下一步”。一次点击只发一个POST，本地同步锁防连点，服务端revision/CAS防跨请求重放；没有循环或自动重试。

执行成功后重新读取任务/目录，继续使用已有步骤、错误类型和耗时显示；用户再次点击才执行下一步。409、超时或网络错误时禁用本地重试，要求先点“核对最新状态”；若GET返回running步骤，继续阻止重复执行。刷新/切换任务清理页面状态，离页后的迟到POST响应不会更新新页面；服务端已领取的请求可能继续执行，离页不等于取消。

页面明确提示可能调用Embedding或生成模型并产生费用。生成模型计数为既有Completion尝试预算，不包含Embedding请求；不把工具数或模型数当作货币费用。failed/paused不提供恢复按钮，预算不足不追加预算，completed/cancelled不提供执行入口。

## 实际修改

- `backend/app/research/agent.py`：可选expected_revision及领取前冲突检查。
- `backend/app/api/v1/research.py`：严格RunRequest及可空请求体兼容。
- `backend/tests/test_research_run_revision.py`：顺序重放、并发占用、取消后迟到结果、真实HTTP字段/旧客户端兼容，共15项（API在Local/Chroma各测）。
- `frontend/src/components/ResearchExecutionPanel.tsx`、`src/pages/ResearchPage.tsx`、`src/api/research.ts`、`src/types/research.ts`、`src/styles/research.css`：单步入口、预算契约和提示。
- `frontend/e2e/research-run.mjs`：隔离Vite/Chrome浏览器执行状态测试；更新README、计划、基线、开发记录和MVP边界。

## 验证

```powershell
cd E:\RAG4\project\backend
& C:/Users/gy/.conda/envs/rag4-py3.11/python.exe -m pytest tests/test_research_run_revision.py tests/test_research_preview.py tests/test_research_runtime.py tests/test_research_agent.py tests/test_research_goal_preview.py tests/test_partial_artifact_api.py -o addopts='' -q --tb=short

cd E:\RAG4\project\frontend
npm run lint
npm run build
node e2e/research-run.mjs
node e2e/research.mjs
node e2e/research-create.mjs
```

新增后端首轮15 passed /34.25s。浏览器新增8场景通过：一次点击一次执行/无自动循环、新revision下一次手动执行、409需刷新、网络结果不明确且running禁止重试、离页迟到响应、预算不足、paused不隐式恢复、桌面/手机布局（部分断言合并在同一场景）。阅读12及创建9场景回归通过。新执行/创建场景为明确的合成拦截API；阅读使用R37/R39真实冻结响应。不是浏览器直连业务库或真实模型研究验收。桌面/手机截图已检查，输出位于忽略目录 `frontend/e2e/shots/research-run/`。

最终后端相关 **97 passed /195.61s**，包含新增15项及R40/R41/原运行/读取/部分稿回归，退出码0；不是全量后端。前端类型检查和生产构建通过，执行8 + 阅读12 + 创建9，共29个浏览器场景通过；最后文案明确“生成模型”计数后，再次执行8场景及类型/构建通过。未访问业务MySQL或模型API，无新增依赖、迁移或推送。公开摘要见 [R42测试记录](../frontend/e2e/results/research_execution_20261106.json)。

## 限制与下一步

2026-11-06 R43交接：隔离浏览器→真实HTTP→SQLite/保留Local索引已验证，见 [R43记录](research_live_http_acceptance.md)。合成资料/模拟模型不代表业务库、真实论文或语义质量通过；以下为R42当轮边界。

没有后台调度、自动中断恢复或暂停/恢复/取消界面。原控制API的逻辑屏障不等于终止外部模型调用；恢复前必须确认旧执行已停止，本轮不提供可能引起重叠调用的恢复按钮。revision不是持久幂等键；网络结果不明确必须重新读取状态，不能自动重发。

下一片优先做隔离环境的浏览器→真实HTTP→SQL/保留索引闭环，使用已有无外部模型的测试适配器，核对登录、创建预览、单步执行和来源读取之间的契约；不导入实验数据到业务库。之后再按实际中断证据设计受控恢复入口。人工质量门槛、R37错误根因、完整工作区和上线验收仍未完成，不能因按钮已接通标记Phase1–5质量通过。
