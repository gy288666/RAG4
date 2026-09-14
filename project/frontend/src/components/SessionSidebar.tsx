import { useState } from 'react';
import type { SessionItem } from '@/types';
import { SkeletonRows } from '@/components/Spinner';
import { EditIcon, PlusIcon, TrashIcon } from '@/components/Icons';
import { formatRelativeTime } from '@/utils/format';

interface Props {
  sessions: SessionItem[];
  activeId: string | null;
  loading: boolean;
  keyword: string;
  onKeywordChange: (value: string) => void;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
  onRename: (sessionId: string, title: string) => Promise<void>;
  onDelete: (sessionId: string) => void;
}

export default function SessionSidebar({
  sessions,
  activeId,
  loading,
  keyword,
  onKeywordChange,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');

  const startEditing = (session: SessionItem) => {
    setEditingId(session.session_id);
    setDraftTitle(session.title);
  };

  const commitRename = async (sessionId: string) => {
    const title = draftTitle.trim();
    setEditingId(null);
    if (title && title !== sessions.find((s) => s.session_id === sessionId)?.title) {
      await onRename(sessionId, title);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 border-b border-slate-200 p-3">
        <button type="button" onClick={onCreate} className="btn-primary w-full">
          <PlusIcon />
          新建对话
        </button>
        <input
          type="search"
          className="field"
          placeholder="搜索历史对话标题…"
          value={keyword}
          onChange={(e) => onKeywordChange(e.target.value)}
          aria-label="搜索历史对话"
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <SkeletonRows rows={5} />
        ) : sessions.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-slate-400">
            {keyword ? '没有匹配的历史对话' : '还没有对话，点击上方新建开始提问'}
          </p>
        ) : (
          <ul className="space-y-0.5 p-2">
            {sessions.map((session) => {
              const isActive = session.session_id === activeId;
              return (
                <li key={session.session_id}>
                  <div
                    className={`group relative rounded-lg px-3 py-2.5 transition ${
                      isActive ? 'bg-brand-50 ring-1 ring-brand-200' : 'hover:bg-slate-100'
                    }`}
                  >
                    {editingId === session.session_id ? (
                      <input
                        autoFocus
                        className="field py-1 text-sm"
                        value={draftTitle}
                        maxLength={255}
                        onChange={(e) => setDraftTitle(e.target.value)}
                        onBlur={() => commitRename(session.session_id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') commitRename(session.session_id);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        aria-label="编辑会话标题"
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => onSelect(session.session_id)}
                        className="block w-full text-left"
                      >
                        <span
                          className={`block truncate pr-12 text-sm font-medium ${
                            isActive ? 'text-brand-700' : 'text-slate-700'
                          }`}
                        >
                          {session.title}
                        </span>
                        <span className="mt-0.5 block truncate pr-12 text-xs text-slate-400">
                          {session.last_message_preview || '暂无消息'}
                        </span>
                        <span className="mt-0.5 block text-[11px] text-slate-300">
                          {formatRelativeTime(session.updated_at)}
                        </span>
                      </button>
                    )}

                    {editingId !== session.session_id && (
                      <div className="absolute right-2 top-2 flex gap-0.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                        <button
                          type="button"
                          onClick={() => startEditing(session)}
                          title="重命名"
                          aria-label="重命名会话"
                          className="rounded p-1 text-slate-400 hover:bg-white hover:text-brand-600"
                        >
                          <EditIcon className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onDelete(session.session_id)}
                          title="删除"
                          aria-label="删除会话"
                          className="rounded p-1 text-slate-400 hover:bg-white hover:text-rose-600"
                        >
                          <TrashIcon className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
