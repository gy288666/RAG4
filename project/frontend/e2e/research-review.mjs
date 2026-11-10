/** Review UI contracts. Frozen R51 sources, synthetic responses, no providers/DB writes. */
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
const root = fileURLToPath(new URL('../', import.meta.url));
const frozen = JSON.parse(await readFile(new URL('../../backend/evaluation/results/research_owner_review_20261108.json', import.meta.url), 'utf8')).review_view;
const original = structuredClone(frozen.artifact);
original.artifact_id = frozen.source_artifact_id;
original.citations = frozen.items.map((i) => i.claim); original.citation_sources = frozen.items.map((i) => i.source);
for (const item of frozen.items) {
  const row = original.rows.find((r) => r.document_id === item.claim.document_id);
  Object.assign(row.cells.find((c) => c.facet === item.claim.facet), { status: 'supported', statement: item.claim.statement, claim_ids: [item.claim.claim_id], reasons: [] });
}
original.knowledge_gaps = original.rows.flatMap((r) => r.cells.filter((c) => c.status !== 'supported').map((c) => `${r.document_id}:${c.facet}:${c.status}`));
const base = { id: frozen.task_id, goal: original.goal, status: 'completed', revision: 25, corpus_id: original.corpus_id,
  artifact: original, verification: {}, sources: original.rows.map((r) => ({ document_id: r.document_id, title: r.title })), steps: [],
  budget: { max_steps: 13, max_model_calls: 8, max_context_chars: 6000 }, model_calls_used: 6, tool_calls_used: 12 };
