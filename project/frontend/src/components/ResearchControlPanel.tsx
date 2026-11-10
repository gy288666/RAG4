import { useEffect, useRef, useState } from 'react';
import { ApiError } from '@/api/client';
import { controlResearchTask } from '@/api/research';
import type { ResearchTask } from '@/types/research';

export default function ResearchControlPanel({ task, onRefresh }: { task: ResearchTask; onRefresh: () => void }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [confirmCancel, setConfirmCancel] = useState(false);
  const active = useRef(true), lock = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  if (task.status === 'completed' || task.status === 'cancelled') return null;
  const next = task.steps.find((s) => s.status === 'pending');
  const requiresModel = next && ['compare_evidence', 'verify_evidence', 'verify_document'].includes(next.tool_name);
  const canResume = task.status === 'paused' && task.tool_calls_used < task.budget.max_steps
    && (!requiresModel || task.model_calls_used < task.budget.max_model_calls);
  async function control(action: 'pause' | 'resume' | 'cancel') {
    if (lock.current || error || (action === 'resume' && !canResume) || (action === 'cancel' && !confirmCancel)) return;
    lock.current = true; setBusy(true);
    try {
      const result = await controlResearchTask(task.id, task.revision, action);
      if (!active.current) return;
      const expected = { pause: 'paused', resume: 'pending', cancel: 'cancelled' }[action];
      if (result.id !== task.id || result.revision !== task.revision + 1 || result.status !== expected
          || result.model_calls_used !== task.model_calls_used || result.tool_calls_used !== task.tool_calls_used
          || (['max_steps', 'max_model_calls', 'max_context_chars'] as const).some((key) => result.budget[key] !== task.budget[key])) throw new ApiError(409, '控制响应不一致');
      onRefresh();
    } catch (caught) {
      if (active.current) setError(caught instanceof ApiError && caught.code === 409
        ? '任务版本已变化，请核对最新状态后再操作。'
        : '操作结果尚未确认，请核对最新状态，不要重复提交。');
    } finally { lock.current = false; if (active.current) setBusy(false); }
  }
  return <section className="research-section" aria-label="任务控制">
    <div className="research-section-heading"><h2>任务控制</h2><span>版本 {task.revision}</span></div>
    <p className="research-muted text-xs">控制不会执行工具或返还已用预算。暂停/取消会阻止运行中结果继续提交，但不保证立即中断外部请求；继续后仍需手动执行下一步。</p>
    <div className="research-export-actions">
      {['pending', 'running'].includes(task.status) && <button className="research-button" disabled={busy || Boolean(error)} onClick={() => { void control('pause'); }}>暂停任务</button>}
      {task.status === 'paused' && <button className="research-button" disabled={busy || Boolean(error) || !canResume} onClick={() => { void control('resume'); }}>继续为待执行</button>}
      <button className="research-button" disabled={busy || Boolean(error)} onClick={() => setConfirmCancel(true)}>取消任务…</button>
    </div>
    {task.status === 'paused' && !canResume && <p className="research-muted text-xs">剩余预算不足以执行下一步，请保留任务记录。</p>}
    {task.status === 'failed' && <p className="research-muted text-xs">失败恢复请使用下方单步执行区的恢复准入检查。</p>}
    {confirmCancel && <div className="research-notice" role="group" aria-label="确认取消任务">
      <p>取消后不能继续此任务。已有证据和步骤记录保留，已用预算不退回。</p>
      <div className="research-export-actions"><button className="research-button" disabled={busy || Boolean(error)} onClick={() => { void control('cancel'); }}>确认取消任务</button>
        <button className="research-button" disabled={busy} onClick={() => setConfirmCancel(false)}>保留任务</button></div>
    </div>}
    {busy && <p role="status">正在保存任务状态…</p>}
    {error && <div className="research-error" role="alert"><p>{error}</p><button className="research-button" onClick={onRefresh}>核对控制状态</button></div>}
  </section>;
}
