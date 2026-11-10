# R52：阅读台结论审阅交互

日期：2026-11-08。承接 [R51 后端接口](research_owner_review.md)，将完成任务的个人审阅接入现有阅读台。用户现在可以查看审阅状态、核对原引用、填写原因并保留/撤下/重置结论，刷新后继续读取历史。不是新模型语义修复，也不把个人意见当成独立人工评测。

## 实际用户路径

1. 打开自己的 completed 任务，先按任务 revision 读取 review 视图并复验来源。比较表使用派生稿；加载中或核验失败不会回退展示原机器稿。
2. 展开“结论审阅”，逐条查看未审阅/已保留/已撤下；原声明、引用页码/区间在撤下后仍可核对。
3. 选择结论和决定，填写非空白原因，显式保存。请求携带当前 view.task_revision 及 view.source_artifact_id，actor/时间由服务器决定。
4. 成功后更新比较表、详情版本及目录版本，清空结论选择与原因，原机器 Artifact 保留。表格明确标为“已撤下”，不把内部原因代码当用户说明。历史按原记录展示原因与时间，重置不是删除。
5. 400/409、网络不确定或返回身份不一致时，锁定提交并隐藏不确定的比较表；点击“核对最新审阅”重读，不自动重发。离开任务后迟到的结果不更新新任务。

有进行中请求和当前草稿版本两道防重复保护，即使响应很快也不会用未修改的旧草稿再次提交。刷新/离页不声称取消已经发出的写入；未保存输入不跨刷新保留，提交结果不确定时必须先读回历史。

当前仅 completed 原稿支持操作，失败部分稿仍保留原只读路径。新前端要求匹配的 R51 后端；旧服务缺 review 接口时会阻止展示 completed 比较表，而不是偷偷回退到可能已撤下的原稿。

## 返回一致性与展示边界

客户端检查任务、revision、原稿和 corpus 身份；逐项比对原声明/引用、来源所属 ChunkSet、事件历史前缀/顺序/结论绑定和最新状态，核对派生表的可见结论与原表单元格。身份匹配但表述被换掉、审阅状态与事件不符也拒绝展示。前端检查不是签名验证或替代后端权限/来源验证。

原因与引文以 React 文本呈现；包含 HTML 的原因不会执行。错误后不把旧表当成最新审阅展示，也不在保存时增加 Agent 工具/模型调用。初始只读不会发送审阅 POST；所有决定由用户显式触发。

## 界面与实际文件

应用 frontend-design-taste，沿用阅读台的编辑式纸面布局：纸白/深墨/深绿、细分隔线、现有字阶与6px圆角，组件8px节奏；没有新增渐变/卡片栅格/表情图标。撤下状态以文字和边线标识，表单有键盘焦点，移动端无页面横向溢出。已检查桌面、手机及真实 HTTP 截图，无清单致命项。

- `frontend/src/components/ResearchClaimReviewPanel.tsx`：展开式结论清单、原文、历史、表单及提交生命周期。
- `frontend/src/pages/ResearchPage.tsx`：完成任务读取审阅视图、更新版本、来源展示和不确定结果屏障，原失败部分稿路径保留。
- `frontend/src/api/research.ts`：readClaimReview / recordClaimReview / checkClaimReview；`types/research.ts` 增加事件、视图和决定类型。
- `frontend/src/styles/research.css`：局部 tokens、表单/历史/状态及焦点样式，不改聊天/知识库样式。
- `frontend/e2e/research-review.mjs`：10个新浏览器契约场景，使用R51来源重建的拦截响应；生命周期增加有界等待和阶段日志。
- `frontend/e2e/research.mjs`：完成稿回归改为匹配review读取；`research-live.mjs` 增加真实审阅/重载/越权验证。
- `backend/tests/support/research_live_server.py`：隔离验收审计增加审阅事件数，后端生产代码未在本轮改动。
- 公开验收JSON、本页及根README/计划/基线、development_process/research_backend_mvp 更新。

## 验证与证据

前端目录 `E:\RAG4\project\frontend`：

```powershell
npm run lint
npm run build
node e2e/research-review.mjs
node e2e/research.mjs
node e2e/research-run.mjs
node e2e/research-live.mjs
```

类型检查和生产构建通过。浏览器共 **47组**：新增审阅10、原阅读13、执行/恢复15、真实HTTP合成文献9；不是47个独立语义样本。新增场景覆盖快速双击、空白原因、移动布局、400/409、已提交但响应丢失、来源失败、身份/表格/状态不一致、迟到响应和文本转义。

真实HTTP路径为浏览器登录→Vite代理→Uvicorn→新临时SQLite/LocalVectorStore，浏览器无page.route、无注入登录态。先执行合成研究任务，再通过页面withdraw/reset/retain，核对SQL中3条历史、刷新后仍可见、原机器Artifact/预算/已用调用不变、其他账号对review读写404。整套fixture的12次生成由本地确定性transport模拟，**外部提供方调用0**；审阅本身不增加生成或Embedding调用。baseline、retained vectors、active指针均保全。不是三篇真实论文的模型质量评测或用户本人确认。

后端目录额外执行：

```powershell
python -m pytest tests/test_live_fixture_safety.py -o addopts='' -q --tb=short
# 3 passed /3.76s
```

一个并发浏览器尝试出现停滞，没有最终报告，未计入通过数；只停止确认属于本轮的runner/Vite，新增有界生命周期诊断，最终各组串行通过。停滞准确根因未知，不声称已修复浏览器/系统问题。

完整检查范围、源码摘要及live audit见 [R52验收记录](../frontend/e2e/results/research_owner_review_ui_20261108.json)。截图保留在本地忽略目录 `frontend/e2e/shots/research-review/` 和 `research-live/`；不将缺少远程PNG的本地路径冒充GitHub图片。未重跑后端全量或旧R51的171项，R51验证作为历史证据保留。无新增依赖，无业务数据库、原PDF/向量或原真实任务修改，无模型训练或GitHub推送，用户artifacts保留。

## 下一入口与回退

下一片增加当前审阅稿的可追溯导出/原稿对照，重点确保已撤下结论不会因导出原机器Markdown重新出现；仍使用现有数据，不增加模型/索引设施。失败部分稿审阅需要独立设计，不能直接放宽后端状态与历史不变量；完整工作区、独立人工质量及R49协议真实验收仍未完成。

回退界面时保留后端审阅解析器及历史，不能删事件。旧前端若回去展示原机器稿会丢掉当前审阅语义，应停用对应研究展示入口或保留当前审阅读取逻辑，不把原稿当撤下后的视图。
