/** 与后端 api_document.md 对齐的类型定义。 */

/** 统一响应包裹格式（api_document 1.3）。 */
export interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T;
}

export interface Paged<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export type UserRole = 'user' | 'admin';

export interface UserInfo {
  id: number;
  email: string;
  role: UserRole;
}

export interface LoginResult {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_info: UserInfo;
}

/** 文档解析状态机（PRD 4.2.4）。 */
export type DocStatus = 'pending' | 'parsing' | 'vectorizing' | 'ready' | 'failed';

export interface DocumentItem {
  id: string;
  file_name: string;
  file_size: number;
  status: DocStatus;
  status_label: string;
  created_at: string;
  updated_at: string;
}

export interface SessionItem {
  session_id: string;
  title: string;
  last_message_preview: string;
  created_at: string;
  updated_at: string;
}

/** 引用溯源条目 [I-3]：PDF 有 page，TXT/MD 用 chunk_index 表示第 N 个片段。 */
export interface Citation {
  index: number;
  doc_id?: string | null;
  doc_name: string;
  page: number | null;
  chunk_index: number;
  snippet: string;
}

export interface MessageItem {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[] | null;
  created_at: string;
  /** 前端本地态：该条消息是否正在流式生成中 */
  streaming?: boolean;
  /** 本轮降级告警，如 rerank_timeout [M-6] */
  warnings?: string[];
}

export interface AdminUserItem {
  user_id: number;
  email: string;
  role: UserRole;
  status: number;
  doc_count: number;
  last_login_at: string | null;
  created_at: string;
}

export interface ResetRequestItem {
  id: number;
  email: string;
  user_id: number | null;
  is_handled: number;
  requested_at: string;
  last_request_at: string;
  handled_at: string | null;
}

export interface SystemConfigs {
  llm: { base_url: string; api_key_masked: string; model: string; aux_model: string };
  rerank: {
    provider: 'remote' | 'local';
    api_url: string;
    api_key_masked: string;
    model: string;
    version: string;
    local_path: string;
    top_k: number;
  };
  embedding: {
    provider: 'remote' | 'local';
    model: string;
    version: string;
    local_path: string;
    base_url: string;
    api_key_masked: string;
  };
  chunking: { chunk_size: number; overlap: number };
  retrieval: { top_n: number; history_rounds: number };
}

export interface ConfigUpdatePayload {
  llm?: { base_url?: string; api_key?: string; model?: string; aux_model?: string };
  rerank?: {
    provider?: 'remote' | 'local';
    api_url?: string;
    api_key?: string;
    model?: string;
    version?: string;
    local_path?: string;
    top_k?: number;
  };
  embedding?: {
    provider?: 'remote' | 'local';
    model?: string;
    version?: string;
    local_path?: string;
    base_url?: string;
    api_key?: string;
  };
  chunking?: { chunk_size?: number; overlap?: number };
  retrieval?: { top_n?: number; history_rounds?: number };
}

export interface StatsData {
  period_days: number;
  total_calls: number;
  total_llm_calls: number;
  total_tokens_used: number;
  total_rerank_calls: number;
  total_ocr_calls: number;
  total_vector_searches: number;
  failure_count: number;
  failure_rate: string;
  daily_trend: { date: string; count: number }[];
  ocr_failed_queue: {
    doc_id: string;
    file_name: string;
    error: string;
    created_at: string;
  }[];
}
