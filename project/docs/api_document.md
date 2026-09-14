# 基于RAG的学术知识引擎 — 接口设计与对接规范 (API Spec)

> 文档版本：v1.0  
> 更新日期：2026-07-23  
> 状态：正式稿

---

## 1. 全局设计规范

### 1.1 基础路径
所有 API 请求的基础路由前缀为：
```
/api/v1
```

### 1.2 通信协议
*   **传输协议**：全站使用 HTTPS 进行安全传输。
*   **请求格式**：除文件上传使用 `multipart/form-data` 外，其他 POST/PUT 请求体一律使用 `application/json; charset=utf-8`。
*   **认证机制**：除注册/登录/密码重置申请外，所有 API 请求头均需携带 JWT 令牌：
    ```http
    Authorization: Bearer <JWT_TOKEN>
    ```

### 1.3 统一响应数据格式 (Envelope)
系统采用固定的 JSON 包裹格式来处理所有同步请求：

#### 1.3.1 成功响应示例
```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "id": 1,
    "email": "user@outlook.com"
  }
}
```

#### 1.3.2 失败响应示例
```json
{
  "code": 400,
  "message": "邮箱格式不符合规范",
  "data": null
}
```

#### 1.3.3 全局状态码定义 (`code`)
| 业务状态码 | 对应 HTTP 状态 | 说明 |
|------------|----------------|------|
| **200** | 200 OK | 请求执行成功。 |
| **400** | 400 Bad Request | 参数校验失败、格式错误或违反业务规则。 |
| **401** | 401 Unauthorized | JWT 令牌缺失、过期或无效。 |
| **403** | 403 Forbidden | 权限不足（如非管理员请求后台管理接口）。 |
| **404** | 404 Not Found | 资源不存在（如会话、文档不存在）。 |
| **500** | 500 Internal Error| 后端内部服务器异常。 |

---

## 2. 用户与认证模块 (`/api/v1/auth`)

### 2.1 用户注册
*   **接口**：`POST /api/v1/auth/register`
*   **权限**：无需 Token。
*   **请求体**：
    ```json
    {
      "email": "user@outlook.com",
      "password": "strongpassword123"
    }
    ```
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "注册成功，请登录",
      "data": {
        "email": "user@outlook.com",
        "created_at": "2026-07-23 21:24:35"
      }
    }
    ```

### 2.2 用户登录
*   **接口**：`POST /api/v1/auth/login`
*   **权限**：无需 Token。
*   **请求体**：
    ```json
    {
      "email": "user@outlook.com",
      "password": "strongpassword123"
    }
    ```
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "登录成功",
      "data": {
        "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
        "token_type": "Bearer",
        "expires_in": 604800,
        "user_info": {
          "id": 12,
          "email": "user@outlook.com",
          "role": "user"
        }
      }
    }
    ```

### 2.3 提交密码重置申请
*   **接口**：`POST /api/v1/auth/reset-request`
*   **权限**：无需 Token。
*   **频率限制 [M-4]**：同一邮箱地址 10 分钟内只允许提交 1 次；若已有未处理的申请，返回 400 错误。
*   **请求体**：
    ```json
    {
      "email": "user@outlook.com"
    }
    ```
*   **响应数据（成功）**：
    ```json
    {
      "code": 200,
      "message": "已提交重置申请，请联系管理员为您重置密码",
      "data": null
    }
    ```
*   **响应数据（10 分钟内重复提交）**：
    ```json
    {
      "code": 400,
      "message": "您已有待处理的申请，请联系管理员或 10 分钟后重试",
      "data": null
    }
    ```
    > **说明**：系统记录此邮箱的密码重置请求，管理员可在管理后台查看并生成临时密码。

---

## 3. 知识库管理模块 (`/api/v1/docs`)

