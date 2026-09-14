/**
 * 产品演示录屏：驱动真实运行中的应用走完整流程，逐段按旁白时长控制节奏，
 * 并在画面底部注入中文字幕条。输出 webm，后续由 mux.sh 合成带配音的 mp4。
 */
import { chromium } from 'playwright';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = 'http://127.0.0.1:5173';
const VIDEO_DIR = join(HERE, 'raw');
const MODE = process.env.MODE || 'desktop';
const W = MODE === 'mobile' ? 430 : 1280;
const H = MODE === 'mobile' ? 760 : 720;

const segs = JSON.parse(readFileSync(join(HERE, 'durations.json'), 'utf-8'));
const D = Object.fromEntries(segs.map((s) => [s.id, s.dur]));
const CAP = Object.fromEntries(segs.map((s) => [s.id, s.cap]));

mkdirSync(VIDEO_DIR, { recursive: true });

const EMAIL = 'researcher@qq.com';
const PASSWORD = 'demo123456';

const DOC = `Transformer 架构与自注意力机制研究综述

一、自注意力机制的核心作用
自注意力机制（Self-Attention）是 Transformer 架构的核心组件。它能够直接建立序列中
任意两个位置之间的联系，将任意两个 token 之间的路径长度缩短为常数级别。相比循环
神经网络需要逐步传递隐藏状态，自注意力在捕捉长距离依赖方面具有本质优势。

二、并行化带来的训练效率提升
由于自注意力对序列中所有位置的计算相互独立，Transformer 可以在时间维度上完全并行，
显著缩短了大规模语料上的训练时间，这是它取代循环神经网络成为主流架构的关键原因。

三、多头注意力
多头注意力将查询、键、值分别投影到多个不同的表示子空间，让模型能够在不同子空间中
并行关注不同类型的信息，随后拼接并再次线性变换。
`;

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH,
  args: ['--no-sandbox', '--force-device-scale-factor=1', '--hide-scrollbars'],
});
const context = await browser.newContext({
  viewport: { width: W, height: H },
  recordVideo: { dir: VIDEO_DIR, size: { width: W, height: H } },
  deviceScaleFactor: 1,
});
const page = await context.newPage();

// ---------- 字幕条：随导航自动重建 ----------
await context.addInitScript(() => {
  window.__cap = (title, sub) => {
    let bar = document.getElementById('__capbar');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = '__capbar';
      bar.style.cssText = [
        'position:fixed', 'left:0', 'right:0', 'bottom:0', 'z-index:2147483647',
        'padding:14px 28px 16px', 'pointer-events:none',
        'background:#0A0E20', 'box-shadow:0 -18px 26px -10px rgba(10,14,32,.55)',
        'font-family:"Microsoft YaHei","PingFang SC","WenQuanYi Zen Hei",sans-serif',
        'transition:opacity .25s', 'opacity:0',
      ].join(';');
      bar.innerHTML =
        '<div id="__capt" style="color:#E9B44C;font-size:13px;font-weight:700;letter-spacing:2px;margin-bottom:4px"></div>' +
        '<div id="__caps" style="color:#fff;font-size:20px;font-weight:600;line-height:1.4"></div>';
      document.body.appendChild(bar);
    }
    document.getElementById('__capt').textContent = title || '';
    document.getElementById('__caps').textContent = sub || '';
    bar.style.opacity = title || sub ? '1' : '0';
  };
  window.__card = (title, sub) => {
    let ov = document.getElementById('__cardov');
    if (!ov) {
      ov = document.createElement('div');
      ov.id = '__cardov';
      ov.style.cssText = [
        'position:fixed', 'inset:0', 'z-index:2147483646', 'display:flex',
        'flex-direction:column', 'align-items:center', 'justify-content:center',
        'background:#12193F', 'transition:opacity .4s', 'opacity:0',
        'font-family:"Microsoft YaHei","PingFang SC","WenQuanYi Zen Hei",sans-serif',
      ].join(';');
      ov.innerHTML =
        '<div style="font-size:15px;color:#E9B44C;letter-spacing:6px;margin-bottom:22px" id="__cardk"></div>' +
        '<div style="font-size:46px;color:#fff;font-weight:700;letter-spacing:2px" id="__cardt"></div>' +
        '<div style="font-size:19px;color:#CADCFC;margin-top:20px" id="__cards"></div>';
      document.body.appendChild(ov);
    }
    if (title === null) { ov.style.opacity = '0'; setTimeout(() => ov.remove(), 450); return; }
    document.getElementById('__cardk').textContent = 'RAG ACADEMIC KNOWLEDGE ENGINE';
    document.getElementById('__cardt').textContent = title;
    document.getElementById('__cards').textContent = sub || '';
    ov.style.opacity = '1';
  };
});

