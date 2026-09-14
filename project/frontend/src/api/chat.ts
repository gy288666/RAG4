import { API_BASE, ApiError, getToken, request } from './client';
import type { Citation, MessageItem, Paged, SessionItem } from '@/types';

export function createSession() {
  return request<{ session_id: string; title: string; created_at: string }>({
    url: '/chat/session',
    method: 'POST',
  });
}

export function renameSession(sessionId: string, title: string) {
  return request<{ session_id: string; title: string; updated_at: string }>({
    url: `/chat/session/${sessionId}`,
    method: 'PUT',
    data: { title },
  });
}

export function listSessions(params: { keyword?: string; page?: number; page_size?: number } = {}) {
  return request<Paged<SessionItem>>({ url: '/chat/sessions', params });
}

export function deleteSession(sessionId: string) {
  return request<null>({ url: `/chat/session/${sessionId}`, method: 'DELETE' });
}

export function listMessages(sessionId: string) {
  return request<MessageItem[]>({ url: `/chat/session/${sessionId}/messages` });
}

/** SSE 各阶段事件的回调集合（api_document 4.6.1）。 */
export interface StreamHandlers {
  onChunk: (delta: string) => void;
  onTitle?: (payload: { session_id: string; title: string }) => void;
  onDone: (payload: { message_id: string; citations: Citation[]; warnings?: string[] }) => void;
  onError?: (message: string) => void;
}

/**
 * 发起流式问答。
 *
 * 浏览器原生 EventSource 只支持 GET 且无法自定义请求头，
 * 因此这里用 fetch + ReadableStream 手动解析 SSE 报文。
 * 返回的 abort 函数可在用户点击“停止生成”或组件卸载时中断连接。
 */
export function streamQuery(
  payload: { session_id: string; query: string; enable_rag: boolean },
  handlers: StreamHandlers,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/chat/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken() ?? ''}`,
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        // 鉴权失败等错误仍走统一 Envelope
        let message = '问答服务暂时不可用，请稍后重试';
        try {
          const body = await response.json();
          message = body?.message || message;
          if (body?.code === 401) {
            throw new ApiError(401, message);
          }
        } catch {
          /* 响应体不是 JSON 时忽略 */
        }
        handlers.onError?.(message);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      // SSE 以空行分隔帧；网络分包可能把一帧切开，故需缓冲
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let separator = buffer.indexOf('\n\n');
        while (separator !== -1) {
          const frame = buffer.slice(0, separator);
          buffer = buffer.slice(separator + 2);
          dispatchFrame(frame, handlers);
          separator = buffer.indexOf('\n\n');
        }
      }
      if (buffer.trim()) dispatchFrame(buffer, handlers);
    } catch (error) {
      if ((error as Error)?.name === 'AbortError') return;
      handlers.onError?.(
        error instanceof ApiError ? error.message : '连接中断，请检查网络后重试',
      );
    }
  })();

  return () => controller.abort();
}

function dispatchFrame(frame: string, handlers: StreamHandlers) {
  let event = 'message';
  const dataLines: string[] = [];

  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) return;

  let data: Record<string, unknown>;
  try {
    data = JSON.parse(dataLines.join('\n'));
  } catch {
    return;
  }

  switch (event) {
    case 'chunk':
      handlers.onChunk(String(data.content ?? ''));
      break;
    case 'title':
      handlers.onTitle?.(data as unknown as { session_id: string; title: string });
      break;
    case 'done':
      handlers.onDone({
        message_id: String(data.message_id ?? ''),
        citations: (data.citations as Citation[]) ?? [],
        warnings: (data.warnings as string[]) ?? [],
      });
      break;
    case 'error':
      handlers.onError?.(String(data.message ?? '生成失败，请重试'));
      break;
    default:
      break;
  }
}
