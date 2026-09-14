/** Axios 实例：统一注入 JWT、解包 Envelope、集中处理错误提示。 */
import axios, { type AxiosRequestConfig } from 'axios';
import type { ApiEnvelope } from '@/types';

export const TOKEN_KEY = 'rag_access_token';
export const USER_KEY = 'rag_user_info';

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export const http = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  timeout: 60000,
});

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

http.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/** 业务异常：携带后端返回的中文提示，页面可直接展示。 */
export class ApiError extends Error {
  code: number;

  constructor(code: number, message: string) {
    super(message);
    this.code = code;
    this.name = 'ApiError';
  }
}

/** 401 时清空登录态并跳转登录页（避免在拦截器里直接依赖 Router）。 */
function handleUnauthorized() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  if (!location.pathname.startsWith('/login')) {
    location.href = `/login?redirect=${encodeURIComponent(location.pathname)}`;
  }
}

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error)) {
      const envelope = error.response?.data as ApiEnvelope<unknown> | undefined;
      const code = envelope?.code ?? error.response?.status ?? 500;
      if (code === 401) {
        handleUnauthorized();
      }
      const message =
        envelope?.message ||
        (error.code === 'ECONNABORTED' ? '请求超时，请检查网络后重试' : '网络异常，请稍后重试');
      return Promise.reject(new ApiError(code, message));
    }
    return Promise.reject(new ApiError(500, '未知错误，请稍后重试'));
  },
);

/** 发起请求并解包 data 字段；非 200 业务码统一抛出 ApiError。 */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request<ApiEnvelope<T>>(config);
  const envelope = response.data;
  if (envelope.code !== 200) {
    throw new ApiError(envelope.code, envelope.message);
  }
  return envelope.data;
}

export function toMessage(error: unknown, fallback = '操作失败，请稍后重试'): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
