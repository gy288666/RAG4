# R45：已结束网络失败的显式恢复准备

日期：2026-11-07。承接R40–R44未提交代码，保留用户artifacts。只实现“核对恢复条件→确认恢复为待执行”，不自动运行、不追加在线预算、不修改R44真实失败任务或R37旧任务。

## 问题与范围

原Agent已有CAS领取、显式control及迟到结果屏障，但暂停/恢复只改变状态，不能据此证明旧本地调用已经退出。直接把旧resume接到界面可能造成重叠请求。本轮新增保守路径，旧control/CLI接口继续兼容，不宣称它们获得了新的恢复保证。

新路径仅接收failed、恰有一个已结束失败步骤、无running/cancelled未完成步骤、失败为明确网络错误，且剩余工具/生成预算足以覆盖**全部剩余计划**的任务。时间字段必须可解析、有时区且结束不早于开始；不会用“等几秒”作为终止证明。未分类RuntimeError不放行，只有其本次持久化模型调用记录明确失败且为网络错误时才识别。

执行历史还必须满足 `revision == 2 * tool_calls_used + len(retry_events)`：正常步骤领取/结束各一次CAS，恢复准备一次CAS。额外旧control、无法解释的checkpoint写入或中断历史会破坏关系并被拒绝。这里依赖当前固定计划和SQL写入协议，不是通用进程探测或租约；宁可拒绝旧记录，也不猜测其旧调用状态。

**本地尝试已结束不代表供应商已经停止计算。** 超时后再次执行仍可能重复计费，界面在确认前明确提示；恢复准备本身不发模型/Embedding请求。旧运行中、paused、预算耗尽、语义/协议错误与历史不明任务均不自动恢复。

## 接口与状态

- `GET /api/v1/research-tasks/{id}/retry`：JWT本人范围，no-store，返回不可变 `RetryDecision`（任务/revision、eligible/reason、失败步骤ID、剩余/所需工具与生成预算、sources_validated）。状态/历史准入先于向量后端初始化；准入成功后复验原文件、索引、ChunkSet和任务快照，不读模型凭据。
- `POST /api/v1/research-tasks/{id}/retry`：严格非负整数 `expected_revision`，重新执行准入和来源检查后CAS；过期/不允许409，来源失效400/404，其他用户404、匿名401。仅改为pending、清空该失败步骤的当前结果/时间，计数、预算、声明、证据束、成功步骤和文档核验报告保持不变。
- `RetryEvent`：保存失败revision、当时调用计数和完整失败ResearchStep快照；`ResearchTask.retry_events` 最多24条。空历史不输出该字段，保持历史序列化和旧检查点身份。失败诊断不会因重置步骤而消失。
- 前端：失败任务先“核对恢复条件”，显示将准备的具体步骤及全部剩余预算。只有同任务/版本、来源已验证的可用决定才显示“确认恢复为待执行”；恢复后刷新，不自动POST run。历史尝试可展开查看。双击锁、版本冲突、来源变化和离页迟到响应均保守处理。

读取视图与提交均前后检查可观察来源变化；不声称跨PDF文件/向量/SQL的一次分布式事务。恢复后的执行仍走原完整来源复验。pending期间不继续显示旧failed部分稿，底层成功核验与失败记录均保留。

## 实际代码

- `backend/app/research/recovery.py`：RetryDecision、准入、retry_candidate纯转换。
- `backend/app/research/tasks.py`：RetryEvent与可选序列化历史；`agent.py` 校验历史与固定计划一致。
- `backend/app/research/runtime.py`：read_retry、retry_failed及无模型来源复验；`api/v1/research.py` 两个受保护路由。
- `frontend/src/types/research.ts`、`src/api/research.ts`、`components/ResearchExecutionPanel.tsx`：类型、请求与两步确认界面。
- `backend/tests/test_research_explicit_retry.py`：新增20项，覆盖预算/历史/来源/权限/CAS/完整失败快照和成功报告保留。
- `frontend/e2e/research-run.mjs` 新增7场景（共15）；`e2e/research-live.mjs` 扩展为8组真实HTTP检查；`backend/tests/support/research_live_server.py` 增加恢复历史审计。阅读/创建脚本仅补充失败截图与定位信息，阅读可按 `RESEARCH_TEST_CASE` 缩小范围、以 `RESEARCH_TEST_DIAGNOSTICS` 输出上下文边界，不放宽超时或鉴权。