const other = { ...base, id: 'research_other_review', goal: 'Another saved research task', status: 'pending', revision: 0, artifact: null, verification: null };
const out = new URL('./shots/research-review/', import.meta.url); await mkdir(out, { recursive: true });
const port = Number(process.env.RESEARCH_TEST_PORT || 5184), origin = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, windowsHide: true, stdio: 'pipe' });
let ready = false, startupError = '', browser; const results = [];
const bounded = (promise, name, ms = 30000) => {
  let timer; return Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`Timed out: ${name}`)), ms); })]).finally(() => clearTimeout(timer));
};
server.stdout.on('data', (x) => { if (String(x).includes('Local:')) ready = true; });
server.stderr.on('data', (x) => { startupError += x; });
async function scenario(name, run, { handler, mobile = false } = {}) {
  console.log(`START ${name}`);
  const context = await bounded(browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 } }), 'browser context');
  await context.addInitScript(() => { localStorage.setItem('rag_access_token', 'browser-contract-test'); localStorage.setItem('rag_user_info', JSON.stringify({ id: 1, email: 'reader@example.test', role: 'user' })); });
  const page = await context.newPage(); page.setDefaultTimeout(12000);
  let task = structuredClone(base), events = [];
  const calls = [], errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  function view() {
    const items = frozen.items.map((i) => {
      const last = events.filter((e) => e.claim_id === i.claim.claim_id).at(-1);
      return { ...i, review_status: last ? { retain: 'retained', withdraw: 'withdrawn', reset: 'unreviewed' }[last.decision] : 'unreviewed', latest_event_id: last?.event_id || null };
    });
    const artifact = structuredClone(original), withdrawn = new Set(items.filter((i) => i.review_status === 'withdrawn').map((i) => i.claim.claim_id));
    artifact.citations = artifact.citations.filter((c) => !withdrawn.has(c.claim_id));
    for (const row of artifact.rows) for (const cell of row.cells) if (cell.claim_ids.some((id) => withdrawn.has(id))) Object.assign(cell, { status: 'uncertain', statement: null, claim_ids: [], reasons: ['owner_review_withdrawn'] });
    artifact.knowledge_gaps = artifact.rows.flatMap((r) => r.cells.filter((c) => c.status !== 'supported').map((c) => `${r.document_id}:${c.facet}:${c.status}`));
    return { ...frozen, view_id: `fixture-view-${task.revision}`, task_revision: task.revision, events: structuredClone(events), items, artifact };
  }
  function commit(body, claimId) {
    assert.equal(body.expected_revision, task.revision); assert.equal(body.source_artifact_id, original.artifact_id);
    assert.deepEqual(Object.keys(body).sort(), ['decision', 'expected_revision', 'reason', 'source_artifact_id']);
    task = { ...task, revision: task.revision + 1 };
    events.push({ event_id: `fixture-event-${task.revision}`, task_id: task.id, source_artifact_id: original.artifact_id, claim_id: claimId,
      actor_id: 1, sequence: events.length + 1, task_revision: task.revision, previous_event_id: events.at(-1)?.event_id || null,
      decision: body.decision, reason: body.reason, reviewed_at: '2026-11-08T20:00:00Z' });
    task.claim_reviews = structuredClone(events);
    return view();
  }
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request(), url = new URL(request.url()), body = request.postDataJSON();
    calls.push({ path: url.pathname, method: request.method(), body });
    const send = (data, code = 200, message = '请求未完成') => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify({ code, data, message }) });
    try {
      assert.equal(request.headers().authorization, 'Bearer browser-contract-test');
      if (handler && await handler({ route, url, body, send, task, view, commit })) return;
      if (url.pathname.endsWith('/research-tasks')) return send({ items: [task, other].map((t) => ({ id: t.id, revision: t.revision, status: t.status, goal_preview: t.goal })), total: 2, offset: 0, limit: 8 });
      if (url.pathname.endsWith(`/${other.id}`)) return send(other);
      if (url.pathname.endsWith(`/${task.id}`)) return send(task);
      if (url.pathname.endsWith('/review') && request.method() === 'GET') {
        assert.equal(url.searchParams.get('expected_revision'), String(task.revision)); return send(view());
      }
      if (url.pathname.endsWith('/review') && request.method() === 'POST') {
        const claimId = decodeURIComponent(url.pathname.split('/').at(-2));
        const result = commit(body, claimId); return send(result);
      }
      throw new Error('Unexpected review test endpoint');
    } catch (e) { errors.push(e.message); return send(null, 500); }
  });
  const open = async () => { await page.goto(`${origin}/research/${base.id}`); await page.getByText(/按当前审阅展示/).waitFor(); await page.locator('.research-review > summary').click(); };
  const fill = async (decision = 'withdraw', reason = 'This passage does not cover the complete claim.') => {
    await page.getByLabel('选择结论').selectOption(frozen.items.find((i) => i.claim.document_id === 'realm').claim.claim_id);
    await page.getByLabel('审阅决定').selectOption(decision); await page.getByLabel('审阅原因').fill(reason);
  };
  try {
    await run({ page, calls, open, fill });
    assert.deepEqual(errors, []); assert(!calls.some((c) => /\/(run|retry|preview)$/.test(c.path)));
    results.push({ name, passed: true }); console.log(`PASS ${name}`);
  } finally { await bounded(context.close(), 'context cleanup', 5000); }
}
try {
  for (let n = 0; !ready; n++) { if (n > 250 || server.exitCode != null) throw new Error(`Vite unavailable: ${startupError}`); await new Promise((r) => setTimeout(r, 50)); }
  console.log('START browser launch');
  browser = await bounded(chromium.launch({ headless: true, timeout: 30000, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : { channel: 'chrome' }) }), 'browser launch', 35000);
  await scenario('withdraw reset retain preserve history, original source and revision fence', async ({ page, calls, open, fill }) => {
    await open(); assert.equal(calls.filter((c) => c.method === 'POST').length, 0);
    await fill(); await page.getByRole('button', { name: '保存审阅决定', exact: true }).dblclick();
    await page.getByText('已保存版本 26', { exact: true }).waitFor(); await page.getByText(/展示 3 条已有结论/).waitFor();
    await page.locator('.research-table').getByText('已撤下', { exact: true }).waitFor();
    assert.equal(calls.filter((c) => c.method === 'POST').length, 1);
    const withdrawn = page.locator('.research-review-list > li[data-review-status=withdrawn]');
    await withdrawn.getByRole('button', { name: /核对原文/ }).click(); await page.getByRole('region', { name: '引用原文' }).waitFor();
    await page.getByRole('button', { name: '关闭原文' }).click();
    await fill('reset'); await page.getByRole('button', { name: '保存审阅决定', exact: true }).click();
    await page.getByText('已保存版本 27', { exact: true }).waitFor(); await page.getByText(/展示 4 条已有结论/).waitFor();
    await fill('retain', '<img src=x onerror="window.privateReviewExecuted=true">');
    await page.getByRole('button', { name: '保存审阅决定', exact: true }).click(); await page.getByText('已保存版本 28', { exact: true }).waitFor();
    await page.locator('.research-review-list > li[data-review-status=retained]').locator('summary').click();
    await page.getByText('<img src=x onerror="window.privateReviewExecuted=true">', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.privateReviewExecuted), undefined);
    assert.deepEqual(calls.filter((c) => c.method === 'POST').map((c) => c.body.expected_revision), [25, 26, 27]);
    await page.screenshot({ path: fileURLToPath(new URL('desktop.png', out)) });
  });
  await scenario('blank reason disabled and mobile layout fits', async ({ page, open, fill }) => {
    await open(); await fill('withdraw', '   '); assert(await page.getByRole('button', { name: '保存审阅决定', exact: true }).isDisabled());
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await page.screenshot({ path: fileURLToPath(new URL('mobile.png', out)) });
    await page.getByRole('button', { name: '导出当前审阅稿（Markdown）', exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: fileURLToPath(new URL('export-mobile.png', out)) });
  }, { mobile: true });
  await scenario('unsaved decisions stay local and export uses the last saved snapshot', async ({ page, calls, open, fill }) => {
    await open(); await fill('withdraw', 'UNSAVED_EDITOR_NOTE');
    const started = page.waitForEvent('download');
    await page.getByRole('button', { name: '导出当前审阅稿（Markdown）', exact: true }).click();
    const file = await started, content = await readFile(await file.path(), 'utf8');
    assert(content.includes(frozen.items.find((i) => i.claim.document_id === 'realm' && i.claim.facet === 'method').claim.statement));
    assert(!content.includes('UNSAVED_EDITOR_NOTE')); assert.equal(await page.getByLabel('审阅原因').inputValue(), 'UNSAVED_EDITOR_NOTE');
    assert.equal(calls.filter((c) => c.method === 'POST').length, 0);
  });
  await scenario('downloads keep reviewed original and audit material distinct and recheck each snapshot', async ({ page, calls, open, fill }) => {
    await open(); await fill(); await page.getByRole('button', { name: '保存审阅决定', exact: true }).click();
    await page.getByText('已保存版本 26', { exact: true }).waitFor();
    const removed = frozen.items.find((i) => i.claim.document_id === 'realm' && i.claim.facet === 'method').claim.statement;
    const downloadText = async (label) => {
      const started = page.waitForEvent('download'); await page.getByRole('button', { name: label, exact: true }).click();
      const file = await started; return { name: file.suggestedFilename(), text: await readFile(await file.path(), 'utf8') };
    };
    const before = calls.filter((c) => c.path.endsWith('/review') && c.method === 'GET').length;
    const reviewed = await downloadText('导出当前审阅稿（Markdown）');
    assert(reviewed.name.endsWith('-r26-reviewed.md')); assert(!reviewed.text.includes(removed)); assert(reviewed.text.includes('已撤下'));
    const audit = await downloadText('导出审阅记录（JSON）');
    assert.equal(JSON.parse(audit.text).contains_withdrawn_material_for_audit, true);
    assert.equal(JSON.parse(audit.text).task_revision, 26);
    await page.locator('.research-original > summary').click();
    await page.getByText(`原机器稿：${removed}`, { exact: true }).waitFor();
    const original = await downloadText('导出原机器稿快照（Markdown）');
    assert(original.name.endsWith('-original-machine.md')); assert(original.text.includes(removed)); assert(original.text.includes('它不是当前审阅稿'));
    assert.equal(calls.filter((c) => c.path.endsWith('/review') && c.method === 'GET').length, before + 3);
    assert.equal(calls.filter((c) => c.method === 'POST').length, 1);
    await page.screenshot({ path: fileURLToPath(new URL('export-comparison.png', out)) });
  });
  for (const code of [400, 409]) await scenario(`${code} export revalidation prevents download and blocks stale view`, async ({ page, calls, open }) => {
    await open(); let downloads = 0; page.on('download', () => downloads++);
    await page.getByRole('button', { name: '导出当前审阅稿（Markdown）', exact: true }).click();
    await page.getByRole('button', { name: '核对最新审阅', exact: true }).waitFor();
    assert.equal(downloads, 0); assert.equal(await page.locator('.research-table').count(), 0);
    assert(await page.getByRole('button', { name: '导出当前审阅稿（Markdown）', exact: true }).isDisabled());
    assert.equal(calls.filter((c) => c.method === 'POST').length, 0);
  }, { handler: (() => { let reads = 0; return async ({ url, send }) => {
    if (!url.pathname.endsWith('/review')) return false;
    if (++reads === 1) return false; await send(null, code, '来源或审阅已变化'); return true;
  }; })() });
  await scenario('late export after navigation produces no file for the new task', async ({ page, open }) => {
    await open(); let downloads = 0; page.on('download', () => downloads++);
    await page.getByRole('button', { name: '导出当前审阅稿（Markdown）', exact: true }).click();
    await page.getByRole('link', { name: /Another saved research task/ }).click();
    await page.getByRole('heading', { name: other.goal, exact: true }).waitFor(); await page.waitForTimeout(500);
    assert.equal(downloads, 0); assert.equal(await page.getByRole('region', { name: '审阅稿导出与原稿对照' }).count(), 0);
  }, { handler: (() => { let reads = 0; return async ({ url, send, view }) => {
    if (!url.pathname.endsWith('/review') || ++reads === 1) return false;
    await new Promise((r) => setTimeout(r, 350)); await send(view()); return true;
  }; })() });
  await scenario('review writes and snapshot downloads are mutually disabled while pending', async ({ page, open, fill }) => {
    await open(); await fill(); await page.getByRole('button', { name: '保存审阅决定', exact: true }).click();
    assert(await page.getByRole('button', { name: '导出当前审阅稿（Markdown）', exact: true }).isDisabled());
    await page.getByText('已保存版本 26', { exact: true }).waitFor();
    const started = page.waitForEvent('download'); await page.getByRole('button', { name: '导出当前审阅稿（Markdown）', exact: true }).click();
    assert(await page.getByLabel('审阅原因').isDisabled()); await started;
  }, { handler: (() => { let reads = 0; return async ({ url, body, send, commit }) => {
    if (!url.pathname.endsWith('/review')) return false;
    if (body) { const result = commit(body, url.pathname.split('/').at(-2)); await new Promise((r) => setTimeout(r, 250)); await send(result); return true; }
    if (++reads === 1) return false;
    await new Promise((r) => setTimeout(r, 250)); return false;
  }; })() });
  for (const code of [400, 409]) await scenario(`${code} write locks and hides uncertain comparison until refresh`, async ({ page, calls, open, fill }) => {
    await open(); await fill(); await page.getByRole('button', { name: '保存审阅决定', exact: true }).click();
    await page.getByRole('button', { name: '核对最新审阅' }).waitFor(); assert.equal(await page.locator('.research-table').count(), 0);
    assert(await page.getByLabel('审阅原因').isDisabled()); await page.waitForTimeout(200);
    assert.equal(calls.filter((c) => c.method === 'POST').length, 1);
    await page.getByRole('button', { name: '核对最新审阅' }).click(); await page.getByText(/按当前审阅展示/).waitFor();
  }, { handler: async ({ url, body, send }) => url.pathname.includes('/claims/') && body ? (await send(null, code), true) : false });
  await scenario('lost response may be committed, refresh discovers it without a second write', async ({ page, calls, open, fill }) => {
    await open(); await fill(); await page.getByRole('button', { name: '保存审阅决定', exact: true }).click();
    await page.getByRole('button', { name: '核对最新审阅' }).waitFor(); assert.equal(await page.locator('.research-table').count(), 0);
    await page.getByRole('button', { name: '核对最新审阅' }).click(); await page.getByText('已保存版本 26', { exact: true }).waitFor();
    await page.getByText(/展示 3 条已有结论/).waitFor(); assert.equal(calls.filter((c) => c.method === 'POST').length, 1);
  }, { handler: async ({ route, url, body, commit }) => {
    if (!url.pathname.includes('/claims/') || !body) return false;
    commit(body, url.pathname.split('/').at(-2)); await route.abort('connectionfailed'); return true;
  } });
  await scenario('read failure never falls back to machine artifact', async ({ page }) => {
    await page.goto(`${origin}/research/${base.id}`); await page.getByText('无法确认最新审阅，暂不展示比较表。').waitFor();
    assert.equal(await page.locator('.research-table').count(), 0);
  }, { handler: async ({ url, send }) => url.pathname.endsWith('/review') ? (await send(null, 400, '来源已变化'), true) : false });
  await scenario('mismatched source artifact rejected before displaying conclusions', async ({ page }) => {
    await page.goto(`${origin}/research/${base.id}`); await page.getByText('无法确认最新审阅，暂不展示比较表。').waitFor();
    assert.equal(await page.locator('.research-table').count(), 0);
  }, { handler: async ({ url, send, view }) => url.pathname.endsWith('/review') ? (await send({ ...view(), source_artifact_id: 'other' }), true) : false });
  for (const mutation of ['cell', 'status']) await scenario(`inconsistent ${mutation} rejected despite matching task and artifact IDs`, async ({ page }) => {
    await page.goto(`${origin}/research/${base.id}`); await page.getByText('无法确认最新审阅，暂不展示比较表。').waitFor();
    assert.equal(await page.locator('.research-table').count(), 0);
  }, { handler: async ({ url, send, view }) => {
    if (!url.pathname.endsWith('/review')) return false;
    const bad = structuredClone(view());
    if (mutation === 'cell') bad.artifact.rows[0].cells[0].statement = 'Unrelated statement under the same ID';
    else bad.items[0].review_status = 'withdrawn';
    await send(bad); return true;
  } });
  await scenario('late write after task navigation cannot paint old review into new task', async ({ page, open, fill }) => {
    await open(); await fill(); await page.getByRole('button', { name: '保存审阅决定', exact: true }).click();
    await page.getByRole('link', { name: /Another saved research task/ }).click();
    await page.getByRole('heading', { name: other.goal, exact: true }).waitFor(); await page.waitForTimeout(500);
    assert.equal(await page.locator('.research-review').count(), 0); assert.equal(await page.getByText(/审阅决定已保存/).count(), 0);
  }, { handler: async ({ url, body, send, commit }) => {
    if (!url.pathname.includes('/claims/') || !body) return false;
    const result = commit(body, url.pathname.split('/').at(-2)); await new Promise((r) => setTimeout(r, 350)); await send(result); return true;
  } });
} finally {
  if (browser) await bounded(browser.close(), 'browser cleanup', 5000).catch((e) => console.error(e.message));
  server.kill();
  await writeFile(new URL('results.json', out), JSON.stringify({ mode: 'intercepted API; reconstructed R51 machine fixture', provider_requests: 0, results }, null, 2));
}
