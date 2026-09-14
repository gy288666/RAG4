/**
 * 端到端冒烟测试：用真实浏览器走一遍完整用户旅程，并在关键节点截图。
 *
 * 覆盖：注册 → 登录 → 上传文档 → 等待解析就绪 → SSE 流式问答 →
 *       点击引用查看原文 → 管理后台三个页面 → 移动端响应式
 *
 * 前置条件（两个服务都要先起好）：
 *   后端  cd backend && DEV_MOCK_AI=true uvicorn app.main:app --port 8000
 *   前端  cd frontend && npm run dev
 *
 * 运行：cd frontend && npm run e2e
 *
 * 环境变量：
 *   E2E_BASE_URL     前端地址，默认 http://127.0.0.1:5173
 *   E2E_SHOTS_DIR    截图输出目录，默认 frontend/e2e/shots
 *   CHROMIUM_PATH    自定义 Chromium 可执行文件路径（容器环境可能需要）
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173';
const SHOTS = process.env.E2E_SHOTS_DIR || join(HERE, 'shots');
const EMAIL = `demo${Date.now() % 100000}@qq.com`;
// 接真实模型时解析与生成都更慢，可用 E2E_TIMEOUT 放宽等待
const WAIT = Number(process.env.E2E_TIMEOUT || 30000);
const PASSWORD = 'demo123456';

mkdirSync(SHOTS, { recursive: true });

const log = (...args) => console.log('▶', ...args);

// 用于上传的示例文献
const DOC = `Transformer 架构与自注意力机制研究综述

一、自注意力机制的核心作用
自注意力机制（Self-Attention）是 Transformer 架构的核心组件。它能够直接建立序列中任意
两个位置之间的联系，将任意两个 token 之间的路径长度缩短为常数级别。相比循环神经网络需要
逐步传递隐藏状态，自注意力在捕捉长距离依赖方面具有本质优势。

二、多头注意力
多头注意力（Multi-Head Attention）将查询、键、值分别投影到多个不同的表示子空间，
让模型能够在不同子空间中并行关注不同类型的信息，随后拼接并再次线性变换。

三、并行化带来的训练效率提升
由于自注意力对序列中所有位置的计算相互独立，Transformer 可以在时间维度上完全并行，
显著缩短了大规模语料上的训练时间，这是其取代循环网络成为主流架构的关键原因之一。
`;

const browser = await chromium.launch({
  // 未指定时交给 Playwright 自行解析已下载的浏览器
  ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
  args: ['--no-sandbox'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

const errors = [];
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
page.on('pageerror', (e) => errors.push(String(e)));

const shot = async (name) => {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
  log(`截图 ${name}.png`);
};

try {
  // ---------- 1. 登录页 ----------
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForSelector('text=欢迎回来');
  await shot('01-login');

  // ---------- 2. 注册 ----------
  await page.click('text=立即注册');
  await page.waitForSelector('text=创建账号');
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASSWORD);
  await page.fill('#confirm', PASSWORD);
  await shot('02-register');
  await page.click('button[type=submit]');

  // ---------- 3. 登录 ----------
  await page.waitForSelector('text=欢迎回来');
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForSelector('text=开始你的学术问答', { timeout: WAIT });
  log('登录成功，进入问答页');
  await shot('03-chat-empty');

  // ---------- 4. 上传文档 ----------
  await page.click('text=我的知识库');
  await page.waitForSelector('text=选择文件上传');
  const docPath = join(tmpdir(), 'transformer-review.txt');
  writeFileSync(docPath, DOC, 'utf-8');
  await page.setInputFiles('input[type=file]', docPath);

  // 必须等列表行里的状态徽章，而不是筛选栏上同名的「已就绪」按钮
  await page.waitForSelector('li:has-text("transformer-review.txt") >> text=已就绪', { timeout: WAIT });
  await page.waitForTimeout(300);
  log('文档解析与向量化完成，状态：已就绪');
  await shot('04-knowledge');

  // ---------- 5. 流式问答 ----------
  await page.click('text=智能问答');
  await page.waitForSelector('textarea');
  await page.fill('textarea', '自注意力机制的作用是什么？');
  await page.click('button:has-text("发送")');

  // 等引用卡片本身（按文件名匹配），而不是模型正文里同名的「参考来源」字样，
  // 否则会在流式输出中途就误判为完成
  await page.waitForSelector('button:has-text("transformer-review.txt")', { timeout: WAIT });
  await page.waitForSelector('button:has-text("发送")', { timeout: WAIT }); // 「停止」变回「发送」= 流结束
  log('SSE 流式回答完成，引用卡片已渲染');
  await page.waitForTimeout(600);
  await shot('05-chat-answer');

  // ---------- 6. 点击引用查看原文 ----------
  await page.click('button:has-text("transformer-review.txt")');
  await page.waitForSelector('text=引用原文');
  await shot('06-citation-modal');
  await page.keyboard.press('Escape');

  // ---------- 7. 管理后台（用初始管理员账号） ----------
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.fill('#email', 'admin@outlook.com');
  await page.fill('#password', 'admin123456');
  await page.click('button[type=submit]');
  await page.waitForSelector('text=用户管理', { timeout: WAIT });

  await page.click('text=用户管理');
  await page.waitForSelector('table');
  await shot('07-admin-users');

  await page.click('text=系统配置');
  await page.waitForSelector('text=大模型（OpenAI 兼容接口）');
  await shot('08-admin-configs');

  await page.click('text=运行监控');
  await page.waitForSelector('text=大模型调用次数');
  await page.waitForTimeout(400);
  await shot('09-admin-stats');

  // ---------- 8. 移动端响应式 ----------
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await shot('10-mobile-chat');

  log(`\n全部流程走通。控制台错误数：${errors.length}`);
  if (errors.length) errors.slice(0, 5).forEach((e) => log('  ERR', e));
} catch (error) {
  console.error('✖ 失败：', error.message);
  await page.screenshot({ path: `${SHOTS}/failure.png` });
  process.exitCode = 1;
} finally {
  await browser.close();
}
