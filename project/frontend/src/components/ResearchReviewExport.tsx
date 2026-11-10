import { useEffect, useRef, useState } from 'react';
import { ApiError, toMessage } from '@/api/client';
import { checkClaimReview, readClaimReview } from '@/api/research';
import { buildReviewFile, type ReviewExportKind } from '@/utils/reviewExport';
import type { ClaimReviewView, ResearchTask } from '@/types/research';

interface Props {
  task: ResearchTask; view: ClaimReviewView; disabled: boolean;
  onBusyChange: (value: boolean) => void; onUncertain: () => void; onReload: () => void;
}
const LABEL = { reviewed: '当前审阅稿', audit: '审阅记录', original: '原机器稿快照' };
const STATUS = { unreviewed: '未审阅', retained: '个人审阅保留', withdrawn: '已撤下' };

export default function ResearchReviewExport({ task, view, disabled, onBusyChange, onUncertain, onReload }: Props) {
  const [busy, setBusy] = useState(false), [blocked, setBlocked] = useState(false);
  const [message, setMessage] = useState(''), [error, setError] = useState('');
  const request = useRef<AbortController | null>(null), inFlight = useRef(false), live = useRef(true);
  const currentView = useRef(view.view_id); currentView.current = view.view_id;
  useEffect(() => { live.current = true; return () => { live.current = false; request.current?.abort(); onBusyChange(false); }; }, [onBusyChange]);
  useEffect(() => { setMessage(''); setError(''); setBlocked(false); }, [view.view_id]);
  async function download(kind: ReviewExportKind) {
    if (inFlight.current || disabled || blocked) return;
    const controller = new AbortController(), expectedView = view.view_id;
    request.current = controller; inFlight.current = true; setBusy(true); onBusyChange(true); setMessage(''); setError('');
    try {
      const fresh = await readClaimReview(task.id, view.task_revision, controller.signal);
      if (!live.current || controller.signal.aborted || currentView.current !== expectedView) return;
      checkClaimReview(fresh, task);
      if (fresh.view_id !== expectedView) throw new ApiError(409, '审阅快照已变化，请重新核对。');
      const file = buildReviewFile(task, fresh, kind);
      const url = URL.createObjectURL(new Blob([file.content], { type: file.type }));
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = file.name;
      document.body.appendChild(anchor);
      try { anchor.click(); } finally { anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
      setMessage(`已导出${LABEL[kind]} · 版本 ${fresh.task_revision}`);
    } catch (caught) {
      if (live.current && !controller.signal.aborted) {
        setBlocked(true); onUncertain();
        setError(caught instanceof ApiError && caught.code === 409 ? '审阅版本已变化，本次未导出。请核对最新审阅。'
          : `${toMessage(caught, '无法核对导出来源')}。本次未导出，请核对最新审阅。`);
      }
    } finally {
      inFlight.current = false;
      if (live.current) { setBusy(false); onBusyChange(false); }
    }
  }
  const unavailable = busy || disabled || blocked;
  return <section className="research-section research-export" aria-label="审阅稿导出与原稿对照">
    <div className="research-section-heading"><h2>保存研究结果</h2><span>当前审阅版本 {view.task_revision}</span></div>
    <p className="research-muted text-xs">只导出已保存的审阅状态，不包含表单中未提交的决定。当前稿保留仍可见的结论和引用；下载前核对来源与版本，个人审阅不等于独立质量验收。</p>
    <div className="research-export-actions">
      <button type="button" className="research-button" disabled={unavailable} onClick={() => { void download('reviewed'); }}>导出当前审阅稿（Markdown）</button>
      <button type="button" className="research-button" disabled={unavailable} onClick={() => { void download('audit'); }}>导出审阅记录（JSON）</button>
    </div>
    <p className="research-muted text-xs">审阅记录包含已撤下材料，仅供追溯，不是当前比较表。</p>
    {busy && <p role="status" className="research-muted mt-4">核对来源并准备下载…</p>}
    {message && <p role="status" className="research-muted mt-4">{message}</p>}
    {error && <div className="research-error" role="alert"><p>{error}</p><button type="button" className="research-button" onClick={onReload}>核对最新审阅</button></div>}
    <details className="research-original">
      <summary>与原机器稿对照（含已撤下内容）</summary>
      <p className="research-muted mt-4 text-xs">原稿 {task.artifact?.citations.length || 0} 条结论；当前审阅稿 {view.artifact.citations.length} 条。以下保留原表述用于对照，不代表当前稿接受这些结论。</p>
      <ul className="research-review-list">{view.items.map((item) => <li key={item.claim.claim_id}>
        <div className="research-review-label"><strong>{task.sources.find((s) => s.document_id === item.claim.document_id)?.title}</strong><span>当前：{STATUS[item.review_status]}</span></div>
        <p>原机器稿：{item.claim.statement}</p>
      </li>)}</ul>
      <button type="button" className="research-button" disabled={unavailable} onClick={() => { void download('original'); }}>导出原机器稿快照（Markdown）</button>
    </details>
  </section>;
}
