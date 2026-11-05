# R39：失败任务部分稿的授权只读接口

2026-11-04。**已将R37部分稿接入正常JWT鉴权的后端读取路径，提供比较表、引用原文和缺口。** 请求不会恢复或完成任务，不调用模型；R37任务仍failed，研究质量门槛仍未通过。

## 用户入口

```http
GET /api/v1/research-tasks/{task_id}/partial-artifact?expected_revision={revision}
Authorization: Bearer <已有登录令牌>
```

expected_revision可省略；传入时必须是当前任务版本。未登录401、禁用用户403、他人的任务（包括管理员访问他人）或不存在任务404（不存在的来源也可能返回404）；非支持状态/版本冲突409；来源或检查点校验失败400。接口目前只接受failed且没有最终verification/artifact的任务；已完成任务继续从原详情接口读取，不重新解释已有最终报告。

使用现有登录令牌的PowerShell示例（令牌只放在当前进程环境，不写入源码）：

```powershell
$partialHeaders = @{ Authorization = "Bearer $env:RAG4_ACCESS_TOKEN" }
Invoke-RestMethod -Method Get -Uri 'http://localhost:8000/api/v1/research-tasks/<task_id>/partial-artifact?expected_revision=<revision>' -Headers $partialHeaders
```

这是新读取接口，研究任务创建/执行/控制和RAG3上传、检索、引用接口不变。没有新增前端页面或业务库迁移。

## 数据结构与共享逻辑

`app/research/partial.py`新增不可变`PartialArtifactView`，并把原脚本中的partial_verification原样移入生产模块；API和CLI通过`build_partial_view(task, corpus)`复用同一审计/产物逻辑。

| 字段 | 含义 |
| --- | --- |
| view_id / view_version | 可重复计算的内容身份与格式版本；不作为授权凭据 |
| task_id / task_revision | 生成该视图所依据的任务与版本 |
| source_task_status | 固定failed，不把部分稿标记为完成 |
| artifact | 原有比较表、知识缺口、核验记录、精确Citation和SourceLocator/页码 |
| markdown | 带“失败任务部分稿”说明的可阅读内容 |
| retained_documents | 已提交核验报告的文档 |
| unverified_documents | 未提交核验报告的文档，结论全部保留为不足 |
| task_marked_completed / artifact_attached_to_task | 固定false；不写回Task |
| quality_gate_passed | 固定false，仍需人工复核 |
| model_calls / embedding_calls | 本次视图读取的调用数，固定0；不清零历史任务用量 |

view_id由完整视图内容计算，格式版本、任务版本和Artifact共同参与；不存在生成时间等随机字段。相同任务及来源重复请求得到相同view_id。原R37Artifact身份和Markdown字节内容均保持一致，未把已有声明重新标成支持。

`PartialArtifactView`不是持久化归档或新Task。`scripts/export_research_partial.py::partial_verification`保留为兼容入口，委托生产模块；原导出脚本改用相同的build_partial_view，不从脚本反向依赖生产路由。

## 授权、来源和只读约束

`app/research/runtime.py::read_partial_artifact`按以下顺序读取：

1. 用当前登录用户加载SQL任务，校验payload摘要/状态/版本；他人、状态不支持或expected_revision不符时，不初始化向量适配器。
2. 从任务冻结的index_version_id读取保留索引、ChunkSet和用户文档绑定，核对文件字节SHA和语料身份；不使用当前active指针替换研究来源。
3. 校验每个成功VerificationBatch，未完成文档全部insufficient；按冻结结果条件策略计算必要的字面审计，ArtifactComposer再次重建来源/审计。
4. 返回前再次核对来源与任务快照，观测到来源变化则拒绝，任务版本/状态变化返回409。

