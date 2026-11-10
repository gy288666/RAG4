import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError, toMessage } from '@/api/client';
import { checkClaimReview, listResearchTasks, readClaimReview, readPartialArtifact, readResearchTask } from '@/api/research';
import Spinner from '@/components/Spinner';
import ResearchExecutionPanel from '@/components/ResearchExecutionPanel';
import ResearchClaimReviewPanel from '@/components/ResearchClaimReviewPanel';
import ResearchReviewExport from '@/components/ResearchReviewExport';
import ResearchControlPanel from '@/components/ResearchControlPanel';
import type { ClaimReviewView, Facet, PartialArtifactView, ResearchArtifact, ResearchClaim, ResearchSource, ResearchSummary, ResearchTask } from '@/types/research';
import '@/styles/research.css';

const PAGE_SIZE = 8;
const STATUS = { pending: '待执行', running: '执行中', paused: '已暂停', completed: '执行结束', failed: '执行失败', cancelled: '已取消' };
const STEP_STATUS = { pending: '待执行', running: '执行中', succeeded: '已完成', failed: '失败', cancelled: '已取消' };
const FACETS: [Facet, string][] = [['method', '方法'], ['dataset', '数据集'], ['result', '结果'], ['limitation', '局限']];
const CELL_STATUS = { missing: '未检出证据', uncertain: '待核验', conflict: '证据冲突' };
interface ActiveSource { claim: ResearchClaim; source?: ResearchSource; title: string }

function pageLabel(source?: ResearchSource) {
  if (source?.page_start == null) return '页码未记录';
  return source.page_end != null && source.page_end !== source.page_start
    ? `文献第 ${source.page_start}–${source.page_end} 页` : `文献第 ${source.page_start} 页`;
}

