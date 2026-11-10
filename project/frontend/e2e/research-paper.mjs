/** Explicit live-provider experiment, never part of the default test command. */
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
if (!process.argv.includes('--allow-live')) throw new Error('Live acceptance requires --allow-live (up to 3 embedding and 8 completion requests)');
const retryCopy = process.argv.includes('--retry-copy');
const root = fileURLToPath(new URL('../', import.meta.url));
const backendRoot = fileURLToPath(new URL('../../backend/', import.meta.url));
const output = resolve(backendRoot, process.env.RAG4_ACCEPTANCE_OUTPUT || (retryCopy ? 'data/research-paper-retry-20261108' : 'data/research-paper-browser-20261106'));
const shots = new URL(retryCopy ? './shots/research-paper-retry/' : './shots/research-paper/', import.meta.url); await mkdir(shots, { recursive: true });
const python = process.env.RAG4_TEST_PYTHON || 'C:/Users/gy/.conda/envs/rag4-py3.11/python.exe';
const input = retryCopy ? ['--source-run', 'data/research-paper-browser-20261106', '--vectors', 'data/research-paper-browser-20261106/vectors',
  '--task-name', 'research_18e5ac69ce68573054a1ac4e.json', '--database-name', 'snapshot.sqlite', '--retry-copy', '--embedding-limit', '2', '--completion-limit', '6']
  : ['--source-run', 'data/research-condition-repair-20261104', '--vectors', 'data/research-condition-e2e-20261104/vectors'];
