/** Synthetic execution-state browser contracts; never connects to a model or business DB. */
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
const root = fileURLToPath(new URL('../', import.meta.url)), out = new URL('./shots/research-run/', import.meta.url);
await mkdir(out, { recursive: true });
const base = JSON.parse(await readFile(new URL('../../backend/evaluation/results/research_condition_e2e_20261104.json', import.meta.url), 'utf8')).failed_task;
const pending = { ...base, status: 'pending', revision: 0, model_calls_used: 0, tool_calls_used: 0, verification: null, artifact: null,
  steps: base.steps.map((s) => ({ ...s, status: 'pending', result: null })) };
const other = { ...pending, id: 'research_other_run_test', goal: 'Other research record' };
const port = Number(process.env.RESEARCH_TEST_PORT || 5180), origin = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, windowsHide: true, stdio: 'pipe' });
let ready = false, startupError = '', browser;
server.stdout.on('data', (s) => { if (String(s).includes('Local:')) ready = true; });
server.stderr.on('data', (s) => { startupError += s; });
const results = [];
const runButton = (page) => page.getByRole('button', { name: '执行下一步', exact: true });
async function scenario(name, run, { handler, initial = pending, mobile = false } = {}) {
  let task = structuredClone(initial);
  const context = await browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 } });
  await context.addInitScript(() => { localStorage.setItem('rag_access_token', 'browser-contract-test'); localStorage.setItem('rag_user_info', JSON.stringify({ id: 1, email: 'reader@example.test', role: 'user' })); });
  const page = await context.newPage(), calls = [], errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request(), url = new URL(req.url()), body = req.postDataJSON();
    calls.push({ method: req.method(), path: url.pathname, body });
    assert.equal(req.headers().authorization, 'Bearer browser-contract-test');
    const send = (data, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify({ code, message: code === 200 ? 'ok' : '请求未完成', data }) });
    if (handler && await handler({ route, url, body, send, task, setTask: (t) => { task = t; } })) return;
    if (url.pathname.endsWith('/control')) {
      assert.equal(req.method(), 'POST'); assert.equal(body.expected_revision, task.revision);
      assert.deepEqual(Object.keys(body).sort(), ['action', 'expected_revision']);
      task = { ...task, revision: task.revision + 1, status: { pause: 'paused', resume: 'pending', cancel: 'cancelled' }[body.action] };
      await new Promise((r) => setTimeout(r, 100)); return send(task);
    }
    if (url.pathname.endsWith('/run')) {
      assert.equal(req.method(), 'POST'); assert.equal(body.expected_revision, task.revision);
      const n = task.steps.findIndex((s) => s.status === 'pending');
      task = { ...task, revision: task.revision + 2, status: 'running', tool_calls_used: task.tool_calls_used + 1,
        steps: task.steps.map((s, i) => i === n ? { ...s, status: 'succeeded' } : s) };
      await new Promise((r) => setTimeout(r, 150)); return send(task);
    }
    assert.equal(req.method(), 'GET', 'only explicit single-step POST is allowed');
    if (url.pathname.endsWith('/research-tasks')) return send({ items: [task, other].map((t) => ({ id: t.id, goal_preview: t.goal, revision: t.revision, status: t.status })), total: 2, limit: 8, offset: 0 });
    if (url.pathname.endsWith('/partial-artifact')) return send(null, 400);
    if (url.pathname.endsWith(`/${task.id}`)) return send(task);
    if (url.pathname.endsWith(`/${other.id}`)) return send(other);
    throw new Error(`Unexpected endpoint ${url.pathname}`);
  });
  try {
    await page.goto(`${origin}/research/${pending.id}`);
    await page.getByRole('region', { name: '单步执行' }).waitFor();
    await run(page, calls);
    assert.deepEqual(errors, []); results.push({ name, passed: true }); console.log(`PASS ${name}`);
  } finally { await context.close(); }
}
try {
  for (let i = 0; !ready; i++) { if (i > 200 || server.exitCode != null) throw new Error(`Vite startup failed: ${startupError}`); await new Promise((r) => setTimeout(r, 50)); }
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : { channel: process.env.RESEARCH_BROWSER_CHANNEL || 'chrome' }) });
  await scenario('pause resume and explicit cancellation never execute a tool', async (page, calls) => {
    await page.getByRole('button', { name: '暂停任务', exact: true }).dblclick();
    await page.getByText('已保存版本 1', { exact: true }).waitFor();
    await page.getByRole('button', { name: '继续为待执行', exact: true }).click();
    await page.getByText('已保存版本 2', { exact: true }).waitFor();
    await page.getByRole('button', { name: '取消任务…', exact: true }).click();
    assert.equal(calls.filter((c) => c.path.endsWith('/control')).length, 2);
    await page.getByRole('button', { name: '确认取消任务', exact: true }).click();
    await page.getByText('已保存版本 3', { exact: true }).waitFor();
    assert.equal(await page.getByRole('region', { name: '任务控制' }).count(), 0);
    assert.deepEqual(calls.filter((c) => c.path.endsWith('/control')).map((c) => c.body.action), ['pause', 'resume', 'cancel']);
    assert(!calls.some((c) => c.path.endsWith('/run')));
  });
  for (const code of [409, 500]) await scenario(`control ${code} locks without resubmission`, async (page, calls) => {
    await page.getByRole('button', { name: '暂停任务', exact: true }).click();
    await page.getByRole('button', { name: '核对控制状态', exact: true }).waitFor();
    assert(await page.getByRole('button', { name: '暂停任务', exact: true }).isDisabled());
    assert.equal(calls.filter((c) => c.path.endsWith('/control')).length, 1);
  }, { handler: async ({ url, send }) => url.pathname.endsWith('/control') ? (await send(null, code), true) : false });
  await scenario('late control response does not replace a newly selected task', async (page) => {
    await page.getByRole('button', { name: '暂停任务', exact: true }).click();
    await page.getByRole('link', { name: /Other research record/ }).click();
    await page.getByRole('heading', { name: other.goal, exact: true }).waitFor();
    await page.waitForTimeout(400);
    assert.equal(await page.getByRole('button', { name: '继续为待执行', exact: true }).count(), 0);
  }, { handler: async ({ url, task, send }) => {
    if (!url.pathname.endsWith('/control')) return false;
    await new Promise((r) => setTimeout(r, 250)); await send({ ...task, status: 'paused', revision: task.revision + 1 }); return true;
  } });
  await scenario('one click is one revision-fenced attempt, never an automatic loop', async (page, calls) => {
    await runButton(page).dblclick(); await page.getByText('已保存版本 2', { exact: true }).waitFor();
    await page.waitForTimeout(350); assert.equal(calls.filter((c) => c.path.endsWith('/run')).length, 1);
    await runButton(page).click(); await page.getByText('已保存版本 4', { exact: true }).waitFor();
    assert.deepEqual(calls.filter((c) => c.path.endsWith('/run')).map((c) => c.body.expected_revision), [0, 2]);
  });
  await scenario('409 blocks another attempt until explicit state refresh', async (page, calls) => {
    await runButton(page).click(); await page.getByRole('alert').filter({ hasText: '任务版本已变化' }).waitFor();
    assert(await runButton(page).isDisabled());
    await page.getByRole('button', { name: '核对最新状态' }).click(); await runButton(page).waitFor();
    assert.equal(calls.filter((c) => c.path.endsWith('/run')).length, 1);
  }, { handler: async ({ url, send }) => url.pathname.endsWith('/run') ? (await send(null, 409), true) : false });
  await scenario('network uncertainty never resubmits and running checkpoint stays blocked', async (page, calls) => {
    await runButton(page).click(); await page.getByRole('alert').filter({ hasText: '执行可能仍在服务端进行' }).waitFor();
    assert(await runButton(page).isDisabled());
    await page.getByRole('button', { name: '核对最新状态' }).click();
    await page.getByText(/已保存的步骤仍为执行中/).waitFor();
    assert.equal(await runButton(page).count(), 0);
    assert.equal(calls.filter((c) => c.path.endsWith('/run')).length, 1);
  }, { handler: async ({ route, url, task, setTask }) => {
    if (!url.pathname.endsWith('/run')) return false;
    setTask({ ...task, status: 'running', revision: 1, tool_calls_used: 1, steps: task.steps.map((s, i) => i === 0 ? { ...s, status: 'running' } : s) });
    await route.abort('timedout'); return true;
  } });
  await scenario('leaving task ignores its late execution response', async (page, calls) => {
    await runButton(page).click(); await page.locator('.research-task-link').filter({ hasText: other.goal }).click();
    await page.getByRole('heading', { name: other.goal, exact: true }).waitFor();
    await page.waitForTimeout(450); assert(page.url().endsWith(other.id));
    assert.equal(calls.filter((c) => c.path.endsWith('/run')).length, 1);
  }, { handler: async ({ url, send, task }) => {
    if (!url.pathname.endsWith('/run')) return false;
    await new Promise((r) => setTimeout(r, 350)); try { await send({ ...task, revision: 2 }); } catch { /* page may be closed */ } return true;
  } });
  await scenario('insufficient budget disables execution without consuming a step', async (page, calls) => {
    await page.getByText(/剩余预算不足以执行下一步/).waitFor();
    assert.equal(await runButton(page).count(), 0); assert(!calls.some((c) => c.method === 'POST'));
  }, { initial: { ...pending, tool_calls_used: pending.budget.max_steps } });
  await scenario('paused task exposes no execution or implicit recovery', async (page, calls) => {
    await page.getByText(/当前状态不能直接执行/).waitFor(); assert.equal(await runButton(page).count(), 0);
    assert(!calls.some((c) => c.method === 'POST'));
  }, { initial: { ...pending, status: 'paused' } });
  await scenario('mobile execution budgets and action remain readable', async (page) => {
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await runButton(page).scrollIntoViewIfNeeded();
    await page.screenshot({ path: fileURLToPath(new URL('mobile.png', out)) });
  }, { mobile: true });
  await scenario('desktop execution budget and action', async (page) => {
    await page.screenshot({ path: fileURLToPath(new URL('desktop.png', out)) });
  });
  const failedStep = { ...pending.steps[1], status: 'failed', started_at: '2026-11-07T00:00:00+00:00', finished_at: '2026-11-07T00:00:01+00:00',
    result: { status: 'failed', elapsed_ms: 1000, error_type: 'ConnectTimeout', error_code: 'research_tool_failed', warnings: [], model_calls: [] } };
  const failed = { ...pending, status: 'failed', revision: 4, tool_calls_used: 2,
    steps: pending.steps.map((s, i) => i === 0 ? { ...s, status: 'succeeded' } : i === 1 ? failedStep : s) };
  const decision = { task_id: failed.id, task_revision: 4, eligible: true, reason: 'available', failed_step_id: failedStep.id,
    remaining_tools: 11, required_tools: 10, remaining_model_calls: 8, required_model_calls: 6, sources_validated: true };
  await scenario('explicit recovery retains budget/history and does not run automatically', async (page, calls) => {
    await page.getByRole('button', { name: '核对恢复条件', exact: true }).click();
    const confirm = page.getByRole('button', { name: '确认恢复为待执行', exact: true });
    await confirm.waitFor(); await confirm.dblclick();
    await page.getByText('已保存版本 5', { exact: true }).waitFor();
    assert.equal(calls.filter((c) => c.path.endsWith('/retry') && c.method === 'POST').length, 1);
    assert(!calls.some((c) => c.path.endsWith('/run')));
    await page.getByText('保留的失败尝试 · 1', { exact: true }).click();
    await page.getByText(/ConnectTimeout · 1000ms/).waitFor();
    await page.screenshot({ path: fileURLToPath(new URL('retry-prepared.png', out)) });
  }, { initial: failed, handler: async ({ url, body, send, setTask }) => {
    if (!url.pathname.endsWith('/retry')) return false;
    if (!body) { await send(decision); return true; }
    assert.equal(body.expected_revision, 4);
    const restored = { ...failed, status: 'pending', revision: 5,
      steps: failed.steps.map((s) => s.status === 'failed' ? { ...s, status: 'pending', result: null, started_at: null, finished_at: null } : s),
      retry_events: [{ failed_revision: 4, tool_calls_used: 2, model_calls_used: 0, failed_step: failedStep }] };
    await new Promise((r) => setTimeout(r, 150)); setTask(restored); await send(restored); return true;
  } });
  for (const [reason, label] of [['insufficient_budget', '剩余预算不足以覆盖未完成计划'], ['unaccounted_history', '无法排除旧执行仍在进行']]) {
    await scenario(`recovery blocked: ${reason}`, async (page, calls) => {
      await page.getByRole('button', { name: '核对恢复条件', exact: true }).click();
      await page.getByText(new RegExp(label)).waitFor();
      assert.equal(await page.getByRole('button', { name: '确认恢复为待执行', exact: true }).count(), 0);
      assert(!calls.some((c) => c.method === 'POST'));
    }, { initial: failed, handler: async ({ url, send }) => url.pathname.endsWith('/retry') ? (await send({ ...decision, eligible: false, reason, sources_validated: false }), true) : false });
  }
  await scenario('recovery revision conflict requires refresh and never resubmits', async (page, calls) => {
    await page.getByRole('button', { name: '核对恢复条件', exact: true }).click();
    await page.getByRole('button', { name: '确认恢复为待执行', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: '恢复条件或版本已变化' }).waitFor();
    assert.equal(calls.filter((c) => c.method === 'POST').length, 1);
    assert.equal(await page.getByRole('button', { name: '确认恢复为待执行', exact: true }).count(), 0);
  }, { initial: failed, handler: async ({ url, body, send }) => url.pathname.endsWith('/retry') ? (await send(body ? null : decision, body ? 409 : 200), true) : false });
  await scenario('changed source prevents recovery confirmation', async (page, calls) => {
    await page.getByRole('button', { name: '核对恢复条件', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: '请求未完成' }).last().waitFor();
    assert.equal(await page.getByRole('button', { name: '确认恢复为待执行', exact: true }).count(), 0);
    assert(!calls.some((c) => c.method === 'POST'));
  }, { initial: failed, handler: async ({ url, send }) => url.pathname.endsWith('/retry') ? (await send(null, 400), true) : false });
  await scenario('late recovery decision cannot overwrite another task', async (page, calls) => {
    await page.getByRole('button', { name: '核对恢复条件', exact: true }).click();
    await page.locator('.research-task-link').filter({ hasText: other.goal }).click();
    await page.getByRole('heading', { name: other.goal, exact: true }).waitFor();
    await page.waitForTimeout(400);
    assert.equal(await page.getByRole('button', { name: '确认恢复为待执行', exact: true }).count(), 0);
    assert(!calls.some((c) => c.method === 'POST'));
  }, { initial: failed, handler: async ({ url, send }) => {
    if (!url.pathname.endsWith('/retry')) return false;
    await new Promise((r) => setTimeout(r, 300)); try { await send(decision); } catch { /* closed context */ } return true;
  } });
  await scenario('mobile recovery conditions and confirmation fit viewport', async (page) => {
    await page.getByRole('button', { name: '核对恢复条件', exact: true }).click();
    await page.getByRole('button', { name: '确认恢复为待执行', exact: true }).scrollIntoViewIfNeeded();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: fileURLToPath(new URL('retry-mobile.png', out)) });
  }, { initial: failed, mobile: true, handler: async ({ url, send }) => url.pathname.endsWith('/retry') ? (await send(decision), true) : false });
  console.log(`${results.length} execution browser scenarios passed (synthetic intercepted API)`);
} finally { await browser?.close(); server.kill(); await writeFile(new URL('results.json', out), JSON.stringify({ fixture_mode: 'synthetic intercepted execution API', results, external_model_calls: 0 }, null, 2)); }
