# Phase 2.2：独立候选索引构建与验证

本切片从 Phase 2.1 的完整 ChunkSet 开始，冻结远程 Embedding 调用配置，写入独立 staging Collection，回读全部记录验证后保存 manifest。`validated` 不是 `active`，当前在线上传和问答仍沿用原流程。

## 服务入口

```python
from app.services.index_build_service import EmbeddingSpec, create_build, run_build, get_build

spec = EmbeddingSpec(
    endpoint="https://api.siliconflow.cn/v1/embeddings",
    model_id="Qwen/Qwen3-Embedding-8B",
    version="siliconflow-qwen3-8b-v1",  # 调用方显式命名，不推断厂商权重版本
    dimension=4096,
)
build = create_build(user_id, chunk_set_id, spec, idempotency_key="paper-attempt-1")
result = run_build(user_id, build.id, api_key=key_from_secure_config)
assert result.status == "validated"
```

`EmbeddingSpec` 为冻结的 Pydantic 模型，包含 provider、endpoint、model_id、version、dimension、timeout_seconds。仅支持 remote，API Key 只作为执行参数存在于内存；不持久化到任务或 manifest。不会读取运行时可变模型配置，也不会受 DEV_MOCK_AI 影响；测试通过注入 Adapter 工厂模拟模型输出。

调用方必须提供已认证 user_id。暂未开放 HTTP 管理接口；这些接口供后续索引编排服务调用。

## 状态、验证与失败边界

- `document_index_builds` 保存不可复用的 staging 命名空间、ChunkSet ID、模型配置、幂等键、状态、错误阶段/分类、时间、耗时和验证 manifest。
- `pending → running → validated/failed`。同键同请求返回原 build，冲突拒绝；同 build 只抢占执行一次。重试用新键，生成独立 namespace。
- 写入前拒绝非空 namespace，拒绝数量不符、维度不符、NaN/Infinity、非数值和全零向量。
- `BaseVectorStore.read_records` 在 Local/Chroma 中提供完整回读，不使用 top-K 近似检索代替验证。比较全部 ID、数量、文本、来源 metadata、维度和向量值；Chroma float32 回读使用有限误差容忍。
- 验证 manifest 保存 chunk/input/parser/chunking/tokenizer/engine/model 身份、片数、维度和 ID 摘要；只有验证成功且 SQL 事务提交后才成为 validated。
- 写入中途失败、回读不一致、SQL 发布失败均不激活，旧索引不变。失败 namespace 保留用于诊断，重试不覆盖它；暂未实现垃圾回收。
- MySQL 发布与文档删除使用同一文档行锁，远程模型调用在锁外完成。删除文档清理相关 build 和全部版本向量。SQLite 不提供 FOR UPDATE 行锁，尚不承诺跨进程删除与构建的完整并发语义。

## 数据库与真实验证

已有库先执行 `migrations/002_chunk_preparation.sql`，再执行 `003_index_builds.sql`，仅增加表。开发 `init_db()` 可建新表。旧全量初始化脚本含 DROP DATABASE，不用于升级。

真实测试脚本：`backend/scripts/validate_index_staging.py`。运行前在当前进程环境设置 `RAG4_TEST_MYSQL_PASSWORD`，可选设置 `RAG4_TEST_MYSQL_HOST` / `RAG4_TEST_MYSQL_USER` / `RAG4_TEST_MYSQL_PORT`。端口默认 **3307**（本机 MySQL 8.4.9，RAG4 主开发实例）；兼容性测试可显式指定 3306（MySQL 5.7.44）。从 backend 执行：

```powershell
python scripts/validate_index_staging.py --credentials-file 'E:\RAG3\提示.txt'
```

脚本固定调用 SiliconFlow 官方 API；仅使用生成的合成文本。创建并保留唯一命名的验证数据库和临时文件目录，不修改已有业务库、不删除数据库。API Key 从本地文件提取，不打印；数据库密码不写脚本。

本轮已在实际 MySQL **5.7.44-log** 上验证两份迁移重复执行，以及 MySQL → ChunkSet → SiliconFlow Qwen3-Embedding-8B → Chroma → 回读验证：1 个合成子片、4096 维，validated，构建耗时 3750ms，旧 baseline 记录保持不变。这里的时间是单次功能检查，不是性能基准。之前观察到的 MySQL 8.4.9 是客户端版本。

## 下一步与限制

Phase 2.3 已引入用户级 manifest/文档覆盖集合和 active 指针：完整候选通过验证才事务切换，查询使用对应模型快照，保留旧版本以供回滚。详见 [激活接口](index_activation.md)。单文档 staging 不能直接替代用户全部文档 Collection。

还需处理构建后数据变化及删除的再次验证、上传增量合并、批量任务、取消、租约恢复和存储位置绑定。当前只验证构建完成时的状态，不能保证 validated Collection 之后未被外部修改；激活前必须重新验证。远程模型别名可能被厂商更新，本地权重指纹和跨部署执行环境冻结尚未实现。

本轮没有新增依赖，也没有修改业务库的在线模型设置、激活指针或默认切分器。