export default function ResearchPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [items, setItems] = useState<ResearchSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [task, setTask] = useState<ResearchTask | null>(null);
  const [taskLoading, setTaskLoading] = useState(false);
  const [taskError, setTaskError] = useState('');
  const [partial, setPartial] = useState<PartialArtifactView | null>(null);
  const [partialLoading, setPartialLoading] = useState(false);
  const [partialError, setPartialError] = useState('');
  const [review, setReview] = useState<ClaimReviewView | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState('');
  const [reviewNotice, setReviewNotice] = useState('');
  const [reviewUncertain, setReviewUncertain] = useState(false);
  const [reviewWriting, setReviewWriting] = useState(false), [exporting, setExporting] = useState(false);
  const currentTask = useRef<ResearchTask | null>(null);
  const [source, setSource] = useState<ActiveSource | null>(null);
  const sourcePanel = useRef<HTMLElement>(null);
  const sourceTrigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true); setListError(''); setItems([]);
    listResearchTasks(offset, PAGE_SIZE, controller.signal).then((data) => {
      if (!controller.signal.aborted) { setItems(data.items); setTotal(data.total); }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setListError(toMessage(error, '无法读取研究任务'));
    }).finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [offset, refresh]);

  useEffect(() => {
    if (!taskId && items.length) navigate(`/research/${encodeURIComponent(items[0].id)}`, { replace: true });
  }, [items, taskId, navigate]);

  useEffect(() => {
    const controller = new AbortController();
    setTask(null); setPartial(null); setReview(null); setSource(null); setTaskError(''); setPartialError(''); setReviewError(''); setReviewNotice(''); setReviewLoading(false); setReviewUncertain(false);
    setPartialLoading(false); setTaskLoading(Boolean(taskId));
    if (taskId) void (async () => {
      try {
        const loaded = await readResearchTask(taskId, controller.signal);
        if (controller.signal.aborted) return;
        if (loaded.id !== taskId) throw new ApiError(409, '任务信息已变化，请刷新后重读');
        setTask(loaded); setTaskLoading(false);
        if (loaded.status === 'completed' && loaded.artifact) {
          setReviewLoading(true);
          try {
            const view = await readClaimReview(loaded.id, loaded.revision, controller.signal);
            if (controller.signal.aborted) return;
            checkClaimReview(view, loaded); setReview(view);
          } catch (error) {
            if (!controller.signal.aborted) setReviewError(error instanceof ApiError && error.code === 409
              ? '审阅版本已变化，请刷新任务后重新核对。' : toMessage(error, '无法核对审阅与来源，请刷新后重读。'));
          } finally { if (!controller.signal.aborted) setReviewLoading(false); }
        }
        if (loaded.status === 'failed' && !loaded.artifact && !loaded.verification) {
          setPartialLoading(true);
          try {
            const view = await readPartialArtifact(loaded.id, loaded.revision, controller.signal);
            if (controller.signal.aborted) return;
            if (view.task_id !== loaded.id || view.task_revision !== loaded.revision || view.artifact.corpus_id !== loaded.corpus_id
                || view.source_task_status !== 'failed' || view.task_marked_completed || view.artifact_attached_to_task) {
              throw new ApiError(409, '稿件与任务版本不一致，请刷新后重读');
            }
            setPartial(view);
          } catch (error) {
            if (!controller.signal.aborted) setPartialError(error instanceof ApiError && error.code === 409
              ? '任务版本或状态已变化，请刷新任务后重读。' : toMessage(error, '部分稿暂时无法读取，来源可能已变化。'));
          } finally { if (!controller.signal.aborted) setPartialLoading(false); }
        }
      } catch (error) {
        if (!controller.signal.aborted) setTaskError(toMessage(error, '无法读取该任务'));
      } finally { if (!controller.signal.aborted) setTaskLoading(false); }
    })();
    return () => controller.abort();
  }, [taskId, refresh]);

  useEffect(() => {
    if (source) { sourcePanel.current?.focus(); sourcePanel.current?.scrollIntoView({ block: 'nearest' }); }
  }, [source]);

  const selected = task?.id === taskId ? task : null;
  currentTask.current = selected;
  const artifact = selected ? (selected.status === 'completed' ? (!reviewUncertain && review?.task_id === selected.id ? review.artifact : null)
    : partial?.task_id === selected.id ? partial.artifact : selected.artifact) : null;
  const reload = () => { setTask(null); setPartial(null); setReview(null); setSource(null); setRefresh((v) => v + 1); };
  const acceptReview = (updated: ClaimReviewView) => {
    const present = currentTask.current;
    if (!present || present.id !== updated.task_id || present.revision >= updated.task_revision) return;
    setReview(updated); setReviewUncertain(false); setSource(null); setReviewNotice('审阅决定已保存。比较表已按最新审阅更新，原机器稿保留。');
    setTask({ ...present, revision: updated.task_revision, claim_reviews: updated.events });
    setItems((rows) => rows.map((row) => row.id === updated.task_id ? { ...row, revision: updated.task_revision } : row));
  };
  const openSource = (claim: ResearchClaim, title: string, event: React.MouseEvent<HTMLButtonElement>, data: ResearchArtifact) => {
    sourceTrigger.current = event.currentTarget;
    setSource({ claim, title, source: data.citation_sources?.find((s) => s.claim_id === claim.claim_id) });
  };
  const closeSource = () => { setSource(null); if (sourceTrigger.current?.isConnected) sourceTrigger.current.focus(); };

  return <div className="research-page">
    <header className="research-header">
      <div><h1>研究阅读台</h1><p>查看已保存任务，核对结论与来源。</p></div>
      <div className="flex flex-wrap gap-2"><Link className="research-button" to="/research/new">准备新研究</Link><button type="button" className="research-button" onClick={reload} disabled={listLoading || taskLoading || partialLoading || reviewLoading}>刷新任务</button></div>
    </header>
    <div className="research-grid">
      <aside className="research-catalog" aria-label="我的研究任务">
        <div className="research-catalog-heading"><h2>研究任务</h2><span>{total} 条记录</span></div>
        {listLoading ? <div className="research-loading" role="status"><Spinner />读取目录…</div>
          : listError ? <div className="research-empty" role="alert">{listError}<br /><button className="research-button" onClick={reload}>重试读取</button></div>
          : <ul className="research-task-list">{items.map((item, index) => <li key={item.id}>
            <Link to={`/research/${encodeURIComponent(item.id)}`} className="research-task-link" aria-current={item.id === taskId ? 'page' : undefined}>
              <strong>{item.goal_preview || `研究记录 ${String(offset + index + 1).padStart(2, '0')}`}</strong>
              <span className="research-task-meta"><span>{STATUS[item.status] ?? '未知状态'}</span><span>版本 {item.revision}</span></span>
            </Link>
          </li>)}{!items.length && <li className="research-empty">尚无已保存的研究任务。</li>}</ul>}
        <div className="research-pagination">
          <button className="research-button" aria-label="上一页任务" disabled={offset === 0 || listLoading} onClick={() => setOffset((v) => Math.max(0, v - PAGE_SIZE))}>上一页</button>
          <span>第 {Math.floor(offset / PAGE_SIZE) + 1} 页</span>
          <button className="research-button" aria-label="下一页任务" disabled={offset + PAGE_SIZE >= total || listLoading} onClick={() => setOffset((v) => v + PAGE_SIZE)}>下一页</button>
        </div>
      </aside>

      <main className="research-content" aria-label="研究任务详情" aria-busy={taskLoading || partialLoading || reviewLoading}>
        {taskLoading && <div className="research-loading" role="status"><Spinner />读取任务…</div>}
        {taskError && <div className="research-error" role="alert"><strong>无法读取该任务</strong><p>{taskError}</p><button className="research-button" onClick={reload}>重试读取</button></div>}
        {!taskId && !listLoading && <div className="research-empty"><h2 className="research-goal">从一份已有研究记录开始</h2><p>这里用于阅读已保存的任务与来源。你也可以继续在<Link to="/knowledge" className="underline">知识库</Link>整理文献。</p></div>}
        {selected && <>
          <h2 className="research-goal">{selected.goal}</h2>
          <div className="research-context"><span>{STATUS[selected.status] ?? '未知状态'}</span><span>已保存版本 {selected.revision}</span><span>{selected.sources.length} 篇文献</span></div>
          <div className="research-notice" role="note">
            <strong>{selected.status === 'failed' ? '任务未完成，保留内容仍可供核查' : selected.status === 'completed' ? '执行已结束，结论仍需人工复核' : '查看当前已保存的进度'}</strong>
            <p>{selected.status === 'failed' ? '部分稿只展示已保留的核验结果，未完成或证据不足的内容继续标为待核验。' : '比较表不作跨论文性能排名，机器判断不等同于人工确认。'}</p>
          </div>

          <ResearchControlPanel key={`control-${selected.id}:${selected.revision}`} task={selected} onRefresh={reload} />
          <ResearchExecutionPanel key={`${selected.id}:${selected.revision}`} task={selected} onRefresh={reload} />
          <details className="research-section">
            <summary className="cursor-pointer">计划与步骤 · {selected.steps.filter((s) => s.status === 'succeeded').length}/{selected.steps.length} 已完成</summary>
            <ol className="research-steps">{selected.steps.map((step, index) => <li key={step.id} data-status={step.status}>
              <span className="research-step-number">{String(index + 1).padStart(2, '0')}</span>
              <div><p>{step.objective}</p>{step.result?.error_type && <details><summary>诊断详情</summary><pre>{[step.result.error_type, step.result.error_code, ...step.result.warnings].filter(Boolean).join('\n')}</pre></details>}</div>
              <span className="research-step-status">{STEP_STATUS[step.status] ?? '未知'}{step.result && <span className="block text-right text-[11px]">{(step.result.elapsed_ms / 1000).toFixed(1)}s</span>}</span>
            </li>)}</ol>
          </details>

          <section className="research-section" aria-label="比较产物">
            <div className="research-section-heading"><h2>{partial ? '失败任务的部分比较稿' : '已保存的比较产物'}</h2><span>待人工复核</span></div>
            {partialLoading && <div className="research-loading" role="status"><Spinner />核对来源并读取部分稿…</div>}
            {partialError && <div className="research-error" role="alert"><p>{partialError}</p><button className="research-button" onClick={reload}>刷新后重读</button></div>}
            {reviewLoading && <div className="research-loading" role="status"><Spinner />核对来源并读取结论审阅…</div>}
            {reviewError && <div className="research-error" role="alert"><p>{reviewError}</p><p>无法确认最新审阅，暂不展示比较表。</p><button className="research-button" onClick={reload}>刷新后重读</button></div>}
            {reviewNotice && <p className="research-notice" role="status">{reviewNotice}</p>}
            {reviewUncertain && <p className="research-notice">当前审阅结果待核对，暂不展示比较表。请核对最新审阅。</p>}
            {artifact && <>
              <p className="research-muted mb-4 text-xs">展示 {artifact.citations.length} 条已有结论 · {artifact.knowledge_gaps.length} 个待核验单元格{review ? ' · 按当前审阅展示，来源已复验' : partial ? ' · 来源已在本次读取中复验' : ' · 引用为任务保存时的快照'}</p>
              <div className="research-table-wrap"><table className="research-table">
                <caption className="sr-only">文献方法、数据集、结果与局限比较。已有结论均需人工复核。</caption>
                <thead><tr><th scope="col">文献</th>{FACETS.map(([facet, label]) => <th key={facet} scope="col">{label}</th>)}</tr></thead>
                <tbody>{artifact.rows.map((row) => <tr key={row.document_id}><th scope="row">{row.title}</th>{FACETS.map(([facet]) => {
                  const cell = row.cells.find((c) => c.facet === facet);
                  const unverified = partial?.unverified_documents.includes(row.document_id) ?? false;
                  const withdrawn = review?.items.some((item) => item.claim.document_id === row.document_id && item.claim.facet === facet && item.review_status === 'withdrawn') ?? false;
                  return <td key={facet}>{cell?.status === 'supported' && cell.statement ? <><p>{cell.statement}</p>{cell.claim_ids.map((id) => {
                    const claim = artifact.citations.find((c) => c.claim_id === id);
                    return claim ? <button key={id} type="button" className="research-cite" onClick={(e) => openSource(claim, row.title, e, artifact)}>查看引文 {artifact.citations.indexOf(claim) + 1}</button> : <span key={id} className="research-muted">原文定位缺失</span>;
                  })}</> : <><span className="research-muted">{withdrawn ? '已撤下' : unverified ? '未完成核验' : cell && cell.status !== 'supported' ? CELL_STATUS[cell.status] : '待核验'}</span>{(unverified || Boolean(cell?.reasons.length)) && <details className="research-reasons"><summary>查看原因</summary>{unverified ? <p>尚无完整核验报告。请先查看任务步骤，不能据此判断论文是否报告相关内容。</p> : cell?.reasons.map((reason, i) => <p key={i}>{reason === 'owner_review_withdrawn' ? '这条结论已由你撤下。可在结论审阅中查看原因和历史。' : reason}</p>)}</details>}</>}</td>;
                })}</tr>)}</tbody>
              </table></div>
              {partial && partial.unverified_documents.length > 0 && <p className="research-muted mt-4 text-xs">尚未提交完整核验报告：{selected.sources.filter((s) => partial.unverified_documents.includes(s.document_id)).map((s) => s.title).join('、')}</p>}
            </>}
            {!artifact && !partialLoading && !partialError && !reviewLoading && !reviewError && !reviewUncertain && <p className="research-empty">当前记录没有可读取的比较稿。可展开步骤查看已保存进度。</p>}
          </section>
          {review && review.task_id === selected.id && <ResearchClaimReviewPanel key={selected.id} task={selected} view={review} onSaved={acceptReview} onReload={reload}
            disabled={exporting || reviewUncertain} onBusyChange={setReviewWriting}
            onUncertain={() => { setReviewUncertain(true); setReviewNotice(''); setSource(null); }}
            onSource={(item, event) => {
              sourceTrigger.current = event.currentTarget;
              setSource({ claim: item.claim, source: item.source, title: selected.sources.find((s) => s.document_id === item.claim.document_id)?.title || '原文' });
            }} />}
          {review && review.task_id === selected.id && <ResearchReviewExport key={`export-${selected.id}`} task={selected} view={review}
            disabled={reviewWriting || reviewUncertain} onBusyChange={setExporting} onReload={reload}
            onUncertain={() => { setReviewUncertain(true); setReviewNotice(''); setSource(null); }} />}

          {source && <section className="research-source" ref={sourcePanel} tabIndex={-1} aria-label="引用原文">
            <div className="research-source-heading"><div><h3>引用原文 · {source.title}</h3><p className="research-muted mt-2 text-xs">{pageLabel(source.source)}{source.source?.section_path.length ? ` · ${source.source.section_path.join(' / ')}` : ''}</p></div><button className="research-button" onClick={closeSource}>关闭原文</button></div>
            <p className="mt-4 text-sm">{source.claim.statement}</p>
            <blockquote>{source.claim.citation.quote}</blockquote>
            <details><summary>定位详情</summary><dl><dt>切片</dt><dd>{source.claim.citation.chunk_id}</dd><dt>字符区间</dt><dd>[{source.claim.citation.char_start}, {source.claim.citation.char_end})</dd>{source.source && <><dt>切分集合</dt><dd>{source.source.chunk_set_id}</dd><dt>原文区间</dt><dd>{source.source.source_locator.spans.map((s) => `${s.block_id} [${s.char_start}, ${s.char_end})`).join('；')}</dd></>}</dl></details>
            <p className="research-muted mt-4 text-xs">这是任务引用的原始片段，不能代表整篇论文；未定位到内容不等于论文没有报告。</p>
          </section>}
        </>}
      </main>
    </div>
  </div>;
}
