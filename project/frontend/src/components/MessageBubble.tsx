import { Fragment, type ReactNode } from 'react';
import type { Citation, MessageItem } from '@/types';
import { WARNING_LABELS, citationLocator, splitAnswer } from '@/utils/format';
import { SealMark } from '@/components/Icons';

interface Props {
  message: MessageItem;
  onCitationClick: (citation: Citation) => void;
}

/**
 * 把答案正文中的 [1]、[2] 数字标记渲染为可点击的角标（PRD 4.3.4）。
 * 印章朱 + 等宽数字是全站的「溯源签名」：所有引用标记共用同一套样式。
 * 未命中引用列表的标记按纯文本原样保留。
 */
function renderWithMarkers(
  text: string,
  citations: Citation[],
  onCitationClick: (citation: Citation) => void,
) {
  const parts = text.split(/(\[\d+\])/g);
  const nodes: ReactNode[] = [];
  parts.forEach((part, index) => {
    const matched = /^\[(\d+)\]$/.exec(part);
    if (!matched) {
      nodes.push(<Fragment key={index}>{part}</Fragment>);
      return;
    }
    const citation = citations.find((c) => c.index === Number(matched[1]));
    if (!citation) {
      nodes.push(<Fragment key={index}>{part}</Fragment>);
      return;
    }
    const marker = (
      <button
        type="button"
        onClick={() => onCitationClick(citation)}
        title={`查看来源：${citation.doc_name}`}
        className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded border border-seal-200
                   bg-seal-50 px-1 align-baseline font-mono text-xs font-semibold text-seal-700
                   transition hover:bg-seal-100"
      >
        {matched[1]}
      </button>
    );
    // 行内原子元素会绕过中文避头尾规则，紧跟的句读会落到行首；
    // 把角标与紧随的一个标点绑进 nowrap 组，让二者作为一个整体换行。
    const next = parts[index + 1];
    if (next && /^[。，、；：）」』！？.，;:)!?]/.test(next)) {
      parts[index + 1] = next.slice(1);
      nodes.push(
        <span key={index} className="whitespace-nowrap">
          {marker}
          {next.charAt(0)}
        </span>,
      );
    } else {
      nodes.push(<Fragment key={index}>{marker}</Fragment>);
    }
  });
  return nodes;
}

export default function MessageBubble({ message, onCitationClick }: Props) {
  const isUser = message.role === 'user';
  const citations = message.citations ?? [];
  const { body, references } = isUser
    ? { body: message.content, references: '' }
    : splitAnswer(message.content);

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {isUser ? (
        <span
          aria-hidden="true"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand-600 font-serif text-sm text-white"
        >
          我
        </span>
      ) : (
        <SealMark className="h-8 w-8 rounded-md" textClassName="text-sm" />
      )}

      <div className={`min-w-0 max-w-[min(46rem,88%)] ${isUser ? 'items-end' : ''}`}>
        <div
          className={`whitespace-pre-wrap break-words rounded-lg px-4 py-3 text-sm leading-7 ${
            isUser ? 'bg-brand-600 text-white' : 'card text-slate-800'
          } ${message.streaming ? 'streaming-caret' : ''}`}
        >
          {isUser ? body : renderWithMarkers(body, citations, onCitationClick)}
        </div>

        {/* 降级告警 [M-6] */}
        {message.warnings?.map((warning) => (
          <p
            key={warning}
            className="mt-2 rounded-md bg-ochre-50 px-3 py-2 text-xs text-ochre-700"
          >
            {WARNING_LABELS[warning] ?? warning}
          </p>
        ))}

        {/* 引用溯源卡片：点击展开原文（PRD 4.3.4） */}
        {citations.length > 0 && (
          <div className="mt-3">
            <p className="mb-1.5 text-xs font-medium text-slate-400">参考来源</p>
            <ul className="space-y-1.5">
              {citations.map((citation) => (
                <li key={citation.index}>
                  <button
                    type="button"
                    onClick={() => onCitationClick(citation)}
                    className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-left
                               transition hover:border-seal-300 hover:bg-seal-50"
                  >
                    <span className="flex items-center gap-2">
                      <span className="flex h-4 min-w-4 items-center justify-center rounded-sm border border-seal-200 bg-seal-50 px-1 font-mono text-[10px] font-semibold text-seal-700">
                        {citation.index}
                      </span>
                      <span className="truncate text-xs font-medium text-slate-700">
                        {citation.doc_name}
                      </span>
                      <span className="shrink-0 font-mono text-[11px] text-slate-400">
                        {citationLocator(citation.page, citation.chunk_index)}
                      </span>
                    </span>
                    <span className="mt-1 line-clamp-2 block text-xs text-slate-500">
                      {citation.snippet}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 模型自带的纯文本来源清单：仅在生成结束且没有结构化引用时兜底展示。
            生成过程中不显示——此时 done 帧尚未到达，展示它会在切换为引用卡片时闪烁。 */}
        {!message.streaming && !citations.length && references && (
          <pre className="mt-2 whitespace-pre-wrap rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600">
            {references}
          </pre>
        )}
      </div>
    </div>
  );
}
