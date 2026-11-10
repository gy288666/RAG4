# R53：审阅稿导出与原机器稿对照

日期：2026-11-09。本轮完成从“审阅结论”到“保存可追溯研究结果”的用户路径，不增加模型或索引设施，不修改后端生产接口/数据库。

## 用户可完成的操作

completed 任务的阅读台新增“保存研究结果”：

- **当前审阅稿（Markdown）**：只包含仍可见的结论和引用，撤下单元格标为“已撤下”，不插入撤下理由或历史中可能重复的旧表述。
- **审阅记录（JSON）**：保留完整 review_view，包括原结论、已撤下材料、理由/时间/事件链；文件明确标为审计记录，不能当当前比较稿。
- **原机器稿快照（Markdown）**：位于可展开的“与原机器稿对照（含已撤下内容）”下，单独文件名和警示，保留原始机器结论用于对照，不是当前审阅稿。

页面同时展示原稿/当前稿结论数、原表述和当前审阅状态。导出只包含**已保存**状态：未提交的表单决定不会被自动保存或混入文件，下载后未提交的输入仍留在表单内。

每个下载前都以 view.task_revision 重新 GET review，执行既有任务/原稿/事件/表格一致性检查，并核对确定性 view_id 未变。409、来源变化、网络失败或返回不一致停止下载、隐藏不确定比较表并要求显式核对。离开任务会取消读请求，迟到结果不在新任务发起下载。

保存和导出互斥：写入未结束不能下载，准备下载期间不能提交审阅。导出只有GET复验和本地Blob下载，不创建任务、不POST新事件，也不执行Agent/模型。原稿及服务端记录不改。

## 文件身份和内容规则

新增纯函数 `buildReviewFile(task, view, kind)`，kind 为 reviewed/audit/original，返回 name/type/content；同一快照和种类重复调用得到相同字节，没有客户端当前时间造成的随机差异。

文件采用 research-review-export-v1，带 task/revision、corpus、review_view、原稿与派生Artifact身份、annotation_status 和 quality_gate_passed=false。revision 是导出复验时的任务版本，不意味着原机器稿重新生成。文件名包含任务、revision及reviewed/review-audit/original-machine，不使用文献标题作路径。

Markdown 从结构化 rows/citations/items 生成，**不使用存储的 artifact.markdown**，防止旧字符串把已撤下结论带回。结论/引用绑定和表格一致性再次核对；当前稿的引用只从可见声明产生。来源包含原文片段、PDF页码、ChunkSet、chunk和字符范围；完整SourceLocator及章节信息可在审计JSON中追溯。

目标/标题/表格文字进行HTML/Markdown转义；原始引文放入动态长度代码围栏，源文中的反引号不能关闭围栏。引用内部文本保留，不把文献/原因里的HTML当作页面执行。文件名仅使用受限字符并有固定前缀。身份元数据采用JSON代码块，避免Markdown转义使ID难以精确复制。

原稿Markdown是结构化机器快照的安全重排，不承诺与后端旧Markdown格式逐字节相同。审计JSON不是完整任务/数据库备份，不含模型凭据或可还原原PDF的全部数据；它明确可能包含已撤下材料。个人审阅仍不等于独立人工质量标签。

## 实际修改文件

- `frontend/src/utils/reviewExport.ts`：确定性文件构造、范围/引文检查、Markdown安全与文件名。
- `frontend/src/components/ResearchReviewExport.tsx`：新导出区、原稿对照、下载前复验、取消/失败屏障及Blob回收。
- `frontend/src/components/ResearchClaimReviewPanel.tsx`、`pages/ResearchPage.tsx`：读写互斥和通用“当前审阅结果待核对”提示，复用原审阅/来源流程。
- `frontend/src/styles/research.css`：现有tokens上的轻量布局，保留原纸面/深绿、6px圆角和8px间距。
- `frontend/e2e/review-export.unit.mjs`：通过既有TypeScript编译器转译纯函数，10项测试，无新增测试依赖。
- `frontend/e2e/research-review.mjs`：新增6个导出浏览器场景；`research-live.mjs` 增加真实下载/读回JSON检查。
- 公开验收JSON、本页及根README/计划/基线、development_process/research_backend_mvp 同步交接。

## 验证结果

在 `E:\RAG4\project\frontend`：

```powershell
npm run lint
npm run build
node --test e2e/review-export.unit.mjs
node e2e/research-review.mjs
node e2e/research.mjs
node e2e/research-run.mjs
node e2e/research-live.mjs
```

类型/构建通过，**10项导出单元测试**、**54组浏览器检查**通过（审阅/导出16、阅读13、执行15、真实HTTP合成文献10）。新增6个导出场景覆盖三类文件实际内容/文件名、未保存输入不入稿、400/409不下载、离页迟到不下载及读写互斥。单元首轮9项中1项发现元数据ID转义问题，改为JSON代码块后通过；后补文件名/状态检查，共10项通过。

真实浏览器无API拦截，经正常登录/Vite/Uvicorn/隔离SQLite：withdraw后实际下载Markdown，断言被撤下的合成声明不再作为结论/引用输出，view_id和revision可追溯；reset/retain及刷新后导出JSON，读回3条完整事件。原机器Artifact、预算/已用计数、baseline/retained vectors/active不变。外部提供方调用0；整套fixture研究执行使用本地确定性transport，审阅和导出不增加模型/Embedding调用。

公开命令范围、各场景、源码摘要和server audit见 [R53验收摘要](../frontend/e2e/results/research_review_export_20261109.json)。原三论文数据只作为R51冻结来源重建的浏览器契约输入；真实HTTP本轮使用合成文献，不能称真实论文新模型评测。未跑后端全量、未重跑R51/R52历史后端测试；后端生产源码和原R46输入摘要保持不变。

桌面/手机导出截图已检查，沿用frontend-design-taste清单，无致命项；截图留在本地忽略目录 `frontend/e2e/shots/research-review/export-comparison.png`、`export-mobile.png`。无依赖安装、业务MySQL、真实源PDF/向量/任务改写、训练或GitHub推送，用户artifacts保留。

## 限制、回退与下一交付

当前仅completed审阅视图导出；失败部分稿导出/可写审阅未扩展，导出也不替代PDF/Word正式出版格式。下载后文件可被使用者修改，内容身份是追溯标识，不是数字签名；来源检查完成后的未来并发变化不会追溯修改已下载的版本化快照。

回退为移除导出界面，现有审阅读取和所有事件仍保留，无迁移回滚或删数据。下一片收口研究工作区生命周期：核对并接入现有暂停/继续/取消接口及状态反馈，保留预算和迟到结果屏障，避免只展示状态却无法完成操作。真实评测冻结、独立人工质量及部署回滚验收仍未完成；不因导出功能通过而晋级R49模型协议。