### 3.1 上传多文档
*   **接口**：`POST /api/v1/docs/upload`
*   **权限**：需普通用户或管理员 Token。
*   **请求格式**：`multipart/form-data`
*   **请求参数**：
    *   `files`: File 数组 (单文件最大 50MB，单次请求最多支持 10 个文件)。
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "文档上传成功，后端已启动异步解析入库",
      "data": [
        {
          "id": "doc_8f9g1h2j...",
          "file_name": "Attention_Is_All_You_Need.pdf",
          "file_size": 2241502,
          "status": "pending",
          "created_at": "2026-07-23 21:26:00"
        },
        {
          "id": "doc_9a8b7c6d...",
          "file_name": "DeepSeek_V4_Report.pdf",
          "file_size": 4209121,
          "status": "pending",
          "created_at": "2026-07-23 21:26:01"
        }
      ]
    }
    ```
    > **说明**：该接口保存完文件后立即返回 `pending` 状态，后端开启后台线程或 Celery 任务去提取文本（如扫描件触发 OCR 解析）并计算向量写入独立 Collection。

### 3.2 获取文档列表 (支持轮询状态)
*   **接口**：`GET /api/v1/docs/list`
*   **权限**：需 Token 隔离。
*   **请求参数** (Query)：
    *   `page`: 整数 (默认 1)
    *   `page_size`: 整数 (默认 10)
    *   `status`: 字符串 (可选，过滤状态：`pending`, `parsing`, `vectorizing`, `ready`, `failed`)
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "获取成功",
      "data": {
        "total": 45,
        "page": 1,
        "page_size": 10,
        "items": [
          {
            "id": "doc_8f9g1h2j...",
            "file_name": "Attention_Is_All_You_Need.pdf",
            "file_size": 2241502,
            "status": "ready",
            "created_at": "2026-07-23 21:26:00"
          },
          {
            "id": "doc_9a8b7c6d...",
            "file_name": "DeepSeek_V4_Report.pdf",
            "file_size": 4209121,
            "status": "vectorizing",
            "created_at": "2026-07-23 21:26:01"
          }
        ]
      }
    }
    ```

### 3.3 删除文档
*   **接口**：`DELETE /api/v1/docs/{doc_id}`
*   **权限**：只能删除本人名下的文档。
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "文档删除成功，已清理关联的向量与元数据",
      "data": null
    }
    ```

---

## 4. 智能问答模块 (`/api/v1/chat`)

### 4.1 创建新会话
*   **接口**：`POST /api/v1/chat/session`
*   **请求体**：无
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "会话创建成功",
      "data": {
        "session_id": "sess_3e4r5t6y...",
        "title": "新对话",
        "created_at": "2026-07-23 21:28:00"
      }
    }
    ```

### 4.2 修改会话标题 (手动重命名)
*   **接口**：`PUT /api/v1/chat/session/{session_id}`
*   **请求体**：
    ```json
    {
      "title": "Transformer 论文精读"
    }
    ```
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "修改成功",
      "data": {
        "session_id": "sess_3e4r5t6y...",
        "title": "Transformer 论文精读",
        "updated_at": "2026-07-23 21:29:10"
      }
    }
    ```

### 4.3 获取会话列表
*   **接口**：`GET /api/v1/chat/sessions`
*   **请求参数** (Query)：
    *   `keyword`: 字符串（可选，按标题进行模糊搜索）
    *   `page`: 整数（默认 1）[M-3]
    *   `page_size`: 整数（默认 20，最大 50）
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "获取成功",
      "data": {
        "total": 32,
        "page": 1,
        "page_size": 20,
        "items": [
          {
            "session_id": "sess_3e4r5t6y...",
            "title": "Transformer 论文精读",
            "last_message_preview": "自注意力机制可以建立序列中任意两个位置之间的...",
            "created_at": "2026-07-23 21:28:00",
            "updated_at": "2026-07-23 21:29:10"
          }
        ]
      }
    }
    ```
    > **说明**：`last_message_preview` 为该会话最新一条 `assistant` 消息正文的前 60 字，方便用户快速识别历史对话内容。[I-2]

