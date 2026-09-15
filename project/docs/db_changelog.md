# 数据库变更记录

> 基线：`init_db.sql` v1.1（随 requirements_document.md v1.1 发布）

---

## v1.2 — 2026-07-26（实现阶段）

实现过程中发现两处「文档已定义接口、但基线表结构无法支撑」的缺口，做了最小
必要的向后兼容扩展。两项变更均为**新增**，不修改也不删除任何已有字段，
已上线的 v1.1 数据库执行下方 `ALTER` 语句即可平滑升级。

### 1. `usage_logs` 新增 `ref_id`

| 项目 | 说明 |
|------|------|
| **背景** | `api_document.md` 5.7 要求 `GET /api/v1/admin/stats` 返回 `ocr_failed_queue`，其中每一项包含 `doc_id` 与 `file_name`。 |
| **问题** | v1.1 的 `usage_logs` 表只有 `error_message`，没有任何字段能把一条失败日志关联回具体文档，无法生成该队列。 |
| **方案** | 新增可空字段 `ref_id VARCHAR(64)`，记录关联业务对象 ID（当前用于 `documents.id`），并建立索引。统计接口据此 JOIN `documents` 取回文件名。 |
| **备选方案** | 曾考虑把 doc_id 编码进 `error_message` 字符串再解析，但会让日志内容与结构化查询耦合、且无法建索引，故弃用。 |

```sql
ALTER TABLE `usage_logs`
    ADD COLUMN `ref_id` VARCHAR(64) DEFAULT NULL
        COMMENT '关联业务对象ID（如 documents.id），用于 OCR 失败队列回溯 [v1.2]'
        AFTER `error_message`,
    ADD KEY `idx_usage_ref_id` (`ref_id`);
```

### 2. `system_configs` 新增 4 条默认配置

| 配置项 | 默认值 | 背景 |
|--------|--------|------|
| `embedding.base_url` | `''` | PRD 4.2.3 要求调用 `Qwen/Qwen3-Embedding-8B`，而该模型通常与对话模型不在同一服务商。留空时复用 `llm.base_url`，保持 v1.1 的默认行为不变。 |
| `embedding.api_key` | `''` | 同上；以 AES-256 密文存储 [S-1]，留空则复用 `llm.api_key`。 |
| `retrieval.top_n` | `20` | PRD 4.3.1 定义了密集检索 Top-N（如 N=20），但 v1.1 只把 Rerank 的 Top-K 做成了可配置项，Top-N 是硬编码。 |
| `retrieval.history_rounds` | `5` | PRD 4.3.3 明确「历史轮数上限由管理员在后台配置」，v1.1 缺少对应配置项。 |

```sql
INSERT INTO `system_configs` (`config_key`, `config_value`, `description`) VALUES
    ('embedding.base_url', '',   'Embedding 服务 Base URL（留空则复用 llm.base_url）'),
    ('embedding.api_key',  '',   'Embedding API 调用密钥（AES-256密文，留空则复用 llm.api_key）'),
    ('retrieval.top_n',    '20', '密集检索阶段返回的候选片段数量 Top-N'),
    ('retrieval.history_rounds', '5', '多轮对话携带的历史轮数上限（PRD 4.3.3）')
ON DUPLICATE KEY UPDATE `config_value` = VALUES(`config_value`);
```

> 应用层的 `config_service` 在启动时会自动补齐缺失的配置项，因此忘记执行上述
> INSERT 也不会导致服务不可用，但建议随 DDL 一并执行以便 DBA 侧账实相符。

---

## 与接口文档的其余对齐说明（未改表结构）

以下差异通过**新增响应字段**解决，属于向后兼容的接口增强，不影响既有前端：

| 接口 | 新增字段 | 原因 |
|------|----------|------|
| `GET /api/v1/docs/list` | `status_label`、`updated_at` | 前端直接展示中文状态；`updated_at` 用于判断解析是否卡滞 [M-1]。 |
| `GET /api/v1/admin/users` | `last_login_at`、`page`、`page_size` | PRD 4.5.1 要求展示最后登录时间；分页字段与其他列表接口保持一致。 |
| `GET /api/v1/admin/reset-requests` | `id`、`user_id`、`is_handled`、`last_request_at`、`handled_at` | 管理员需要据 `user_id` 一键跳转重置密码；其余字段用于展示处理状态。 |
| `GET /api/v1/admin/configs` | `embedding.base_url`、`embedding.api_key_masked`、`retrieval` 块 | 对应上文新增的配置项，Key 一律脱敏 [S-1]。 |
| `GET /api/v1/admin/stats` | `total_calls`、`total_vector_searches`、`daily_trend` | 支撑后台趋势图与总览卡片。 |
| SSE `done` 帧 | `warnings` | PRD 4.3.3 [M-6] 明确要求携带 `rerank_timeout` 等降级告警。 |
| 引用条目 | `doc_id`、`chunk_index` | [I-3] 要求 TXT/Markdown 用 `chunk_index` 标注「第 N 个片段」。 |

### 新增接口