const backend = spawn(python, ['scripts/serve_research_acceptance.py', ...input, '--output', output, '--allow-live'], { cwd: backendRoot, windowsHide: true, stdio: 'pipe' });
let logs = '', browser, vite, failure, meta;
backend.stderr.on('data', (s) => { logs = (logs + s).slice(-8000); });
backend.stdout.on('data', (s) => { logs = (logs + s).slice(-8000); });
const report = { date: retryCopy ? '2026-11-08' : '2026-11-06', retry_copy: retryCopy, quality_gate_passed: false, api_interception: false, output, steps: [] };
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(check, ms = 45000) { const deadline = Date.now() + ms; while (Date.now() < deadline) { if (await check()) return; await delay(100); } throw new Error('Acceptance wait exceeded limit'); }
const port = Number(process.env.RESEARCH_TEST_PORT || 5182), origin = `http://127.0.0.1:${port}`;
try {
  await until(async () => {
    if (backend.exitCode != null) throw new Error(`Acceptance server failed before browser: ${logs}`);
    try { meta = JSON.parse(await readFile(resolve(output, 'ready.json'), 'utf8')); return true; } catch { return false; }
  });
  let ready = false;
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
    cwd: root, windowsHide: true, stdio: 'pipe', env: { ...process.env, VITE_API_BASE_URL: '', VITE_API_TARGET: `http://127.0.0.1:${meta.port}` } });
  vite.stdout.on('data', (s) => { if (String(s).includes('Local:')) ready = true; });
  await until(async () => { if (vite.exitCode != null) throw new Error('Vite port unavailable'); return ready; });
  browser = await chromiumBrowser();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }), page = await context.newPage();
  const errors = []; page.on('pageerror', (e) => errors.push(e.message));
  const route = retryCopy ? `/research/${meta.source_task_id}` : '/research/new';
  await page.goto(origin + route); await page.waitForURL('**/login');
  await page.locator('#email').fill('paper-acceptance@outlook.com'); await page.locator('#password').fill('paper-acceptance-password');
  await page.getByRole('button', { name: '登录', exact: true }).click(); await page.waitForURL('**' + route);
  const token = await page.evaluate(() => localStorage.getItem('rag_access_token'));
  let task;
  if (retryCopy) {
    const before = (await (await context.request.get(`${origin}/api/v1/research-tasks/${meta.source_task_id}`, { headers: { Authorization: `Bearer ${token}` } })).json()).data;
    await page.getByRole('button', { name: '核对恢复条件', exact: true }).click();
    const response = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith('/retry') && r.request().method() === 'POST');
    await page.getByRole('button', { name: '确认恢复为待执行', exact: true }).click();
    const prepared = await response; assert.equal(prepared.status(), 200); task = (await prepared.json()).data;
    assert.equal(task.status, 'pending'); assert.equal(task.revision, before.revision + 1);
    assert.deepEqual(task.budget, before.budget); assert.deepEqual(task.bundles, before.bundles);
    assert.deepEqual(task.steps[0], before.steps[0]);
    assert.equal(task.tool_calls_used, before.tool_calls_used); assert.equal(task.model_calls_used, before.model_calls_used);
    assert.deepEqual(task.retry_events.at(-1).failed_step, before.steps.find((s) => s.status === 'failed'));
    report.recovery = { from_revision: before.revision, pending_revision: task.revision, successful_search_preserved: true, counters_preserved: true };
  } else {
  await page.getByRole('radio').first().check();
  for (const name of ['dpr.pdf', 'fid.pdf', 'realm.pdf']) await page.getByRole('checkbox', { name, exact: true }).check();
  await page.getByLabel('02 / 研究目标').fill(meta.goal);
  await page.getByRole('button', { name: '校验来源并预览计划', exact: true }).click();
  await page.getByRole('region', { name: '待确认研究计划' }).waitFor();
  const created = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/v1/research-tasks' && r.request().method() === 'POST');
  await page.getByRole('button', { name: '确认创建待执行任务', exact: true }).click();
  const createResponse = await created; assert.equal(createResponse.status(), 200);
  task = (await createResponse.json()).data;
  assert.notEqual(task.id, meta.source_task_id); assert.equal(task.model_calls_used, 0);
  report.new_task_id = task.id;
  }
  report.task_id = task.id;
  await page.waitForURL(`**/research/${task.id}`);
  await page.getByText(`已保存版本 ${task.revision}`, { exact: true }).waitFor();
  for (let n = 0; n < 13 && !['failed', 'completed', 'cancelled', 'paused'].includes(task.status); n++) {
    await page.getByRole('button', { name: '执行下一步', exact: true }).click();
    // GET-only observation handles a browser timeout without retrying the POST.
    let observed;
    await until(async () => {
      const response = await context.request.get(`${origin}/api/v1/research-tasks/${task.id}`, { headers: { Authorization: `Bearer ${token}` } });
      assert.equal(response.status(), 200); observed = (await response.json()).data;
      if (observed.revision > task.revision && !observed.steps.some((s) => s.status === 'running')) return true;
      await delay(2000); return false;
    }, 90000);
    task = observed;
    report.steps.push({ revision: task.revision, status: task.status, tool_calls: task.tool_calls_used, model_calls: task.model_calls_used,
      error_code: task.error_code, failed_step: task.steps.find((s) => s.status === 'failed')?.result ?? null });
    await page.getByRole('button', { name: '刷新任务', exact: true }).click();
    await page.getByText(`已保存版本 ${task.revision}`, { exact: true }).waitFor();
    console.log(`Observed revision ${task.revision}: ${task.status}; tools=${task.tool_calls_used}, completion attempts=${task.model_calls_used}`);
  }
  report.task_status = task.status; report.task_completed = task.status === 'completed';
  assert(['failed', 'completed'].includes(task.status), 'bounded run must stop at terminal observation');
  if (task.status === 'failed') await page.getByRole('heading', { name: '失败任务的部分比较稿' }).waitFor();
  const cite = page.getByRole('button', { name: '查看引文 1', exact: true });
  if (await cite.count()) { await cite.click(); await page.getByRole('region', { name: '引用原文' }).waitFor(); }
  await page.screenshot({ path: fileURLToPath(new URL('observed-task.png', shots)) });
  assert.deepEqual(errors, []); report.browser_errors = errors; report.observed = true;
} catch (e) { failure = e; report.error = e.message; }
finally {
  await browser?.close(); vite?.kill();
  if (backend.exitCode == null) { await writeFile(resolve(output, 'stop'), 'stop'); try { await until(async () => backend.exitCode != null, 20000); } catch { backend.kill(); } }
  try {
    report.audit = JSON.parse(await readFile(resolve(output, 'audit.json'), 'utf8'));
    for (const name of ['original_task_file_unchanged', 'original_database_unchanged', 'original_vectors_unchanged', 'copied_vectors_unchanged', 'active_unchanged']) assert.equal(report.audit[name], true, name);
    if (retryCopy) {
      assert.equal(report.audit.successful_source_steps_unchanged, true);
      assert.equal(report.audit.original_budget_unchanged, true);
    } else assert.equal(report.audit.parent_task_unchanged, true);
    assert(report.audit.calls.filter((c) => c.path.endsWith('/embeddings')).length <= (retryCopy ? 2 : 3));
    assert(report.audit.calls.filter((c) => c.path.endsWith('/completions')).length <= (retryCopy ? 6 : 8));
    assert.equal(report.audit.task_count, retryCopy ? 0 : 1);
  } catch (e) { failure ||= e; report.audit_error = e.message; }
  await writeFile(new URL('results.json', shots), JSON.stringify(report, null, 2));
  console.log(`Acceptance evidence retained: ${output}`);
}
if (failure) throw failure;
async function chromiumBrowser() {
  const { chromium } = await import('playwright');
  return chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : { channel: process.env.RESEARCH_BROWSER_CHANNEL || 'chrome' }) });
}
