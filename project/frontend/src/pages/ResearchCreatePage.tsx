import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, toMessage } from '@/api/client';
import { createResearchTask, listRetainedVersions, previewResearchTask, readRetainedVersion } from '@/api/research';
import type { ResearchDraft, ResearchPreview, RetainedVersion, VersionDetail } from '@/types/research';
import '@/styles/research.css';

export default function ResearchCreatePage() {
  const navigate = useNavigate();
  const [offset, setOffset] = useState(0), [refresh, setRefresh] = useState(0);
  const [versions, setVersions] = useState<RetainedVersion[]>([]), [total, setTotal] = useState(0);
  const [versionId, setVersionId] = useState(''), [detail, setDetail] = useState<VersionDetail | null>(null);
  const [documents, setDocuments] = useState<string[]>([]), [goal, setGoal] = useState('');
  const [listLoading, setListLoading] = useState(true), [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(''), [listError, setListError] = useState('');
  const [preview, setPreview] = useState<{ data: ResearchPreview; draft: ResearchDraft } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false), [creating, setCreating] = useState(false);
  // The synchronous lock also fences double clicks before React commits disabled.
  const creatingLock = useRef(false), epoch = useRef(0);
  const previewRequest = useRef<AbortController | null>(null);
  const mounted = useRef(true), previewPanel = useRef<HTMLElement>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; previewRequest.current?.abort(); }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true); setListError('');
    listRetainedVersions(offset, controller.signal).then((data) => {
      if (!controller.signal.aborted) { setVersions(data.items); setTotal(data.total); }
    }).catch((e: unknown) => { if (!controller.signal.aborted) setListError(toMessage(e)); })
      .finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [offset, refresh]);
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setDetailLoading(Boolean(versionId));
    if (versionId) readRetainedVersion(versionId, controller.signal).then((data) => {
      if (!controller.signal.aborted) {
        if (data.id !== versionId || data.manifest_integrity !== 'valid') throw new ApiError(409, '版本清单已变化，请重新选择');
        setDetail(data);
      }
    }).catch((e: unknown) => { if (!controller.signal.aborted) setError(toMessage(e)); })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [versionId, refresh]);
  useEffect(() => { if (preview) previewPanel.current?.focus(); }, [preview]);
  function invalidate() {
    epoch.current++; previewRequest.current?.abort(); setPreview(null); setPreviewLoading(false); setError('');
  }
  function chooseVersion(id: string) { invalidate(); setDocuments([]); setDetail(null); setVersionId(id); }
  const valid = detail?.id === versionId && documents.length >= 3 && documents.length <= 5 && goal.trim().length > 0 && goal.length <= 2000;
  async function review() {
    if (!valid || creatingLock.current) return;
    invalidate();
    const generation = epoch.current, controller = new AbortController();
    previewRequest.current = controller; setPreviewLoading(true);
    const draft: ResearchDraft = { index_version_id: versionId, document_ids: documents, goal: goal.trim(),
      plan_version: 'research-comparison-v2', context_policy: 'local-window-v3', candidate_policy: 'source-role-v3',
      extraction_protocol: 'source-handles-v2', response_format: 'text', verification_protocol: 'facet-handles-v5',
      verification_context_policy: 'preceding-children-v1', result_condition_policy: 'explicit-row-v1' };
    try {
      const data = await previewResearchTask(draft, controller.signal);
      if (controller.signal.aborted || generation !== epoch.current) return;
      if (data.index_version_id !== draft.index_version_id || data.goal !== draft.goal || data.task_created !== false
          || data.status !== 'preview' || data.sources.map((s) => s.document_id).join('\n') !== draft.document_ids.join('\n')) {
        throw new ApiError(409, '预览与所选范围不一致，请重新预览');
      }
      setPreview({ data, draft });
    } catch (e) { if (!controller.signal.aborted && generation === epoch.current) setError(toMessage(e)); }
    finally { if (!controller.signal.aborted && generation === epoch.current) setPreviewLoading(false); }
  }
  async function confirm() {
    if (!preview || creatingLock.current) return;
    creatingLock.current = true; setCreating(true); setError('');
    try {
      const task = await createResearchTask(preview.draft, preview.data.preview_id);
      if (mounted.current) navigate(`/research/${encodeURIComponent(task.id)}`, { replace: true });
    } catch (e) {
      if (mounted.current) {
        setPreview(null);
        setError(e instanceof ApiError && e.code === 409 ? '来源、配置或预算已变化，请重新预览后创建。'
          : `${toMessage(e)}。请先返回任务列表确认是否已创建，避免重复提交。`);
      }
    } finally { creatingLock.current = false; if (mounted.current) setCreating(false); }
  }
  return <div className="research-page">
    <header className="research-header"><div><h1>准备文献比较</h1><p>选择保留文献，核对计划，再保存待执行任务。</p></div><Link className="research-button" to="/research">返回阅读台</Link></header>
    <main className="research-create-content">
      <p className="research-notice">创建后任务停留在待执行状态。预览不调用模型；研究结论仍需人工复核。</p>
      {error && <div role="alert" className="research-error"><p>{error}</p><button className="research-button" disabled={creating} onClick={() => { invalidate(); setDocuments([]); setRefresh((v) => v + 1); }}>重新读取来源</button></div>}
      <fieldset disabled={creating}>
        <legend className="research-form-heading">01 / 选择保留版本和 3–5 篇文献</legend>
        <p className="research-muted mb-4 text-xs">版本清单仅表示历史记录完整；预览时会重新校验来源和索引。选择不会激活或重建索引。</p>
        {listLoading ? <p role="status">读取版本…</p> : listError ? <div role="alert">{listError}<button className="research-button" onClick={() => setRefresh((v) => v + 1)}>重读版本</button></div>
          : !versions.length ? <p className="research-empty">尚无可选择的保留版本。请先完成文献索引准备；上传文献可前往<Link to="/knowledge" className="underline">知识库</Link>。</p>
          : <div className="research-version-list">{versions.map((v) => <label key={v.id}>
            <input type="radio" name="version" value={v.id} checked={v.id === versionId} disabled={v.manifest_integrity !== 'valid' || (v.document_count ?? 0) < 3}
              onChange={() => chooseVersion(v.id)} />
            <span><strong>{v.created_at} · {v.document_count ?? '未知'} 篇文献{v.is_active ? ' · 当前使用' : ''}</strong><small>{v.id}{v.manifest_integrity !== 'valid' ? ' · 清单损坏' : (v.document_count ?? 0) < 3 ? ' · 不足三篇' : ''}</small></span>
          </label>)}</div>}
        <div className="research-form-pagination"><button className="research-button" disabled={!offset || listLoading} onClick={() => setOffset((v) => Math.max(0, v - 8))}>上一页版本</button>
          <span>第 {offset / 8 + 1} 页 · {total} 个版本</span><button className="research-button" disabled={offset + 8 >= total || listLoading} onClick={() => setOffset((v) => v + 8)}>下一页版本</button></div>
        {detailLoading && <p role="status">读取文献清单…</p>}
        {detail?.id === versionId && <fieldset className="research-document-list"><legend>已选 {documents.length}/5 篇文献</legend>{detail.documents?.map((doc) => <label key={doc.id}>
          <input type="checkbox" checked={documents.includes(doc.id)} disabled={!documents.includes(doc.id) && documents.length >= 5}
            onChange={(e) => { invalidate(); setDocuments((old) => e.target.checked ? [...old, doc.id] : old.filter((id) => id !== doc.id)); }} /><span>{doc.file_name}</span>
        </label>)}</fieldset>}
        <label className="research-form-heading mt-8 block" htmlFor="research-goal">02 / 研究目标</label>
        <textarea id="research-goal" className="research-goal-input" rows={4} maxLength={2000} value={goal}
          onChange={(e) => { invalidate(); setGoal(e.target.value); }} placeholder="例如：比较所选论文的方法、数据集、结果和局限，注明实验条件并列出证据缺口。" />
        <p className="research-muted mt-2 text-xs">{goal.length}/2000 字符 · 不作跨论文直接性能排名</p>
        <button className="research-button mt-4" disabled={!valid || previewLoading} onClick={() => void review()}>{previewLoading ? '正在校验来源…' : '校验来源并预览计划'}</button>
      </fieldset>
      {preview && <section ref={previewPanel} tabIndex={-1} className="research-preview" aria-label="待确认研究计划">
        <h2 className="research-form-heading">03 / 核对计划</h2><p className="mt-4">{preview.data.goal}</p>
        <p className="research-muted mt-3 text-xs">{preview.data.sources.length} 篇文献 · {preview.data.steps.length} 步 · 模型 {preview.data.model_id}</p>
        <p className="mt-3 text-sm">预算上限：{preview.data.budget.max_steps} 次工具执行、{preview.data.budget.max_model_calls} 次模型调用、每次上下文 {preview.data.budget.max_context_chars} 字符。失败重试也占用预算，实际费用取决于模型。</p>
        <details className="mt-4"><summary>查看固定步骤与策略</summary><ol className="research-plan-list">{preview.data.steps.map((s) => <li key={s.id}>{s.objective}</li>)}</ol>
          <p className="research-muted text-xs">逐篇核验 v2 / 来源角色召回 v3 / 分面引用 v5 / 前文补充 / 显式实验条件。质量门槛尚未通过。</p></details>
        <p className="research-muted my-4 text-xs">创建时再次检查来源及预览摘要。此操作只保存 pending 任务，不执行工具或请求模型。</p>
        <button className="research-button research-primary" disabled={creating} onClick={() => void confirm()}>{creating ? '正在保存…' : '确认创建待执行任务'}</button>
      </section>}
    </main>
  </div>;
}
