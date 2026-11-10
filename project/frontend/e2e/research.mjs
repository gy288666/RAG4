/** Read-only browser contracts using real frozen R37/R39 responses, not live model output. */
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const root = fileURLToPath(new URL('../', import.meta.url));
const load = async (name) => JSON.parse(await readFile(new URL(`../../backend/evaluation/results/${name}`, import.meta.url), 'utf8'));
const task = (await load('research_condition_e2e_20261104.json')).failed_task;
const view = (await load('research_partial_artifact_api_20261104.json')).api_check.view;
const out = new URL('./shots/research/', import.meta.url);
await mkdir(out, { recursive: true });
const port = Number(process.env.RESEARCH_TEST_PORT || 5178);
const origin = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, windowsHide: true, stdio: 'pipe' });
let serverError = '';
server.stderr.on('data', (s) => { serverError += s; });
const results = [];
let browser;
const summary = (t) => ({ id: t.id, status: t.status, revision: t.revision, goal_preview: t.goal.slice(0, 160) });
const clone = (x) => structuredClone(x);
const waitFor = async (check) => {
  const until = Date.now() + 15000;
  while (Date.now() < until) { if (await check()) return; await new Promise((r) => setTimeout(r, 40)); }
  throw new Error('Timed out waiting for assertion');
};
async function scenario(name, run, { authenticated = true, mobile = false, handler } = {}) {
  if (process.env.RESEARCH_TEST_CASE && !name.includes(process.env.RESEARCH_TEST_CASE)) return;
  if (process.env.RESEARCH_TEST_DIAGNOSTICS) console.log(`[research-test] start ${name}`);
  const context = await browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 } });
  if (authenticated) await context.addInitScript(() => {
    // Deliberately fake browser-test token; never a production credential.
    if (!sessionStorage.getItem('test-initialized')) {
      localStorage.setItem('rag_access_token', 'browser-contract-test');
      localStorage.setItem('rag_user_info', JSON.stringify({ id: 1, email: 'reader@example.test', role: 'user' }));
      sessionStorage.setItem('test-initialized', '1');
    }
  });
  const page = await context.newPage();
  if (process.env.RESEARCH_TEST_CASE) page.setDefaultTimeout(5000);
  const calls = [], errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request(), url = new URL(req.url());
    calls.push({ method: req.method(), path: url.pathname, search: url.search });
    assert.equal(req.method(), 'GET', 'reading must not mutate data');
    assert.equal(req.headers().authorization, 'Bearer browser-contract-test');
    const send = (data, code = 200, message = 'ok') => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify({ code, message, data }) });
    if (handler && await handler({ route, req, url, send })) return;
    if (url.pathname.endsWith('/research-tasks')) return send({ items: [summary(task)], total: 1, limit: 8, offset: 0 });
    if (url.pathname.endsWith('/partial-artifact')) {
      assert.equal(url.searchParams.get('expected_revision'), String(task.revision));
      return send(view);
    }
    if (url.pathname.endsWith(`/${task.id}`)) return send(task);
    throw new Error(`Unexpected API path: ${url.pathname}`);
  });
  try {
    await run(page, calls);
    assert.deepEqual(errors, [], 'no uncaught browser exceptions');
    results.push({ name, passed: true });
    console.log(`PASS ${name}`);
  } catch (error) {
    await page.screenshot({ path: fileURLToPath(new URL('failure.png', out)) });
    console.log(JSON.stringify({ scenario: name, url: page.url(), browserErrors: errors, calls }));
    throw error;
  } finally {
    if (process.env.RESEARCH_TEST_DIAGNOSTICS) console.log(`[research-test] closing ${name}`);
    await context.close();
    if (process.env.RESEARCH_TEST_DIAGNOSTICS) console.log(`[research-test] closed ${name}`);
  }
}
const ready = async (page) => {
  await page.goto(`${origin}/research`);
  await page.getByRole('heading', { name: '失败任务的部分比较稿' }).waitFor();
  await page.getByRole('button', { name: '查看引文 1', exact: true }).waitFor();
};
try {
  await waitFor(async () => {
    if (server.exitCode != null) throw new Error(`Vite failed: ${serverError}`);
    try { return (await fetch(origin)).ok; } catch { return false; }
  });
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : { channel: process.env.RESEARCH_BROWSER_CHANNEL || 'chrome' }) });
  await scenario('real failed task, steps, exact citation, focus and GET-only', async (page, calls) => {
    await ready(page);
    assert.equal(await page.getByRole('button', { name: /查看引文/ }).count(), 2);
    assert.equal(await page.locator('.research-table td').count(), 12);
    await page.getByText('任务未完成，保留内容仍可供核查', { exact: true }).waitFor();
    await page.screenshot({ path: fileURLToPath(new URL('desktop.png', out)) });
    await page.getByRole('button', { name: '查看引文 1', exact: true }).click();
    const source = page.getByRole('region', { name: '引用原文' });
    await source.waitFor();
    assert.equal(await source.locator('blockquote').textContent(), view.artifact.citations[0].citation.quote);
    assert.equal(await source.evaluate((el) => document.activeElement === el), true);
    await source.getByText('文献第 2 页', { exact: false }).waitFor();
    await page.screenshot({ path: fileURLToPath(new URL('source.png', out)) });
    await page.getByRole('button', { name: '关闭原文' }).click();
    assert.equal(await page.getByRole('button', { name: '查看引文 1', exact: true }).evaluate((el) => document.activeElement === el), true);
    await page.getByText(/计划与步骤 ·/).click();
    assert.equal(await page.locator('.research-steps > li').count(), task.steps.length);
    assert(calls.some((c) => c.search.includes('expected_revision=24')));
  });
  await scenario('mobile table scrolls inside viewport', async (page) => {
    await ready(page);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert(await page.locator('.research-table-wrap').evaluate((el) => el.scrollWidth > el.clientWidth));
    await page.screenshot({ path: fileURLToPath(new URL('mobile.png', out)) });
    await page.getByRole('button', { name: '查看引文 1', exact: true }).click();
    await page.getByRole('button', { name: '关闭原文' }).waitFor({ state: 'visible' });
  }, { mobile: true });
  await scenario('source change suppresses partial conclusions', async (page) => {
    await page.goto(`${origin}/research/${task.id}`);
    await page.getByRole('alert').filter({ hasText: '来源已变化' }).waitFor();
    assert.equal(await page.getByRole('button', { name: /查看引文/ }).count(), 0);
  }, { handler: async ({ url, send }) => url.pathname.endsWith('/partial-artifact') ? (await send(null, 400, '来源已变化'), true) : false });
  let revision = task.revision;
  await scenario('conflict refresh uses new revision without stale artifact', async (page) => {
    await page.goto(`${origin}/research/${task.id}`);
    await page.getByRole('alert').filter({ hasText: '任务版本或状态已变化' }).waitFor();
    revision++;
    await page.getByRole('button', { name: '刷新后重读' }).click();
    await page.getByRole('button', { name: '查看引文 1', exact: true }).waitFor();
    await page.getByText(`已保存版本 ${revision}`, { exact: true }).waitFor();
  }, { handler: async ({ url, send }) => {
    if (url.pathname.endsWith('/partial-artifact')) {
      assert.equal(url.searchParams.get('expected_revision'), String(revision));
      await send(revision === task.revision ? null : { ...view, task_revision: revision }, revision === task.revision ? 409 : 200);
      return true;
    }
    if (url.pathname.endsWith(`/${task.id}`)) { await send({ ...task, revision }); return true; }
    return false;
  } });
  await scenario('empty owned task list', async (page) => {
    await page.goto(`${origin}/research`);
    await page.getByText('尚无已保存的研究任务。', { exact: true }).waitFor();
    assert.equal(await page.locator('.research-task-link').count(), 0);
  }, { handler: async ({ url, send }) => url.pathname.endsWith('/research-tasks') ? (await send({ items: [], total: 0, offset: 0, limit: 8 }), true) : false });
  await scenario('401 clears session and returns to login', async (page) => {
    await page.goto(`${origin}/research`);
    await page.waitForURL('**/login?redirect=*');
    assert.equal(await page.evaluate(() => localStorage.getItem('rag_access_token')), null);
  }, { handler: async ({ send }) => { await send(null, 401, '登录已失效'); return true; } });
  await scenario('anonymous protected route does not fetch research', async (page, calls) => {
    await page.goto(`${origin}/research`);
    await page.waitForURL('**/login*');
    assert.equal(calls.length, 0);
  }, { authenticated: false });
  const completed = { ...clone(task), status: 'completed', artifact: view.artifact, verification: {} };
  await scenario('completed snapshot does not request failed partial view', async (page, calls) => {
    await page.goto(`${origin}/research/${task.id}`);
    await page.getByText('执行已结束，结论仍需人工复核', { exact: true }).waitFor();
    await page.getByRole('button', { name: '查看引文 1', exact: true }).waitFor();
    assert(!calls.some((c) => c.path.endsWith('/partial-artifact')));
    await page.getByText(/按当前审阅展示/).waitFor();
  }, { handler: async ({ url, send }) => {
    if (url.pathname.endsWith(`/${task.id}`)) { await send(completed); return true; }
    if (url.pathname.endsWith('/review')) {
      await send({ view_id: 'review-fixture', task_id: task.id, task_revision: completed.revision,
        source_artifact_id: completed.artifact.artifact_id, artifact: completed.artifact, events: [],
        annotation_status: 'owner_review_overlay', quality_gate_passed: false, model_calls: 0, embedding_calls: 0,
        items: completed.artifact.citations.map((claim) => ({ claim, source: completed.artifact.citation_sources.find((s) => s.claim_id === claim.claim_id), review_status: 'unreviewed', latest_event_id: null })) });
      return true;
    }
    return false;
  } });
  const injected = clone(view);
  injected.artifact.citations[0].citation.quote = '<img src=x onerror="window.injected=true">';
  await scenario('source excerpt is escaped text', async (page) => {
    await ready(page);
    await page.getByRole('button', { name: '查看引文 1', exact: true }).click();
    assert.equal(await page.locator('.research-source blockquote').textContent(), injected.artifact.citations[0].citation.quote);
    assert.equal(await page.locator('.research-source img').count(), 0);
    assert.equal(await page.evaluate(() => window.injected), undefined);
  }, { handler: async ({ url, send }) => url.pathname.endsWith('/partial-artifact') ? (await send(injected), true) : false });
  const second = { ...clone(task), id: 'research_browser_second', goal: 'Second saved research task', status: 'pending', steps: [] };
  await scenario('pagination fetches summaries without per-row detail calls', async (page, calls) => {
    await ready(page);
    await page.getByRole('button', { name: '下一页任务' }).click();
    await page.locator('.research-task-link').filter({ hasText: second.goal }).waitFor();
    assert(calls.some((c) => c.search.includes('offset=8')));
    assert(!calls.some((c) => c.path.endsWith(`/${second.id}`)));
    await page.getByRole('button', { name: '上一页任务' }).click();
    await page.locator('.research-task-link').filter({ hasText: task.goal }).waitFor();
  }, { handler: async ({ url, send }) => {
    if (!url.pathname.endsWith('/research-tasks')) return false;
    const offset = Number(url.searchParams.get('offset'));
    assert.equal(url.searchParams.get('limit'), '8');
    await send({ items: [summary(offset ? second : task)], total: 9, limit: 8, offset });
    return true;
  } });
  let listFailed = true;
  await scenario('list failure can be retried', async (page) => {
    await page.goto(`${origin}/research`);
    await page.getByRole('alert').filter({ hasText: '目录暂不可用' }).waitFor();
    listFailed = false;
    await page.getByRole('button', { name: '重试读取' }).click();
    await page.getByRole('button', { name: '查看引文 1', exact: true }).waitFor();
  }, { handler: async ({ url, send }) => {
    if (listFailed && url.pathname.endsWith('/research-tasks')) { await send(null, 500, '目录暂不可用'); return true; }
    return false;
  } });
  await scenario('switching task ignores delayed old partial response', async (page) => {
    await page.goto(`${origin}/research/${task.id}`);
    await page.getByText('核对来源并读取部分稿…', { exact: true }).waitFor();
    await page.locator('.research-task-link').filter({ hasText: second.goal }).click();
    await page.getByRole('heading', { name: second.goal, exact: true }).waitFor();
    await page.waitForTimeout(450);
    assert.equal(await page.getByRole('button', { name: /查看引文/ }).count(), 0);
    assert.equal(await page.locator('.research-source').count(), 0);
  }, { handler: async ({ url, send }) => {
    if (url.pathname.endsWith('/research-tasks')) { await send({ items: [summary(task), summary(second)], total: 2, offset: 0, limit: 8 }); return true; }
    if (url.pathname.endsWith(`/${second.id}`)) { await send(second); return true; }
    if (url.pathname.endsWith('/partial-artifact')) { await new Promise((r) => setTimeout(r, 350)); try { await send(view); } catch { /* aborted by navigation */ } return true; }
    return false;
  } });
  const unavailableView = clone(view);
  unavailableView.unverified_documents = task.sources.map((s) => s.document_id);
  unavailableView.artifact.citations = [];
  unavailableView.artifact.citation_sources = [];
  unavailableView.artifact.knowledge_gaps = unavailableView.artifact.rows.flatMap((row) => row.cells.map((cell) => `${row.document_id}:${cell.facet}:unverified`));
  unavailableView.artifact.rows.forEach((row) => row.cells.forEach((cell) => {
    cell.status = 'missing'; cell.statement = null; cell.claim_ids = []; cell.reasons = ['retrieved_evidence_insufficient'];
  }));
  await scenario('unfinished verification is not presented as missing paper evidence', async (page) => {
    await page.goto(`${origin}/research/${task.id}`);
    await page.locator('.research-table td').first().waitFor();
    assert.equal(await page.locator('.research-table td > span').filter({ hasText: /^未完成核验$/ }).count(), 12);
    assert.equal(await page.locator('.research-table').getByText('未检出证据', { exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: /查看引文/ }).count(), 0);
    await page.locator('.research-table td details').first().locator('summary').click();
    await page.getByText('尚无完整核验报告。请先查看任务步骤，不能据此判断论文是否报告相关内容。', { exact: true }).first().waitFor();
    await page.screenshot({ path: fileURLToPath(new URL('unverified.png', out)) });
  }, { handler: async ({ url, send }) => url.pathname.endsWith('/partial-artifact') ? (await send(unavailableView), true) : false });
  console.log(`${results.length} browser scenarios passed (intercepted API, frozen real payloads)`);
} finally {
  await browser?.close();
  server.kill();
  await writeFile(new URL('results.json', out), JSON.stringify({ fixture_mode: 'intercepted API with frozen R37/R39 payloads', model_calls: 0, results }, null, 2));
}
