# R43：隔离浏览器与真实 HTTP 研究闭环

日期：2026-11-06。承接R40–R42未提交代码，先核对Git状态、真实接口、SQL/索引夹具和模型契约，再补齐此前浏览器拦截API留下的集成验证缺口。保留用户 `artifacts/`，不访问业务MySQL或模型API。

## 实际交付

新增 `frontend/e2e/research-live.mjs`：自动创建全新临时目录，启动独立Python服务与Vite代理；浏览器不使用 `page.route()`、不注入localStorage或测试JWT，实际填写登录表单，所有研究API经Vite→Uvicorn→FastAPI→SQLite/LocalVectorStore。第二个账号使用独立浏览器上下文真实登录验证隔离。

新增 `backend/tests/support/research_live_server.py`：在任何app导入前固定独立SQLite、上传/向量目录、测试密钥和不存在的ENV_FILE，拒绝非指定前缀、非空或不存在的根目录。只绑定127.0.0.1随机端口；用合成TXT文献准备保留版本，active不变。测试模式只存在于独立脚本，不添加生产测试路由或切换生产默认值。

生成适配器使用真实 `JsonResearchModel` 和 `httpx.MockTransport`，返回确定性合成wire JSON，继续走解析、引用身份、facet核验、条件策略、SQL检查点与ArtifactComposer。Embedding为脚本内确定性适配器，原上传基线使用已有DEV_MOCK_AI。阻止测试服务进程连接非回环地址；不加载业务.env、提供商凭据或调用远程模型。该适配器不是语义模型，其supported判断不能用于论文质量验收。

通过目录内停止标记让Uvicorn正常退出后写审计，再停止本次Vite进程；保留每次临时SQLite、上传文件和向量数据用于检查，不删除或重用数据库。启动/场景/审计失败返回非零并保存失败记录，不把此前通过的浏览器断言当整轮成功。`backend/tests/test_live_fixture_safety.py` 覆盖3类不安全根目录拒绝且旧数据不变。

## 真实 HTTP 验证结果

最终新目录完整运行 **7组检查通过**：

1. 浏览器真实登录→本人保留版本与3篇文献→目标→后端计划预览→确认创建pending，初始调用计数0。
2. 11次显式单步POST完成SQL任务（revision22、工具11、生成模型6），生成3条方法引用和9个缺口；页面原文与后端Artifact引文逐字一致。TXT无页码，显示“页码未记录”。
3. 已完成任务以旧revision0再请求执行返回409，不追加执行。
4. 另一个真实登录账号目录和版本列表为空；本人以外的任务详情、run、partial-artifact均404。
5. 匿名真实HTTP任务查询和run均401。
6. 第二个任务在第三篇核验中注入一次确定性ReadTimeout，经真实模型错误/工具/SQL路径保存failed（revision18、工具9、生成模型6），保留两份核验报告；部分稿显示2条引用/10缺口，完整Artifact仍未附加。
7. 只修改该独立临时目录内首篇来源文件，刷新部分稿真实HTTP400，页面不再显示旧引用或旧原文。

退出审计确认：两个SQL任务状态与上述一致，原3条上传基线及全部保留版本向量摘要不变，active仍 `[null,0]`。12次**本地模拟**Completion尝试（其中1次注入失败），9批本地Embedding（含3批构建），远程提供商调用0。这不是在线模型用量或费用。

初次6组通过后补齐匿名检查、保留向量摘要、退出状态与失败报告断言，最终7组通过；两次使用不同全新目录，不累计为13组用例。桌面完整产物/原文与失败部分稿截图已检查。截图、完整审计及临时目录位置在忽略目录 `frontend/e2e/shots/research-live/`，公开摘要见 [R43验证记录](../frontend/e2e/results/research_live_http_20261106.json)。

## 命令与环境

```powershell
cd E:\RAG4\project\frontend
node e2e/research-live.mjs
npm run lint
npm run build

cd E:\RAG4\project\backend
& C:/Users/gy/.conda/envs/rag4-py3.11/python.exe -m pytest tests/test_live_fixture_safety.py tests/test_research_run_revision.py tests/test_research_preview.py -o addopts='' -q --tb=short
```

默认现有Conda Python路径和本机Chrome；可用 `RAG4_TEST_PYTHON` 指定Python、`CHROMIUM_PATH`或`RESEARCH_BROWSER_CHANNEL`指定浏览器、`RESEARCH_TEST_PORT`指定Vite端口（默认5181）。后端绑定回环随机端口，Vite代理只指向本轮服务。所有依赖沿用现有requirements/package-lock，无新增依赖。

最终后端相关 **40 passed /83.28s**，其中新增3项根目录安全门禁；前端 `npm run lint`、`npm run build` 通过。R42历史97项及29个拦截浏览器场景属于前轮证据，本轮未重跑这些全量范围；真实HTTP7组也不与pytest40项混称一个测试数量。

## 边界与下一步

R44后续：已在真实三论文新副本运行浏览器/硅基流动有预算验收，第二次查询Embedding连接超时，首败即停、0生成，未完成研究或语义验收；同时修复未核验单元格误示缺少证据。详见 [真实验收记录](research_real_paper_acceptance.md)。以下保留R43当轮边界。

这是合成资料/模型下的真实浏览器HTTP契约和持久化闭环，覆盖LocalVectorStore和临时SQLite；不是业务账号、MySQL/Chroma生产部署、真实论文语义或真实模型可用性验收。没有实现暂停/恢复/取消界面、自动后台执行、断网恢复或新质量策略；R37精确根因及人工语义门槛仍未通过。

下一步优先把现有用户路径用于真实论文的有预算验收，逐条检查结论和来源，记录缺口与费用/错误；不因合成流程通过宣布研究质量达标。受控恢复只在确认旧执行已停止的明确场景中做有界入口，不自动续跑预算耗尽任务，也不继续扩建索引/队列。R40–R43尚未提交或推送。
