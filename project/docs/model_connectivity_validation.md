# 硅基流动与 MySQL 实际连通验证

本轮按用户授权从本机 `E:\RAG3\提示.txt` 读取 API Key，访问 `https://api.siliconflow.cn/v1`。仅发送短合成英文文本；没有上传用户文档，也没有修改后台模型配置。密钥未写入仓库或输出。

| 模型 | 接口 | HTTP | 有效结果 | 单次耗时 |
| --- | --- | --- | --- | --- |
| deepseek-ai/DeepSeek-V4-Flash | chat/completions | 200 | 非空正文 | 6110ms |
| Qwen/Qwen3-Embedding-8B | embeddings | 200 | 1 条，4096 维 | 3656ms |
| Qwen/Qwen3-Embedding-4B | embeddings | 200 | 1 条，2560 维 | 3469ms |
| Pro/BAAI/bge-m3 | embeddings | 200 | 1 条，1024 维 | 2812ms |
| Qwen/Qwen3-Reranker-8B | rerank | 200 | 2 条排序结果 | 2907ms |
| Qwen/Qwen3-Reranker-4B | rerank | 200 | 2 条排序结果 | 2875ms |
| Pro/BAAI/bge-reranker-v2-m3 | rerank | 200 | 2 条排序结果 | 2813ms |

以上为单次连通性检查，不代表吞吐、检索质量、稳定时延或未来可用性。没有查询余额。

本机 `127.0.0.1:3306` 使用用户提供的账号连接成功，`SELECT VERSION()` 为 **5.7.44-log**；本机安装的 mysql.exe 客户端为 8.4.9。数据库密码未写入仓库。

随后运行 [真实索引联调脚本](../backend/scripts/validate_index_staging.py)，验证 MySQL → 完整 ChunkSet → 项目 RemoteEmbeddingAdapter → SiliconFlow → Chroma → 完整回读验证。成功：1 条合成子片、4096 维、3750ms、baseline 保持不变，重复执行同 build 不再调用模型。

两次脚本运行留下以下独立验证资源，均未删除，也未迁移业务数据库：

- `rag4_staging_validation_c0d597be5788`：首次脚本因 SQL 注释分号拆分错误失败；已修正脚本。
- `rag4_staging_validation_ba7a4dc829c3`：修正后完整成功；002/003 迁移各重复执行两次通过。
- 临时目录分别为 `C:\Users\gy\AppData\Local\Temp\rag4_staging_validation_wsci4vgx` 和 `C:\Users\gy\AppData\Local\Temp\rag4_staging_validation_e2q_w2qk`，仅包含本轮合成资料/向量。

Chroma/posthog 的既有 telemetry 签名日志仍存在，但写入和回读验证通过。本轮未修改该依赖。

## 双 MySQL 实例核对与选型修正

用户指出本机有两个实例后，已分别实际连接确认：

| 端口 | 服务版本 | 服务默认字符集 | 用途决定 |
| --- | --- | --- | --- |
| 3306 | 5.7.44-log | latin1 | 保留旧环境及兼容性验证 |
| 3307 | 8.4.9 | utf8mb4 | RAG4 主开发与真实联调 |

额外核实：RAG3 的本地 `.env` 实际使用 3307/rag_high；RAG4 当前没有本地 `.env`。因此选用 3307 与原项目环境一致，不能从 mysql.exe 版本推断默认端口服务版本，也不能把只查过 3306 当成查完本机环境。

验证脚本增加 `RAG4_TEST_MYSQL_PORT`，默认 3307，连接和 SQLAlchemy URL 都显式带端口。已在 3307 新建 `rag4_staging_validation_9ae02af11c81`，重复执行 002/003 迁移并完成真实 SiliconFlow → Chroma 链路：validated、1 条/4096 维、3625ms、baseline 未变化。验证目录 `C:\Users\gy\AppData\Local\Temp\rag4_staging_validation_93bdsfxk` 和验证库均保留。

两个实例上的现有业务库均未改动。正式 RAG4 应另设专用业务库，并通过 DATABASE_URL 显式指定 3307；本轮仅调整验证脚本默认值，没有修改应用的通用默认连接或写入新的本地凭据文件。

## 2026-09-17：激活、查询与回滚验证

本次 Qwen3-Embedding-8B 在首次及重试中出现 ModelRuntimeTimeout，候选状态 failed，阶段 embedding；没有创建或激活用户级版本。这说明先前 HTTP 200 仅代表当时连通，不代表持续可用。

随后对 Pro/BAAI/bge-m3 进行独立合成文本探测，HTTP 200 / 1024 维 / 5328ms。显式通过验证脚本的 `--embedding-model 'Pro/BAAI/bge-m3' --embedding-dimension 1024` 选择该模型，在 MySQL 8.4.9/3307 上完成 002/003/004 迁移重复执行、候选验证、active 激活、真实查询、切换版本、回滚和停用。结果 `activation_search_rollback=passed`，候选构建 4139ms，baseline 保留。未修改业务默认模型。

本次新增且保留的验证数据库与合成文件目录：

- `rag4_staging_validation_f92491346b0c`：Qwen8B 首次超时；`C:\Users\gy\AppData\Local\Temp\rag4_staging_validation_h6plzyh_`。
- `rag4_staging_validation_dcca3824b113`：Qwen8B 重试超时；`C:\Users\gy\AppData\Local\Temp\rag4_staging_validation_qkvjx444`。
- `rag4_staging_validation_70ff9134b3f7`：BGE 完整通过；`C:\Users\gy\AppData\Local\Temp\rag4_staging_validation_k31u5qz7`。

密码和 Key 均未记录，业务数据库未迁移，验证数据未删除。

## Phase 2.4 批量重建验证

在 3307 新建并保留 `rag4_staging_validation_00fe156e3cc1`，目录为 `C:\Users\gy\AppData\Local\Temp\rag4_staging_validation_epc7k1p2`。002–005 增量脚本重复执行通过。首次完整脚本的候选构建 validated，但在线查询返回 EmbeddingError，该次未算整条通过；脚本随后增加脱敏 cause_type 输出以便区分失败来源。

在同一独立库单独验证新批量接口：`rebuild_18d6216a6e1f09580c51110d`，attempt=1、ready、1 个 checkpoint、5077ms，显式激活/停用通过，baseline 1 条保留。之后再次激活这个批量版本并真实查询，返回合成文档 1 条证据，随后停用。模型为 Pro/BAAI/bge-m3 / 1024 维，未切换业务模型或迁移业务数据库。

## Phase 2.5 中断恢复验证

复用 `rag4_staging_validation_00fe156e3cc1` 和原 Chroma 合成向量，006 迁移重放两次。仅在验证库构造“running 且已有 checkpoint”的中断快照：`rebuild_18d6250442ef5d588bcff42a` 恢复为 `rebuild_18d62504b414cedcf544844c`，原任务 cancelled、续接 ready、1 个 checkpoint、125ms，active 指针保持不变。续接传空 API Key 仍完成，证明没有重复调用模型，而是校验并复用原真实向量。

另用两线程在真实 MySQL 并发恢复 `rebuild_18d6251f0be890488911c070`，均返回同一个目标 `rebuild_18d6251f0e40e1ecb2bcfd72`。未创建新的业务数据库、未强杀进程、未删除验证记录；本轮不需要额外付费模型调用。
