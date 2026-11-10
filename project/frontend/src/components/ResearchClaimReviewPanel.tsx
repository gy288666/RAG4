import { useEffect, useRef, useState } from 'react';
import { ApiError, toMessage } from '@/api/client';
import { checkClaimReview, recordClaimReview } from '@/api/research';
import type { ClaimReviewDecision, ClaimReviewItem, ClaimReviewView, ResearchTask } from '@/types/research';

const STATUS = { unreviewed: '未审阅', retained: '已保留', withdrawn: '已撤下' };
const DECISION = { retain: '保留', withdraw: '撤下', reset: '重置为未审阅' };
const FACET = { method: '方法', dataset: '数据集', result: '结果', limitation: '局限' };
interface Props {
  task: ResearchTask; view: ClaimReviewView; onSaved: (view: ClaimReviewView) => void; onReload: () => void;
  onUncertain: () => void;
  disabled: boolean; onBusyChange: (value: boolean) => void;
  onSource: (item: ClaimReviewItem, event: React.MouseEvent<HTMLButtonElement>) => void;
}

export default function ResearchClaimReviewPanel({ task, view, onSaved, onReload, onSource, onUncertain, disabled, onBusyChange }: Props) {
  const [claimId, setClaimId] = useState('');
  const [decision, setDecision] = useState<ClaimReviewDecision>('withdraw');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [locked, setLocked] = useState(false);
  const inFlight = useRef(false), live = useRef(true);
  const draftRevision = useRef<number | null>(null);
  useEffect(() => { live.current = true; return () => { live.current = false; onBusyChange(false); }; }, [onBusyChange]);
  useEffect(() => { setClaimId(''); setReason(''); setLocked(false); setError(''); }, [view.view_id]);
  const titles = new Map(task.sources.map((s) => [s.document_id, s.title]));
  const selected = view.items.find((item) => item.claim.claim_id === claimId);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (inFlight.current || locked || disabled || draftRevision.current !== view.task_revision || !selected || !reason.trim() || reason.length > 1000) return;
    draftRevision.current = null;
    inFlight.current = true; setBusy(true); onBusyChange(true); setError('');
    try {
      const updated = await recordClaimReview(task.id, claimId, view.task_revision, view.source_artifact_id, decision, reason);
      if (!live.current) return;
      checkClaimReview(updated, task, view.task_revision + 1);
      const last = updated.events[updated.events.length - 1];
      if (!last || last.claim_id !== claimId || last.decision !== decision || last.reason !== reason
          || last.task_revision !== updated.task_revision) throw new ApiError(409, '返回的审阅记录不一致，请核对最新状态。');
      onSaved(updated);
    } catch (caught) {
      if (live.current) {
        onUncertain();
        setLocked(true);
        setError(caught instanceof ApiError && caught.code === 409 ? '审阅版本已变化。请先核对最新审阅，再决定是否提交。'
          : `${toMessage(caught, '审阅未能保存')}。保存结果尚未确认，请核对最新审阅，避免重复提交。`);
      }
    } finally { inFlight.current = false; if (live.current) { setBusy(false); onBusyChange(false); } }
  }
  return <details className="research-section research-review" aria-label="结论审阅">
    <summary>结论审阅 · {view.items.filter((i) => i.review_status === 'withdrawn').length} 条撤下 · {view.items.filter((i) => i.review_status === 'unreviewed').length} 条未审阅</summary>
    <p className="research-muted mt-4 text-xs">个人审阅记录不等同于独立质量验收。原机器稿保留；撤下仅影响当前比较表，重置会恢复为未审阅并保留历史。</p>
    <ul className="research-review-list">{view.items.map((item, index) => <li key={item.claim.claim_id} data-review-status={item.review_status}>
      <div className="research-review-label"><strong>{String(index + 1).padStart(2, '0')} / {titles.get(item.claim.document_id)} · {FACET[item.claim.facet]}</strong><span>{STATUS[item.review_status]}</span></div>
      <p>{item.claim.statement}</p>
      <button type="button" className="research-cite" onClick={(e) => onSource(item, e)}>核对原文 {index + 1}</button>
      {view.events.some((e) => e.claim_id === item.claim.claim_id) && <details className="research-review-history"><summary>审阅历史</summary>
        <ol>{view.events.filter((e) => e.claim_id === item.claim.claim_id).map((e) => <li key={e.event_id}>
          <p><strong>{DECISION[e.decision]}</strong> · <time dateTime={e.reviewed_at}>{new Date(e.reviewed_at).toLocaleString('zh-CN')}</time></p><p>{e.reason}</p>
        </li>)}</ol>
      </details>}
    </li>)}</ul>
    {!view.items.length && <p className="research-muted">没有可审阅的已入稿结论。审阅不会把证据不足的候选提升为结论。</p>}
    {view.items.length > 0 && <form className="research-review-form" onSubmit={(e) => { void save(e); }} aria-label="记录结论审阅">
      <fieldset disabled={busy || locked || disabled}>
        <label htmlFor="review-claim">选择结论</label><select id="review-claim" value={claimId} onChange={(e) => { draftRevision.current = view.task_revision; setClaimId(e.target.value); }} required>
          <option value="">请选择要核对的结论</option>{view.items.map((item, i) => <option key={item.claim.claim_id} value={item.claim.claim_id}>{i + 1}. {titles.get(item.claim.document_id)} · {FACET[item.claim.facet]}</option>)}
        </select>
        {selected && <p className="research-review-selected">{selected.claim.statement} <span>（{STATUS[selected.review_status]}）</span></p>}
        <label htmlFor="review-decision">审阅决定</label><select id="review-decision" value={decision} onChange={(e) => { draftRevision.current = view.task_revision; setDecision(e.target.value as ClaimReviewDecision); }}>
          <option value="withdraw">撤下这条结论</option><option value="retain">保留这条结论</option><option value="reset">重置为未审阅</option>
        </select>
        <label htmlFor="review-reason">审阅原因</label><textarea id="review-reason" rows={3} maxLength={1000} required value={reason} onChange={(e) => { draftRevision.current = view.task_revision; setReason(e.target.value); }} placeholder="说明引用覆盖了什么，或缺少哪部分依据。" />
        <div className="research-review-actions"><span>{reason.length}/1000</span><button className="research-button" type="submit" disabled={!selected || !reason.trim()}>{busy ? '正在保存审阅…' : '保存审阅决定'}</button></div>
      </fieldset>
    </form>}
    {error && <div className="research-error" role="alert"><p>{error}</p><button type="button" className="research-button" onClick={onReload}>核对最新审阅</button></div>}
  </details>;
}