const timeline = [];
let elapsed = 0;

/** 播放一段：设置字幕，执行动作，然后补足到该段旁白时长 */
async function seg(id, action) {
  const dur = D[id] * 1000;
  const t0 = Date.now();
  const entry = { id, narration: D[id], start: +(elapsed / 1000).toFixed(3), actual: null };
  timeline.push(entry);
  await page.evaluate(([t, s]) => window.__cap(t, s), [CAP[id], '']).catch(() => {});
  if (action) await action();
  // 动作可能超出旁白时长（真实模型生成时间不定），此时如实记录实际耗时，
  // 音轨在后期按实际时长补静音对齐，而不是强行截断画面。
  const remain = dur - (Date.now() - t0);
  if (remain > 0) await page.waitForTimeout(remain);
  const actual = (Date.now() - t0) / 1000;
  entry.actual = +actual.toFixed(3);
  elapsed += actual * 1000;
  console.log(`▶ ${id.padEnd(18)} 旁白 ${D[id].toFixed(1)}s  画面 ${actual.toFixed(1)}s`);
}

const slow = async (loc, text) => {
  await loc.click();
  await loc.fill('');
  await loc.type(text, { delay: 55 });
};

try {
  if (MODE === 'desktop') {
  // ---------- 01 片头 ----------
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForSelector('text=欢迎回来');
  await page.evaluate(() => window.__card('基于 RAG 的学术知识引擎', '上传文献 · 语义提问 · 可溯源回答'));
  await seg('01_intro');
  await page.evaluate(() => window.__card(null));
  await page.waitForTimeout(500);

  // ---------- 02 注册 ----------
  await seg('02_register', async () => {
    await page.click('text=立即注册');
    await page.waitForSelector('text=创建账号');
    await slow(page.locator('#email'), EMAIL);
    await slow(page.locator('#password'), PASSWORD);
    await slow(page.locator('#confirm'), PASSWORD);
    await page.waitForTimeout(600);
    await page.click('button[type=submit]');
    // 账号已存在时停留在注册页并提示，此时直接返回登录页即可
    await Promise.race([
      page.waitForSelector('text=欢迎回来', { timeout: 8000 }).catch(() => {}),
      page.waitForSelector('text=该邮箱已被注册', { timeout: 8000 }).catch(() => {}),
    ]);
    if (!(await page.locator('text=欢迎回来').count())) {
      await page.click('text=返回登录');
      await page.waitForSelector('text=欢迎回来');
    }
  });

  // ---------- 03 登录 ----------
  await seg('03_login', async () => {
    await slow(page.locator('#email'), EMAIL);
    await slow(page.locator('#password'), PASSWORD);
    await page.waitForTimeout(400);
    await page.click('button[type=submit]');
    await page.waitForSelector('text=开始你的学术问答', { timeout: 30000 });
  });

  // ---------- 04 上传 ----------
  await seg('04_upload', async () => {
    await page.click('text=我的知识库');
    await page.waitForSelector('text=选择文件上传');
    await page.waitForTimeout(1200);
    const p = join(tmpdir(), 'Transformer-Self-Attention-Review.md');
    writeFileSync(p, DOC, 'utf-8');
    await page.setInputFiles('input[type=file]', p);
  });

  // ---------- 05 解析状态 ----------
  await seg('05_parsing', async () => {
    await page.waitForSelector('li:has-text("Transformer-Self-Attention-Review") >> text=已就绪', { timeout: 60000 });
  });

  // ---------- 06 提问 ----------
  await seg('06_ask', async () => {
    await page.click('text=智能问答');
    await page.waitForSelector('textarea');
    await page.waitForTimeout(800);
    await slow(page.locator('textarea'), '自注意力机制的作用是什么？');
    await page.waitForTimeout(500);
    await page.click('button:has-text("发送")');
  });

  // ---------- 07 流式 ----------
  await seg('07_stream');

  // ---------- 08 引用卡片 ----------
  await seg('08_citation', async () => {
    await page.waitForSelector('button:has-text("Transformer-Self-Attention-Review")', { timeout: 90000 });
    await page.waitForSelector('button:has-text("发送")', { timeout: 90000 });
  });

  // ---------- 09 引用弹窗 ----------
  await seg('09_modal', async () => {
    await page.click('button:has-text("Transformer-Self-Attention-Review")');
    await page.waitForSelector('text=引用原文');
    // 弹窗需覆盖本段大部分时间，否则旁白在讲原文、画面却已经关掉了
    await page.waitForTimeout(11500);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(600);
  });

  // ---------- 10 多轮追问 ----------
  await seg('10_multiturn', async () => {
    await slow(page.locator('textarea'), '它相比循环神经网络有什么优势？');
    await page.waitForTimeout(400);
    await page.click('button:has-text("发送")');
    await page.waitForSelector('button:has-text("发送")', { timeout: 90000 });
  });

  // ---------- 11 管理后台：用户 ----------
  await seg('11_admin_user', async () => {
    await page.evaluate(() => localStorage.clear());
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    await page.fill('#email', 'admin@outlook.com');
    await page.fill('#password', 'admin123456');
    await page.click('button[type=submit]');
    await page.waitForSelector('text=用户管理', { timeout: 30000 });
    await page.click('text=用户管理');
    await page.waitForSelector('table');
  });

  // ---------- 12 系统配置 ----------
  await seg('12_admin_config', async () => {
    await page.click('text=系统配置');
    await page.waitForSelector('text=大模型（OpenAI 兼容接口）');
    await page.waitForTimeout(3000);
    await page.mouse.wheel(0, 380);
    await page.waitForTimeout(3000);
    await page.mouse.wheel(0, 380);
  });

  // ---------- 13 运行监控 ----------
  await seg('13_admin_stats', async () => {
    await page.mouse.wheel(0, -900);
    await page.click('text=运行监控');
    await page.waitForSelector('text=大模型调用次数');
  });

  // ---------- 15 片尾 ----------
  await page.waitForTimeout(600);
  await page.evaluate(() => { window.__cap('', ''); window.__card('把时间还给真正需要人做的事', '77 个自动化测试通过 · 已接入真实大模型完成端到端验证'); });
  await seg('15_outro');

  } else {
  // ================= 移动端单独录制（430×760）=================
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASSWORD);
  await page.click('button[type=submit]');
  // 用移动端专有元素判断进入：'学术知识引擎' 在桌面侧边栏里也存在但不可见，
  // 直接等它会一直阻塞
  await page.waitForSelector('[aria-label="打开菜单"]', { timeout: 30000 });
  await page.waitForTimeout(800);

  // 可选交互一律给短超时：默认 30s 超时被 catch 吞掉会把本段拖长数十秒
  const tap = (sel) => page.click(sel, { timeout: 2500 }).catch(() => {});
  await seg('14_mobile', async () => {
    await page.waitForTimeout(2000);
    await tap('[aria-label="打开会话列表"]');      // 会话抽屉
    await page.waitForTimeout(2600);
    await page.locator('aside, .fixed').locator('button').filter({ hasText: '注意力' })
      .first().click({ timeout: 2500 }).catch(() => {});
    await page.waitForTimeout(3200);
    await tap('[aria-label="打开菜单"]');          // 主导航抽屉
    await page.waitForTimeout(2200);
  });
  }

  console.log(`\n总时长约 ${(elapsed / 1000).toFixed(1)} 秒`);
} catch (e) {
  console.error('✖ 录制中断：', e.message);
  await page.screenshot({ path: join(HERE, 'fail.png') }).catch(() => {});
  const body = await page.evaluate(() => document.body.innerText.slice(0, 400)).catch(() => '');
  console.error('--- 当前页面文本 ---\n' + body);
  process.exitCode = 1;
} finally {
  await page.waitForTimeout(500);
  await context.close();   // 必须关闭 context，视频才会写盘
  await browser.close();
  writeFileSync(join(HERE, `timeline_${MODE}.json`), JSON.stringify(timeline, null, 1), 'utf-8');
}
