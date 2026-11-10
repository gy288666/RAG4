# R41：保留文献选择、计划预览与显式创建

日期：2026-11-05。继 R40 只读阅读台，补齐“本人保留版本→选择3–5篇文献→研究目标→后端校验/计划预览→确认保存pending任务”。保留前轮未提交代码及用户 `artifacts/`，本轮未提交或推送。

## 设计与实现

复用已有 `/index-versions` 分页和详情；它们只表示历史清单完整，不表示当前来源或向量仍可用。页面禁选清单损坏和不足三篇的版本，选择后显示该版本文献。没有自动激活、重建或导入实验库。所有来源在预览和创建时继续由既有 `_load_scope` 校验本人归属、ChunkSet、文件SHA和向量版本。

新增 `POST /api/v1/research-tasks/preview`，请求使用既有创建字段，返回稳定预览身份、目标、来源标题、固定步骤、预算、计划版本和模型名。no-store，预览不保存SQL任务，不调用模型或Embedding。`prepare_task` 从原创建流程提取，预览/创建共享来源和计划/预算验证；`task_preview` 对排除随机任务ID的完整草稿做确定性SHA256摘要。

原创建接口增加可选 `expected_preview_id`，不传时保持旧客户端兼容。新页面必须提交预览摘要；创建重新构建并验证草稿，目标/来源/配置/策略/预算不匹配返回409且不写任务。摘要用于一致性检查，不是授权凭据或幂等键；本人权限检查不会省略。来源失效返回400/404。创建只存pending/revision0，调用计数为零。

前端新增 `/research/new`，阅读台提供“准备新研究”。修改目标或文献立即使预览失效，旧请求被取消，迟到响应不显示；重复点击创建由同步锁和禁用控件拦截。创建成功跳回任务详情。409要求重新预览；其他失败清空预览并提示先检查任务列表，不自动重复POST。尚无持久化创建幂等键，网络响应丢失时不能保证跨页面重新提交只创建一次。

新页面显式使用既有受控试验策略：comparison-v2、local-window-v3、source-role-v3、source-handles-v2、facet-handles-v5、preceding-children-v1、explicit-row-v1，response_format=text。未更改旧API默认策略。按文献数由服务端提供默认预算：最多工具 `max(12, 3*n+4)` 次、模型 `max(8, 2*n+2)` 次，上下文6000字符；失败/重试仍占预算。这些策略尚未通过人工质量验收，页面明确提示。

## 文件与入口

- 后端：`app/research/runtime.py` 的 `prepare_task/task_preview/create_task`；`app/api/v1/research.py` 的预览路由、共享请求映射和确认摘要字段；`tests/test_research_preview.py`。
- 前端：`src/pages/ResearchCreatePage.tsx`；`src/types/research.ts` 新增版本/草稿/预览类型；`src/api/research.ts` 新增版本读取、预览/创建请求；`App.tsx` 路由、`ResearchPage.tsx` 入口、`src/styles/research.css` 表单样式；`e2e/research-create.mjs`。
- README、开发计划、基线、开发过程及后端MVP同步记录当前边界；没有新依赖、表结构迁移、业务MySQL操作、模型探测或默认切换。

## 验证方式

```powershell
cd E:\RAG4\project\backend
& C:/Users/gy/.conda/envs/rag4-py3.11/python.exe -m pytest tests/test_research_preview.py tests/test_research_runtime.py tests/test_research_agent.py tests/test_research_goal_preview.py tests/test_partial_artifact_api.py -o addopts='' -q --tb=short

cd E:\RAG4\project\frontend
npm run lint
npm run build
node e2e/research-create.mjs
node e2e/research.mjs
```

浏览器使用现有Chrome、拦截API：创建测试是明确的合成契约响应，读取回归使用R37/R39真实冻结响应，不冒充浏览器直连业务库。创建场景覆盖显式预览/一次提交、编辑失效、至多五篇/空目标、409不自动重试、空版本、来源失败、迟到预览、手机布局；断言无run请求和浏览器未捕获异常。截图在忽略目录 `frontend/e2e/shots/research-create/`，已检查桌面和手机。

最终后端相关 **82 passed /172.45s**，其中新增预览/创建11类用例在Local/Chroma各运行一次，共22项。覆盖稳定预览且无写入、摘要确认的pending创建、目标/预算/模型改变409、来源改变400、重复/不足/越界范围、不足预算、匿名401和他人（包括管理员）404；原运行/读取/部分稿回归同时通过。首次新增测试20项通过后补了他人权限回归，最终以上述82项为准，未执行全量后端。

最终 `npm run lint` 和 `npm run build` 通过；新增 **9个创建浏览器场景通过**（包含文献详情读取失败后重试），原阅读台 **12场景通过**，合计21场景，不能与后端用例混称一个全量测试数。桌面选择表单、预览和手机截图已检查。公开命令与结果见 [R41验证摘要](../frontend/e2e/results/research_creation_20261105.json)。

## 当前限制和下一片

2026-11-06 R42交接：已接显式单步执行/预算与手动刷新，新增revision检查防旧页面顺序重放，见 [R42记录](research_single_step_execution.md)。下述为R41当轮边界；受控恢复、真实浏览器HTTP联调及质量仍未验收。

没有执行、暂停/恢复/取消控件或后台调度；没有承诺创建幂等性、生产部署或完整研究工作区。历史清单可能在预览时失效，页面必须展示失败，不能退回旧数据。R37错误根因和人工语义质量门槛仍未解决，创建一个pending任务不意味着生成研究成果。

下一片仅在新pending任务上接显式、一次一步的有界执行与状态刷新，复用现有run/control和冻结预算；先核对跨请求并发、用户离页/请求超时的状态读取与恢复规则，再提供会调用模型的按钮。不得自动续跑旧预算耗尽任务或把浏览器循环当作可靠后台队列。业务账号浏览器联调与人工逐项来源审阅分别验收。