### 4.4 删除会话
*   **接口**：`DELETE /api/v1/chat/session/{session_id}`
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "会话已删除",
      "data": null
    }
    ```

### 4.5 获取历史消息记录
*   **接口**：`GET /api/v1/chat/session/{session_id}/messages`
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "获取成功",
      "data": [
        {
          "message_id": "msg_01...",
          "role": "user",
          "content": "自注意力机制的作用是什么？",
          "citations": null,
          "created_at": "2026-07-23 21:30:00"
        },
        {
          "message_id": "msg_02...",
          "role": "assistant",
          "content": "自注意力机制 [1] 可以建立序列中任意两个位置之间的直接联系...",
          "citations": [
            {
              "index": 1,
              "doc_name": "Attention_Is_All_You_Need.pdf",
              "page": 3,
              "snippet": "Self-attention, sometimes called intra-attention is an attention mechanism relating different positions of a single sequence..."
            }
          ],
          "created_at": "2026-07-23 21:30:05"
        }
      ]
    }
    ```

### 4.6 智能流式问答 (SSE 协议)
*   **接口**：`POST /api/v1/chat/query`
*   **协议类型**：Server-Sent Events (SSE)
*   **请求体**：
    ```json
    {
      "session_id": "sess_3e4r5t6y...",
      "query": "自注意力机制的作用是什么？",
      "enable_rag": true
    }
    ```
*   **`enable_rag` 参数行为说明 [S-4]**：
    *   `true`（默认）：完整 RAG 流程（向量检索 → Rerank → LLM 生成），`done` 帧中含引用列表。
    *   `false`：跳过向量检索与 Rerank，仍传入本会话历史对话上下文保持多轮连贯，直接调用 LLM 生成回答。`done` 帧中 `citations` 为空数组 `[]`，对应 `chat_messages.citations` 字段存 `null`。
*   **超时降级策略 [M-6]**：
    *   Query Rewrite 超时（> 3s）：降级为原始问题直接检索，SSE 连接不中断。
    *   Rerank API 超时（> 3s）：跳过 Rerank，使用向量检索 Top-K 结果；`done` 帧附加 `"warnings": ["rerank_timeout"]`。
    *   LLM 超时（> 30s）：推送 `event: error` 并关闭连接。

#### 4.6.1 SSE 流式事件推送流程规范
在问答响应中，连接建立后，响应头应设置为：
```http
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

推送的数据以 JSON 字符串形式分发，并定义事件名称区分不同阶段的数据类型。

##### 阶段 1：流式返回文本块 (event: `chunk`)
系统以增量文本（tokens）形式返回回答。
```text
event: chunk
data: {"content": "自注"}

event: chunk
data: {"content": "意力"}

