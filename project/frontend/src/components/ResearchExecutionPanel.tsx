import { useEffect, useRef, useState } from 'react';
import { ApiError, toMessage } from '@/api/client';
import { runResearchStep, readRetryDecision, prepareResearchRetry } from '@/api/research';
import type { ResearchTask, RetryDecision } from '@/types/research';

const RETRY_REASON = {
  available: '可准备恢复',
  not_failed: '任务状态已变化，请刷新后核对。',
  attempt_not_finished: '检查点不能证明失败尝试已结束，请刷新状态。',
  unaccounted_history: '无法排除旧执行仍在进行，暂不支持恢复此检查点，请保留记录。',
  not_network_failure: '此次错误不属于已识别的网络失败，需要先检查错误与来源。',
  insufficient_budget: '剩余预算不足以覆盖未完成计划，不能恢复，请保留记录。',
};

/** Each click requests one revision-fenced step, never a browser job loop. */
export default function ResearchExecutionPanel({ task, onRefresh }: { task: ResearchTask; onRefresh: () => void }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [retry, setRetry] = useState<RetryDecision | null>(null);
  const lock = useRef(false), mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const running = task.steps.some((s) => s.status === 'running');
  const next = task.steps.find((s) => s.status === 'pending');
  const usesModel = next && ['compare_evidence', 'verify_evidence', 'verify_document'].includes(next.tool_name);
  const hasBudget = task.tool_calls_used < task.budget.max_steps && (!usesModel || task.model_calls_used < task.budget.max_model_calls);
  const executable = ['pending', 'running'].includes(task.status) && !running && Boolean(next) && hasBudget;
  async function run() {
    if (lock.current || !executable || error) return;
    lock.current = true; setBusy(true);
    try {
      const updated = await runResearchStep(task.id, task.revision);
      if (!mounted.current) return;
      if (updated.id !== task.id || updated.revision < task.revision) throw new ApiError(409, '执行响应与当前任务不一致');
      onRefresh();
    } catch (e) {
      if (mounted.current) setError(e instanceof ApiError && e.code === 409
        ? '任务版本已变化或另一个请求正在执行。请刷新状态后再决定下一步。'
        : `${toMessage(e)}。执行可能仍在服务端进行，请先刷新状态，勿直接重试。`);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  async function recovery(prepare: boolean) {
    if (lock.current || task.status !== 'failed' || (prepare && !retry?.eligible)) return;
    lock.current = true; setBusy(true); setError('');
    try {
      if (!prepare) {
        const decision = await readRetryDecision(task.id);
        if (!mounted.current) return;
        if (decision.task_id !== task.id || decision.task_revision !== task.revision
            || (decision.eligible && (!decision.sources_validated || decision.failed_step_id !== task.steps.find((s) => s.status === 'failed')?.id))) {
          throw new ApiError(409, '恢复条件已变化，请刷新');
        }
        setRetry(decision);
      } else {
        const updated = await prepareResearchRetry(task.id, task.revision);
        if (!mounted.current) return;
        if (updated.id !== task.id || updated.status !== 'pending' || updated.revision !== task.revision + 1
            || updated.tool_calls_used !== task.tool_calls_used || updated.model_calls_used !== task.model_calls_used) {
          throw new ApiError(409, '恢复响应与检查点不一致');
        }
        onRefresh();
      }
    } catch (e) {
      if (mounted.current) {
        setRetry(null);
        setError(e instanceof ApiError && e.code === 409 ? '恢复条件或版本已变化，请刷新状态后核对。'
          : prepare ? '恢复请求结果尚未确认，请先刷新状态，不要重复提交。' : toMessage(e, '无法核对恢复条件'));
      }
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section className="research-execution" aria-label="单步执行">
    <div className="research-section-heading"><h2>执行与预算</h2><span>每次点击仅执行一步</span></div>
    <p className="research-muted text-xs">工具 {task.tool_calls_used}/{task.budget.max_steps} 次 · 生成模型 {task.model_calls_used}/{task.budget.max_model_calls} 次 · 上下文上限 {task.budget.max_context_chars} 字符</p>
    {executable && <><p className="mt-3 text-sm">下一步：{next?.objective}</p><p className="research-muted my-3 text-xs">可能调用 Embedding 或生成模型并产生费用；失败尝试也计入预算。离开页面不会停止服务端请求。</p>
      <button className="research-button research-primary" disabled={busy || Boolean(error)} onClick={() => void run()}>{busy ? '正在执行本步…' : '执行下一步'}</button></>}
    {running && <p className="mt-3 text-sm">已保存的步骤仍为执行中。刷新可核对最新状态；本页不会自动重发或恢复该步骤。</p>}
    {!hasBudget && ['pending', 'running'].includes(task.status) && !running && <p className="mt-3 text-sm">剩余预算不足以执行下一步，请保留记录。本页不会追加预算或自动重试。</p>}
    {task.status === 'paused' && <p className="research-muted mt-3 text-xs">当前状态不能直接执行；已有步骤和预算记录保留。本页暂不提供暂停任务的恢复操作。</p>}
    {task.status === 'failed' && <div className="mt-3 text-sm">
      <p className="research-muted mb-3 text-xs">失败任务不能直接执行。仅已结束的网络失败且剩余预算足够时，可先核对来源和恢复条件。</p>
      <button className="research-button" disabled={busy || Boolean(error)} onClick={() => void recovery(false)}>{busy ? '正在处理…' : '核对恢复条件'}</button>
      {retry && <div className="mt-4" role="status">
        {retry.eligible ? <><p>将准备：{task.steps.find((s) => s.id === retry.failed_step_id)?.objective}</p>
          <p>剩余工具 {retry.remaining_tools} 次 / 计划需 {retry.required_tools} 次；剩余生成调用 {retry.remaining_model_calls} 次 / 计划需 {retry.required_model_calls} 次。</p>
          <p className="research-muted my-3 text-xs">来源已复验。恢复保留已用预算、声明和成功报告，仅将失败步骤准备为待执行，不调用模型。之后仍需手动点击“执行下一步”。</p>
          <p className="research-muted my-3 text-xs">本地尝试结束不代表供应商已停止计算，超时后再次执行可能重复计费。</p>
          <button className="research-button" disabled={busy} onClick={() => void recovery(true)}>确认恢复为待执行</button></>
          : <p>{RETRY_REASON[retry.reason]}</p>}
      </div>}
    </div>}
    {Boolean(task.retry_events?.length) && <details className="mt-4 text-xs"><summary>保留的失败尝试 · {task.retry_events?.length}</summary>
      <ol className="research-plan-list">{task.retry_events?.map((event) => <li key={event.failed_revision}>版本 {event.failed_revision} · {event.failed_step.objective} · {event.failed_step.result?.error_type ?? '未知错误'} · {event.failed_step.result?.elapsed_ms ?? 0}ms</li>)}</ol>
    </details>}
    {error && <div role="alert" className="research-error mt-4"><p>{error}</p><button className="research-button" onClick={onRefresh}>核对最新状态</button></div>}
  </section>;
}
