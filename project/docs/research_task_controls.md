# R54：工作区暂停、继续与取消

日期：2026-11-10。复用既有control API及状态机，不改后端生产逻辑，不增加模型调用或调度设施。

阅读台对pending/running提供暂停，对paused提供“继续为待执行”，非终态可明确确认取消。completed/cancelled不展示控制。失败任务没有通用继续按钮，继续走既有恢复准入，避免绕过未知历史/网络失败/预算检查。取消保留步骤和证据，不返还预算。暂停/取消能阻止旧结果提交，不承诺立即中断外部请求。

每次控制携带expected_revision；验证返回任务、revision+1、目标状态和不变的预算/已用计数。双击有in-flight保护；409/网络不确定锁定，要求显式核对，不自动重复。离开任务忽略迟到控制响应。继续只改待执行，不自动运行下一工具。paused剩余预算不足时禁用继续；这只是下一步检查，不保证后续整个计划预算充足。旧控制历史导致失败恢复不可解释的限制保留，未伪装成已修复。

实际文件：frontend/src/components/ResearchControlPanel.tsx、pages/ResearchPage.tsx、api/research.ts；e2e/research-run.mjs及research-live.mjs；本页、验收JSON及根README/计划/基线和开发记录。沿用frontend-design-taste纸面/深绿、现有间距/按钮/焦点，无新依赖或全站改版。

验证命令：

```powershell
# E:\RAG4\project\frontend
npm run lint
npm run build
node e2e/research-run.mjs
node e2e/research-live.mjs
# E:\RAG4\project\backend，Conda rag4-py3.11
python -m pytest tests/test_research_agent.py tests/test_research_run_revision.py -o addopts='' -q --tb=short
```

类型/构建通过；19组执行/恢复浏览器场景通过（新增暂停/继续/取消、409、500和迟到响应4组），后端34 passed /37.02s，覆盖现有取消/迟到结果保护。真实HTTP合成文献11组通过，包括正常登录后的暂停→继续，既有用量仍为0，随后显式执行和审阅流程正常，原稿/向量/active保全，外部提供方0调用。使用隔离SQLite和本地确定性provider transport，非真实模型语义评测。完整范围/源码摘要见 [验收JSON](../frontend/e2e/results/research_task_controls_20261110.json)。未跑后端全量、未直接改写业务库/原PDF/向量，无训练或GitHub推送，用户artifacts保留。桌面截图已检查，界面清单无致命项。

回退为移除新控制界面，已发生状态与记录保留，不还原预算或删任务。下一交付收敛冻结评测与真实研究任务验收，先盘点20题/引用支持率证据和人工标注缺口；不继续无界扩展诊断或索引平台。完整工作区、独立人工质量和部署回滚验收仍未全部完成。