event: chunk
data: {"content": "机制"}
```

##### 阶段 2：流式返回首轮提问的自动标题生成 (event: `title`，可选)
若是该会话的**第一次**提问，在文本传输期间或即将结束时，系统将异步生成首问摘要，并在中途或后半段推送到前端，方便前端侧边栏立即更新标题而无需刷新：
```text
event: title
data: {"session_id": "sess_3e4r5t6y...", "title": "注意力机制探究"}
```

##### 阶段 3：最后一帧返回引用溯源数据与结束标记 (event: `done`)
在整个 LLM 文本输出完毕后，**在最后一帧返回结构化的引用列表**及消息 ID。
```text
event: done
data: {
  "message_id": "msg_assistant_123...",
  "citations": [
    {
      "index": 1,
      "doc_name": "Attention_Is_All_You_Need.pdf",
      "page": 3,
      "snippet": "Self-attention, sometimes called intra-attention is an attention mechanism..."
    }
  ]
}
```

##### 阶段 4：出错推送 (event: `error`，仅在发生异常时推送)
```text
event: error
data: {"code": 500, "message": "云端 Rerank API 调用超时"}
```

---

## 5. 管理员后台模块 (`/api/v1/admin`)

所有 `/api/v1/admin/*` 下的接口，请求头不仅需要携带 Token，且 Token 对应的用户角色必须为 `admin`。

### 5.1 获取所有用户列表
*   **接口**：`GET /api/v1/admin/users`
*   **参数** (Query)：`page`, `page_size`, `keyword`
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "获取成功",
      "data": {
        "total": 120,
        "items": [
          {
            "user_id": 1,
            "email": "admin@outlook.com",
            "role": "admin",
            "status": 1,
            "doc_count": 0,
            "created_at": "2026-03-01 10:00:00"
          },
          {
            "user_id": 12,
            "email": "user@outlook.com",
            "role": "user",
            "status": 1,
            "doc_count": 15,
            "created_at": "2026-07-23 21:24:35"
          }
        ]
      }
    }
    ```

### 5.2 变更用户角色与状态
*   **接口**：`PUT /api/v1/admin/users/{user_id}/role-status`
*   **请求体**：
    ```json
    {
      "role": "admin",  // 可选值："user", "admin"
      "status": 0       // 可选值：1 (启用), 0 (禁用)
    }
    ```
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "更新用户角色和状态成功",
      "data": null
    }
    ```

### 5.3 密码重置请求列表
*   **接口**：`GET /api/v1/admin/reset-requests`
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "获取成功",
      "data": [
        {
          "email": "user@outlook.com",
          "requested_at": "2026-07-23 21:25:10"
        }
      ]
    }
    ```

### 5.4 管理员手动重置用户密码
*   **接口**：`PUT /api/v1/admin/users/{user_id}/reset-password`
*   **请求体**：无
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "重置密码成功",
      "data": {
        "temporary_password": "Temp_pwd_987654"
      }
    }
    ```
    > **说明**：此接口生成一个随机的临时密码，由管理员手动转交给对应的用户进行首次登录。

### 5.5 获取系统全局配置参数
*   **接口**：`GET /api/v1/admin/configs`
*   **响应数据**（API Key 脱敏，不返回明文）[S-1]：
    ```json
    {
      "code": 200,
      "message": "获取配置成功",
      "data": {
        "llm": {
          "base_url": "https://api.deepseek.com",
          "api_key_masked": "sk-****Flash",
          "model": "deepseek-ai/DeepSeek-V4-Flash"
        },
        "rerank": {
          "api_url": "https://api.cohere.com/v1/rerank",
          "api_key_masked": "****xxxx",
          "top_k": 5
        },
        "embedding": {
          "model": "Qwen/Qwen3-Embedding-8B"
        },
        "chunking": {
          "chunk_size": 600,
          "overlap": 60
        }
      }
    }
    ```
    > **安全说明 [S-1]**：API Key 在数据库中以 AES-256 加密保存，此接口仅返回脱敏掩码，绝不向前端返回明文 Key。`embedding` 块为新增字段，管理员可修改 Embedding 模型名称 [M-2]。

### 5.6 更新系统全局配置参数
*   **接口**：`PUT /api/v1/admin/configs`
*   **请求体**（所有字段均为可选，仅传入需要更新的字段）：
    ```json
    {
      "llm": {
        "base_url": "https://api.deepseek.com",
        "api_key": "sk-xxxxxxxxx",
        "model": "deepseek-ai/DeepSeek-V4-Flash"
      },
      "rerank": {
        "api_url": "https://api.cohere.com/v1/rerank",
        "api_key": "rerank-key-xxxxxxxxx",
        "top_k": 5
      },
      "embedding": {
        "model": "Qwen/Qwen3-Embedding-8B"
      },
      "chunking": {
        "chunk_size": 800,
        "overlap": 80
      }
    }
    ```
    > **安全说明 [S-1]**：API Key 明文由后端接收后立即进行 AES-256 加密存储，不在任何响应中返回明文。
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "系统全局配置参数已成功保存并立即生效",
      "data": null
    }
    ```

### 5.7 运行监控数据 [I-4]
*   **接口**：`GET /api/v1/admin/stats`
*   **权限**：Admin Token。
*   **请求参数** (Query)：
    *   `days`: 整数（可选，统计最近 N 天的数据，默认 7）
*   **响应数据**：
    ```json
    {
      "code": 200,
      "message": "获取成功",
      "data": {
        "period_days": 7,
        "total_llm_calls": 1240,
        "total_tokens_used": 3872000,
        "total_rerank_calls": 980,
        "total_ocr_calls": 45,
        "failure_count": 12,
        "failure_rate": "0.97%",
        "ocr_failed_queue": [
          {
            "doc_id": "doc_xxxx",
            "file_name": "扫描件.pdf",
            "error": "图像分辨率过低，OCR 识别失败",
            "created_at": "2026-07-23 14:22:10"
          }
        ]
      }
    }
    ```
