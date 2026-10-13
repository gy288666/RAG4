# Phase 2.1：持久化切分准备任务

本切片新增后端 Python 服务，不改变上传/检索接口和默认配置。任务 `succeeded` 仅表示完整 ChunkSet 已通过校验并持久化，不表示向量索引已重建或激活。

## 调用入口

从 backend 目录使用项目 Python 环境，应用完成数据库初始化后调用：

```python
from app.chunking import ChunkingConfig
from app.services.index_job_service import create_job, run_job, get_job, load_chunk_set

job = create_job(
    user_id, document_id, idempotency_key="prepare-paper-v2-attempt-1",
    config=ChunkingConfig(chunking_version="rag4-structured-v2"),
)
result = run_job(user_id, job.id)
if result.status == "succeeded":
    chunks = load_chunk_set(user_id, result.chunk_set_id)
    # chunks.parent_chunks / child_chunks 可供后续索引构建使用
```

调用方必须传入已认证的 user_id；服务对任务、文档和结果均检查所有权。没有新增公共 HTTP 路由或自动后台队列。

## 持久化与一致性

- `document_index_jobs` 保存源文件 SHA-256、显式切分配置、用户级幂等键、任务种类、状态、UTC 时间、耗时和错误分类。
- 同用户相同键及相同请求返回原任务；键被用于其他文档/配置时报错。失败重试需新键，不覆盖失败记录。重复键不会重新读取变化后的源文件。
- `pending → running → succeeded/failed`，SQL 条件更新抢占，重复执行返回当前状态。进程退出后的 running 保留用于诊断，尚无租约/自动恢复。
- 执行时复制原文到临时快照并核对摘要，解析的是通过校验的快照；源文件变更拒绝执行。临时快照自动清理。
- `document_chunk_sets` 按内容 ID 插入完整 JSON，包含父片、子片、来源及 parser/engine/tokenizer/config 版本。相同内容复用，既有内容不覆盖；读取时重新校验身份和结构。
- 结果插入与任务成功状态在同一个 SQL 事务提交。失败事务回滚，不更新文档状态或任何向量；失败时保存错误分类，避免持久化异常中的密钥/原文。
- 删除文档会清除这两类附属记录；MySQL 外键支持级联，文档服务也显式清理以兼容未开启外键的 SQLite。

## 数据库升级与回退

开发/测试的 `init_db()` 会创建新表。已有 MySQL 库使用 `migrations/002_chunk_preparation.sql`，先在备份副本演练，再针对明确选定的数据库执行。该脚本仅增加表，可重复执行；不会修复已存在但结构不匹配的表。

**不要使用 `init_db.sql` 升级既有库**：该历史全量初始化脚本包含 DROP DATABASE。新建环境运行全量初始化后仍需执行本增量脚本（或通过应用 init_db 创建）。本轮未连接或迁移用户真实数据库。

代码回退时停止调用新服务并保留新增表即可，旧版本不依赖它们；无需删除数据。没有新增依赖。

## 当前边界与下一切片

Phase 2.2 已新增独立向量 staging 和远程 Embedding 配置快照，Phase 2.3 已增加 [用户级激活与回滚](index_activation.md)。批量调度、取消、恢复和增量合并仍未实现。parser/engine/tokenizer 记录的是执行版本，尚未建立跨部署可重放的执行环境；当前固定使用确定性字符计数器。大文档 JSON 存储会增加 SQL 占用，需要后续容量验证。

`load_chunk_set` 现已接入候选构建服务，完成 staging 验证，并可组装完整用户版本后显式激活。不能直接把切分 succeeded 或候选 validated 当成在线索引可用。