不调用模型配置服务、LLM、Embedding、任务保存、激活或重建。成功响应设置`Cache-Control: no-store`；服务日志记录内容view_id及elapsed_ms，不记录令牌、来源文本或凭据。此机制能发现读取期间观测到的变化，不提供文件/向量/SQL之间的全局原子事务。保留存储、源文件或索引不可用时无法生成该视图，不能把旧引文当作当前来源验证成功。

## 实际HTTP验证

新增脚本在新的SQLite副本中使用R37真实三论文失败任务，不读取模型APIKEY：

```powershell
cd project/backend
python scripts/check_partial_artifact_api.py --source-run data/research-condition-repair-20261104 --vectors data/research-condition-e2e-20261104/vectors --output data/research-partial-api-20261104
python scripts/export_research_partial.py --source-run data/research-condition-repair-20261104 --vectors data/research-condition-e2e-20261104/vectors --output data/research-partial-cli-20261104
```

路径已存在，重放须选择新输出目录。HTTP检查使用TestClient和仅在内存中的签名测试JWT，走真实get_current_user与任务归属检查；在副本中增加另一个测试用户，仅用于他人404验证。未覆盖生产登录流程、服务器部署或业务MySQL迁移。

实际owner=200、anonymous=401、other_user=404、stale_revision=409；两次本人请求view_id一致，no-store生效。仍为两条方法/10缺口；API与CLI的Artifact ID和Markdown完全相等，也等于R37保存的部分稿。原任务JSON/SQL行、向量文件及active指针不变，模型/Embedding调用0。日志中真实数据两次视图生成约3470/3383ms，只是该样本结果，不作为负载性能基线。

## 回归验证及实际文件

新增`tests/test_partial_artifact_api.py`共16项Local/Chroma回归，覆盖本人读取、401/403/404、管理员无越权、无效/冲突版本、来源字节变化/删除、检查点摘要损坏、读取中版本/来源变化、配置/模型适配器不可用、状态/数据不写回和稳定view_id。

实现前首个回归404失败，新增路由及共享模块后20项通过；扩展测试后相关53项通过。最终：

```powershell
python -m pytest tests/test_partial_artifact_api.py tests/test_research_runtime.py tests/test_research_agent.py tests/test_research_verification_batches.py tests/test_failed_partial_export.py tests/test_response_contract_diagnostics.py -o addopts='' -q --tb=short --show-capture=no
```

**102 passed /115.66s**，新增16项，无失败/跳过。该范围覆盖新API和原任务运行/取消/恢复、批次、旧CLI、错误诊断；未重复历史R37完整641项。当前收集694项，不称全部694已全量执行。

实际代码文件：`app/research/partial.py`、`app/research/runtime.py`、`app/api/v1/research.py`、`scripts/export_research_partial.py`、`scripts/check_partial_artifact_api.py`、`tests/test_partial_artifact_api.py`。另外更新CONTEXT、README、计划、基线、开发过程、后端MVP和本记录，保存两份公开结果；无新增依赖、模型调用或数据库迁移。

- [真实任务HTTP鉴权、视图与只读检查](../backend/evaluation/results/research_partial_artifact_api_20261104.json)
- [测试命令、范围和源码摘要](../backend/evaluation/results/research_partial_artifact_api_tests_20261104.json)

## 下一用户路径与未完成事项

下一切片围绕现有登录和API建立最小前端阅读路径：自己的任务列表→任务状态/步骤→失败部分稿→引用原文与缺口，先读取既有任务，不触发新的模型执行。复用现有文档访问能力，保持RAG3页面；不展开全站改版、图谱动画、通用工作流或索引设施。需要在有研究任务的环境验证，不能把本次隔离副本自动导入业务库。

这是Phase 5部分产物的可访问能力，为计划3.4节最小操作入口提供接口；不代表Phase 1–5质量已全部通过。R37 ValueError精确根因、方法语义/引用匹配和人工评测仍待完成；安全诊断随正常有预算执行捕获。研究工作区前端、Neo4j、正式训练、生产部署均未在本轮实现，代码尚未提交或推送。
