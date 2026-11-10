import type { ClaimReviewView, ResearchArtifact, ResearchClaim, ResearchTask } from '@/types/research';

export type ReviewExportKind = 'reviewed' | 'audit' | 'original';
export interface ReviewExportFile { name: string; type: string; content: string }
const SCHEMA = 'research-review-export-v1';
const FACETS = { method: '方法', dataset: '数据集', result: '结果', limitation: '局限' };
const STATUS = { unreviewed: '机器支持，未审阅', retained: '个人审阅保留', withdrawn: '已撤下' };
const text = (value: string) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/([\\`*_[\]{}()!|])/g, '\\$1').replace(/[\r\n]+/g, ' ');
function code(value: string) {
  const width = Math.max(3, ...Array.from(value.matchAll(/`+/g), (m) => m[0].length + 1));
  const fence = '`'.repeat(width);
  return `${fence}text\n${value}\n${fence}`;
}
function sameClaim(a: ResearchClaim, b: ResearchClaim) {
  return a.claim_id === b.claim_id && a.document_id === b.document_id && a.facet === b.facet && a.statement === b.statement
    && a.citation.chunk_id === b.citation.chunk_id && a.citation.char_start === b.citation.char_start
    && a.citation.char_end === b.citation.char_end && a.citation.quote === b.citation.quote;
}

/** Deterministic local files from structured data; stored Markdown is never an authority. */
export function buildReviewFile(task: ResearchTask, view: ClaimReviewView, kind: ReviewExportKind): ReviewExportFile {
  const original = task.artifact;
  if (!original || task.status !== 'completed' || view.task_id !== task.id || view.task_revision !== task.revision
      || view.source_artifact_id !== original.artifact_id || view.artifact.corpus_id !== task.corpus_id || original.corpus_id !== task.corpus_id
      || view.quality_gate_passed !== false || view.annotation_status !== 'owner_review_overlay'
      || !['reviewed', 'audit', 'original'].includes(kind)) throw new Error('导出快照与当前审阅不一致，请重新核对。');
  const all = new Map(view.items.map((item) => [item.claim.claim_id, item]));
  if (view.items.some((item) => !['unreviewed', 'retained', 'withdrawn'].includes(item.review_status))
      || all.size !== view.items.length || all.size !== original.citations.length || original.citations.some((c) => !all.has(c.claim_id)
      || !sameClaim(c, all.get(c.claim_id)!.claim) || all.get(c.claim_id)!.source.claim_id !== c.claim_id)) throw new Error('导出引文与原稿不一致。');
  const visible = view.items.filter((item) => item.review_status !== 'withdrawn');
  const ids = new Set(visible.map((item) => item.claim.claim_id));
  if (view.artifact.citations.length !== ids.size || new Set(view.artifact.citations.map((c) => c.claim_id)).size !== ids.size
      || view.artifact.citations.some((c) => !ids.has(c.claim_id) || !sameClaim(c, all.get(c.claim_id)!.claim))) throw new Error('当前审阅稿含已撤下或不匹配的引文。');
  const manifest = { schema_version: SCHEMA, task_id: task.id, task_revision: view.task_revision, corpus_id: task.corpus_id,
    review_view_id: view.view_id, source_artifact_id: view.source_artifact_id, reviewed_artifact_id: view.artifact.artifact_id,
    annotation_status: view.annotation_status, quality_gate_passed: false };
  const stem = `research-${task.id.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 80)}-r${view.task_revision}`;
  if (kind === 'audit') return { name: `${stem}-review-audit.json`, type: 'application/json;charset=utf-8',
    content: JSON.stringify({ ...manifest, export_kind: 'review_audit', contains_withdrawn_material_for_audit: true,
      notice: '包含原结论与已撤下材料，仅供追溯，不是当前审阅稿或独立质量验收。', review_view: view }, null, 2) + '\n' };
  const artifact: ResearchArtifact = kind === 'original' ? original : view.artifact;
  const citations = artifact.citations;
  const numbers = new Map(citations.map((c, i) => [c.claim_id, i + 1]));
  const used = new Set<string>();
  const lines = [kind === 'original' ? '# 原机器稿快照（仅供对照）' : '# 当前个人审阅稿', '',
    kind === 'original' ? '> 本文件包含原机器结论，可能包括后来已撤下的内容。它不是当前审阅稿。'
      : '> 按个人审阅筛选，未审阅的机器结论仍可能存在；不代表独立人工质量验收，不作跨论文性能排名。', '',
    '## 快照身份', '', code(JSON.stringify(manifest, null, 2)), '',
    `研究目标：${text(task.goal)}`, '', '| 文献 | 方法 | 数据集 | 结果 | 局限 |', '| --- | --- | --- | --- | --- |'];
  for (const row of artifact.rows) {
    const cells = (Object.keys(FACETS) as (keyof typeof FACETS)[]).map((facet) => {
      const cell = row.cells.find((c) => c.facet === facet);
      if (!cell) throw new Error('导出表格缺少字段。');
      if (cell.status !== 'supported') return kind === 'reviewed' && view.items.some((i) => i.claim.document_id === row.document_id
        && i.claim.facet === facet && i.review_status === 'withdrawn') ? '已撤下' : { missing: '证据未检出', uncertain: '待核验', conflict: '证据冲突' }[cell.status];
      if (!cell.claim_ids.length) throw new Error('导出结论缺少引用。');
      for (const id of cell.claim_ids) {
        const claim = all.get(id)?.claim;
        if (!claim || !numbers.has(id) || claim.document_id !== row.document_id || claim.facet !== facet || claim.statement !== cell.statement) throw new Error('导出表格与引文不一致。');
        used.add(id);
      }
      return `${text(cell.statement || '')} ${cell.claim_ids.map((id) => `[${numbers.get(id)}]`).join(' ')}`;
    });
    lines.push(`| ${text(row.title)} | ${cells.join(' | ')} |`);
  }
  if (used.size !== citations.length) throw new Error('导出包含未在表格使用的引用。');
  lines.push('', '## 引用与来源', '');
  for (const claim of citations) {
    const item = all.get(claim.claim_id)!;
    const source = item.source;
    lines.push(`### [${numbers.get(claim.claim_id)}] ${text(task.sources.find((s) => s.document_id === claim.document_id)?.title || claim.document_id)}`, '',
      `- 结论身份：${text(claim.claim_id)}`, `- 原稿状态：机器支持${kind === 'reviewed' ? `；当前状态：${STATUS[item.review_status]}` : ''}`,
      `- PDF 页码：${source.page_start == null ? '未记录' : `${source.page_start}–${source.page_end ?? source.page_start}`}`,
      `- 切片：${text(claim.citation.chunk_id)}；字符区间：[${claim.citation.char_start}, ${claim.citation.char_end})`,
      `- 切分集合：${text(source.chunk_set_id)}`, `- 来源：${text(source.source_locator.source.uri)}`, '', code(claim.citation.quote), '');
  }
  lines.push('## 知识缺口', '', ...artifact.knowledge_gaps.map((gap) => `- ${text(gap)}`), '');
  return { name: `${stem}-${kind === 'original' ? 'original-machine' : 'reviewed'}.md`, type: 'text/markdown;charset=utf-8', content: lines.join('\n') };
}
