# R40：已有研究任务的最小阅读入口

日期：2026-11-04。起点：`main / a945864`，R34–R39 已推送。本轮继续计划第 3.4 节的用户读取路径，不扩建索引平台。用户原有未跟踪 `artifacts/` 保留。当前代码尚未提交或推送。

## 实际交付

新增受现有登录保护的 `/research`、`/research/:taskId` 和“研究阅读台”导航。左侧分页查询本人任务，右侧显示真实保存的目标、状态、revision、文献数和计划/步骤。比较表区分已有结论、待核验、未检出与冲突；失败任务仍显示失败，不把部分产物算作完成或人工质量通过。

失败且尚无完整核验/产物的任务使用 R39 的授权只读部分稿接口，附 `expected_revision`。来源改变或版本冲突时显示错误，不退回展示旧稿；刷新先清空旧任务、部分稿和原文，切换任务时取消旧请求并忽略迟到响应。已有完整产物作为保存时快照显示，与本次来源复验的部分稿明确区分。

引文入口显示保存的原文、PDF 页码/章节、切片和字符区间。原文用 React 文本渲染，不解释 HTML 或 Markdown。打开后聚焦原文区域，关闭后恢复引文按钮焦点。移动端比较表局部横向滚动。没有假数据注入生产页面，没有声称具备 PDF 整页查看能力。

## 接口与文件

- 后端 `app/research/store.py`：列表增加可空 `goal_preview`，最多 160 字符。先校验 payload 摘要及 ID/owner/status/revision，再取目标；损坏记录只隐藏摘要，详情继续执行完整校验。不返回 checkpoint 正文、不追加逐行详情查询、不改表结构。
- `frontend/src/types/research.ts`：只读 `ResearchSummary/List/Task/Step`、`ResearchArtifact/Claim/Source` 和 `PartialArtifactView` 类型。
- `frontend/src/api/research.ts`：`listResearchTasks`、`readResearchTask`、`readPartialArtifact`，仅 GET，复用 JWT/Envelope 和 AbortSignal。
- `frontend/src/pages/ResearchPage.tsx`、`src/styles/research.css`：目录、步骤、比较表、缺口和原文区域；`App.tsx`、`components/AppLayout.tsx`、`components/Icons.tsx` 接路由和导航。
- `backend/tests/test_research_goal_preview.py`：新增 5 项，覆盖本人/他人范围、长度、损坏摘要/JSON/身份和不修改任务。
- `frontend/e2e/research.mjs`：新增独立浏览器回归，自动启动/停止自己创建的 Vite 进程。默认现有 Chrome，可用 `RESEARCH_BROWSER_CHANNEL` 或 `CHROMIUM_PATH` 指定浏览器，端口可由 `RESEARCH_TEST_PORT` 修改。

## 实际验证

```powershell
cd E:\RAG4\project\backend
& C:/Users/gy/.conda/envs/rag4-py3.11/python.exe -m pytest tests/test_research_goal_preview.py tests/test_research_agent.py tests/test_partial_artifact_api.py -q

cd E:\RAG4\project\frontend
npm run lint
npm run build
node e2e/research.mjs
```

后端 **40 项通过**（包含 5 项新增），退出码 0；当前 pytest 配置不打印耗时摘要，本轮不补造秒数。前端类型检查、生产构建通过；**12 个浏览器场景通过**：真实失败任务/精确引文/步骤/焦点、手机布局、来源变化、409 刷新与新 revision、空目录、401、匿名路由、已完成快照、HTML 转义、分页不逐行请求详情、目录失败重试、任务切换竞态。每个浏览器场景断言只发 GET 且无未捕获浏览器异常。初次启动缺少 Playwright 配套 Chromium，改用本机已安装 Chrome 后通过，无新依赖或下载。

浏览器以保存的 R37 Task、R39 PartialArtifactView 为响应基础，**拦截 API，不是生产账号浏览器联调**；异常/分页/竞态场景显式修改测试响应。两条方法结论、10 个缺口及原文由真实快照提供，未证明语义正确。R39 的真实 HTTP 权限/来源验证保持独立证据，不混称本轮浏览器实时访问业务库。

已检查桌面、手机、原文截图；输出在忽略目录 `frontend/e2e/shots/research/`，可由测试复现。公开验证摘要见 [R40 测试记录](../frontend/e2e/results/research_reading_20261104.json)。没有运行全量后端或旧在线模型 E2E；没有访问业务 MySQL、模型 API、切换 active、迁移数据库或新增依赖。

## 限制与下一入口

2026-11-05 R41交接：下述创建前置已核实并补齐文献选择、后端预览及确认创建pending任务，见 [R41记录](research_task_creation.md)。R40以下段落为当轮边界；执行、完整工作区和人工质量仍未完成。

这是 Phase 6 的只读第一片，不是完整研究工作区：没有创建/选择论文/执行/暂停按钮、自动进度推送、整页 PDF 阅读器和完整产物编辑。空业务库不会导入实验副本冒充用户成果。

下一片按计划补“选择本人已保留版本的 3–5 篇论文→研究目标→预览受控计划→显式创建 pending 任务”，复用现有创建契约。前置条件是核实文档与保留版本发现接口、本人范围、预算与策略默认值；创建与模型执行分开，先做可审阅计划及权限/版本测试，再接显式有界执行。不要把前端按钮当作可靠后台调度，不自动续跑预算耗尽的 R37 任务。

Phase 1–5 的人工语义质量门槛仍未通过，R37 ValueError 精确根因仍未知；诊断随合法有限预算执行捕获。Neo4j、生产调度、正式微调和上线验收仍待完成。
