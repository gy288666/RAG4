import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import MessageBubble from '@/components/MessageBubble';
import Modal from '@/components/Modal';
import SessionSidebar from '@/components/SessionSidebar';
import Spinner, { LoadingBlock } from '@/components/Spinner';
import {
  createSession,
  deleteSession,
  listMessages,
  listSessions,
  renameSession,
  streamQuery,
} from '@/api/chat';
import { toMessage } from '@/api/client';
import { useToast } from '@/context/ToastContext';
import type { Citation, MessageItem, SessionItem } from '@/types';
import { citationLocator } from '@/utils/format';
import { SealMark, SendIcon, MenuIcon } from '@/components/Icons';

export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const toast = useToast();

  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [keyword, setKeyword] = useState('');

  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);

  const [input, setInput] = useState('');
  const [enableRag, setEnableRag] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const abortRef = useRef<(() => void) | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  /** 已在本地持有消息的会话 ID，避免重复拉取覆盖流式渲染中的消息 */
  const loadedSessionRef = useRef<string | null>(null);

  // ---------- 会话列表（标题模糊搜索，300ms 防抖） ----------
  const loadSessions = useCallback(
    async (search: string) => {
      try {
        const data = await listSessions({ keyword: search || undefined, page_size: 50 });
        setSessions(data.items);
      } catch (error) {
        toast.error(toMessage(error, '加载历史会话失败'));
      } finally {
        setSessionsLoading(false);
      }
    },
    [toast],
  );

  useEffect(() => {
    const timer = setTimeout(() => loadSessions(keyword.trim()), keyword ? 300 : 0);
    return () => clearTimeout(timer);
  }, [keyword, loadSessions]);

  // ---------- 历史消息 ----------
  useEffect(() => {
    if (!sessionId) {
      // 回到「新对话」空状态：进行中的流已无处渲染，直接中断
      abortRef.current?.();
      abortRef.current = null;
      setStreaming(false);
      loadedSessionRef.current = null;
      setMessages([]);
      return;
    }

    // 首次提问时会先建会话再跳转，本地已有乐观消息与进行中的 SSE 流。
    // 此时若再从服务端拉取历史，助手消息尚未落库，会把流式占位气泡覆盖掉，
    // 后续 chunk 找不到目标消息，回答就再也渲染不出来。
    if (loadedSessionRef.current === sessionId) return;

    // 切换到其他会话时，中断上一个会话尚未完成的生成
    abortRef.current?.();
    abortRef.current = null;
    setStreaming(false);

    let cancelled = false;
    setMessagesLoading(true);
    listMessages(sessionId)
      .then((data) => {
        if (!cancelled) {
          setMessages(data);
          loadedSessionRef.current = sessionId;
        }
      })
      .catch((error) => {
        if (!cancelled) {
          toast.error(toMessage(error, '加载对话记录失败'));
          navigate('/chat', { replace: true });
        }
      })
      .finally(() => {
        if (!cancelled) setMessagesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, navigate, toast]);

  // 组件卸载时中断未完成的 SSE 连接
  useEffect(() => () => abortRef.current?.(), []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  // ---------- 会话操作 ----------
  const handleCreate = async () => {
    try {
      const data = await createSession();
      setSessions((prev) => [
        {
          session_id: data.session_id,
          title: data.title,
          last_message_preview: '',
          created_at: data.created_at,
          updated_at: data.created_at,
        },
        ...prev,
      ]);
      setSidebarOpen(false);
      navigate(`/chat/${data.session_id}`);
    } catch (error) {
      toast.error(toMessage(error, '创建会话失败'));
    }
  };

  const handleRename = async (id: string, title: string) => {
    try {
      await renameSession(id, title);
      setSessions((prev) =>
        prev.map((s) => (s.session_id === id ? { ...s, title } : s)),
      );
      toast.success('标题已更新');
    } catch (error) {
      toast.error(toMessage(error, '修改标题失败'));
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('确定删除该会话吗？删除后将无法恢复。')) return;
    try {
      await deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.session_id !== id));
      toast.success('会话已删除');
      if (id === sessionId) navigate('/chat', { replace: true });
    } catch (error) {
      toast.error(toMessage(error, '删除会话失败'));
    }
  };

  // ---------- 发送提问 ----------
  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const question = input.trim();
    if (!question || streaming) return;

    // 未选中会话时自动创建，避免用户多点一次
    let targetId = sessionId;
    if (!targetId) {
      try {
        const data = await createSession();
        targetId = data.session_id;
        setSessions((prev) => [
          {
            session_id: data.session_id,
            title: data.title,
            last_message_preview: '',
            created_at: data.created_at,
            updated_at: data.created_at,
          },
          ...prev,
        ]);
        // 新会话的消息完全由本地维护，跳转后不必再向服务端拉取
        loadedSessionRef.current = targetId;
        navigate(`/chat/${targetId}`, { replace: true });
      } catch (error) {
        toast.error(toMessage(error, '创建会话失败'));
        return;
      }
    }

    const pendingId = `local_${Date.now()}`;
    setInput('');
    setStreaming(true);
    setMessages((prev) => [
      ...prev,
      {
        message_id: `${pendingId}_user`,
        role: 'user',
        content: question,
        citations: null,
        created_at: '',
      },
      {
        message_id: pendingId,
        role: 'assistant',
        content: '',
        citations: null,
        created_at: '',
        streaming: true,
      },
    ]);

    const updateAssistant = (patch: Partial<MessageItem>) =>
      setMessages((prev) =>
        prev.map((m) => (m.message_id === pendingId ? { ...m, ...patch } : m)),
      );

    abortRef.current = streamQuery(
      { session_id: targetId, query: question, enable_rag: enableRag },
      {
        onChunk: (delta) =>
          setMessages((prev) =>
            prev.map((m) =>
              m.message_id === pendingId ? { ...m, content: m.content + delta } : m,
            ),
          ),
        // 首轮提问的标题即时同步到侧边栏，无需刷新
        onTitle: ({ session_id, title }) =>
          setSessions((prev) =>
            prev.map((s) => (s.session_id === session_id ? { ...s, title } : s)),
          ),
        onDone: ({ message_id, citations, warnings }) => {
          updateAssistant({
            message_id,
            citations: citations.length ? citations : null,
            warnings,
            streaming: false,
          });
          setStreaming(false);
          abortRef.current = null;
          loadSessions(keyword.trim());
        },
        onError: (message) => {
          updateAssistant({ streaming: false });
          setStreaming(false);
          abortRef.current = null;
          toast.error(message);
        },
      },
    );
  };

  const handleStop = () => {
    abortRef.current?.();
    abortRef.current = null;
    setStreaming(false);
    setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)));
  };

  const sidebar = (
    <SessionSidebar
      sessions={sessions}
      activeId={sessionId ?? null}
      loading={sessionsLoading}
      keyword={keyword}
      onKeywordChange={setKeyword}
      onSelect={(id) => {
        setSidebarOpen(false);
        navigate(`/chat/${id}`);
      }}
      onCreate={handleCreate}
      onRename={handleRename}
      onDelete={handleDelete}
    />
  );

  return (
    <div className="flex h-full">
      <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-white md:block">
        {sidebar}
      </aside>

      {sidebarOpen && (
        <div className="fixed inset-0 z-20 md:hidden">
          <div
            className="absolute inset-0 bg-slate-900/40"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          <div className="animate-fade-in relative h-full w-72 bg-white shadow-xl">{sidebar}</div>
        </div>
      )}

      <section className="flex min-w-0 flex-1 flex-col bg-slate-50">
        <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-3">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100 md:hidden"
            aria-label="打开会话列表"
          >
            <MenuIcon />
          </button>
          <h2 className="min-w-0 flex-1 truncate text-sm font-medium text-slate-700">
            {sessions.find((s) => s.session_id === sessionId)?.title ?? '新对话'}
          </h2>
          <label className="flex shrink-0 cursor-pointer items-center gap-2 text-xs text-slate-500">
            <input
              type="checkbox"
              checked={enableRag}
              onChange={(e) => setEnableRag(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 accent-brand-600 focus:ring-brand-500"
            />
            知识库检索
          </label>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
          {messagesLoading ? (
            <LoadingBlock text="正在加载对话记录…" />
          ) : messages.length === 0 ? (
            <EmptyState enableRag={enableRag} />
          ) : (
            <div className="mx-auto flex max-w-4xl flex-col gap-6">
              {messages.map((message) => (
                <MessageBubble
                  key={message.message_id}
                  message={message}
                  onCitationClick={setActiveCitation}
                />
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <form
          onSubmit={handleSubmit}
          className="border-t border-slate-200 bg-white px-4 py-3"
        >
          <div className="mx-auto flex max-w-4xl items-end gap-2">
            <textarea
              className="field max-h-40 min-h-[2.75rem] flex-1 resize-none py-2.5"
              rows={1}
              // 占位符保持简短，换行快捷键说明放在下方提示行，避免窄屏被截断
              placeholder={enableRag ? '基于我的知识库提问…' : '直接与模型对话…'}
              value={input}
              disabled={streaming}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              aria-label="提问输入框"
            />
            {streaming ? (
              <button type="button" onClick={handleStop} className="btn-ghost h-11 shrink-0">
                <Spinner />
                停止
              </button>
            ) : (
              <button type="submit" className="btn-primary h-11 shrink-0" disabled={!input.trim()}>
                <SendIcon />
                发送
              </button>
            )}
          </div>
          <p className="mx-auto mt-1.5 max-w-4xl text-center text-[11px] text-slate-400">
            Enter 发送，Shift+Enter 换行；回答严格基于检索到的资料生成，若资料不足会明确告知。
          </p>
        </form>
      </section>

      {/* 引用原文展开弹窗（PRD 4.3.4 交互展开） */}
      <Modal
        open={Boolean(activeCitation)}
        title="引用原文"
        size="lg"
        onClose={() => setActiveCitation(null)}
      >
      {activeCitation && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-seal-200 bg-seal-50 px-1 font-mono text-xs font-semibold text-seal-700">
              {activeCitation.index}
            </span>
            <span className="font-medium text-slate-800">{activeCitation.doc_name}</span>
            <span className="font-mono text-slate-400">
              {citationLocator(activeCitation.page, activeCitation.chunk_index)}
            </span>
          </div>
          <p className="whitespace-pre-wrap rounded-md bg-slate-50 p-4 text-sm leading-7 text-slate-700">
            {activeCitation.snippet}
          </p>
        </div>
      )}
      </Modal>
    </div>
  );
}

function EmptyState({ enableRag }: { enableRag: boolean }) {
  const suggestions = [
    '这篇论文的核心创新点是什么？',
    '对比几篇文献中实验设置的差异',
    '总结第三章的主要结论并标注出处',
  ];

  return (
    <div className="mx-auto flex max-w-md flex-col items-center justify-center py-16 text-center">
      <SealMark className="h-12 w-12 rounded-lg" textClassName="text-2xl" />
      <h3 className="heading mt-5 text-lg">开始你的学术问答</h3>
      <p className="mt-2 text-sm leading-6 text-slate-500">
        {enableRag
          ? '系统会在你的专属知识库中语义检索相关片段，并在回答中标注可点击的引用来源。'
          : '当前为纯模型对话模式，不会检索知识库；勾选右上角「知识库检索」可启用溯源问答。'}
      </p>
      <ul className="mt-6 w-full border-t border-slate-200 text-left">
        {suggestions.map((suggestion, index) => (
          <li
            key={suggestion}
            className="flex items-baseline gap-3 border-b border-slate-200 py-2.5 text-sm text-slate-600"
          >
            <span className="font-mono text-xs text-seal-500">0{index + 1}</span>
            {suggestion}
          </li>
        ))}
      </ul>
    </div>
  );
}
