/** UI contract tests with explicit synthetic server responses; no live DB/model. */
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
const root = fileURLToPath(new URL('../', import.meta.url));
const out = new URL('./shots/research-create/', import.meta.url);
await mkdir(out, { recursive: true });
const port = Number(process.env.RESEARCH_TEST_PORT || 5179), origin = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, windowsHide: true, stdio: 'pipe' });
let serverReady = false, serverError = '';
server.stdout.on('data', (s) => { if (String(s).includes('Local:')) serverReady = true; });
server.stderr.on('data', (s) => { serverError += s; });
server.on('error', (e) => { serverError += e.message; });
const results = [], version = { id: 'version-browser-test', created_at: '2026-11-05 10:00:00', is_active: false, manifest_integrity: 'valid', document_count: 6 };
const docs = Array.from({ length: 6 }, (_, i) => ({ id: `paper-${i}`, file_name: `Paper ${i + 1}.pdf` }));
const base = JSON.parse(await readFile(new URL('../../backend/evaluation/results/research_condition_e2e_20261104.json', import.meta.url), 'utf8')).failed_task;
const pending = { ...base, id: 'research_ui_created', goal: 'Compare methods and evidence gaps', status: 'pending', revision: 0, steps: [], verification: null, artifact: null, sources: docs.slice(0, 3).map((d) => ({ document_id: d.id, title: d.file_name })) };
function preview(body) {
  return { preview_id: 'a'.repeat(64), status: 'preview', task_created: false, model_calls: 0,
    index_version_id: body.index_version_id, goal: body.goal, sources: body.document_ids.map((id) => ({ document_id: id, title: docs.find((d) => d.id === id).file_name })),
    steps: base.steps.map((s) => ({ ...s, status: 'pending', result: null })),
    budget: { max_steps: 13, max_model_calls: 8, max_context_chars: 6000 }, plan_version: 'research-comparison-v2', model_id: 'contract-test-model' };
}
let browser;
async function scenario(name, run, { handler, mobile = false } = {}) {
  const context = await browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 } });
  await context.addInitScript(() => { localStorage.setItem('rag_access_token', 'browser-contract-test'); localStorage.setItem('rag_user_info', JSON.stringify({ id: 1, email: 'reader@example.test', role: 'user' })); });
  const page = await context.newPage(), calls = [], errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request(), url = new URL(req.url()), body = req.postDataJSON();
    calls.push({ method: req.method(), path: url.pathname, body });
    assert(!url.pathname.endsWith('/run'), 'preparation must not execute models');
    assert.equal(req.headers().authorization, 'Bearer browser-contract-test');
    const send = (data, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify({ code, message: code === 200 ? 'ok' : '来源或预览已变化', data }) });
    if (handler && await handler({ url, req, body, send, calls })) return;
    if (url.pathname.endsWith('/index-versions')) return send({ items: [version], total: 1, offset: 0, limit: 8 });
    if (url.pathname.endsWith(`/${version.id}`)) return send({ ...version, documents: docs });
    if (url.pathname.endsWith('/preview')) return send(preview(body));
    if (url.pathname.endsWith('/research-tasks') && req.method() === 'POST') { assert.equal(body.expected_preview_id, 'a'.repeat(64)); return send(pending); }
    if (url.pathname.endsWith('/research-tasks')) return send({ items: [], total: 0, offset: 0, limit: 8 });
    if (url.pathname.endsWith(`/${pending.id}`)) return send(pending);
    throw new Error(`Unexpected request ${req.method()} ${url.pathname}`);
  });
  try { await run(page, calls); assert.deepEqual(errors, []); results.push({ name, passed: true }); console.log(`PASS ${name}`); }
  catch (error) {
    console.log(JSON.stringify({ scenario: name, url: page.url(), browserErrors: errors, calls }));
    await page.screenshot({ path: fileURLToPath(new URL('failure.png', out)) });
    throw error;
  }
  finally { await context.close(); }
}
const reviewButton = (page) => page.getByRole('button', { name: '校验来源并预览计划', exact: true });
const createButton = (page) => page.getByRole('button', { name: '确认创建待执行任务', exact: true });
async function select(page) {
  await page.goto(`${origin}/research/new`);
  await page.getByRole('radio').check();
  for (let i = 1; i <= 3; i++) await page.getByRole('checkbox', { name: `Paper ${i}.pdf`, exact: true }).check();
  await page.getByLabel('02 / 研究目标').fill(pending.goal);
}
async function review(page) {
  await select(page); await reviewButton(page).click();
  await createButton(page).waitFor();
}
try {
  for (let i = 0; !serverReady; i++) { if (i > 200 || server.exitCode != null) throw new Error(`Vite startup failed: ${serverError}`); await new Promise((r) => setTimeout(r, 50)); }
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : { channel: process.env.RESEARCH_BROWSER_CHANNEL || 'chrome' }) });
  await scenario('explicit preview then one pending create, without run', async (page, calls) => {
    await select(page);
    await page.locator('.research-create-content').evaluate((el) => { el.scrollTop = 0; });
    await page.screenshot({ path: fileURLToPath(new URL('selection.png', out)) });
    await reviewButton(page).click(); await createButton(page).waitFor();
    assert.equal(calls.filter((c) => c.path.endsWith('/research-tasks') && c.method === 'POST').length, 0);
    await page.screenshot({ path: fileURLToPath(new URL('desktop.png', out)) });
    await createButton(page).dblclick();
    await page.waitForURL(`**/research/${pending.id}`);
    assert.equal(calls.filter((c) => c.path.endsWith('/research-tasks') && c.method === 'POST').length, 1);
    await page.getByText('待执行', { exact: true }).waitFor();
    const body = calls.find((c) => c.path.endsWith('/preview')).body;
    assert.equal(body.result_condition_policy, 'explicit-row-v1');
    assert.equal(body.plan_version, 'research-comparison-v2');
  });
  await scenario('goal and document edits invalidate reviewed plan', async (page) => {
    await review(page); await page.getByLabel('02 / 研究目标').fill('Changed goal');
    assert.equal(await createButton(page).count(), 0);
    await reviewButton(page).click(); await createButton(page).waitFor();
    await page.getByRole('checkbox', { name: 'Paper 3.pdf', exact: true }).uncheck();
    assert.equal(await createButton(page).count(), 0);
    assert(await reviewButton(page).isDisabled());
  });
  await scenario('select at most five documents, require nonblank goal', async (page) => {
    await select(page);
    for (let i = 4; i <= 5; i++) await page.getByRole('checkbox', { name: `Paper ${i}.pdf`, exact: true }).check();
    assert(await page.getByRole('checkbox', { name: 'Paper 6.pdf', exact: true }).isDisabled());
    await page.getByLabel('02 / 研究目标').fill('   '); assert(await reviewButton(page).isDisabled());
  });
  await scenario('409 requires a fresh preview, no automatic create retry', async (page, calls) => {
    await review(page); await createButton(page).click();
    await page.getByRole('alert').filter({ hasText: '重新预览' }).waitFor();
    assert.equal(await createButton(page).count(), 0);
    assert.equal(calls.filter((c) => c.path.endsWith('/research-tasks') && c.method === 'POST').length, 1);
  }, { handler: async ({ url, req, send }) => url.pathname.endsWith('/research-tasks') && req.method() === 'POST' ? (await send(null, 409), true) : false });
  await scenario('empty versions cannot create or invent tasks', async (page, calls) => {
    await page.goto(`${origin}/research/new`); await page.getByText(/尚无可选择的保留版本/).waitFor();
    assert(await reviewButton(page).isDisabled()); assert(!calls.some((c) => c.method === 'POST'));
  }, { handler: async ({ url, send }) => url.pathname.endsWith('/index-versions') ? (await send({ items: [], total: 0, offset: 0, limit: 8 }), true) : false });
  await scenario('source failure produces no plan or create', async (page) => {
    await select(page); await reviewButton(page).click();
    await page.getByRole('alert').waitFor(); assert.equal(await createButton(page).count(), 0);
  }, { handler: async ({ url, send }) => url.pathname.endsWith('/preview') ? (await send(null, 400), true) : false });
  await scenario('stale preview response is ignored after editing', async (page) => {
    await select(page); await reviewButton(page).click();
    await page.getByLabel('02 / 研究目标').fill('Edited during preview');
    await page.waitForTimeout(450); assert.equal(await createButton(page).count(), 0);
  }, { handler: async ({ url, body, send }) => {
    if (!url.pathname.endsWith('/preview')) return false;
    await new Promise((r) => setTimeout(r, 350)); try { await send(preview(body)); } catch { /* aborted */ } return true;
  } });
  await scenario('mobile preparation is readable and has no body overflow', async (page) => {
    await review(page);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: fileURLToPath(new URL('mobile.png', out)) });
    assert(await createButton(page).isVisible());
  }, { mobile: true });
  let detailUnavailable = true;
  await scenario('transient version detail failure can be reloaded', async (page) => {
    await page.goto(`${origin}/research/new`); await page.getByRole('radio').check();
    await page.getByRole('alert').waitFor(); detailUnavailable = false;
    await page.getByRole('button', { name: '重新读取来源', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Paper 1.pdf', exact: true }).waitFor();
    assert.equal(await page.getByRole('alert').count(), 0);
  }, { handler: async ({ url, send }) => detailUnavailable && url.pathname.endsWith(`/${version.id}`) ? (await send(null, 400), true) : false });
  console.log(`${results.length} creation browser scenarios passed (synthetic intercepted API)`);
} finally {
  await browser?.close(); server.kill();
  await writeFile(new URL('results.json', out), JSON.stringify({ fixture_mode: 'synthetic intercepted API contract', model_calls: 0, results }, null, 2));
}