无新依赖、数据库表/迁移、默认模型/策略变更、索引重建或调度。

## 验证及真实检查点观察

```powershell
cd E:\RAG4\project\backend
& C:/Users/gy/.conda/envs/rag4-py3.11/python.exe -m pytest tests/test_research_explicit_retry.py tests/test_research_agent.py tests/test_research_run_revision.py tests/test_research_runtime.py tests/test_partial_artifact_api.py tests/test_research_verification_batches.py tests/test_research_checkpoint_recovery.py tests/test_failed_partial_export.py -o addopts='' -q --tb=short

cd E:\RAG4\project\frontend
node e2e/research-run.mjs
node e2e/research.mjs
node e2e/research-create.mjs
node e2e/research-live.mjs
npm run lint
npm run build
```

后端 **121 passed /174.46s**，新增20项；非全量。旧检查点空历史序列化保持，连续两次网络失败后恢复仍可在原预算内完成；legacy控制历史、无结束时间/非法时间、running、语义错误、预算不足、来源变化、他人和重复并发提交均覆盖。

执行/恢复15、阅读13、创建9个拦截浏览器场景最终通过；真实HTTP扩展8组通过。后者用全新临时SQLite/Local索引、合成TXT和MockTransport：先观察failed/revision18保留两报告，恢复仅属于夹具的来源文件原始字节后显式核对/确认，最终pending/revision19，工具9/生成6未变、2份报告和原失败快照完整保留，run请求数仍20，未因恢复增加任何模型/Embedding尝试。原基线、保留向量和active不变，远程提供商调用0。桌面、手机及真实HTTP恢复截图已检查。

浏览器首批并行验证出现登录/首屏导航与元素等待超时，一条读取夹具进程长时间未退出，仅终止已核实属于本轮的进程及其子进程。按diagnosing-bugs缩小到首场景、增加失败截图/URL/错误/请求路径和上下文边界日志；缩小场景与独立完整重跑均通过，未定位稳定根因，不能声称修复了登录或Chrome问题，也没有靠增加超时或自动重试掩盖。最终创建9场景亦独立通过。该环境不稳定性保留为验证限制。

离线读取真实JSON作纯准入检查，未进行来源API复验或SQL恢复：

| 检查点 | 决定 | 工具剩余/所需 | 生成剩余/所需 |
| --- | --- | --- | --- |
| R44新任务 revision4 | available（sources_validated=false） | 11/10 | 8/6 |
| R37旧任务 revision24 | unaccounted_history，拒绝；预算也不足 | 2/3 | 0/1 |

本轮没有发硅基流动请求，没有更改真实失败任务或原数据库。公开命令/结果见 [R45测试记录](../frontend/e2e/results/research_retry_20261107.json)。截图/完整合成运行审计在忽略目录 `frontend/e2e/shots/`；临时库保留。最终类型检查和生产构建通过。

## 限制与下一片

R46后续（2026-11-08）：R44新副本已由真实浏览器核对/恢复并在原预算内完成，2查询/6生成全200；原输入不变。机器4条支持中1条被Agent来源复核撤下，质量未通过。见 [R46记录](research_real_recovery.md)，以下保留R45当轮边界。

只支持能证明当前本地尝试已经终结的网络失败准备；旧control历史、paused、崩溃留下running和任意协议/语义错误没有通用恢复入口。不能证明供应商停止计算，不能保证货币费用上限，不能通过该接口增加预算或覆盖产物。

下一片可在新副本上针对R44这一已结束任务另开明确有限在线窗口，从失败步骤继续，保留DPR成功检索/已有预算和全部失败记录；先执行准入/来源复验，首败即停，不自动续跑R37耗尽任务。真实生成、逐项来源语义质量和人工验收仍未完成。R40–R45尚未提交或推送。
