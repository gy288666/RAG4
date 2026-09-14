/**
 * 视觉走查截图脚本：拦截 /api/v1 接口并返回真实感样例数据，
 * 无需启动后端即可渲染登录后的全部页面，用于设计走查。
 *
 * 运行：cd frontend && npm run build && npm run preview -- --port 4173 &
 *       E2E_BASE_URL=http://127.0.0.1:4173 node e2e/design-shots.mjs
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const SHOTS = process.env.E2E_SHOTS_DIR || join(HERE, 'shots');
mkdirSync(SHOTS, { recursive: true });

const ok = (data) => ({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, message: 'ok', data }) });

const sessions = {
  total: 3, page: 1, page_size: 50,
  items: [
    { session_id: 's1', title: 'Transformer 注意力机制的演变', last_message_preview: '自注意力与因果注意力的区别主要体现在…', created_at: '2026-08-20T10:00:00', updated_at: '2026-08-28T09:12:00' },
    { session_id: 's2', title: 'RAG 检索增强生成综述笔记', last_message_preview: '该综述将 RAG 分为 Naive、Advance…', created_at: '2026-08-22T14:00:00', updated_at: '2026-08-27T18:40:00' },
    { session_id: 's3', title: '实验设置对比', last_message_preview: '三篇文献的学习率与批量大小差异…', created_at: '2026-08-25T09:00:00', updated_at: '2026-08-26T11:05:00' },
  ],
};

const messages = [
  {
    message_id: 'm1', role: 'user', citations: null, created_at: '2026-08-28T09:10:00',
    content: '自注意力机制和传统的循环网络相比，主要优势是什么？请结合文献说明。',
  },
  {
    message_id: 'm2', role: 'assistant', created_at: '2026-08-28T09:11:00',
    content:
      '与循环网络相比，自注意力的核心优势有两点：\n\n一是并行度。循环网络必须按时间步串行计算，而自注意力对序列中所有位置一次性建模，训练效率显著更高 [1]。\n\n二是长程依赖的建模路径更短。任意两个位置之间直接建立连接，路径长度为 O(1)，缓解了梯度随距离衰减的问题 [1][2]。\n\n原文在实验部分也验证了这一点：在机器翻译任务上，Transformer 用更少的训练时间超过了当时的循环网络基线 [2]。',
    warnings: [],
    citations: [
      { index: 1, doc_id: 'd1', doc_name: 'Attention Is All You Need.pdf', page: 3, chunk_index: 12, snippet: '…self-attention layer connects all positions with a constant number of sequentially executed operations, whereas a recurrent layer requires O(n) sequential operations.' },
      { index: 2, doc_id: 'd2', doc_name: '基于检索增强生成的研究综述.docx', page: 7, chunk_index: 31, snippet: '…在 WMT 2014 英德翻译任务上，Transformer 在 8 张 GPU 上训练 3.5 天即取得 28.4 BLEU，大幅优于此前所有基线模型。' },
    ],
  },
];

const documents = {
  total: 5, page: 1, page_size: 10,
  items: [
    { id: 'd1', file_name: 'Attention Is All You Need.pdf', file_size: 2_214_592, status: 'ready', status_label: '已就绪', created_at: '2026-08-20T10:00:00', updated_at: '2026-08-20T10:03:00' },
    { id: 'd2', file_name: '基于检索增强生成的研究综述.docx', file_size: 1_048_576, status: 'ready', status_label: '已就绪', created_at: '2026-08-21T10:00:00', updated_at: '2026-08-21T10:02:00' },
    { id: 'd3', file_name: '大规模语言模型 Survey.pdf', file_size: 8_388_608, status: 'parsing', status_label: '解析中', created_at: '2026-08-28T09:30:00', updated_at: '2026-08-28T09:31:00' },
    { id: 'd4', file_name: '实验记录-八月.md', file_size: 48_128, status: 'failed', status_label: '失败', created_at: '2026-08-27T16:00:00', updated_at: '2026-08-27T16:01:00' },
    { id: 'd5', file_name: '参考文献清单.txt', file_size: 12_800, status: 'vectorizing', status_label: '向量化中', created_at: '2026-08-28T08:00:00', updated_at: '2026-08-28T08:05:00' },
  ],
};

const stats = {
  period_days: 7, total_calls: 1284, total_llm_calls: 962, total_tokens_used: 1_842_300,
  total_rerank_calls: 910, total_ocr_calls: 47, total_vector_searches: 1123,
  failure_count: 12, failure_rate: '0.93%',
  daily_trend: [
    { date: '2026-08-22', count: 120 }, { date: '2026-08-23', count: 98 },
    { date: '2026-08-24', count: 210 }, { date: '2026-08-25', count: 186 },
    { date: '2026-08-26', count: 245 }, { date: '2026-08-27', count: 203 },
    { date: '2026-08-28', count: 222 },
  ],
  ocr_failed_queue: [
    { doc_id: 'doc_9f2a', file_name: '扫描版学位论文.pdf', error: 'OCR 引擎未能识别第 12 页文本，已加入重试队列', created_at: '2026-08-27 16:20:11' },
  ],
};

const users = {
  total: 2, page: 1, page_size: 20,
  items: [
    { user_id: 1, email: 'chen.lab@outlook.com', role: 'admin', status: 1, doc_count: 12, last_login_at: '2026-08-28 09:00', created_at: '2026-07-01 10:00' },
    { user_id: 2, email: 'student_2024@qq.com', role: 'user', status: 1, doc_count: 5, last_login_at: '2026-08-27 21:34', created_at: '2026-07-15 18:22' },
  ],
};

const CHROMIUM_PATH =
  process.env.CHROMIUM_PATH ||
  join(process.env.LOCALAPPDATA || '', 'ms-playwright', 'chromium-1223', 'chrome-win64', 'chrome.exe');

await using browser = await chromium.launch({ executablePath: CHROMIUM_PATH });

// 未登录上下文：截认证页
const pub = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await pub.route('**/api/v1/**', (route) => route.fulfill(ok(null)));
for (const [name, path] of [['login', '/login'], ['register', '/register']]) {
  await pub.goto(`${BASE}${path}`, { waitUntil: 'networkidle' });
  await pub.waitForTimeout(300);
  await pub.screenshot({ path: join(SHOTS, `${name}.png`) });
  console.log('shot:', name);
}
await pub.context().close();

// 登录态上下文（管理员）：截业务页面
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.addInitScript(() => {
  localStorage.setItem('rag_access_token', 'mock-token');
  localStorage.setItem('rag_user_info', JSON.stringify({ id: 1, email: 'chen.lab@outlook.com', role: 'admin' }));
});

await page.route('**/api/v1/**', async (route) => {
  const url = new URL(route.request().url());
  const path = url.pathname.replace('/api/v1', '');
  if (path === '/chat/sessions') return route.fulfill(ok(sessions));
  if (path === '/chat/session/s1/messages') return route.fulfill(ok(messages));
  if (path === '/docs/list') return route.fulfill(ok(documents));
  if (path === '/admin/stats') return route.fulfill(ok(stats));
  if (path === '/admin/users') return route.fulfill(ok(users));
  if (path === '/admin/reset-requests') return route.fulfill(ok([]));
  if (path === '/auth/me') return route.fulfill(ok({ last_login_at: '2026-08-28 09:00:00', created_at: '2026-07-01 10:00:00' }));
  return route.fulfill(ok(null));
});

const shots = [
  ['chat-empty', '/chat'],
  ['chat-messages', '/chat/s1'],
  ['knowledge', '/knowledge'],
  ['profile', '/profile'],
  ['admin-stats', '/admin/stats'],
  ['admin-users', '/admin/users'],
];

for (const [name, path] of shots) {
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(SHOTS, `${name}.png`) });
  console.log('shot:', name);
}

await browser.close();
console.log('done ->', SHOTS);
