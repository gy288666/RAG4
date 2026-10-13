# Phase 2.3：用户级版本、激活与回滚

本切片在单文档 staging 之上建立用户级完整版本，接入现有问答检索路径。未激活时保持原有配置与 Collection；显式激活后仅检索该版本列出的候选集合，不混入 baseline 或其他版本。

## 接口

```python
from app.services.index_version_service import (
    create_version, active_state, switch_version,
)

version = create_version(user_id, all_validated_build_ids)
previous_version, revision = active_state(user_id)
switch_version(user_id, version.id, expected_revision=revision)

# 回滚到保留的旧版本，仍会检查完整性。
current_version, revision = active_state(user_id)
switch_version(user_id, previous_version, expected_revision=revision)
# previous_version=None 表示退回原上传/检索路径，而不是删除任何向量。
```

所有接口要求调用方使用已认证用户 ID；候选和版本均校验所有权。本轮仅提供后端服务接口，未开放 HTTP 管理接口或前端按钮。

## 验证与切换语义

- `IndexVersion` 保存有 SHA-256 校验的不可变 JSON 清单，包含全部文档、统一 EmbeddingSpec 和每份候选的 namespace/ChunkSet/向量摘要。
- 版本必须覆盖当前用户的全部文档，每份文档恰好一份 validated build，且所有文档 ready。拒绝部分覆盖、重复候选和不同模型配置混合。
- 新构建 manifest 增加完整记录摘要，涵盖 ID、文本、metadata 及 float32 规范化后的向量。激活和检索都重新回读校验。旧版缺此摘要的候选须新建 build，不通过补写摘要把未知状态当成已验证。
- `ActiveIndex` 保存 version_id/revision；切换用 SQL 条件更新检查 expected_revision。`IndexSwitch` 审计记录与指针在同一事务提交，事务失败两者均回滚。
- 成功/失败切换的耗时与错误通过现有 usage_logs 的 index_switch 事件追踪。没有覆盖或删除旧 Collection。
- 回滚与激活使用同一接口和完整性门禁。重复提交旧 revision 会拒绝，而不是静默覆盖其他调用者的操作。

## 在线检索

`rag_service.retrieve` 先调用 `search_active`。没有 active 指针时返回 None，继续原 Embedding/向量检索/Reranker 流程；有指针时使用冻结模型构建查询向量，对清单内各文档候选检索后按分数合并 Top-N，再交给原 Reranker 和引用生成。

API Key 仍来自当前安全配置，不写入版本清单。冻结 endpoint 必须等于当前凭据绑定的 Embedding endpoint，防止把 Key 发送给另一个历史地址；模型 ID、版本与维度来自冻结清单。DEV_MOCK_AI 不会把显式激活的真实版本自动替换为假模型。

一次检索固定读取一个版本，允许并发切换时已开始的请求完成旧快照。查询后再次核对文档集合，避免网络等待期间上传/删除造成悄悄漏文档或继续返回已删除文档。

## 文档变更与限制

本切片尚无增量合并：新增、删除、重命名或非 ready 状态会让 active 检索明确失败，要求创建完整新版本，或显式切换 None 恢复 baseline 路径。原上传接口仍可用，原数据未覆盖；不会隐式切换模型来掩盖版本失配。

本轮保护的是服务管理的文档与向量状态；不承诺对数据库、文件和 Collection 的外部并发篡改提供跨系统原子隔离。原文件磁盘内容被外部替换也不等同于上传了新文档。MySQL 激活读取文档行锁；SQLite 的跨进程一致性仍需后续完善。

为优先保证当前小规模场景正确性，激活和每次 active 查询均完整回读候选，成本与全部切片数量相关。后续需要不可变存储约束、分页验证和缓存策略，不能视作大规模上线性能方案。没有批量任务调度、取消/租约恢复、失败 namespace GC 或 UI。

## 迁移与回退

新增 `migrations/004_active_indexes.sql`，顺序执行 002 → 003 → 004；开发 init_db() 可建表。不执行含 DROP DATABASE 的旧初始化脚本。新增表不要求修改旧表。

停止使用版本化查询可 `switch_version(user_id, None, expected_revision=...)`。代码回退保留新表与候选集合即可；旧引用结构不变。回滚版本要求文档集合仍匹配，否则应先退回 baseline。原路径使用当前运行配置，不能把退回 baseline 等同于恢复一份冻结的 RAG3 配置快照。

真实验证脚本 `scripts/validate_index_staging.py` 已扩展到迁移重放、激活、真实查询、切换旧版本和停用；默认 MySQL 3307，每次只创建独立验证库和合成资料。