| 接口 | 用途 |
|------|------|
| `GET /api/v1/auth/me` | 前端刷新页面后回填当前用户信息。 |
| `POST /api/v1/auth/change-password` | PRD 4.1.2 要求「用户使用临时密码登录后须立即修改密码」，并触发 `token_version + 1` [S-2]，但接口文档未定义对应端点。 |
| `GET /api/v1/chat/session/{id}/messages` | 接口文档 4.5 已定义，此处列出以便对照。 |
| `GET /api/health` | 部署健康检查与容器探针。 |

---

## v1.3 — 2026-07-26（接入真实模型联调）

用硅基流动（SiliconFlow）的真实 API 跑通全链路后，发现两处「按文档实现、
但接上真实模型就不可用」的问题，均通过新增可配置项解决。

### 1. `system_configs` 新增 `rerank.model`

| 项目 | 说明 |
|------|------|
| **背景** | 需求文档 4.5.2 只要求管理员可配置 Rerank 的终结点、Key 与 Top-K。 |
| **问题** | Rerank 请求体必须携带 `model` 字段，而各服务商取值完全不同（Cohere 用 `rerank-multilingual-v3.0`，硅基流动用 `BAAI/bge-reranker-v2-m3`）。原先硬编码为 Cohere 的取值，换任何其他服务商精排必然失败——且失败会被降级逻辑静默吞掉，表现为「Rerank 永远超时」。 |
| **方案** | 新增 `rerank.model` 配置项（默认 `BAAI/bge-reranker-v2-m3`），管理后台可改。 |

### 2. `system_configs` 新增 `llm.aux_model`

| 项目 | 说明 |
|------|------|
| **背景** | 需求文档 4.3.3 规定 Query Rewrite 超时（>3s）降级、4.4.2 规定异步生成会话标题。 |
| **问题** | 当前主流模型（含文档指定的 `deepseek-ai/DeepSeek-V4-Flash`）多为**推理型**，会先流式输出 `reasoning_content` 思考内容再输出正文。实测同一条「生成 15 字标题」的请求：DeepSeek-V4-Flash 耗时 **19.9s**，而小模型 `Qwen/Qwen3-VL-8B-Instruct` 仅 **1.8s**。这导致问题改写（3s 预算）与标题生成（8s 预算）几乎每次都超时降级——功能虽未中断，但改写形同虚设、标题永远退化为问题前 15 字。 |
| **方案** | 新增 `llm.aux_model`，供问题改写与标题生成使用；留空则复用主模型，行为与之前完全一致。配置小模型后实测：改写 2.4s、标题 2.1s，均在预算内成功。 |

### 3. 其他联调期修复（不涉及表结构）

| 问题 | 现象 | 修复 |
|------|------|------|
| 未设置 `max_tokens` | 推理模型的思考内容计入输出预算，服务商默认值（常见 512）被思考吃光，正文被截断甚至为空 | 主生成显式设置 `max_tokens=4096` |
| 标题生成与主回答流并发 | 同一 API Key 并发请求触发服务商限流，实测出现主回答流被中途掐断（只输出 25 字） | 改为主回答流结束后再顺序生成标题；接口文档允许标题在「即将结束时」推送 |
| 空回答无提示 | 模型未产出正文时前端显示空白气泡 | 检测到空正文时不落库，直接推送 `event: error` 提示重试 |

---

## v1.4 — 2026-09-14（RAG4 模型微调接入）

为 Embedding 与 Reranker 新增统一的远程/本地 Adapter 配置。该版本不新增数据表，
只向 `system_configs` 增加六个键，因此可向后兼容升级：

| 配置项 | 默认值 | 用途 |
|---|---|---|
| `embedding.provider` | `remote` | `remote` 或 `local` Adapter |
| `embedding.version` | `baseline` | 模型身份与 Chroma 索引命名空间 |
| `embedding.local_path` | `''` | 本地微调模型目录 |
| `rerank.provider` | `remote` | `remote` 或 `local` Adapter |
| `rerank.version` | `baseline` | 精排模型实验版本 |
| `rerank.local_path` | `''` | 本地微调模型目录 |

```sql
INSERT INTO `system_configs` (`config_key`, `config_value`, `description`) VALUES
    ('embedding.provider', 'remote',   'Embedding Adapter：remote 或 local'),
    ('embedding.version',  'baseline', 'Embedding 模型版本，同时作为向量索引命名空间'),
    ('embedding.local_path','',         '本地微调 Embedding 目录'),
    ('rerank.provider',    'remote',   'Rerank Adapter：remote 或 local'),
    ('rerank.version',     'baseline', 'Rerank 模型版本，用于实验追踪'),
    ('rerank.local_path',  '',         '本地微调 Reranker 目录')
ON DUPLICATE KEY UPDATE `config_value` = VALUES(`config_value`);
```

基线版本继续读取旧 Collection `col_user_{user_id}`。非基线 Embedding 使用带版本
摘要的新 Collection；切回旧版本无需删除新索引。文档删除会清理该用户下该文档的
所有版本向量。
