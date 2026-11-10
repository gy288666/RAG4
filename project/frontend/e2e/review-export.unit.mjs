/** Pure export contracts, transpiled with the already installed TypeScript compiler. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../src/utils/reviewExport.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 } }).outputText;
const { buildReviewFile } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
const data = JSON.parse(await readFile(new URL('../../backend/evaluation/results/research_owner_review_20261108.json', import.meta.url), 'utf8')).review_view;
function fixture() {
  const view = structuredClone(data), original = structuredClone(view.artifact);
  original.artifact_id = view.source_artifact_id;
  original.citations = view.items.map((i) => i.claim); original.citation_sources = view.items.map((i) => i.source);
  for (const item of view.items) Object.assign(original.rows.find((r) => r.document_id === item.claim.document_id).cells.find((c) => c.facet === item.claim.facet),
    { status: 'supported', statement: item.claim.statement, claim_ids: [item.claim.claim_id], reasons: [] });
  const task = { id: view.task_id, revision: view.task_revision, status: 'completed', corpus_id: view.artifact.corpus_id,
    goal: 'Compare research evidence', artifact: original, sources: original.rows.map((r) => ({ document_id: r.document_id, title: r.title })) };
  return { task, view };
}
test('reviewed Markdown omits withdrawn statements/quotes and ignores stale stored Markdown', () => {
  const { task, view } = fixture(), withdrawn = view.items.find((i) => i.review_status === 'withdrawn');
  view.artifact.markdown = task.artifact.markdown = `UNSAFE_STALE_MARKDOWN ${withdrawn.claim.statement}`;
  const file = buildReviewFile(task, view, 'reviewed');
  assert(!file.content.includes(withdrawn.claim.statement)); assert(!file.content.includes(withdrawn.claim.citation.quote));
  assert(!file.content.includes('UNSAFE_STALE_MARKDOWN'));
  assert(file.content.includes('已撤下')); assert(file.content.includes(view.view_id));
  for (const item of view.items.filter((i) => i.review_status !== 'withdrawn')) assert(file.content.includes(item.claim.citation.quote));
  assert(file.name.endsWith('-reviewed.md'));
});
test('original is explicitly historical and audit explicitly retains withdrawn material', () => {
  const { task, view } = fixture(), withdrawn = view.items.find((i) => i.review_status === 'withdrawn');
  const original = buildReviewFile(task, view, 'original');
  assert(original.content.includes('它不是当前审阅稿')); assert(original.content.includes(withdrawn.claim.statement));
  assert(original.name.endsWith('-original-machine.md'));
  const audit = JSON.parse(buildReviewFile(task, view, 'audit').content);
  assert.equal(audit.contains_withdrawn_material_for_audit, true); assert.equal(audit.quality_gate_passed, false);
  assert.deepEqual(audit.review_view, view);
});
test('same snapshot produces identical bytes without modifying inputs', () => {
  const { task, view } = fixture(), before = JSON.stringify({ task, view });
  for (const kind of ['reviewed', 'original', 'audit']) assert.deepEqual(buildReviewFile(task, view, kind), buildReviewFile(task, view, kind));
  assert.equal(JSON.stringify({ task, view }), before);
});
for (const kind of ['reviewed', 'original', 'audit']) test(`${kind} rejects a stale revision/source identity`, () => {
  const { task, view } = fixture();
  assert.throws(() => buildReviewFile({ ...task, revision: task.revision + 1 }, view, kind));
  assert.throws(() => buildReviewFile(task, { ...view, source_artifact_id: 'other' }, kind));
});
test('cannot reintroduce a withdrawn citation or alter a visible quote', () => {
  const { task, view } = fixture();
  view.artifact.citations.push(view.items.find((i) => i.review_status === 'withdrawn').claim);
  assert.throws(() => buildReviewFile(task, view, 'reviewed'));
  const good = fixture(); good.view.artifact.citations[0].citation.quote = 'invented';
  assert.throws(() => buildReviewFile(good.task, good.view, 'reviewed'));
});
test('HTML/Markdown titles are escaped and code fences cannot be closed by a source quote', () => {
  const { task, view } = fixture();
  task.goal = '<img src=x onerror=alert(1)> ![tracker](https://example.test/x)';
  const item = view.items.find((i) => i.review_status !== 'withdrawn'), quote = '```\n<img src=x>\n````\n![tracker](x)';
  item.claim.citation.quote = quote;
  task.artifact.citations.find((c) => c.claim_id === item.claim.claim_id).citation.quote = quote;
  view.artifact.citations.find((c) => c.claim_id === item.claim.claim_id).citation.quote = quote;
  const file = buildReviewFile(task, view, 'reviewed');
  assert(file.content.includes('&lt;img')); assert(file.content.includes('`````text\n' + quote + '\n`````'));
  assert(!file.content.includes('研究目标：<img'));
});
test('invalid table claims cannot become exported conclusions', () => {
  const { task, view } = fixture();
  view.artifact.rows[0].cells[0].statement = 'unrelated';
  assert.throws(() => buildReviewFile(task, view, 'reviewed'));
});
test('filenames cannot introduce paths, and invalid status/kind cannot be exported', () => {
  const { task, view } = fixture(); task.id = view.task_id = '../../CON/unsafe:name';
  const file = buildReviewFile(task, view, 'reviewed');
  assert(!/[\\/:]/.test(file.name)); assert(file.name.startsWith('research-'));
  assert.throws(() => buildReviewFile(task, view, 'unknown'));
  view.items[0].review_status = 'gold'; assert.throws(() => buildReviewFile(task, view, 'audit'));
});
