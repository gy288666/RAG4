import { ApiError, request } from './client';
import type { ResearchList, ResearchTask, PartialArtifactView, VersionList, VersionDetail, ResearchDraft, ResearchPreview, RetryDecision, ClaimReviewView, ClaimReviewDecision } from '@/types/research';

export function readClaimReview(id: string, revision: number, signal?: AbortSignal) {
  return request<ClaimReviewView>({ url: `/research-tasks/${encodeURIComponent(id)}/review`, params: { expected_revision: revision }, signal });
}
/** Never retry a write automatically: a lost response may follow a committed event. */
export function recordClaimReview(id: string, claimId: string, revision: number, artifactId: string, decision: ClaimReviewDecision, reason: string) {
  return request<ClaimReviewView>({ method: 'POST', url: `/research-tasks/${encodeURIComponent(id)}/claims/${encodeURIComponent(claimId)}/review`,
    data: { expected_revision: revision, source_artifact_id: artifactId, decision, reason } });
}
export function checkClaimReview(view: ClaimReviewView, task: ResearchTask, revision = task.revision) {
  const original = task.artifact;
  const fail = () => { throw new ApiError(409, '审阅内容与任务版本不一致，请核对最新状态。'); };
  if (!original || task.status !== 'completed' || view.task_id !== task.id || view.task_revision !== revision
      || view.source_artifact_id !== original.artifact_id || view.artifact.corpus_id !== task.corpus_id
      || view.annotation_status !== 'owner_review_overlay' || view.quality_gate_passed !== false
      || view.model_calls !== 0 || view.embedding_calls !== 0 || view.items.length !== original.citations.length) fail();
  if (!original) return;
  const before = task.claim_reviews || [];
  const delta = revision - task.revision;
  if (![0, 1].includes(delta) || view.events.length !== before.length + delta
      || before.some((event, i) => event.event_id !== view.events[i]?.event_id)) fail();
  const eventIds = new Set<string>();
  const latest = new Map<string, typeof view.events[number]>();
  view.events.forEach((event, i) => {
    if (eventIds.has(event.event_id) || event.task_id !== task.id || event.source_artifact_id !== original.artifact_id
        || event.sequence !== i + 1 || event.previous_event_id !== (i ? view.events[i - 1].event_id : null)
        || !['retain', 'withdraw', 'reset'].includes(event.decision) || event.task_revision > revision
        || !original.citations.some((c) => c.claim_id === event.claim_id)) fail();
    eventIds.add(event.event_id); latest.set(event.claim_id, event);
  });
  if (view.events.length && view.events[view.events.length - 1].task_revision !== revision) fail();
  const ids = new Set<string>();
  for (const item of view.items) {
    const c = item.claim, old = original.citations.find((claim) => claim.claim_id === c.claim_id);
    if (!old || ids.has(c.claim_id) || c.document_id !== old.document_id || c.facet !== old.facet || c.statement !== old.statement
        || c.citation.chunk_id !== old.citation.chunk_id || c.citation.char_start !== old.citation.char_start
        || c.citation.char_end !== old.citation.char_end || c.citation.quote !== old.citation.quote
        || item.source.claim_id !== c.claim_id || !['unreviewed', 'retained', 'withdrawn'].includes(item.review_status)) fail();
    ids.add(c.claim_id);
    const event = latest.get(c.claim_id);
    const status = event ? { retain: 'retained', withdraw: 'withdrawn', reset: 'unreviewed' }[event.decision] : 'unreviewed';
    if (item.review_status !== status || item.latest_event_id !== (event?.event_id || null)) fail();
    const source = original.citation_sources?.find((s) => s.claim_id === c.claim_id);
    if (!source || source.chunk_set_id !== item.source.chunk_set_id) fail();
  }
  const visible = view.items.filter((item) => item.review_status !== 'withdrawn').map((item) => item.claim.claim_id);
  if (view.artifact.citations.length !== visible.length || new Set(view.artifact.citations.map((c) => c.claim_id)).size !== visible.length
      || view.artifact.citations.some((c) => !visible.includes(c.claim_id))) fail();
  if (view.artifact.rows.length !== original.rows.length) fail();
  for (const oldRow of original.rows) {
    const row = view.artifact.rows.find((r) => r.document_id === oldRow.document_id);
    if (!row || row.title !== oldRow.title || row.cells.length !== oldRow.cells.length) { fail(); continue; }
    for (const oldCell of oldRow.cells) {
      const cell = row.cells.find((c) => c.facet === oldCell.facet);
      if (!cell) { fail(); continue; }
      const withdrawn = oldCell.claim_ids.some((id) => !visible.includes(id));
      if (withdrawn ? cell.status !== 'uncertain' || cell.statement !== null || cell.claim_ids.length !== 0
        : cell.status !== oldCell.status || cell.statement !== oldCell.statement || cell.claim_ids.join('|') !== oldCell.claim_ids.join('|')) fail();
    }
  }
}

export function listResearchTasks(offset: number, limit: number, signal?: AbortSignal) {
  return request<ResearchList>({ url: '/research-tasks', params: { offset, limit }, signal });
}
export function readResearchTask(id: string, signal?: AbortSignal) {
  return request<ResearchTask>({ url: `/research-tasks/${encodeURIComponent(id)}`, signal });
}
export function readPartialArtifact(id: string, revision: number, signal?: AbortSignal) {
  return request<PartialArtifactView>({ url: `/research-tasks/${encodeURIComponent(id)}/partial-artifact`, params: { expected_revision: revision }, signal });
}
export function listRetainedVersions(offset: number, signal?: AbortSignal) {
  return request<VersionList>({ url: '/index-versions', params: { offset, limit: 8 }, signal });
}
export function readRetainedVersion(id: string, signal?: AbortSignal) {
  return request<VersionDetail>({ url: `/index-versions/${encodeURIComponent(id)}`, signal });
}
export function previewResearchTask(data: ResearchDraft, signal?: AbortSignal) {
  return request<ResearchPreview>({ method: 'POST', url: '/research-tasks/preview', data, signal });
}
export function createResearchTask(data: ResearchDraft, previewId: string) {
  return request<ResearchTask>({ method: 'POST', url: '/research-tasks', data: { ...data, expected_preview_id: previewId } });
}
/** One explicit attempt. Never retry automatically after timeout or conflict. */
export function runResearchStep(id: string, revision: number) {
  return request<ResearchTask>({ method: 'POST', url: `/research-tasks/${encodeURIComponent(id)}/run`, data: { expected_revision: revision } });
}
export function controlResearchTask(id: string, revision: number, action: 'pause' | 'resume' | 'cancel') {
  return request<ResearchTask>({ method: 'POST', url: `/research-tasks/${encodeURIComponent(id)}/control`, data: { action, expected_revision: revision } });
}
export function readRetryDecision(id: string) {
  return request<RetryDecision>({ url: `/research-tasks/${encodeURIComponent(id)}/retry` });
}
export function prepareResearchRetry(id: string, revision: number) {
  return request<ResearchTask>({ method: 'POST', url: `/research-tasks/${encodeURIComponent(id)}/retry`, data: { expected_revision: revision } });
}
