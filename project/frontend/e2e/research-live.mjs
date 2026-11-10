/** Real browser -> Vite proxy -> Uvicorn -> isolated SQLite/LocalVectorStore.
 * No page.route(), no injected login state, no API stubs in the browser.
 * Deterministic provider transport exists only inside the fixture server.
 */
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
const root = fileURLToPath(new URL('../', import.meta.url));
const fixtureRoot = await mkdtemp(join(tmpdir(), 'rag4-live-e2e-'));
const out = new URL('./shots/research-live/', import.meta.url);
await mkdir(out, { recursive: true });
const python = process.env.RAG4_TEST_PYTHON || 'C:/Users/gy/.conda/envs/rag4-py3.11/python.exe';
const backend = spawn(python, ['tests/support/research_live_server.py', '--root', fixtureRoot], {
  cwd: fileURLToPath(new URL('../../backend/', import.meta.url)), windowsHide: true, stdio: 'pipe' });
let backendLogs = '', vite, browser, failure, lastPage, report = { fixture_root: fixtureRoot, api_interception: false, results: [] };
backend.stdout.on('data', (s) => { backendLogs = (backendLogs + s).slice(-12000); });
backend.stderr.on('data', (s) => { backendLogs = (backendLogs + s).slice(-12000); });
backend.on('error', (e) => { backendLogs += e.message; });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(check, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (await check()) return; await wait(75); }
  throw new Error('Timed out waiting for isolated service');
}
let meta;
const port = Number(process.env.RESEARCH_TEST_PORT || 5181), origin = `http://127.0.0.1:${port}`;
const goal = 'Compare synthetic fixture methods with source citations';
async function login(page, email = 'student@outlook.com') {
  await page.goto(`${origin}/research`); await page.waitForURL('**/login');
  await page.locator('#email').fill(email); await page.locator('#password').fill('fixture-password-123');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.waitForURL('**/research');
}
async function create(page, text) {
  await page.getByRole('link', { name: '准备新研究', exact: true }).click();
  await page.getByRole('radio').check();
  for (const label of ['fixture_dpr.txt', 'fixture_fid.txt', 'fixture_realm.txt']) await page.getByRole('checkbox', { name: label, exact: true }).check();
  await page.getByLabel('02 / 研究目标').fill(text);
  await page.getByRole('button', { name: '校验来源并预览计划', exact: true }).click();
  await page.getByRole('region', { name: '待确认研究计划' }).waitFor();
  const created = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/v1/research-tasks' && r.request().method() === 'POST');
  await page.getByRole('button', { name: '确认创建待执行任务', exact: true }).click();
  const response = await created; assert.equal(response.status(), 200);
  const task = (await response.json()).data;
  assert.equal(task.status, 'pending'); assert.equal(task.model_calls_used, 0);
  await page.waitForURL(`**/research/${task.id}`); await page.getByText('已保存版本 0', { exact: true }).waitFor();
  return task;
}
async function step(page, task) {
  const returned = page.waitForResponse((r) => new URL(r.url()).pathname === `/api/v1/research-tasks/${task.id}/run`);
  await page.getByRole('button', { name: '执行下一步', exact: true }).click();
  const response = await returned; assert.equal(response.status(), 200);
  const updated = (await response.json()).data;
  assert.equal(updated.tool_calls_used, task.tool_calls_used + 1);
  await page.getByText(`已保存版本 ${updated.revision}`, { exact: true }).waitFor();
  return updated;
}
try {
  await until(async () => {
    if (backend.exitCode != null) throw new Error(`Fixture server failed: ${backendLogs}`);
    try { meta = JSON.parse(await readFile(join(fixtureRoot, 'ready.json'), 'utf8')); return true; } catch { return false; }
  }, 60000);
  let viteReady = false, viteError = '';
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
    cwd: root, windowsHide: true, stdio: 'pipe', env: { ...process.env, VITE_API_BASE_URL: '', VITE_API_TARGET: `http://127.0.0.1:${meta.port}` } });
  vite.stdout.on('data', (s) => { if (String(s).includes('Local:')) viteReady = true; });
  vite.stderr.on('data', (s) => { viteError += s; });
  await until(async () => { if (vite.exitCode != null) throw new Error(viteError); return viteReady; });
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : { channel: process.env.RESEARCH_BROWSER_CHANNEL || 'chrome' }) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage(), errors = [], mutations = [];
  lastPage = page;
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('request', (req) => { if (req.method() !== 'GET' && new URL(req.url()).pathname.startsWith('/api/')) mutations.push({ method: req.method(), path: new URL(req.url()).pathname }); });
  await login(page);
  let task = await create(page, goal);
  report.results.push({ name: 'real login, owned version, preview and pending create', passed: true });
  for (const [action, label, expected] of [['pause', '暂停任务', 'paused'], ['resume', '继续为待执行', 'pending']]) {
    const returned = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith('/control'));
    await page.getByRole('button', { name: label, exact: true }).click();
    const response = await returned; assert.equal(response.status(), 200);
    const updated = (await response.json()).data;
    assert.equal(updated.status, expected); assert.equal(updated.revision, task.revision + 1);
    assert.equal(updated.model_calls_used, 0); assert.equal(updated.tool_calls_used, 0);
    task = updated; await page.getByText(`已保存版本 ${task.revision}`, { exact: true }).waitFor();
  }
  report.results.push({ name: 'real pause and resume preserve zero usage and do not execute a tool', passed: true });
  const initial = task;
  for (let n = 0; n < initial.steps.length; n++) task = await step(page, task);
  assert.equal(task.status, 'completed'); assert.equal(task.model_calls_used, 6);
  assert.equal(task.artifact.citations.length, 3); assert.equal(task.artifact.knowledge_gaps.length, 9);
  await page.getByRole('button', { name: '查看引文 1', exact: true }).click();
  const source = page.getByRole('region', { name: '引用原文' });
  assert.equal(await source.locator('blockquote').textContent(), task.artifact.citations[0].citation.quote);
  await source.getByText('页码未记录', { exact: false }).waitFor();
  await page.screenshot({ path: fileURLToPath(new URL('completed-source.png', out)) });
  report.results.push({ name: 'eleven explicit steps, SQL artifact and exact source excerpt', passed: true });
  const token = await page.evaluate(() => localStorage.getItem('rag_access_token'));
  const machineArtifact = JSON.stringify(task.artifact), originalBudget = structuredClone(task.budget);
  const originalUsage = [task.model_calls_used, task.tool_calls_used];
  await page.getByRole('button', { name: '关闭原文', exact: true }).click();
  await page.locator('.research-review > summary').click();
  for (const [index, decision] of ['withdraw', 'reset', 'retain'].entries()) {
    await page.getByLabel('选择结论').selectOption(task.artifact.citations[0].claim_id);
    await page.getByLabel('审阅决定').selectOption(decision);
    await page.getByLabel('审阅原因').fill(`Synthetic fixture review ${decision}; not an independent quality judgment.`);
    const written = page.waitForResponse((r) => new URL(r.url()).pathname.includes('/claims/') && r.request().method() === 'POST');
    await page.getByRole('button', { name: '保存审阅决定', exact: true }).click();
    const http = await written; assert.equal(http.status(), 200);
    const review = (await http.json()).data;
    assert.equal(review.task_revision, task.revision + 1); assert.equal(review.events.length, index + 1);
    assert.equal(review.source_artifact_id, task.artifact.artifact_id);
    assert.equal(review.model_calls, 0); assert.equal(review.embedding_calls, 0); assert.equal(review.quality_gate_passed, false);
    task = { ...task, revision: review.task_revision, claim_reviews: review.events };
    await page.getByText(`已保存版本 ${task.revision}`, { exact: true }).waitFor();
    await page.getByText(new RegExp(`展示 ${decision === 'withdraw' ? 2 : 3} 条已有结论`)).waitFor();
    if (decision === 'withdraw') {
      const started = page.waitForEvent('download');
      await page.getByRole('button', { name: '导出当前审阅稿（Markdown）', exact: true }).click();
      const file = await started, exported = await readFile(await file.path(), 'utf8');
      assert(file.suggestedFilename().endsWith(`-r${task.revision}-reviewed.md`));
      assert(!exported.includes(task.artifact.citations[0].statement));
      assert(exported.includes(review.view_id) && exported.includes('已撤下'));
      await page.screenshot({ path: fileURLToPath(new URL('review-withdrawn.png', out)) });
      report.results.push({ name: 'real download revalidates SQL revision and excludes the withdrawn claim from Markdown', passed: true });
    }
  }
  const storedHttp = await context.request.get(`${origin}/api/v1/research-tasks/${task.id}`, { headers: { Authorization: `Bearer ${token}` } });
  const stored = (await storedHttp.json()).data;
  assert.equal(JSON.stringify(stored.artifact), machineArtifact);
  assert.deepEqual(stored.budget, originalBudget); assert.deepEqual([stored.model_calls_used, stored.tool_calls_used], originalUsage);
  assert.deepEqual(stored.claim_reviews.map((e) => e.decision), ['withdraw', 'reset', 'retain']);
  await page.reload(); await page.getByText(`已保存版本 ${task.revision}`, { exact: true }).waitFor();
  await page.locator('.research-review > summary').click();
  await page.locator('.research-review-list > li[data-review-status=retained]').locator('summary').click();
  await page.getByText('Synthetic fixture review retain; not an independent quality judgment.', { exact: true }).waitFor();
  const auditStarted = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出审阅记录（JSON）', exact: true }).click();
  const auditDownload = await auditStarted, exportedAudit = JSON.parse(await readFile(await auditDownload.path(), 'utf8'));
  assert.equal(exportedAudit.task_revision, task.revision); assert.equal(exportedAudit.review_view.events.length, 3);
  assert.equal(exportedAudit.quality_gate_passed, false);
  await page.screenshot({ path: fileURLToPath(new URL('review-history.png', out)) });
  report.results.push({ name: 'real review withdraw reset retain, SQL history, reload, immutable machine artifact and unchanged usage', passed: true });
  const stale = await context.request.post(`${origin}/api/v1/research-tasks/${task.id}/run`, { headers: { Authorization: `Bearer ${token}` }, data: { expected_revision: 0 } });
  assert.equal(stale.status(), 409);
  report.results.push({ name: 'stale HTTP revision conflicts after completed run', passed: true });
  const foreignContext = await browser.newContext(); const foreign = await foreignContext.newPage();
  foreign.on('pageerror', (e) => errors.push(e.message));
  await login(foreign, 'other@outlook.com');
  await foreign.getByText('尚无已保存的研究任务。', { exact: true }).waitFor();
  const otherToken = await foreign.evaluate(() => localStorage.getItem('rag_access_token'));
  const otherHeaders = { Authorization: `Bearer ${otherToken}` };
  const foreignVersions = await foreignContext.request.get(`${origin}/api/v1/index-versions`, { headers: otherHeaders });
  assert.equal((await foreignVersions.json()).data.total, 0);
  assert.equal((await foreignContext.request.get(`${origin}/api/v1/research-tasks/${task.id}`, { headers: otherHeaders })).status(), 404);
  assert.equal((await foreignContext.request.post(`${origin}/api/v1/research-tasks/${task.id}/run`, { headers: otherHeaders, data: { expected_revision: task.revision } })).status(), 404);
  assert.equal((await foreignContext.request.get(`${origin}/api/v1/research-tasks/${task.id}/partial-artifact`, { headers: otherHeaders })).status(), 404);
  assert.equal((await foreignContext.request.get(`${origin}/api/v1/research-tasks/${task.id}/retry`, { headers: otherHeaders })).status(), 404);
  assert.equal((await foreignContext.request.get(`${origin}/api/v1/research-tasks/${task.id}/review`, { headers: otherHeaders })).status(), 404);
  assert.equal((await foreignContext.request.post(`${origin}/api/v1/research-tasks/${task.id}/claims/${task.artifact.citations[0].claim_id}/review`, {
    headers: otherHeaders, data: { expected_revision: task.revision, source_artifact_id: task.artifact.artifact_id, decision: 'withdraw', reason: 'Foreign fixture request.' } })).status(), 404);
  report.results.push({ name: 'second real login cannot discover or execute owner task', passed: true });
  const anonymous = await browser.newContext();
  assert.equal((await anonymous.request.get(`${origin}/api/v1/research-tasks`)).status(), 401);
  assert.equal((await anonymous.request.post(`${origin}/api/v1/research-tasks/${task.id}/run`, { data: { expected_revision: task.revision } })).status(), 401);
  await anonymous.close();
  report.results.push({ name: 'anonymous real HTTP reads and execution require JWT', passed: true });
  await writeFile(join(fixtureRoot, 'fail-realm'), 'deterministic verification failure');
  let failed = await create(page, 'Compare synthetic fixture methods with a retained failure');
  for (let n = 0; n < 9; n++) failed = await step(page, failed);
  assert.equal(failed.status, 'failed'); assert.equal(failed.verification_batches.length, 2); assert.equal(failed.artifact, null);
  await page.getByRole('heading', { name: '失败任务的部分比较稿' }).waitFor();
  await page.getByRole('button', { name: '查看引文 1', exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: /查看引文/ }).count(), 2);
  await page.screenshot({ path: fileURLToPath(new URL('failed-partial.png', out)) });
  report.results.push({ name: 'real failed verification retains two reports and read-only partial artifact', passed: true });
  const sourcePath = resolve(meta.source_paths[0]), fixtureRelative = relative(resolve(fixtureRoot), sourcePath);
  assert(fixtureRelative && !fixtureRelative.startsWith('..') && !resolve(sourcePath).startsWith('\\\\'));
  const originalFixtureBytes = await readFile(sourcePath);
  await writeFile(sourcePath, 'Changed isolated fixture bytes');
  const unavailable = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith('/partial-artifact') && r.status() === 400);
  await page.getByRole('button', { name: '刷新任务', exact: true }).click(); await unavailable;
  await page.getByRole('alert').first().waitFor();
  assert.equal(await page.getByRole('button', { name: /查看引文/ }).count(), 0);
  assert.equal(await page.getByRole('region', { name: '引用原文' }).count(), 0);
  assert.deepEqual(errors, []);
  assert.equal(mutations.filter((c) => c.path.endsWith('/run')).length, 20);
  report.results.push({ name: 'changed retained source rejects partial reread without stale citations', passed: true });
  // Restore only the explicitly created synthetic file, then exercise the new
  // recovery path without executing another model/tool attempt.
  await writeFile(sourcePath, originalFixtureBytes);
  await page.getByRole('button', { name: '刷新任务', exact: true }).click();
  await page.getByRole('button', { name: '核对恢复条件', exact: true }).click();
  await page.getByRole('button', { name: '确认恢复为待执行', exact: true }).waitFor();
  const preparedResponse = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith('/retry') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '确认恢复为待执行', exact: true }).click();
  const preparedHttp = await preparedResponse; assert.equal(preparedHttp.status(), 200);
  const prepared = (await preparedHttp.json()).data;
  assert.equal(prepared.status, 'pending'); assert.equal(prepared.revision, 19);
  assert.equal(prepared.model_calls_used, failed.model_calls_used); assert.equal(prepared.tool_calls_used, failed.tool_calls_used);
  assert.deepEqual(prepared.budget, failed.budget); assert.deepEqual(prepared.verification_batches, failed.verification_batches);
  assert.deepEqual(prepared.retry_events[0].failed_step, failed.steps.find((s) => s.status === 'failed'));
  await page.getByText('已保存版本 19', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: /查看引文/ }).count(), 0, 'old partial view must be cleared after recovery preparation');
  assert.equal(mutations.filter((c) => c.path.endsWith('/run')).length, 20, 'preparing recovery never runs a tool');
  await page.getByText('保留的失败尝试 · 1', { exact: true }).click();
  await page.screenshot({ path: fileURLToPath(new URL('retry-pending.png', out)) });
  report.results.push({ name: 'explicit recovery retains failed attempt, reports and quotas without running', passed: true });
  assert.deepEqual(errors, []);
  report.browser_passed = true;
  await foreignContext.close(); await context.close();
} catch (error) {
  report.error = error.message; failure = error;
  if (lastPage) {
    report.failed_url = lastPage.url();
    try { await lastPage.screenshot({ path: fileURLToPath(new URL('failure.png', out)) }); } catch { /* context may have closed */ }
  }
}
finally {
  await browser?.close(); vite?.kill();
  if (backend.exitCode == null) {
    await writeFile(join(fixtureRoot, 'stop'), 'stop');
    try { await until(async () => backend.exitCode != null, 15000); } catch { backend.kill(); }
  }
  try {
    report.server_audit = JSON.parse(await readFile(join(fixtureRoot, 'audit.json'), 'utf8'));
    assert.deepEqual(report.server_audit.active_state, [null, 0]);
    assert.equal(report.server_audit.baseline_unchanged, true);
    assert.equal(report.server_audit.retained_vectors_unchanged, true);
    assert.equal(report.server_audit.metrics.external_provider_calls, 0);
    assert.equal(report.server_audit.metrics.completion_attempts, 12);
    assert.equal(report.server_audit.metrics.completion_failures, 1);
    assert.equal(report.server_audit.baseline_record_count, 3);
    assert.equal(report.server_audit.tasks.length, 2);
    assert(report.server_audit.tasks.some((t) => t.status === 'completed' && t.revision === 27 && t.artifact_attached && t.claim_reviews === 3));
    assert(report.server_audit.tasks.some((t) => t.status === 'pending' && t.revision === 19 && t.verification_batches === 2 && !t.artifact_attached && t.retry_events === 1));
    assert.equal(backend.exitCode, 0, 'fixture server must shut down gracefully');
    report.audit_passed = true;
  } catch (error) {
    report.audit_passed = false; report.error ||= error.message; failure ||= error;
    if (!report.browser_passed) report.backend_log_tail = backendLogs;
  } finally {
    report.passed = Boolean(report.browser_passed && report.audit_passed);
    await writeFile(new URL('results.json', out), JSON.stringify(report, null, 2));
    console.log(`Isolated fixture retained at ${fixtureRoot}`);
  }
}
if (failure) throw failure;
console.log(`${report.results.length} real HTTP checks passed; baseline, retained vectors and active pointer unchanged`);
