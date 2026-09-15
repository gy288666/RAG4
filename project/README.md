# 基于 RAG 的学术知识引擎

> 上传专业文献，通过语义检索 + 大模型生成，获得**精准、可溯源**的学术问答。
>
> 实现依据：`docs/requirements_document.md` (v1.1) 与 `docs/api_document.md` (v1.0)。

---

## 目录

- [功能一览](#功能一览)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [离线体验模式](#离线体验模式)
- [接口概览](#接口概览)
- [核心实现说明](#核心实现说明)
- [测试](#测试)
- [生产部署](#生产部署)
- [常见问题](#常见问题)

---

## 功能一览

### 普通用户

| 模块 | 能力 |
|------|------|
| **账号** | 邮箱注册（主流后缀白名单）、登录（JWT，7 天有效）、找回密码申请、修改密码 |
| **知识库** | 拖拽批量上传（PDF / DOCX / TXT / Markdown，单文件 ≤50MB、单次 ≤10 个）、解析状态实时轮询、按状态与文件名筛选、删除（同步清理向量与物理文件） |
| **智能问答** | SSE 流式回答、可点击的 `[n]` 引用标记与原文弹窗、多轮追问、纯模型对话开关 |
| **历史会话** | 侧边栏列表、标题自动生成与手动重命名、标题模糊搜索、删除 |

### 系统管理员

| 模块 | 能力 |
|------|------|
| **用户管理** | 用户列表（含文档数、最后登录时间）、角色切换、启用/禁用、生成临时密码 |
| **系统配置** | LLM / Rerank / Embedding / 切片 / 检索参数热更新；远程/本地模型、模型版本可切换 |
| **运行监控** | 调用次数、Token 消耗、失败率、每日趋势、OCR 与文档处理失败队列 |

---

## 技术栈

| 层 | 选型 |
|----|------|
| 前端 | React 18 + TypeScript + Vite + React Router + Axios + TailwindCSS |
| 后端 | Conda Python 3.11 + FastAPI + SQLAlchemy 2.0 |
| 关系库 | MySQL 8（开发可用 SQLite） |
| 向量库 | Chroma（用户 + Embedding 版本双重 Collection 隔离） |
| 文档解析 | PyMuPDF / pdfplumber / python-docx / charset-normalizer |
| OCR | PaddleOCR（首选）→ Tesseract（回退），均为可选依赖 |
| 模型 | OpenAI 兼容 API，或 Sentence Transformers 本地 Embedding / Reranker；支持项目数据微调 |

---

## 目录结构

```
RAG4/project/
├── docs/                          # 需求、接口、DDL 与变更记录
│   ├── requirements_document.md
│   ├── api_document.md
│   ├── init_db.sql                # MySQL 建库建表脚本（v1.4）
│   └── db_changelog.md            # 实现阶段的表结构与接口变更说明
│
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI 入口、CORS、异常处理、初始化
│   │   ├── core/                  # 配置、数据库、JWT/bcrypt/AES、依赖注入、统一响应
│   │   ├── models/                # 7 张表的 ORM 映射
│   │   ├── schemas/               # 请求体校验
│   │   ├── api/v1/                # auth / docs / chat / admin 路由
│   │   ├── modeling/              # 模型接口、注册表、远程/本地 Adapter
│   │   ├── services/              # 业务与 RAG 编排（见下）
│   │   └── utils/                 # 时间格式化、时间有序 ID
│   ├── tests/                     # 77 个 pytest 用例
│   ├── requirements.txt
│   ├── requirements-local-models.txt
│   └── .env.example
│
├── training/                      # 硬负样本、微调与离线评测脚本
├── models/                        # 本地模型产物（Git 忽略）
│
└── frontend/
    └── src/
        ├── api/                   # Axios 封装 + SSE 流式解析
        ├── components/            # 布局、消息气泡、会话侧边栏、弹窗、骨架屏
        ├── context/               # 登录态、全局提示
        ├── pages/                 # 登录/注册/找回、问答、知识库、个人设置
        │   └── admin/             # 用户管理、系统配置、运行监控
        ├── types/                 # 与接口文档对齐的 TS 类型
        └── utils/                 # 格式化与引用文本处理
```

### 服务层职责

| 文件 | 职责 |
|------|------|
| `config_service.py` | `system_configs` 读写 + TTL 缓存，API Key 加解密与脱敏 |
| `parser_service.py` | 多格式解析、扫描版 PDF 判定、字符集识别 |
| `ocr_service.py` | OCR 引擎探测与适配（PaddleOCR / Tesseract） |
| `chunking_service.py` | 按段落→句子→字符三级边界切分，支持重叠 |
| `modeling/` | Embedding/Reranker 稳定接口与 remote/local Adapter；业务层不感知训练框架 |
| `embedding_service.py` | 统一模型门面、批量向量化与调用日志 |
| `vector_store.py` | 向量库抽象层；按用户和 Embedding 版本隔离索引 |
| `rerank_service.py` | 统一远程/本地精排，超时或失败自动降级 |
| `llm_service.py` | 流式与非流式生成，Token 统计 |
| `rag_service.py` | 问答编排：改写 → 检索 → 精排 → 生成 → 引用 → 落库 |
| `document_service.py` | 上传落盘、后台线程池解析入库、级联删除 |
| `usage_service.py` | 运行日志记录（管理后台统计数据源） |

---

## 快速开始

### 0. 前置条件

- Conda 与 Python 3.11
- Node.js 18+
- MySQL 8（若只想快速体验，可跳过，见下方 SQLite 方案）

### 1. 初始化数据库

```bash
mysql -u root -p < docs/init_db.sql
```

> 脚本开头包含 `DROP DATABASE IF EXISTS rag_high`，**生产环境执行前请务必删除该行**。

### 2. 启动后端

```bash
cd backend
conda create -n rag4-py3.11 python=3.11 -y
conda activate rag4-py3.11
python -m pip install -r requirements.txt

cp .env.example .env
# 编辑 .env：至少修改 DATABASE_URL 与 SECRET_KEY

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后：

- 接口文档（Swagger）：<http://127.0.0.1:8000/api/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>
- 首次启动若库中没有任何管理员，会自动创建 `INIT_ADMIN_EMAIL` 指定的账号。
  请在 `.env` 中自行设置 `INIT_ADMIN_EMAIL` / `INIT_ADMIN_PASSWORD`，**登录后立即修改密码**。
  切勿把真实密码、数据库口令或 API Key 写入仓库。

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev     # http://127.0.0.1:5173
```

Vite 已配置 `/api` 代理到 `http://127.0.0.1:8000`，无需处理跨域。

### 4. 配置模型服务

以管理员身份登录 → **系统配置**，填写：

- **大模型**：Base URL、API Key、模型名称
- **辅助任务模型**：见下方「重要」说明
- **Embedding**：运行方式、模型名称、模型/索引版本；远程模式填写 Base URL 与 Key，
  本地模式填写模型目录
- **Rerank**：运行方式、模型版本、Top-K；远程模式填写终结点与 Key，本地模式填写模型目录

保存后立即生效，无需重启服务。

本地模型还需执行：

```powershell
python -m pip install -r requirements-local-models.txt
```

微调数据格式、训练命令与上线门禁见 `training/README.md`。更换 Embedding 模型或
Adapter 时，后台强制要求填写新的版本号，以免新旧语义空间混写。

#### 已实测通过的配置（硅基流动 SiliconFlow）

| 配置项 | 取值 |
|--------|------|
| 大模型 Base URL | `https://api.siliconflow.cn/v1` |
| 大模型 | `deepseek-ai/DeepSeek-V4-Flash` |
| **辅助任务模型** | `Qwen/Qwen3-VL-8B-Instruct` |
| Embedding 模型 | `Qwen/Qwen3-Embedding-8B` |
| Rerank 终结点 | `https://api.siliconflow.cn/v1/rerank` |
| Rerank 模型 | `BAAI/bge-reranker-v2-m3` |

三处 API Key 填同一个即可。实测端到端表现：Embedding 约 2.3s、向量检索约 2.4s、
Rerank 约 1.9s、问题改写约 2.4s、标题生成约 2.1s、大模型生成约 8.5s。

> **重要：为什么要单独配置「辅助任务模型」**
>
> 当前主流模型（含默认的 `DeepSeek-V4-Flash`）多为**推理型**，回答前会先输出一
> 段思考内容。这对最终答案质量有益，但会让「问题改写」（3 秒预算）和「会话标题
> 生成」（8 秒预算）这两个短任务频繁超时降级——实测同一条生成标题的请求，
> 推理型主模型耗时 **19.9 秒**，而小模型仅 **1.8 秒**。
>
> 该项留空时会复用主模型，功能不会中断（超时后自动降级：改写退回原始问题、
> 标题退回问题前 15 字），但**改写与自动标题会形同虚设**。填一个小的
> Instruct 模型即可解决，同时还能显著降低这两项的调用成本。

---

## 离线体验模式

没有任何外部 API Key 时，可开启 Mock 模式跑通完整链路（上传 → 解析 → 向量化 →
检索 → 流式回答 → 引用溯源）：

```bash
cd backend
DATABASE_URL="sqlite:///./data/dev.db" DEV_MOCK_AI=true \
  uvicorn app.main:app --port 8000
```

此时 Embedding 使用本地确定性哈希向量、LLM 使用本地 Mock 生成、Rerank 直接跳过。
**该模式仅用于开发联调与自动化测试，严禁用于生产。**

---

## 接口概览

统一响应格式：`{"code": 200, "message": "...", "data": ...}`；
除注册、登录、重置申请外均需 `Authorization: Bearer <JWT>`。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 注册 |
| POST | `/api/v1/auth/login` | 登录，返回 JWT |
| POST | `/api/v1/auth/reset-request` | 提交密码重置申请（10 分钟限 1 次） |
| GET | `/api/v1/auth/me` | 当前用户信息 |
| POST | `/api/v1/auth/change-password` | 修改密码（触发 `token_version + 1`） |
| POST | `/api/v1/docs/upload` | 多文档上传 |
| GET | `/api/v1/docs/list` | 文档列表（分页 / 状态过滤 / 文件名搜索） |
| DELETE | `/api/v1/docs/{doc_id}` | 删除文档及其向量 |
| POST | `/api/v1/chat/session` | 创建会话 |
| PUT | `/api/v1/chat/session/{id}` | 重命名会话 |
| GET | `/api/v1/chat/sessions` | 会话列表（标题模糊搜索） |
| DELETE | `/api/v1/chat/session/{id}` | 删除会话（逻辑删除） |
| GET | `/api/v1/chat/session/{id}/messages` | 历史消息 |
| POST | `/api/v1/chat/query` | **SSE 流式问答** |
| GET | `/api/v1/admin/users` | 用户列表 |
| PUT | `/api/v1/admin/users/{id}/role-status` | 变更角色 / 状态 |
| PUT | `/api/v1/admin/users/{id}/reset-password` | 生成临时密码 |
| GET | `/api/v1/admin/reset-requests` | 密码重置申请列表 |
| GET / PUT | `/api/v1/admin/configs` | 系统配置（Key 脱敏 / 加密写入） |
| GET | `/api/v1/admin/stats` | 运行监控数据 |

### SSE 事件序列

```text
event: chunk    data: {"content": "自注"}                     ← 增量文本，可多次
event: title    data: {"session_id": "...", "title": "..."}   ← 仅首轮提问
event: done     data: {"message_id": "...", "citations": [...], "warnings": []}
event: error    data: {"code": 500, "message": "..."}         ← 仅异常时
```

---

## 核心实现说明

对照需求文档中标注的关键条目：

| 编号 | 要求 | 实现位置 |
|------|------|----------|
| **[S-1]** | API Key AES-256 静态加密，响应仅返回脱敏掩码 | `core/security.py` 的 `encrypt_secret` / `mask_secret`；`api/v1/admin.py` 的 `get_configs` |
| **[S-2]** | `token_version` 使旧 JWT 立即失效 | `core/security.py` 签发时写入；`core/deps.py` 鉴权时与库中值比对 |
| **[S-3]** | 向量 Metadata 五要素，删除时按 `doc_id` 清理 | `services/vector_store.py` 的 `VectorRecord.metadata()` 与 `delete_document` |
| **[S-4]** | `enable_rag=false` 跳过检索，`citations` 存 NULL | `services/rag_service.py` 的 `stream_answer` |
| **[M-1]** | `documents.updated_at` 供前端判断卡滞 | 模型 `onupdate`；前端 `KnowledgePage` 展示与轮询 |
| **[M-4]** | 密码重置 10 分钟频率限制 | `api/v1/auth.py` 的 `reset_request` |
| **[M-6]** | 三级超时降级 | 改写降级见 `rewrite_query`；精排降级见 `rerank_service`；生成超时推 `error` 帧 |
| **[I-2]** | 会话列表返回最新回答前 60 字 | `api/v1/chat.py` 的 `list_sessions` |
| **[I-3]** | PDF 标页码、TXT/MD 标片段序号 | `rag_service.build_citations`；前端 `utils/format.ts` 的 `citationLocator` |
| **[I-4]** | 运行日志与监控统计 | `services/usage_service.py`；`api/v1/admin.py` 的 `get_stats` |

### 数据隔离

- **物理文件**：`{UPLOAD_DIR}/{user_id}/{doc_id}{ext}`，落盘文件名使用 `doc_id`，
  杜绝原始文件名带来的路径穿越与重名覆盖。
- **向量**：基线沿用 `col_user_{user_id}`；微调模型按
  `col_user_{user_id}__{embedding_version}_{digest}` 建立独立 Collection。检索只打开
  当前用户、当前版本的 Collection，既防跨用户读取，也防不同向量空间混写。
- **关系库**：所有列表与详情查询均强制附加 `user_id` 条件；越权访问统一返回
  `404` 而非 `403`，避免资源 ID 被探测。

### 稳定性设计

- 上传接口先落盘 + 写元数据后立即返回 `pending`，解析与向量化在后台线程池执行，
  状态机 `pending → parsing → vectorizing → ready / failed` 全程落库。
- 外部依赖（OCR / Embedding / Rerank / LLM）全部隔离在服务层，任一不可用只影响
  对应环节：OCR 缺失→文档标记失败并进入失败队列；Rerank 超时→降级并告警；
  Chroma 不可用→自动回退本地向量实现。
- 消息 ID 采用纳秒时间戳前缀（`utils/ids.py`）。因为 MySQL `DATETIME` 只精确到秒，
  同一秒内写入的一问一答若仅按 `created_at` 排序会出现顺序颠倒，
  `ORDER BY created_at, id` 配合有序 ID 可保证时序稳定。

---

## 测试

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

测试全程使用 SQLite 临时库 + `DEV_MOCK_AI`，**无需 MySQL、无需任何外部 API Key**。

| 文件 | 覆盖内容 |
|------|----------|
| `test_auth.py` | 注册校验、登录提示区分、JWT 鉴权、重置频率限制、`token_version` 失效 |
| `test_docs.py` | 上传全链路、格式与数量限制、状态流转、跨用户越权、删除清理向量 |
| `test_chat.py` | 会话 CRUD 与越权、SSE 事件序列、引用字段、纯模型模式、多轮上下文、预览文本 |
| `test_admin.py` | RBAC、用户管理、密码重置闭环、Key 加密与脱敏、配置生效、监控统计 |
| `test_services.py` | bcrypt / AES、邮箱密码规则、切片边界、多格式解析、向量隔离、Rerank 降级 |

前端类型与构建检查：

```bash
cd frontend
npm run lint     # tsc --noEmit
npm run build
```

---

## 生产部署

### 后端

```bash
gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 4 -b 0.0.0.0:8000 \
  --timeout 120
```

> `--timeout` 需大于 `LLM_TIMEOUT`，否则长回答会被 worker 提前中断。

### 前端

```bash
cd frontend && npm run build      # 产物在 dist/
```

### Nginx 参考配置

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    client_max_body_size 60m;          # 需大于单文件 50MB 上限

    location / {
        root /var/www/rag-frontend;
        try_files $uri $uri/ /index.html;   # SPA 前端路由
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 流式问答必需：关闭缓冲并放宽读超时
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_http_version 1.1;
    }
}
```

### 上线检查清单

- [ ] `SECRET_KEY` 与 `CONFIG_ENCRYPTION_KEY` 已改为随机长字符串并妥善备份
      （`CONFIG_ENCRYPTION_KEY` 丢失将导致已存 API Key 无法解密）
- [ ] `DEV_MOCK_AI=false`
- [ ] `DEBUG=false`
- [ ] `CORS_ORIGINS` 收敛到实际前端域名
- [ ] 初始管理员密码已修改
- [ ] `init_db.sql` 中的 `DROP DATABASE` 语句已删除
- [ ] `UPLOAD_DIR` / `CHROMA_DIR` 指向持久化磁盘并纳入备份
- [ ] 全站 HTTPS 已启用

---

## 常见问题

**Q：上传的扫描版 PDF 一直显示「失败」？**
服务器未安装 OCR 引擎。安装其一即可：

```bash
pip install paddleocr paddlepaddle          # 推荐，中文识别效果更好
# 或
apt-get install -y tesseract-ocr tesseract-ocr-chi-sim && pip install pytesseract Pillow
```

失败原因可在管理后台「运行监控 → 失败队列」中查看。

**Q：问答时提示「尚未配置 Embedding API Key」？**
到管理后台「系统配置」填写大模型 Key；若 Embedding 与大模型不是同一服务商，
需单独填写 Embedding 的 Base URL 与 Key。

**Q：修改了 Embedding 模型，为什么旧文档搜不到了？**
不同模型的向量维度与语义空间不同。系统会要求新版本号并切换到独立索引，所以旧
索引不会被污染，但新索引初始为空。当前可重新上传评测文档；RAG4 的异步批量重建
任务完成后，应通过显式重建完成切换。

**Q：切片参数改了，历史文档会重新切分吗？**
不会。按 PRD 4.5.2，切片参数仅对之后上传的文档生效。

**Q：回答被截断，或干脆是空白？**
基本都出在推理型模型上——思考内容会占用输出预算。系统已默认把主生成的
`max_tokens` 设为 4096；若你的模型思考特别长，可调大
`backend/app/services/llm_service.py` 中的 `MAX_OUTPUT_TOKENS`。
若模型完全没产出正文，前端会明确提示「大模型未返回有效内容」，而不是显示空白气泡。

**Q：自动生成的会话标题总是问题的前 15 个字？**
说明标题生成超时降级了。到管理后台配置「辅助任务模型」（见上文），用小模型跑
这类短任务即可。同理，多轮追问时若发现指代（「它」「这个方法」）没被正确理解，
也是问题改写超时降级所致，同一处配置一并解决。

**Q：Rerank 一直不生效 / 日志里全是超时？**
先检查「Rerank 模型名称」是否与服务商匹配——各家取值不同（Cohere 用
`rerank-multilingual-v3.0`，硅基流动用 `BAAI/bge-reranker-v2-m3`），填错会被
降级逻辑静默吞掉，表现为「永远超时」。管理后台「运行监控」里可以看到
`rerank_call` 的成败与耗时。

**Q：回答里出现「根据现有资料无法回答该问题」？**
这是预期行为——系统提示词严格约束模型只依据检索到的资料作答，以遏制幻觉。
请确认相关文档已上传且状态为「已就绪」。
