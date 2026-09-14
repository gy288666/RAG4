/**
 * 《基于 RAG 的学术知识引擎》产品演示 PPT 生成器
 * 44 页，与 docs/presentation_script.md 的 P-1 ~ P-44 逐页对应。
 */
const pptxgen = require('pptxgenjs');

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.33 x 7.5
pres.author = 'RAG 学术知识引擎项目组';
pres.company = 'RAG Academic Knowledge Engine';
pres.title = '基于 RAG 的学术知识引擎 — 产品演示';

// ============ 设计系统 ============
const C = {
  ink: '12193F', // 深夜蓝（暗色页背景）
  navy: '1E2761', // 主色
  navySoft: '3A4versa', // placeholder replaced below
  ice: 'CADCFC', // 浅蓝
  gold: 'E9B44C', // 强调色
  white: 'FFFFFF',
  mist: 'F4F7FC', // 浅卡片底
  line: 'E2E8F4',
  gray: '5C6480',
  grayLight: '8A92A8',
  red: 'B3392B',
  green: '2E7D5B',
};
C.navySoft = '2C3A73';

const F = { cn: 'Microsoft YaHei', num: 'Arial' };
const M = { x: 0.7, w: 11.93 }; // 内容区左边距与宽度

const P = { count: 0 };

function sh(opts) {
  // pptxgenjs 会就地改写 options 对象，每次必须新建
  return Object.assign({ type: 'outer', color: '1E2761', blur: 12, offset: 2, angle: 90, opacity: 0.1 }, opts || {});
}

function pageNo(s, dark) {
  P.count += 1;
  s.addText(String(P.count).padStart(2, '0'), {
    x: 12.35, y: 6.92, w: 0.6, h: 0.3, align: 'right',
    fontSize: 10, fontFace: F.num, color: dark ? '5A6494' : C.grayLight,
  });
}

/** 暗色页：封面、章节转场、结论 */
function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: C.ink };
  // 视觉母题：右下角同心圆
  s.addShape(pres.ShapeType.ellipse, {
    x: 10.2, y: 4.5, w: 4.2, h: 4.2, fill: { color: C.navy, transparency: 55 },
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: 11.1, y: 5.4, w: 2.4, h: 2.4, fill: { color: C.navySoft, transparency: 45 },
  });
  return s;
}

/** 亮色内容页 */
function lightSlide(kicker, title) {
  const s = pres.addSlide();
  s.background = { color: C.white };
  if (kicker) {
    s.addText(kicker, {
      x: M.x, y: 0.42, w: 8, h: 0.3, margin: 0,
      fontSize: 12, bold: true, color: C.gold, fontFace: F.cn, charSpacing: 2,
    });
  }
  if (title) {
    s.addText(title, {
      x: M.x, y: 0.75, w: 11.2, h: 0.7, margin: 0,
      fontSize: 32, bold: true, color: C.navy, fontFace: F.cn,
    });
  }
  return s;
}

/** 卡片 */
function card(s, x, y, w, h, opts = {}) {
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.08,
    fill: { color: opts.fill || C.mist },
    line: { color: opts.line || C.line, width: 1 },
    shadow: opts.shadow === false ? undefined : sh(),
  });
}

/** 圆形编号徽章（贯穿全篇的视觉母题） */
function badge(s, x, y, text, opts = {}) {
  const d = opts.d || 0.5;
  s.addShape(pres.ShapeType.ellipse, {
    x, y, w: d, h: d, fill: { color: opts.fill || C.navy },
  });
  s.addText(String(text), {
    x, y, w: d, h: d, align: 'center', valign: 'middle', margin: 0,
    fontSize: opts.size || 15, bold: true,
    color: opts.color || C.white, fontFace: opts.face || F.num,
  });
}

function txt(s, text, o) {
  s.addText(text, Object.assign({ fontFace: F.cn, margin: 0, valign: 'top' }, o));
}

/** 项目符号列表 */
function bullets(s, items, o) {
  const runs = items.map((t, i) => ({
    text: t, options: { bullet: true, breakLine: i !== items.length - 1 },
  }));
  s.addText(runs, Object.assign({
    fontFace: F.cn, fontSize: 13, color: C.gray, lineSpacing: 22, paraSpaceAfter: 6, margin: 0,
  }, o));
}

// =====================================================================
// P-1 封面
// =====================================================================
{
  const s = darkSlide();
  txt(s, '学术研究智能化解决方案', {
    x: M.x, y: 1.65, w: 9, h: 0.35, fontSize: 14, color: C.gold, bold: true, charSpacing: 3,
  });
  txt(s, '基于 RAG 的\n学术知识引擎', {
    x: M.x, y: 2.15, w: 9.5, h: 2.0, fontSize: 52, bold: true, color: C.white, lineSpacing: 62,
  });
  txt(s, '上传你的文献，用中文提问，获得可溯源的精准回答', {
    x: M.x, y: 4.35, w: 9.5, h: 0.4, fontSize: 18, color: C.ice,
  });

  const chips = ['检索增强生成', '私有知识库隔离', '引用可溯源'];
  chips.forEach((t, i) => {
    const x = M.x + i * 2.75;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 5.2, w: 2.5, h: 0.5, rectRadius: 0.25,
      fill: { color: C.navy }, line: { color: C.navySoft, width: 1 },
    });
    txt(s, t, { x, y: 5.2, w: 2.5, h: 0.5, align: 'center', valign: 'middle', fontSize: 12, color: C.ice });
  });

  txt(s, '产品演示与技术汇报　|　2026.07', {
    x: M.x, y: 6.5, w: 6, h: 0.3, fontSize: 12, color: '6B75A5',
  });
  pageNo(s, true);
  s.addNotes('开场：先讲研究生花两周做文献筛选的场景，再引出产品。不要一上来就介绍功能。');
}

// =====================================================================
// P-2 三个数字
// =====================================================================
{
  const s = darkSlide();
  txt(s, '项目完成度', { x: M.x, y: 0.55, w: 8, h: 0.3, fontSize: 13, bold: true, color: C.gold, charSpacing: 2 });
  txt(s, '先看三个数字', { x: M.x, y: 0.92, w: 9, h: 0.7, fontSize: 34, bold: true, color: C.white });

  const stats = [
    { n: '20', t: '个 API 接口', d: '覆盖认证、知识库、问答、\n管理后台四大模块，与接口\n文档逐条对齐', c: C.ice },
    { n: '77', t: '个自动化测试', d: '全部通过，且不依赖 MySQL\n与任何 API Key，克隆即可\n运行', c: C.ice },
    { n: '7', t: '个真实缺陷', d: '在"测试全绿"之后，由浏览器\n实测与真实模型联调发现\n并修复', c: C.gold },
  ];
  stats.forEach((st, i) => {
    const x = M.x + i * 3.85;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.05, w: 3.55, h: 3.3, rectRadius: 0.1,
      fill: { color: C.navy }, line: { color: C.navySoft, width: 1 },
    });
    txt(s, st.n, { x: x + 0.35, y: 2.3, w: 2.9, h: 1.25, fontSize: 66, bold: true, color: st.c, fontFace: F.num });
    txt(s, st.t, { x: x + 0.35, y: 3.6, w: 2.9, h: 0.35, fontSize: 16, bold: true, color: C.white });
    txt(s, st.d, { x: x + 0.35, y: 4.05, w: 2.9, h: 1.1, fontSize: 12, color: '9AA5CE', lineSpacing: 18 });
  });

  txt(s, '「测试全绿」和「真的能用」之间，隔着的正是这 7 个缺陷。', {
    x: M.x, y: 5.75, w: 11, h: 0.4, fontSize: 16, italic: true, color: C.gold,
  });
  pageNo(s, true);
  s.addNotes('强调第三个数字。它比前两个更能说明项目成色。');
}

// =====================================================================
// P-3 议程
// =====================================================================
{
  const s = lightSlide('AGENDA', '今天的议程');
  const items = [
    ['01', '问题与机会', '传统检索与纯大模型的局限，\nRAG 为什么是答案'],
    ['02', '产品全景', '用户端与管理端，\n完整走一遍功能'],
    ['03', '技术架构', '四层架构与 RAG 引擎的\n六个环节'],
    ['04', '安全与隔离', '多用户系统的三层数据隔离\n与密钥保护'],
    ['05', '工程质量', '77 个测试用例，\n以及 7 个真实缺陷'],
    ['06', '演示与展望', '现场演示脚本、\n项目价值与后续规划'],
  ];
  items.forEach((it, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = M.x + col * 4.0, y = 1.75 + row * 2.3;
    card(s, x, y, 3.75, 2.0);
    badge(s, x + 0.28, y + 0.28, it[0], { d: 0.52, size: 14 });
    txt(s, it[1], { x: x + 0.95, y: 0.05 + y + 0.3, w: 2.6, h: 0.4, fontSize: 17, bold: true, color: C.navy });
    txt(s, it[2], { x: x + 0.28, y: y + 1.05, w: 3.2, h: 0.8, fontSize: 12, color: C.gray, lineSpacing: 18 });
  });
  pageNo(s);
}

// =====================================================================
// P-4 信息过载
// =====================================================================
{
  const s = lightSlide('问题与机会 · 01', '不是找不到，是找到的太多');
  card(s, M.x, 1.75, 7.0, 4.3);
  txt(s, '关键词检索为什么失效', { x: M.x + 0.4, y: 2.05, w: 6.2, h: 0.4, fontSize: 18, bold: true, color: C.navy });

  const pts = [
    ['匹配的是字符，不是语义', '搜「幻觉缓解方法」，一篇通篇讲「提升事实一致性」的论文\n一个关键词都对不上，检索不到；而相关工作里随口提一句\n「幻觉」的论文却排在前面。'],
    ['不理解上下文', '「Transformer」在电力工程里是变压器，在深度学习里是\n神经网络架构。检索系统不知道你是谁，也不知道你在做什么。'],
  ];
  pts.forEach((p, i) => {
    const y = 2.6 + i * 1.6;
    badge(s, M.x + 0.4, y, String(i + 1), { d: 0.42, size: 13, fill: C.gold, color: C.navy });
    txt(s, p[0], { x: M.x + 1.0, y: y + 0.02, w: 5.6, h: 0.35, fontSize: 15, bold: true, color: C.navy });
    txt(s, p[1], { x: M.x + 1.0, y: y + 0.45, w: 5.7, h: 1.0, fontSize: 12, color: C.gray, lineSpacing: 18 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 8.1, y: 1.75, w: 4.53, h: 4.3, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '研究者的时间去哪了', { x: 8.45, y: 2.1, w: 3.9, h: 0.35, fontSize: 15, bold: true, color: C.ice });
  txt(s, '2 周', { x: 8.45, y: 2.62, w: 3.9, h: 1.3, fontSize: 64, bold: true, color: C.gold, fontFace: F.num });
  txt(s, '一个新课题的文献筛选期', { x: 8.45, y: 3.95, w: 3.9, h: 0.35, fontSize: 14, color: C.white });
  txt(s, '大量时间不是花在思考和创新上，\n而是花在筛选与验证上——\n这是一种纯粹的损耗。', {
    x: 8.45, y: 4.5, w: 3.9, h: 1.25, fontSize: 13, color: '9AA5CE', lineSpacing: 20,
  });
  pageNo(s);
}

// =====================================================================
// P-5 大模型三堵墙
// =====================================================================
{
  const s = lightSlide('问题与机会 · 02', '大模型来了，但它有三堵墙');
  const walls = [
    ['知识滞后性', '训练数据有截止日期。上个月刚发表的方法，模型一无所知——而学术研究恰恰最关心最新进展。'],
    ['幻觉', '用极其自信、极其流畅的语气，告诉你一个根本不存在的结论，甚至编造论文和作者。在学术场景中这是灾难。'],
    ['领域与私域局限', '实验室内部报告、导师未发表的手稿、公司内部资料——模型从来没见过，也不可能见过。'],
  ];
  walls.forEach((w, i) => {
    const x = M.x + i * 4.0;
    card(s, x, 1.8, 3.75, 3.0, { fill: i === 1 ? 'FDF6E8' : C.mist, line: i === 1 ? C.gold : C.line });
    badge(s, x + 0.32, 2.1, String(i + 1), { d: 0.55, size: 16, fill: i === 1 ? C.gold : C.navy, color: i === 1 ? C.navy : C.white });
    txt(s, w[0], { x: x + 0.32, y: 2.85, w: 3.1, h: 0.4, fontSize: 18, bold: true, color: C.navy });
    txt(s, w[1], { x: x + 0.32, y: 3.35, w: 3.1, h: 1.3, fontSize: 12.5, color: C.gray, lineSpacing: 19 });
  });

  card(s, M.x, 5.1, 11.93, 1.15, { fill: 'FBF2F0', line: 'F0DAD5' });
  txt(s, '亲历案例', { x: M.x + 0.35, y: 5.32, w: 1.4, h: 0.3, fontSize: 13, bold: true, color: C.red });
  txt(s, '问某通用大模型「某论文第 3 章的实验设置」，它给出了数据集、超参数、baseline 对比，细节详实、逻辑合理。\n核对原文——那一章根本不讲实验，全是编的。', {
    x: M.x + 1.85, y: 5.3, w: 9.7, h: 0.8, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-6 RAG：闭卷 vs 开卷
// =====================================================================
{
  const s = lightSlide('问题与机会 · 03', 'RAG：把「记忆」换成「查阅」');
  const cols = [
    { t: '纯大模型 = 闭卷考试', d: '凭记忆答题，记不清就编。\n答案无法验证，出处无从查起。', fill: C.mist, line: C.line, tc: C.gray, badge: '闭卷' },
    { t: 'RAG = 开卷考试', d: '先翻书找到相关章节，再基于原文作答。\n每一句话都能指出出处。', fill: C.navy, line: C.navy, tc: C.ice, badge: '开卷' },
  ];
  cols.forEach((c, i) => {
    const x = M.x + i * 6.15;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 1.75, w: 5.78, h: 1.85, rectRadius: 0.1,
      fill: { color: c.fill }, line: { color: c.line, width: 1 }, shadow: sh(),
    });
    txt(s, c.t, { x: x + 0.35, y: 2.05, w: 5.1, h: 0.4, fontSize: 19, bold: true, color: i === 1 ? C.white : C.navy });
    txt(s, c.d, { x: x + 0.35, y: 2.6, w: 5.1, h: 0.85, fontSize: 13, color: c.tc, lineSpacing: 20 });
  });

  txt(s, 'RAG 在模型生成之前插入了一个检索环节', {
    x: M.x, y: 3.95, w: 8, h: 0.35, fontSize: 15, bold: true, color: C.navy,
  });
  const steps = ['问题向量化', '在私有库中\n语义检索', '拼接为\n背景资料', '模型基于资料\n作答并标注引用'];
  steps.forEach((t, i) => {
    const x = M.x + i * 3.05;
    card(s, x, 4.45, 2.6, 1.15, { fill: C.white, line: C.line });
    badge(s, x + 0.25, 4.62, String(i + 1), { d: 0.38, size: 12, fill: C.gold, color: C.navy });
    txt(s, t, { x: x + 0.72, y: 4.6, w: 1.75, h: 0.8, fontSize: 12, color: C.navy, lineSpacing: 16 });
    if (i < 3) {
      txt(s, '›', { x: x + 2.62, y: 4.75, w: 0.4, h: 0.5, align: 'center', fontSize: 26, color: C.grayLight, fontFace: F.num });
    }
  });
  txt(s, '三堵墙同时被绕开，并且额外获得了纯大模型永远做不到的能力——可溯源。', {
    x: M.x, y: 5.85, w: 11.5, h: 0.4, fontSize: 14, italic: true, color: C.gold,
  });
  pageNo(s);
}

// =====================================================================
// P-7 产品定位
// =====================================================================
{
  const s = darkSlide();
  txt(s, '产品定位', { x: M.x, y: 0.9, w: 8, h: 0.3, fontSize: 13, bold: true, color: C.gold, charSpacing: 2 });
  txt(s, '一个面向学术研究者的、\n私有知识库驱动的、可溯源的\n智能问答系统', {
    x: M.x, y: 1.4, w: 11, h: 1.9, fontSize: 32, bold: true, color: C.white, lineSpacing: 46,
  });
  const kw = [
    ['私有知识库', '每个用户的资料在物理层面隔离，\n不共享、不混淆、不泄露'],
    ['可溯源', '每一条回答都必须能点开看到原文。\n做不到溯源的回答，宁可不给'],
    ['面向学术', '宁可回答「根据现有资料无法回答」，\n也绝不编造'],
  ];
  kw.forEach((k, i) => {
    const x = M.x + i * 3.85;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 3.85, w: 3.55, h: 2.0, rectRadius: 0.1,
      fill: { color: C.navy }, line: { color: C.navySoft, width: 1 },
    });
    txt(s, k[0], { x: x + 0.32, y: 4.15, w: 2.95, h: 0.4, fontSize: 19, bold: true, color: C.gold });
    txt(s, k[1], { x: x + 0.32, y: 4.7, w: 2.95, h: 0.95, fontSize: 12.5, color: C.ice, lineSpacing: 19 });
  });
  txt(s, '三个关键词，每一个都对应一条产品红线。', {
    x: M.x, y: 6.15, w: 8, h: 0.35, fontSize: 13, color: '8A93C4',
  });
  pageNo(s, true);
}

// =====================================================================
// P-8 用户旅程
// =====================================================================
{
  const s = lightSlide('产品全景 · 用户端', '一个新用户的完整路径');
  const js = [
    ['注册登录', '邮箱 + 密码\n无需验证码'],
    ['上传文献', 'PDF / DOCX\nTXT / Markdown'],
    ['解析入库', '解析 → 切分\n→ 向量化'],
    ['提问', '改写 → 检索\n→ 精排 → 生成'],
    ['溯源验证', '点击引用\n查看原文'],
  ];
  js.forEach((j, i) => {
    const x = M.x + i * 2.42;
    const active = i === 4;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.1, w: 2.15, h: 2.5, rectRadius: 0.1,
      fill: { color: active ? C.navy : C.mist }, line: { color: active ? C.navy : C.line, width: 1 }, shadow: sh(),
    });
    badge(s, x + 0.8, 2.35, String(i + 1), { d: 0.55, size: 16, fill: active ? C.gold : C.navy, color: active ? C.navy : C.white });
    txt(s, j[0], { x: x + 0.15, y: 3.1, w: 1.85, h: 0.35, align: 'center', fontSize: 15, bold: true, color: active ? C.white : C.navy });
    txt(s, j[1], { x: x + 0.15, y: 3.55, w: 1.85, h: 0.8, align: 'center', fontSize: 11.5, color: active ? C.ice : C.gray, lineSpacing: 17 });
    if (i < 4) {
      txt(s, '›', { x: x + 2.13, y: 3.1, w: 0.3, h: 0.5, align: 'center', fontSize: 24, color: C.grayLight, fontFace: F.num });
    }
  });
  card(s, M.x, 5.05, 11.93, 1.1, { fill: 'F0F7F4', line: 'D6E8E0' });
  txt(s, '设计原则', { x: M.x + 0.35, y: 5.28, w: 1.3, h: 0.3, fontSize: 13, bold: true, color: C.green });
  txt(s, '看起来只有五步，但每一步背后都有必须认真处理的工程问题：异步解析的状态可观测、多格式解析的降级、切片参数的动态化、越权访问的防御。', {
    x: M.x + 1.75, y: 5.28, w: 9.8, h: 0.6, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-9 注册与登录
// =====================================================================
{
  const s = lightSlide('产品全景 · 用户端', '第一步：注册与登录');
  card(s, M.x, 1.75, 5.78, 4.3);
  txt(s, '产品决策：不要验证码', { x: M.x + 0.38, y: 2.05, w: 5.0, h: 0.4, fontSize: 17, bold: true, color: C.navy });
  txt(s, '目标用户是研究者，注册流程每多一步，流失就多一分。但「不要验证码」不等于「不做校验」。', {
    x: M.x + 0.38, y: 2.5, w: 5.0, h: 0.7, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  bullets(s, [
    '邮箱后缀白名单：outlook / qq / gmail / 163 / 教育网等',
    '密码不少于 6 位，bcrypt 慢哈希 + 随机盐存储',
    '前后端各校验一次——前端为体验，后端为安全边界',
    '登录成功返回 JWT，有效期 7 天',
  ], { x: M.x + 0.42, y: 3.35, w: 5.0, h: 2.3, fontSize: 12.5 });

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.15, y: 1.75, w: 5.48, h: 4.3, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '一个被想过的权衡', { x: 7.5, y: 2.05, w: 4.8, h: 0.4, fontSize: 17, bold: true, color: C.gold });
  txt(s, '登录失败时，我们明确区分\n「邮箱未注册」与「密码错误」。', {
    x: 7.5, y: 2.55, w: 4.8, h: 0.7, fontSize: 14, color: C.white, lineSpacing: 22,
  });
  txt(s, '这确实会带来邮箱枚举的风险。但对于一个内部使用的学术工具，明确的错误提示能大幅减少用户困惑与支持成本——需求文档也明确要求了这一点。\n\n如果要对公网开放，应改为统一提示「邮箱或密码错误」，并加登录失败次数限制。改动只有两行。', {
    x: 7.5, y: 3.4, w: 4.8, h: 2.3, fontSize: 12, color: '9AA5CE', lineSpacing: 19,
  });
  pageNo(s);
  s.addNotes('强调：这类权衡在系统里还有很多，它们是被想过的，不是被忽略的。');
}

// =====================================================================
// P-10 上传文献
// =====================================================================
{
  const s = lightSlide('产品全景 · 用户端', '第二步：上传文献');
  const limits = [['50 MB', '单文件上限'], ['10 个', '单次批量上限'], ['4 种', '支持的格式']];
  limits.forEach((l, i) => {
    const x = M.x + i * 2.5;
    card(s, x, 1.8, 2.3, 1.2, { fill: C.mist });
    txt(s, l[0], { x: x + 0.2, y: 1.95, w: 1.9, h: 0.55, align: 'center', fontSize: 26, bold: true, color: C.navy, fontFace: F.num });
    txt(s, l[1], { x: x + 0.2, y: 2.52, w: 1.9, h: 0.3, align: 'center', fontSize: 11.5, color: C.gray });
  });

  card(s, 8.35, 1.8, 4.28, 1.2, { fill: 'FDF6E8', line: C.gold });
  txt(s, '上传接口不等待解析完成', { x: 8.6, y: 1.98, w: 3.8, h: 0.35, fontSize: 14, bold: true, color: C.navy });
  txt(s, '落盘 + 元数据入库后立即返回，解析在\n后台线程池进行，前端每 3 秒轮询状态。', {
    x: 8.6, y: 2.35, w: 3.8, h: 0.6, fontSize: 11.5, color: C.gray, lineSpacing: 17,
  });

  txt(s, '文档状态机', { x: M.x, y: 3.3, w: 4, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  const states = [
    { t: '排队中', c: C.grayLight }, { t: '解析中', c: 'C99A2E' },
    { t: '向量化中', c: '2E6E9E' }, { t: '已就绪', c: C.green }, { t: '失败', c: C.red },
  ];
  states.forEach((st, i) => {
    const x = M.x + i * 2.42;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 3.85, w: 2.05, h: 0.62, rectRadius: 0.31,
      fill: { color: C.white }, line: { color: st.c, width: 1.5 },
    });
    txt(s, st.t, { x, y: 3.85, w: 2.05, h: 0.62, align: 'center', valign: 'middle', fontSize: 13, bold: true, color: st.c });
    if (i < 4) txt(s, '→', { x: x + 2.03, y: 3.9, w: 0.42, h: 0.5, align: 'center', fontSize: 15, color: C.grayLight, fontFace: F.num });
  });

  card(s, M.x, 4.85, 11.93, 1.3, { fill: C.mist });
  txt(s, '让「卡住」变得可观测', { x: M.x + 0.38, y: 5.05, w: 3.2, h: 0.35, fontSize: 14, bold: true, color: C.navy });
  txt(s, '列表接口额外返回 updated_at（状态最后更新时间）。前端据此判断：一个文件若停在「解析中」超过十分钟没有动静，那大概率是卡住了，而不是还在正常处理。这个字段把一个原本不可见的故障，变成了可以被发现、被排查的现象。', {
    x: M.x + 0.38, y: 5.45, w: 11.2, h: 0.6, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-11 文档解析
// =====================================================================
{
  const s = lightSlide('产品全景 · 用户端', '第三步：文档解析——四种格式，两条路径');
  const fmts = [
    ['电子版 PDF', 'PyMuPDF 逐页提取并记录页码，pdfplumber 兜底。页码最终成为引用里的「第 X 页」。'],
    ['扫描版 PDF', '按页判定：单页有效字符 < 40 即视为图片页，渲染为图像交 OCR。PaddleOCR 优先，Tesseract 回退。'],
    ['DOCX', 'python-docx 提取段落，表格内容同样入库——很多论文的关键数据就在表格里。'],
    ['TXT / Markdown', '字符集自动识别（UTF-8 / GBK）。Markdown 去排版符号但保留标题文字，因为标题语义密度最高。'],
  ];
  fmts.forEach((f, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M.x + col * 6.15, y = 1.8 + row * 2.15;
    card(s, x, y, 5.78, 1.95);
    badge(s, x + 0.32, y + 0.3, String(i + 1), { d: 0.45, size: 13 });
    txt(s, f[0], { x: x + 0.95, y: y + 0.33, w: 4.5, h: 0.35, fontSize: 16, bold: true, color: C.navy });
    txt(s, f[1], { x: x + 0.32, y: y + 0.95, w: 5.15, h: 0.85, fontSize: 12.5, color: C.gray, lineSpacing: 19 });
  });
  card(s, M.x, 6.1, 11.93, 0.75, { fill: 'FBF2F0', line: 'F0DAD5' });
  txt(s, 'OCR 引擎缺失时，系统不崩溃、也不假装成功——标记为「失败」，给出明确中文提示，并进入管理后台的失败队列。', {
    x: M.x + 0.38, y: 6.28, w: 11.2, h: 0.4, fontSize: 12.5, color: C.navy,
  });
  pageNo(s);
}

// =====================================================================
// P-12 切分
// =====================================================================
{
  const s = lightSlide('产品全景 · 用户端', '第四步：切分——为什么不能整篇入库');
  card(s, M.x, 1.78, 5.78, 1.78, { fill: C.mist });
  txt(s, '两个原因', { x: M.x + 0.38, y: 1.95, w: 3, h: 0.32, fontSize: 15, bold: true, color: C.navy });
  txt(s, '① 向量表达能力有限——把一万字压成一个向量，语义被严重稀释；\n② 大模型上下文有限且昂贵——只需送最相关的几段，而不是整本书。', {
    x: M.x + 0.38, y: 2.32, w: 5.15, h: 1.15, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.15, y: 1.78, w: 5.48, h: 1.78, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '参数必须可动态调整', { x: 7.5, y: 1.95, w: 4.6, h: 0.32, fontSize: 15, bold: true, color: C.gold });
  txt(s, '切片大小与重叠字符数没有放之四海皆准的最优值，取决于文献类型、语言与提问风格——所以它们是后台配置项，不是代码常量。', {
    x: 7.5, y: 2.32, w: 4.8, h: 1.15, fontSize: 12, color: C.ice, lineSpacing: 18,
  });

  txt(s, '三级边界切分策略', { x: M.x, y: 3.62, w: 5, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  const lv = [
    ['段落边界', '优先在自然段处断开，语义最完整'],
    ['句子边界', '段落过长时按句号、问号等中英文标点断开'],
    ['字符硬切', '遇到无任何标点的超长文本（代码、化学式）才启用'],
  ];
  lv.forEach((l, i) => {
    const x = M.x + i * 4.0;
    card(s, x, 4.15, 3.75, 1.35, { fill: C.white, line: C.line });
    badge(s, x + 0.3, 4.4, String(i + 1), { d: 0.42, size: 13, fill: C.gold, color: C.navy });
    txt(s, l[0], { x: x + 0.85, y: 4.43, w: 2.6, h: 0.32, fontSize: 14, bold: true, color: C.navy });
    txt(s, l[1], { x: x + 0.3, y: 4.9, w: 3.2, h: 0.55, fontSize: 11.5, color: C.gray, lineSpacing: 17 });
  });
  card(s, M.x, 5.75, 11.93, 0.85, { fill: 'F0F7F4', line: 'D6E8E0' });
  txt(s, '重叠（overlap）的作用：若一个关键结论正好横跨两个切片的边界，没有重叠则两边都不完整；有了重叠，至少有一边是完整的。系统强制校验「重叠 < 切片大小」，否则切分会原地打转。', {
    x: M.x + 0.38, y: 5.95, w: 11.2, h: 0.5, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-13 向量化与五要素
// =====================================================================
{
  const s = lightSlide('产品全景 · 用户端 [S-3]', '第五步：向量化与入库');
  txt(s, '每个向量切片写入向量库时，Metadata 必须包含五个字段', {
    x: M.x, y: 1.72, w: 9, h: 0.35, fontSize: 15, bold: true, color: C.navy,
  });
  const meta = [
    ['doc_id', '文档唯一 ID'], ['user_id', '所属用户 ID'], ['file_name', '原始文件名'],
    ['page', '页码（PDF）'], ['chunk_index', '切片序号'],
  ];
  meta.forEach((m, i) => {
    const x = M.x + i * 2.42;
    card(s, x, 2.2, 2.2, 1.15, { fill: i === 0 ? 'FDF6E8' : C.mist, line: i === 0 ? C.gold : C.line });
    txt(s, m[0], { x: x + 0.1, y: 2.42, w: 2.0, h: 0.35, align: 'center', fontSize: 14, bold: true, color: C.navy, fontFace: F.num });
    txt(s, m[1], { x: x + 0.1, y: 2.82, w: 2.0, h: 0.3, align: 'center', fontSize: 11, color: C.gray });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 3.6, w: 5.78, h: 2.45, rectRadius: 0.1,
    fill: { color: 'FBF2F0' }, line: { color: 'F0DAD5', width: 1 }, shadow: sh(),
  });
  txt(s, '如果缺了 doc_id 会怎样', { x: M.x + 0.38, y: 3.85, w: 5.0, h: 0.35, fontSize: 16, bold: true, color: C.red });
  txt(s, '用户删除文档时，无法定位该文档产生的向量——它们会永远留在向量库里。', {
    x: M.x + 0.38, y: 4.3, w: 5.15, h: 0.6, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  bullets(s, [
    '向量库持续积累垃圾数据，越来越大、检索越来越慢',
    '用户以为已删除的文献，仍会被检索到并出现在引用里',
    '这不只是性能问题，更是数据合规问题',
  ], { x: M.x + 0.42, y: 5.0, w: 5.1, h: 0.95, fontSize: 12, color: C.red });

  card(s, 7.15, 3.6, 5.48, 2.45, { fill: C.mist });
  txt(s, '我们怎么守护它', { x: 7.5, y: 3.85, w: 4.8, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  txt(s, '删除时执行一条精确清除：', { x: 7.5, y: 4.3, w: 4.8, h: 0.3, fontSize: 12.5, color: C.gray });
  s.addShape(pres.ShapeType.roundRect, {
    x: 7.5, y: 4.62, w: 4.78, h: 0.5, rectRadius: 0.06, fill: { color: C.ink }, line: { color: C.ink, width: 1 },
  });
  txt(s, 'collection.delete(where={"doc_id": ...})', {
    x: 7.6, y: 4.62, w: 4.6, h: 0.5, valign: 'middle', fontSize: 11, color: C.ice, fontFace: 'Courier New',
  });
  txt(s, '并且写了一个自动化测试用例专门守护：\n上传 → 断言向量数 > 0 → 删除 → 断言向量数归零。', {
    x: 7.5, y: 5.3, w: 4.8, h: 0.65, fontSize: 12, color: C.gray, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-14 提问背后
// =====================================================================
{
  const s = lightSlide('产品全景 · 智能问答', '用户看到第一个字之前，系统做了四件事');
  const steps = [
    ['问题改写', '追问里的「它」「这个方法」指代什么，向量检索并不知道。先结合历史对话把追问改写成语义完整、可独立检索的查询。', C.navy],
    ['向量检索', '把改写后的问题向量化，在该用户专属的向量集合中检索 Top-N 候选片段，默认 N = 20。', C.navy],
    ['重排序精筛', '把问题与 20 个候选一起交给 Rerank 模型二次打分，选出最相关的 Top-K，默认 K = 4~5。', C.gold],
    ['组装提示词', '把精排片段按序号编号，连同系统提示词与历史对话一起送给大模型。', C.navy],
  ];
  steps.forEach((st, i) => {
    const y = 1.72 + i * 1.2;
    card(s, M.x, y, 11.93, 1.05, { fill: i === 2 ? 'FDF6E8' : C.mist, line: i === 2 ? C.gold : C.line });
    badge(s, M.x + 0.3, y + 0.28, String(i + 1), { d: 0.5, size: 14, fill: st[2], color: st[2] === C.gold ? C.navy : C.white });
    txt(s, st[0], { x: M.x + 0.95, y: y + 0.16, w: 2.2, h: 0.35, fontSize: 16, bold: true, color: C.navy });
    txt(s, st[1], { x: M.x + 3.2, y: y + 0.2, w: 8.4, h: 0.7, fontSize: 12.5, color: C.gray, lineSpacing: 19 });
  });
  txt(s, '为什么要有精排这一步：向量检索是双塔模型，快但精度有限；Rerank 是交互模型，精度高但慢。先用快的粗筛 20 个，再用慢的精排出 4 个——经典的漏斗式设计。', {
    x: M.x, y: 6.6, w: 11.93, h: 0.5, fontSize: 12, italic: true, color: C.gray, lineSpacing: 18,
  });
  pageNo(s);
}

// =====================================================================
// P-15 提示词三条约束
// =====================================================================
{
  const s = lightSlide('产品全景 · 智能问答', '提示词：幻觉遏制的最后一道闸门');
  const rules = [
    ['严格依据背景资料作答', '不是「参考」，是「严格依据」。模型的发挥空间被刻意压缩。', C.mist, C.line],
    ['资料不足时必须明说', '原文约束：「如果资料中没有足够信息来回答问题，请直接说明『根据现有资料无法回答该问题』，切勿编造信息。」', 'FDF6E8', C.gold],
    ['必须打引用标记', '引用了哪一段就在对应位置标上 [1]、[2]，这些标记会被前端解析为可点击的角标。', C.mist, C.line],
  ];
  rules.forEach((r, i) => {
    const y = 1.78 + i * 1.4;
    card(s, M.x, y, 7.6, 1.25, { fill: r[2], line: r[3] });
    badge(s, M.x + 0.32, y + 0.35, String(i + 1), { d: 0.52, size: 15, fill: i === 1 ? C.gold : C.navy, color: i === 1 ? C.navy : C.white });
    txt(s, r[0], { x: M.x + 1.0, y: y + 0.2, w: 6.3, h: 0.35, fontSize: 16, bold: true, color: C.navy });
    txt(s, r[1], { x: M.x + 1.0, y: y + 0.6, w: 6.4, h: 0.6, fontSize: 12, color: C.gray, lineSpacing: 18 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 8.6, y: 1.78, w: 4.03, h: 4.27, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '价值底线', { x: 8.95, y: 2.1, w: 3.4, h: 0.35, fontSize: 17, bold: true, color: C.gold });
  txt(s, '我们宁可让用户失望，\n也不能让用户被误导。', {
    x: 8.95, y: 2.65, w: 3.4, h: 0.75, fontSize: 16, bold: true, color: C.white, lineSpacing: 26,
  });
  txt(s, '在学术场景中，一个诚实的「我不知道」，价值远高于一个流畅的错误答案。', {
    x: 8.95, y: 3.6, w: 3.4, h: 1.0, fontSize: 13, color: C.ice, lineSpacing: 21,
  });
  txt(s, '因为后者会让研究者基于一个虚构的前提，浪费三个月。', {
    x: 8.95, y: 4.85, w: 3.4, h: 0.9, fontSize: 12, color: '9AA5CE', lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-16 流式输出
// =====================================================================
{
  const s = lightSlide('产品全景 · 智能问答', '流式输出：为什么不能等');
  card(s, M.x, 1.75, 5.78, 1.5, { fill: 'FBF2F0', line: 'F0DAD5' });
  txt(s, '如果等待完整生成', { x: M.x + 0.38, y: 1.95, w: 5.0, h: 0.32, fontSize: 15, bold: true, color: C.red });
  txt(s, '用户盯着空白页面等十几秒。不知道系统在工作还是已经卡死，浏览器还可能超时。', {
    x: M.x + 0.38, y: 2.32, w: 5.15, h: 0.75, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  card(s, 7.15, 1.75, 5.48, 1.5, { fill: 'F0F7F4', line: 'D6E8E0' });
  txt(s, 'SSE 边生成边推送', { x: 7.5, y: 1.95, w: 4.8, h: 0.32, fontSize: 15, bold: true, color: C.green });
  txt(s, '一秒内看到第一个字，文字像打字机一样出现。有反馈的等待，感知时长远短于无反馈的等待。', {
    x: 7.5, y: 2.32, w: 4.8, h: 0.75, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });

  txt(s, '四类 SSE 事件', { x: M.x, y: 3.5, w: 4, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  const evs = [
    ['chunk', '增量文本', '推送多次，逐字呈现'],
    ['title', '会话标题', '仅首轮提问推送一次'],
    ['done', '结束帧', '携带完整引用列表与消息 ID'],
    ['error', '错误', '出错时推送后关闭连接'],
  ];
  evs.forEach((e, i) => {
    const x = M.x + i * 3.02;
    card(s, x, 4.0, 2.8, 1.6, { fill: C.white, line: C.line });
    s.addShape(pres.ShapeType.roundRect, {
      x: x + 0.25, y: 4.22, w: 1.45, h: 0.42, rectRadius: 0.21,
      fill: { color: C.ink }, line: { color: C.ink, width: 1 },
    });
    txt(s, e[0], { x: x + 0.25, y: 4.22, w: 1.45, h: 0.42, align: 'center', valign: 'middle', fontSize: 12, bold: true, color: C.gold, fontFace: 'Courier New' });
    txt(s, e[1], { x: x + 0.25, y: 4.78, w: 2.3, h: 0.32, fontSize: 14, bold: true, color: C.navy });
    txt(s, e[2], { x: x + 0.25, y: 5.15, w: 2.35, h: 0.4, fontSize: 11.5, color: C.gray, lineSpacing: 16 });
  });
  txt(s, '界面上还有「停止」按钮——用户发现问错了可以随时中断，不必干等模型把话说完。', {
    x: M.x, y: 5.85, w: 11.93, h: 0.4, fontSize: 12.5, italic: true, color: C.gray,
  });
  pageNo(s);
}

// =====================================================================
// P-17 引用溯源
// =====================================================================
{
  const s = lightSlide('产品全景 · 智能问答', '引用溯源：产品的灵魂');
  const forms = [
    ['正文角标', '回答中的 [1]、[2] 渲染为可点击的蓝色小方块，点击弹窗展示对应原文段落。'],
    ['引用卡片', '回答下方的卡片，显示文件名、位置、原文摘要三项信息，同样可点击展开。'],
  ];
  forms.forEach((f, i) => {
    const x = M.x + i * 3.35;
    card(s, x, 1.78, 3.1, 1.75);
    txt(s, f[0], { x: x + 0.3, y: 2.0, w: 2.5, h: 0.35, fontSize: 16, bold: true, color: C.navy });
    txt(s, f[1], { x: x + 0.3, y: 2.45, w: 2.55, h: 0.95, fontSize: 12, color: C.gray, lineSpacing: 18 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.4, y: 1.78, w: 5.23, h: 1.75, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '[I-3] 位置怎么标', { x: 7.75, y: 2.0, w: 4.5, h: 0.35, fontSize: 16, bold: true, color: C.gold });
  txt(s, 'PDF 标注「第 X 页」，用户可直接翻页核对；\nTXT / Markdown 没有页码，如实标注「第 N 个片段」——硬编一个页码是自欺欺人。', {
    x: 7.75, y: 2.45, w: 4.55, h: 0.95, fontSize: 12, color: C.ice, lineSpacing: 18,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 3.85, w: 11.93, h: 2.25, rectRadius: 0.1,
    fill: { color: 'FDF6E8' }, line: { color: C.gold, width: 1 }, shadow: sh(),
  });
  txt(s, '为什么说它是灵魂，而不是一个附加功能', {
    x: M.x + 0.45, y: 4.1, w: 8, h: 0.4, fontSize: 18, bold: true, color: C.navy,
  });
  txt(s, '如果没有溯源，这个系统就退化成了一个「可能会说谎、但你查不出来」的聊天机器人。\n有了溯源，用户可以用三秒钟验证任何一句话的真伪。', {
    x: M.x + 0.45, y: 4.62, w: 11.0, h: 0.75, fontSize: 14, color: C.navy, lineSpacing: 24,
  });
  txt(s, '可验证性，才是让一个 AI 系统在严肃场景中真正可用的前提。', {
    x: M.x + 0.45, y: 5.5, w: 11.0, h: 0.4, fontSize: 16, bold: true, italic: true, color: 'A5762A',
  });
  pageNo(s);
}

// =====================================================================
// P-18 纯模型对话模式
// =====================================================================
{
  const s = lightSlide('产品全景 · 智能问答 [S-4]', '纯模型对话模式');
  txt(s, '界面右上角的「知识库检索」开关关闭后：', { x: M.x, y: 1.72, w: 8, h: 0.35, fontSize: 14, color: C.gray });

  const changes = [
    ['跳过向量检索', '不再访问向量库', C.red],
    ['跳过 Rerank 精排', '不再调用云端精排服务', C.red],
    ['历史上下文照常传递', '多轮对话的连贯性完全保持', C.green],
  ];
  changes.forEach((c, i) => {
    const x = M.x + i * 4.0;
    card(s, x, 2.2, 3.75, 1.35, { fill: C.white, line: c[2] === C.green ? 'D6E8E0' : 'F0DAD5' });
    txt(s, c[2] === C.green ? '保持' : '跳过', {
      x: x + 0.3, y: 2.42, w: 0.9, h: 0.32, align: 'center', fontSize: 11, bold: true, color: c[2],
    });
    txt(s, c[0], { x: x + 0.3, y: 2.82, w: 3.2, h: 0.32, fontSize: 14.5, bold: true, color: C.navy });
    txt(s, c[1], { x: x + 0.3, y: 3.18, w: 3.2, h: 0.3, fontSize: 11.5, color: C.gray });
  });

  card(s, M.x, 3.85, 5.78, 2.2, { fill: C.mist });
  txt(s, '为什么需要这个模式', { x: M.x + 0.38, y: 4.08, w: 5.0, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  txt(s, '用户的需求不总是「查资料」。有时候他只是想问「帮我把这段话润色一下」「解释一下什么是梯度消失」——这些问题不需要检索，检索反而会引入噪声、拖慢速度、浪费成本。', {
    x: M.x + 0.38, y: 4.55, w: 5.15, h: 1.35, fontSize: 12.5, color: C.gray, lineSpacing: 20,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.15, y: 3.85, w: 5.48, h: 2.2, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '不能假装有引用', { x: 7.5, y: 4.08, w: 4.8, h: 0.35, fontSize: 16, bold: true, color: C.gold });
  txt(s, '此模式下 done 帧的 citations 是空数组，数据库中存 NULL，前端不显示任何引用卡片。\n\n因为这一轮确实没有引用——诚实地什么都不显示，好过编造一个看起来专业的来源。', {
    x: 7.5, y: 4.55, w: 4.8, h: 1.35, fontSize: 12.5, color: C.ice, lineSpacing: 20,
  });
  pageNo(s);
}

// =====================================================================
// P-19 历史会话管理
// =====================================================================
{
  const s = lightSlide('产品全景 · 用户端', '历史会话管理');
  const feats = [
    ['标题自动生成', '首轮提问后调用大模型生成 15 字以内摘要，通过 SSE 的 title 事件实时推送，侧边栏立刻更新'],
    ['手动重命名', '悬停显示铅笔图标，就地编辑，回车保存、Esc 取消'],
    ['模糊搜索', '按标题模糊匹配，输入时 300 毫秒防抖，避免频繁请求'],
    ['内容预览 [I-2]', '列表中显示最新一条回答的前 60 字——光看标题常常想不起来聊过什么'],
    ['逻辑删除', '标记 is_deleted = 1 而非物理删除，便于审计追溯'],
    ['权限隔离', '所有查询强制附加 user_id 条件，无法越权查看他人会话'],
  ];
  feats.forEach((f, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = M.x + col * 4.0, y = 1.8 + row * 2.2;
    card(s, x, y, 3.75, 1.95);
    badge(s, x + 0.3, y + 0.28, String(i + 1), { d: 0.45, size: 13 });
    txt(s, f[0], { x: x + 0.9, y: y + 0.31, w: 2.7, h: 0.35, fontSize: 14.5, bold: true, color: C.navy });
    txt(s, f[1], { x: x + 0.3, y: y + 0.95, w: 3.2, h: 0.9, fontSize: 11.5, color: C.gray, lineSpacing: 17 });
  });
  pageNo(s);
}

// =====================================================================
// P-20 用户管理
// =====================================================================
{
  const s = lightSlide('产品全景 · 管理后台', '用户管理');
  const rows = [
    ['邮箱', '账号标识'], ['角色', '普通用户 / 管理员'], ['状态', '启用 / 禁用'],
    ['上传文档数', '一眼看出谁是活跃用户'], ['最后登录时间', '判断账号活跃度'], ['注册时间', '用户增长追踪'],
  ];
  txt(s, '列表字段', { x: M.x, y: 1.72, w: 4, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  rows.forEach((r, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = M.x + col * 2.6, y = 2.2 + row * 0.85;
    card(s, x, y, 2.4, 0.72, { fill: C.mist, shadow: false });
    txt(s, r[0], { x: x + 0.18, y: y + 0.08, w: 2.1, h: 0.28, fontSize: 13, bold: true, color: C.navy });
    txt(s, r[1], { x: x + 0.18, y: y + 0.38, w: 2.1, h: 0.28, fontSize: 10.5, color: C.gray });
  });

  txt(s, '可执行操作', { x: 8.5, y: 1.72, w: 4, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  const acts = ['切换角色（普通用户 ⇄ 管理员）', '启用 / 禁用账号', '生成临时密码（重置）'];
  acts.forEach((a, i) => {
    const y = 2.2 + i * 0.85;
    card(s, 8.5, y, 4.13, 0.72, { fill: C.white, line: C.line, shadow: false });
    badge(s, 8.68, y + 0.16, String(i + 1), { d: 0.4, size: 12, fill: C.gold, color: C.navy });
    txt(s, a, { x: 9.2, y, w: 3.3, h: 0.72, valign: 'middle', fontSize: 12.5, color: C.navy });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 4.95, w: 11.93, h: 1.35, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '两条防呆规则', { x: M.x + 0.42, y: 5.18, w: 3, h: 0.35, fontSize: 15, bold: true, color: C.gold });
  txt(s, '管理员不能取消自己的管理员角色，也不能禁用自己的账号。否则一个手滑就可能把整个系统锁死，没人能进后台。\n这类设计看起来不起眼，但在生产环境里能救命。', {
    x: M.x + 0.42, y: 5.6, w: 11.0, h: 0.65, fontSize: 12.5, color: C.ice, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-21 密码重置闭环
// =====================================================================
{
  const s = lightSlide('产品全景 · 管理后台 [M-4]', '密码重置：一条完整的人工闭环');
  const steps = [
    ['用户提交申请', '登录页点「忘记密码」，输入注册邮箱'],
    ['频率限制拦截', '同一邮箱 10 分钟内只允许一次，已有未处理申请直接返回 400'],
    ['管理员看到列表', '后台顶部显示醒目的待处理提示条'],
    ['生成临时密码', '随机生成，仅在本次响应显示一次，关闭后无法再查看'],
    ['线下转交 + 改密', '用户用临时密码登录，系统提示立即修改'],
  ];
  steps.forEach((st, i) => {
    const y = 1.78 + i * 0.95;
    card(s, M.x, y, 8.6, 0.82, { fill: i === 1 ? 'FDF6E8' : C.mist, line: i === 1 ? C.gold : C.line, shadow: false });
    badge(s, M.x + 0.28, y + 0.16, String(i + 1), { d: 0.5, size: 14, fill: i === 1 ? C.gold : C.navy, color: i === 1 ? C.navy : C.white });
    txt(s, st[0], { x: M.x + 0.95, y: y + 0.08, w: 2.3, h: 0.32, fontSize: 14.5, bold: true, color: C.navy });
    txt(s, st[1], { x: M.x + 3.3, y: y + 0.1, w: 5.15, h: 0.6, fontSize: 11.5, color: C.gray, lineSpacing: 16 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 9.6, y: 1.78, w: 3.03, h: 4.55, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '为什么要限频', { x: 9.9, y: 2.05, w: 2.5, h: 0.35, fontSize: 15, bold: true, color: C.gold });
  txt(s, '10', { x: 9.9, y: 2.55, w: 2.5, h: 1.1, fontSize: 54, bold: true, color: C.white, fontFace: F.num });
  txt(s, '分钟内限一次', { x: 9.9, y: 3.68, w: 2.5, h: 0.3, fontSize: 13, color: C.ice });
  txt(s, '不然有人写个脚本，几分钟就能刷出几千条待处理申请，把后台淹掉。\n\n系统没有邮件服务，所以采用人工流程——这是资源约束下的合理选择。', {
    x: 9.9, y: 4.12, w: 2.5, h: 2.0, fontSize: 11.5, color: '9AA5CE', lineSpacing: 18,
  });
  pageNo(s);
}

// =====================================================================
// P-22 token_version
// =====================================================================
{
  const s = darkSlide();
  txt(s, '安全机制 [S-2]', { x: M.x, y: 0.5, w: 8, h: 0.3, fontSize: 13, bold: true, color: C.gold, charSpacing: 2 });
  txt(s, 'token_version：让旧令牌立刻失效', {
    x: M.x, y: 0.88, w: 10, h: 0.7, fontSize: 32, bold: true, color: C.white,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 1.85, w: 5.78, h: 2.1, rectRadius: 0.1,
    fill: { color: '2A1A2E' }, line: { color: '5E3040', width: 1 },
  });
  txt(s, '问题', { x: M.x + 0.38, y: 2.08, w: 2, h: 0.32, fontSize: 14, bold: true, color: 'E88B7D' });
  txt(s, 'JWT 是无状态的，一旦签发，在过期之前服务端无法主动撤销。', {
    x: M.x + 0.38, y: 2.45, w: 5.1, h: 0.55, fontSize: 13, color: C.white, lineSpacing: 20,
  });
  txt(s, '用户密码被盗，攻击者已登录并持有一个 7 天有效的 Token。用户改了密码——那个 Token 在剩下的 6 天里依然完全有效。改密码等于没改。', {
    x: M.x + 0.38, y: 3.05, w: 5.1, h: 0.8, fontSize: 12, color: 'C9A5A5', lineSpacing: 18,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.15, y: 1.85, w: 5.48, h: 2.1, rectRadius: 0.1,
    fill: { color: '132A28' }, line: { color: '2E6E5E', width: 1 },
  });
  txt(s, '解法', { x: 7.5, y: 2.08, w: 2, h: 0.32, fontSize: 14, bold: true, color: '7FD1B0' });
  txt(s, '用户表增加 token_version 字段，默认 0。', {
    x: 7.5, y: 2.45, w: 4.8, h: 0.35, fontSize: 13, color: C.white,
  });
  txt(s, '· 签发时把当前版本号写进 Token 载荷\n· 每次鉴权与数据库当前值比对\n· Token 版本号 < 数据库当前值 → 立即 401', {
    x: 7.5, y: 2.85, w: 4.8, h: 1.0, fontSize: 12, color: 'A5CFC0', lineSpacing: 19,
  });

  txt(s, '触发版本号 +1 的两个场景', { x: M.x, y: 4.25, w: 6, h: 0.35, fontSize: 15, bold: true, color: C.gold });
  ['管理员重置该用户密码', '用户自己修改密码'].forEach((t, i) => {
    const x = M.x + i * 3.3;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 4.72, w: 3.1, h: 0.6, rectRadius: 0.3,
      fill: { color: C.navy }, line: { color: C.navySoft, width: 1 },
    });
    txt(s, t, { x, y: 4.72, w: 3.1, h: 0.6, align: 'center', valign: 'middle', fontSize: 12.5, color: C.ice });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 5.55, w: 11.93, h: 1.0, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.gold, width: 1 },
  });
  txt(s, '效果：改密码的那一瞬间，该用户此前签发的所有 Token，在所有设备上全部立即失效。', {
    x: M.x + 0.42, y: 5.72, w: 11.0, h: 0.35, fontSize: 14, bold: true, color: C.gold,
  });
  txt(s, '体验细节：用户自己改密码时会立刻收到新 Token——当前设备不被登出，其他设备全部登出，符合直觉。', {
    x: M.x + 0.42, y: 6.1, w: 11.0, h: 0.35, fontSize: 12, color: C.ice,
  });
  pageNo(s, true);
}

// =====================================================================
// P-23 系统配置
// =====================================================================
{
  const s = lightSlide('产品全景 · 管理后台', '系统配置：不改代码切换模型');
  const cfg = [
    ['大模型', 'Base URL / API Key / 模型名称'],
    ['辅助任务模型', '问题改写与标题生成专用的小模型'],
    ['Embedding', '模型名称 / Base URL / API Key'],
    ['Rerank', '终结点 / API Key / 模型名称 / Top-K'],
    ['切片参数', '切片大小 / 重叠字符数'],
    ['检索参数', 'Top-N 候选数 / 历史轮数上限'],
  ];
  cfg.forEach((c, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M.x + col * 4.3, y = 1.8 + row * 1.05;
    card(s, x, y, 4.05, 0.9, { fill: C.mist, shadow: false });
    txt(s, c[0], { x: x + 0.25, y: y + 0.13, w: 3.6, h: 0.32, fontSize: 14, bold: true, color: C.navy });
    txt(s, c[1], { x: x + 0.25, y: y + 0.47, w: 3.6, h: 0.3, fontSize: 11, color: C.gray });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 9.35, y: 1.8, w: 3.28, h: 3.2, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '改完点保存\n立即全局生效', { x: 9.65, y: 2.1, w: 2.75, h: 0.8, fontSize: 19, bold: true, color: C.gold, lineSpacing: 28 });
  txt(s, '不需要重启服务。配置存数据库，应用层做 5 秒 TTL 缓存，写入时主动失效——既避免每次问答都查库，又保证修改快速生效。', {
    x: 9.65, y: 3.05, w: 2.75, h: 1.6, fontSize: 12, color: C.ice, lineSpacing: 19,
  });

  card(s, M.x, 5.2, 11.93, 1.1, { fill: 'F0F7F4', line: 'D6E8E0' });
  txt(s, '这个能力的价值：从 DeepSeek 换到通义千问，从云端模型换到本地部署的模型，不需要改一行代码、不需要重新发布，在后台改个地址就行。需求文档「模型层抽象」这条要求，落到实处就是这个页面。', {
    x: M.x + 0.4, y: 5.45, w: 11.1, h: 0.65, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-24 API Key 三重保护
// =====================================================================
{
  const s = lightSlide('安全设计 [S-1]', 'API Key 的三重保护');
  const guards = [
    ['静态加密', 'AES-256-GCM', '写入数据库前加密，库里存的是带 enc::v1:: 前缀的密文。选 GCM 是因为它同时提供加密与完整性校验——密文被篡改时解密直接失败，而不是解出垃圾数据。'],
    ['响应脱敏', 'sk-****fkdn', '读取配置的接口永远不返回明文，只返回掩码。我们写了专门的测试用例，断言整个 HTTP 响应体中不包含明文 Key。'],
    ['留空即不改', '防误操作', '前端 Key 输入框永远为空，占位符显示当前掩码。留空表示「保持原值」——如果留空表示「清空」，管理员改个模型名就可能把线上密钥打掉。'],
  ];
  guards.forEach((g, i) => {
    const x = M.x + i * 4.0;
    card(s, x, 1.8, 3.75, 4.0, { fill: i === 0 ? 'FDF6E8' : C.mist, line: i === 0 ? C.gold : C.line });
    badge(s, x + 0.32, 2.1, String(i + 1), { d: 0.58, size: 17, fill: i === 0 ? C.gold : C.navy, color: i === 0 ? C.navy : C.white });
    txt(s, g[0], { x: x + 0.32, y: 2.9, w: 3.1, h: 0.35, fontSize: 18, bold: true, color: C.navy });
    s.addShape(pres.ShapeType.roundRect, {
      x: x + 0.32, y: 3.35, w: 2.4, h: 0.42, rectRadius: 0.21,
      fill: { color: C.ink }, line: { color: C.ink, width: 1 },
    });
    txt(s, g[1], { x: x + 0.32, y: 3.35, w: 2.4, h: 0.42, align: 'center', valign: 'middle', fontSize: 11, color: C.gold, fontFace: 'Courier New' });
    txt(s, g[2], { x: x + 0.32, y: 3.95, w: 3.15, h: 1.7, fontSize: 12, color: C.gray, lineSpacing: 19 });
  });
  txt(s, '加密密钥本身存在环境变量 CONFIG_ENCRYPTION_KEY 中，不入库、不进代码仓库——且必须备份，丢失后所有已存 Key 都解不开。', {
    x: M.x, y: 6.05, w: 11.93, h: 0.4, fontSize: 12, italic: true, color: C.gray,
  });
  pageNo(s);
}

// =====================================================================
// P-25 运行监控
// =====================================================================
{
  const s = lightSlide('产品全景 · 管理后台 [I-4]', '运行监控');
  const metrics = [
    ['大模型调用', '8'], ['Token 消耗', '2,468'], ['Rerank 调用', '4'], ['向量检索', '4'],
    ['OCR 处理', '0'], ['总调用次数', '12'], ['失败次数', '0'], ['失败率', '0.00%'],
  ];
  metrics.forEach((m, i) => {
    const col = i % 4, row = Math.floor(i / 4);
    const x = M.x + col * 3.02, y = 1.75 + row * 1.15;
    card(s, x, y, 2.8, 1.0, { fill: C.mist, shadow: false });
    txt(s, m[0], { x: x + 0.22, y: y + 0.12, w: 2.4, h: 0.28, fontSize: 11, color: C.gray });
    txt(s, m[1], { x: x + 0.22, y: y + 0.42, w: 2.4, h: 0.48, fontSize: 24, bold: true, color: C.navy, fontFace: F.num });
  });

  s.addChart(pres.ChartType.bar, [{
    name: '调用次数',
    labels: ['大模型', 'Rerank', '向量检索', 'Embedding', 'OCR'],
    values: [8, 4, 4, 4, 0],
  }], {
    x: M.x, y: 4.15, w: 6.6, h: 2.2,
    barDir: 'col', chartColors: [C.navy],
    showTitle: true, title: '各环节调用次数分布', titleFontSize: 13, titleColor: C.navy, titleFontFace: F.cn,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 10, dataLabelColor: C.gray,
    catAxisLabelColor: C.gray, catAxisLabelFontSize: 10, catAxisLabelFontFace: F.cn,
    valAxisLabelColor: C.gray, valAxisLabelFontSize: 9,
    valGridLine: { color: C.line, size: 1 }, catGridLine: { style: 'none' },
    showLegend: false, barGapWidthPct: 60,
  });

  card(s, 7.7, 4.15, 4.93, 2.2, { fill: C.white, line: C.line });
  txt(s, '失败队列', { x: 7.98, y: 4.35, w: 4.4, h: 0.32, fontSize: 15, bold: true, color: C.navy });
  txt(s, '列出解析失败的文档：文件名、失败原因、时间、文档 ID。管理员能直接看到「哪个用户的哪个文件因为什么原因失败了」，而不是只看到一个冷冰冰的失败计数。', {
    x: 7.98, y: 4.78, w: 4.4, h: 1.15, fontSize: 12, color: C.gray, lineSpacing: 19,
  });
  txt(s, '每日趋势图用纯 CSS 实现，未引入图表库。', { x: 7.98, y: 5.95, w: 4.4, h: 0.3, fontSize: 11, italic: true, color: C.grayLight });
  pageNo(s);
}

// =====================================================================
// P-26 整体架构
// =====================================================================
{
  const s = lightSlide('技术架构', '四层架构');
  const layers = [
    ['前端', 'React 18 + TypeScript + Vite + TailwindCSS', '单页应用，响应式布局，桌面与移动端共用一套代码', C.ice, C.navy],
    ['后端应用', 'Python 3.10+ + FastAPI + SQLAlchemy 2.0', 'core / models / schemas / api / services / utils 六个包，职责分明', C.navy, C.white],
    ['数据存储', 'MySQL 8 + Chroma + 本地文件系统', '结构化数据、向量、原始文件三类存储各司其职', C.navySoft, C.white],
    ['外部服务', 'LLM API + Embedding API + Rerank API', '全部走 OpenAI 兼容协议，可在后台随时替换', C.mist, C.navy],
  ];
  layers.forEach((l, i) => {
    const y = 1.75 + i * 1.22;
    s.addShape(pres.ShapeType.roundRect, {
      x: M.x, y, w: 11.93, h: 1.08, rectRadius: 0.08,
      fill: { color: l[3] }, line: { color: l[3] === C.mist || l[3] === C.ice ? C.line : l[3], width: 1 }, shadow: sh(),
    });
    txt(s, l[0], { x: M.x + 0.4, y: y + 0.2, w: 1.8, h: 0.35, fontSize: 17, bold: true, color: l[4] });
    txt(s, l[1], { x: M.x + 2.3, y: y + 0.18, w: 5.0, h: 0.35, fontSize: 12.5, bold: true, color: l[4], fontFace: F.num });
    txt(s, l[2], { x: M.x + 2.3, y: y + 0.55, w: 9.2, h: 0.4, fontSize: 11.5, color: l[4] === C.white ? C.ice : C.gray });
    txt(s, `L${4 - i}`, {
      x: M.x + 10.9, y: y + 0.28, w: 0.8, h: 0.4, align: 'right',
      fontSize: 16, bold: true, color: l[4] === C.white ? '6B75A5' : C.grayLight, fontFace: F.num,
    });
  });
  txt(s, '数据流向：浏览器 → HTTP REST / SSE → FastAPI → MySQL + Chroma → 外部模型 API', {
    x: M.x, y: 6.65, w: 11.93, h: 0.35, fontSize: 12, italic: true, color: C.gray,
  });
  pageNo(s);
}

// =====================================================================
// P-27 关键技术决策
// =====================================================================
{
  const s = lightSlide('技术架构', '三个被认真权衡过的决策');
  const dec = [
    ['为什么用 Chroma\n而不是 Milvus？', '本项目数据规模（单用户几十到几百篇）完全在 Chroma 的舒适区。它是嵌入式的，免部署免运维。', '但我们做了向量库抽象层——迁移 Milvus 只需新增一个实现类，上层业务代码一行不改。'],
    ['为什么用同步 ORM\n而不是异步？', '性能瓶颈根本不在数据库。一次大模型生成 8 秒，数据库查询是毫秒级。', 'FastAPI 会把同步路由自动放进线程池，不阻塞事件循环。代码更直白，调试更容易，性能无损。'],
    ['为什么用 SSE\n而不是 WebSocket？', '问答是单向推送场景，客户端不需要在流中反向发消息。', 'SSE 基于普通 HTTP，无需协议升级，断线自动重连，过反向代理的坑也少得多。'],
  ];
  dec.forEach((d, i) => {
    const x = M.x + i * 4.0;
    card(s, x, 1.8, 3.75, 4.35);
    txt(s, d[0], { x: x + 0.32, y: 2.05, w: 3.1, h: 0.8, fontSize: 16, bold: true, color: C.navy, lineSpacing: 24 });
    txt(s, d[1], { x: x + 0.32, y: 2.95, w: 3.15, h: 1.15, fontSize: 12, color: C.gray, lineSpacing: 19 });
    s.addShape(pres.ShapeType.roundRect, {
      x: x + 0.32, y: 4.2, w: 3.15, h: 1.7, rectRadius: 0.08,
      fill: { color: C.white }, line: { color: C.gold, width: 1 },
    });
    txt(s, d[2], { x: x + 0.48, y: 4.38, w: 2.85, h: 1.4, fontSize: 11.5, color: C.navy, lineSpacing: 18 });
  });
  pageNo(s);
}

// =====================================================================
// P-28 RAG 引擎六模块
// =====================================================================
{
  const s = lightSlide('技术架构', 'RAG 引擎：六个职责单一的模块');
  const mods = [
    ['解析', 'parser_service', '多格式解析、扫描版判定、字符集识别'],
    ['切分', 'chunking_service', '三级边界切分、重叠控制'],
    ['向量化', 'embedding_service', '批量调用 Embedding API，批大小 16'],
    ['存储检索', 'vector_store', '用户级隔离的向量读写与删除'],
    ['精排', 'rerank_service', '云端 Rerank，超时自动降级'],
    ['生成', 'llm_service / rag_service', '提示词组装、流式生成、引用构造'],
  ];
  mods.forEach((m, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = M.x + col * 4.0, y = 1.8 + row * 2.1;
    card(s, x, y, 3.75, 1.85);
    badge(s, x + 0.3, y + 0.28, String(i + 1), { d: 0.45, size: 13 });
    txt(s, m[0], { x: x + 0.9, y: y + 0.3, w: 2.6, h: 0.32, fontSize: 15, bold: true, color: C.navy });
    txt(s, m[1], { x: x + 0.3, y: y + 0.88, w: 3.2, h: 0.28, fontSize: 10.5, color: C.gold, fontFace: 'Courier New' });
    txt(s, m[2], { x: x + 0.3, y: y + 1.2, w: 3.2, h: 0.55, fontSize: 11.5, color: C.gray, lineSpacing: 17 });
  });
  card(s, M.x, 6.05, 11.93, 0.85, { fill: 'F0F7F4', line: 'D6E8E0' });
  txt(s, '职责单一带来的真实收益：发现 Rerank 模型名写错时，修改只涉及一个文件的一行；需要给辅助任务单独配模型时，改动集中在一个函数参数上。', {
    x: M.x + 0.4, y: 6.25, w: 11.1, h: 0.5, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-29 三级超时降级
// =====================================================================
{
  const s = lightSlide('技术架构 [M-6]', '三级超时降级：让系统不会整体失败');
  const hdr = ['环节', '超时阈值', '降级行为', '用户感知'];
  const wds = [2.4, 1.6, 5.0, 2.93];
  let cx = M.x;
  hdr.forEach((h, i) => {
    s.addShape(pres.ShapeType.rect, { x: cx, y: 1.78, w: wds[i], h: 0.55, fill: { color: C.navy }, line: { color: C.navy, width: 1 } });
    txt(s, h, { x: cx + 0.18, y: 1.78, w: wds[i] - 0.3, h: 0.55, valign: 'middle', fontSize: 13, bold: true, color: C.white });
    cx += wds[i];
  });
  const rows = [
    ['问题改写', '3 秒', '降级为用原始问题直接检索，SSE 连接不中断', '检索精度略降，仍能得到答案', C.mist],
    ['Rerank 精排', '3 秒', '跳过精排，直接用向量检索 Top-K；done 帧携带 rerank_timeout 警告', '界面显示黄色提示，明确告知质量可能打折', 'FDF6E8'],
    ['大模型生成', '30 秒', '推送 error 事件并关闭连接', '提示重试——这是唯一不可降级的核心依赖', 'FBF2F0'],
  ];
  rows.forEach((r, i) => {
    const y = 2.33 + i * 1.15;
    cx = M.x;
    r.slice(0, 4).forEach((cell, j) => {
      s.addShape(pres.ShapeType.rect, { x: cx, y, w: wds[j], h: 1.1, fill: { color: r[4] }, line: { color: C.line, width: 1 } });
      txt(s, cell, {
        x: cx + 0.18, y: y + 0.1, w: wds[j] - 0.35, h: 0.9, valign: 'middle',
        fontSize: j === 0 ? 13.5 : 11.5, bold: j <= 1, color: j <= 1 ? C.navy : C.gray, lineSpacing: 17,
      });
      cx += wds[j];
    });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 5.95, w: 11.93, h: 1.0, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '同一个设计哲学：辅助环节的失败，不应该导致主流程的失败。', {
    x: M.x + 0.42, y: 6.12, w: 11.0, h: 0.35, fontSize: 15, bold: true, color: C.gold,
  });
  txt(s, '而且降级不是静默的——Rerank 降级时前端会显示明确提示。用户知道这次结果的质量可能打了折扣，透明比假装正常更重要。', {
    x: M.x + 0.42, y: 6.5, w: 11.0, h: 0.35, fontSize: 12, color: C.ice,
  });
  pageNo(s);
}

// =====================================================================
// P-30 数据隔离三层
// =====================================================================
{
  const s = lightSlide('安全设计', '数据隔离的三个层次');
  const lv = [
    ['物理文件隔离', '每个用户的文件存在 {上传目录}/{user_id}/ 下。落盘文件名用系统生成的 doc_id，不是用户上传的原始文件名。', '原始文件名是不可信输入。直接拼路径，一个名为 ../../etc/passwd 的文件就可能造成路径穿越。'],
    ['向量物理隔离', '每个用户在 Chroma 中拥有独立 Collection，命名 col_user_{user_id}。', '这是物理隔离，不是「查询时加个过滤条件」的逻辑隔离——后者只要有一处漏写就是跨用户泄露。'],
    ['关系库隔离', '所有查询强制附加 user_id 条件，越权访问一律返回 404 而非 403。', '403 等于告诉攻击者「资源存在，只是你没权限」，可被用来枚举文档 ID；404 让攻击者什么也得不到。'],
  ];
  lv.forEach((l, i) => {
    const y = 1.78 + i * 1.55;
    card(s, M.x, y, 11.93, 1.4);
    badge(s, M.x + 0.32, y + 0.42, String(i + 1), { d: 0.55, size: 16 });
    txt(s, l[0], { x: M.x + 1.05, y: y + 0.2, w: 2.6, h: 0.35, fontSize: 16, bold: true, color: C.navy });
    txt(s, l[1], { x: M.x + 1.05, y: y + 0.62, w: 5.4, h: 0.7, fontSize: 11.5, color: C.gray, lineSpacing: 17 });
    s.addShape(pres.ShapeType.roundRect, {
      x: M.x + 6.7, y: y + 0.2, w: 4.9, h: 1.0, rectRadius: 0.08,
      fill: { color: C.white }, line: { color: C.gold, width: 1 },
    });
    txt(s, l[2], { x: M.x + 6.88, y: y + 0.33, w: 4.6, h: 0.78, fontSize: 11, color: C.navy, lineSpacing: 17 });
  });
  txt(s, '需求文档 5.2 的要求是「API 层拦截越权查询」。我们在此基础上把向量做成了物理隔离——因为逻辑隔离依赖每一次查询都不写错，而人总会写错。', {
    x: M.x, y: 6.45, w: 11.93, h: 0.4, fontSize: 12, italic: true, color: C.gray,
  });
  pageNo(s);
}

// =====================================================================
// P-31 时序 bug 案例
// =====================================================================
{
  const s = lightSlide('技术架构 · 案例', '一个容易被忽略的时序问题');
  const flow = [
    ['现象', '一问一答两条消息，在列表里显示的顺序颠倒了——先显示回答，再显示问题。', 'FBF2F0', 'F0DAD5', C.red],
    ['根因', 'MySQL 的 DATETIME 默认只精确到秒。一问一答往往在同一秒写入，两条记录的 created_at 完全相同，排序结果不确定。而消息 ID 是随机 UUID，做次级排序键毫无意义。', C.mist, C.line, C.navy],
    ['解法', '让 ID 本身按时间单调递增：纳秒时间戳的十六进制 + 随机后缀，并用锁保证纳秒值严格单调。ORDER BY created_at, id 即可得到稳定且正确的时序——一行 DDL 都不用改。', 'F0F7F4', 'D6E8E0', C.green],
  ];
  flow.forEach((f, i) => {
    const y = 1.8 + i * 1.5;
    card(s, M.x, y, 11.93, 1.35, { fill: f[2], line: f[3] });
    s.addShape(pres.ShapeType.roundRect, {
      x: M.x + 0.3, y: y + 0.42, w: 0.95, h: 0.48, rectRadius: 0.24,
      fill: { color: f[4] }, line: { color: f[4], width: 1 },
    });
    txt(s, f[0], { x: M.x + 0.3, y: y + 0.42, w: 0.95, h: 0.48, align: 'center', valign: 'middle', fontSize: 13, bold: true, color: C.white });
    txt(s, f[1], { x: M.x + 1.5, y: y + 0.25, w: 10.1, h: 0.95, fontSize: 12.5, color: C.gray, lineSpacing: 20, valign: 'middle' });
  });
  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 6.3, w: 11.93, h: 0.72, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 },
  });
  txt(s, '很多严重的线上问题，根因都藏在这种「看起来不可能出错」的地方。而发现它的唯一方式，就是真的把系统跑起来看真实数据。', {
    x: M.x + 0.42, y: 6.3, w: 11.0, h: 0.72, valign: 'middle', fontSize: 13, bold: true, color: C.gold,
  });
  pageNo(s);
}

// =====================================================================
// P-32 测试体系
// =====================================================================
{
  const s = lightSlide('工程质量', '测试体系：77 个用例');
  s.addChart(pres.ChartType.bar, [{
    name: '用例数',
    labels: ['服务层', '管理后台', '认证', '问答', '知识库'],
    values: [30, 15, 12, 11, 9],
  }], {
    x: M.x, y: 1.8, w: 6.2, h: 3.3,
    barDir: 'bar', chartColors: [C.navy],
    showTitle: true, title: '用例分布', titleFontSize: 13, titleColor: C.navy, titleFontFace: F.cn,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 11, dataLabelColor: C.gray,
    catAxisLabelColor: C.gray, catAxisLabelFontSize: 11, catAxisLabelFontFace: F.cn,
    valAxisLabelColor: C.gray, valAxisLabelFontSize: 9,
    valGridLine: { color: C.line, size: 1 }, catGridLine: { style: 'none' },
    showLegend: false, barGapWidthPct: 50,
  });

  card(s, 7.3, 1.8, 5.33, 3.3, { fill: C.mist });
  txt(s, '一个重要的设计', { x: 7.62, y: 2.05, w: 4.7, h: 0.35, fontSize: 17, bold: true, color: C.navy });
  txt(s, '这 77 个用例不依赖任何外部服务。', {
    x: 7.62, y: 2.5, w: 4.7, h: 0.32, fontSize: 14, bold: true, color: C.gold,
  });
  bullets(s, [
    '不需要 MySQL——测试用 SQLite 临时库',
    '不需要向量库服务——Chroma 是嵌入式的',
    '不需要任何 API Key——DEV_MOCK_AI 开关把三类模型换成本地确定性实现',
  ], { x: 7.66, y: 2.95, w: 4.6, h: 1.3, fontSize: 12 });
  txt(s, '任何人克隆代码后敲一个 pytest 就能验证系统是否完好，不需要任何前置配置。这对项目的可维护性与交接价值巨大。', {
    x: 7.62, y: 4.3, w: 4.7, h: 0.7, fontSize: 12, color: C.gray, lineSpacing: 19,
  });

  card(s, M.x, 5.35, 11.93, 1.15, { fill: C.white, line: C.line });
  txt(s, 'Mock 的 Embedding 用字符 n-gram 哈希实现，特点是确定性——相同文本永远得到相同向量，相似文本的余弦相似度也接近。所以连「上传文档 → 检索 → 命中正确片段」这样的完整链路，都能在完全离线的状态下测通。', {
    x: M.x + 0.4, y: 5.58, w: 11.1, h: 0.7, fontSize: 12.5, color: C.gray, lineSpacing: 20,
  });
  pageNo(s);
}

// =====================================================================
// P-33 测试全绿 ≠ 能用
// =====================================================================
{
  const s = darkSlide();
  txt(s, '工程质量 · 关键结论', { x: M.x, y: 1.5, w: 8, h: 0.3, fontSize: 13, bold: true, color: C.gold, charSpacing: 2 });
  txt(s, '测试全绿，\n不等于系统能用', {
    x: M.x, y: 1.95, w: 8.5, h: 1.7, fontSize: 46, bold: true, color: C.white, lineSpacing: 58,
  });
  txt(s, '77 个用例全部通过的那一刻，我以为项目做完了。\n然后我做了两件事：用真实浏览器把产品完整用了一遍，用真实的大模型 API 把链路完整跑了一遍。', {
    x: M.x, y: 3.9, w: 8.3, h: 1.1, fontSize: 15, color: C.ice, lineSpacing: 26,
  });
  s.addShape(pres.ShapeType.roundRect, {
    x: 9.3, y: 1.95, w: 3.33, h: 3.0, rectRadius: 0.12,
    fill: { color: C.gold }, line: { color: C.gold, width: 1 },
  });
  txt(s, '7', { x: 9.3, y: 2.12, w: 3.33, h: 1.75, align: 'center', fontSize: 92, bold: true, color: C.ink, fontFace: F.num });
  txt(s, '个真实缺陷', { x: 9.3, y: 3.92, w: 3.33, h: 0.35, align: 'center', fontSize: 18, bold: true, color: C.ink });
  txt(s, '其中至少两个严重到\n会让用户认为产品是坏的', { x: 9.3, y: 4.32, w: 3.33, h: 0.6, align: 'center', fontSize: 12, color: '6B5410', lineSpacing: 18 });

  txt(s, '这 7 个缺陷比 77 个通过的用例更有价值——它们说明了自动化测试的边界在哪里。', {
    x: M.x, y: 5.6, w: 11.93, h: 0.4, fontSize: 15, italic: true, color: C.gold,
  });
  pageNo(s, true);
}

// =====================================================================
// P-34 第一轮：浏览器实测 3 个缺陷
// =====================================================================
{
  const s = lightSlide('工程质量 · 第一轮验证', '浏览器实测：3 个缺陷');
  const bugs = [
    ['严重', '首轮提问的回答根本不显示', '在「新对话」状态下提问，问题上去了，界面却一片空白。刷新或切换会话后回答又完整出现。', '根因：创建会话后跳转路由，触发历史消息重新拉取，把正在流式渲染的占位气泡覆盖掉了。后端行为完全正确，坏的是前端状态时序。', C.red],
    ['中等', '运行监控柱状图高度为 0', '图表区域有数字、有日期，就是没有柱子。', '根因：父容器 items-end 使各列高度塌缩为内容高度，柱体的百分比高度失去参照基准。纯 CSS 问题，只有用眼睛看才能发现。', 'C99A2E'],
    ['轻微', '控制台两个 404', '缺 favicon。', '一个专业的产品不该有控制台报错。补了内联 SVG 图标。', C.grayLight],
  ];
  bugs.forEach((b, i) => {
    const y = 1.75 + i * 1.6;
    card(s, M.x, y, 11.93, 1.45, { fill: i === 0 ? 'FBF2F0' : C.mist, line: i === 0 ? 'F0DAD5' : C.line });
    s.addShape(pres.ShapeType.roundRect, {
      x: M.x + 0.3, y: y + 0.22, w: 0.85, h: 0.42, rectRadius: 0.21,
      fill: { color: b[4] }, line: { color: b[4], width: 1 },
    });
    txt(s, b[0], { x: M.x + 0.3, y: y + 0.22, w: 0.85, h: 0.42, align: 'center', valign: 'middle', fontSize: 11, bold: true, color: C.white });
    txt(s, b[1], { x: M.x + 1.35, y: y + 0.22, w: 4.5, h: 0.4, fontSize: 15.5, bold: true, color: C.navy });
    txt(s, b[2], { x: M.x + 1.35, y: y + 0.72, w: 4.6, h: 0.6, fontSize: 11.5, color: C.gray, lineSpacing: 17 });
    txt(s, b[3], { x: M.x + 6.2, y: y + 0.25, w: 5.4, h: 1.05, fontSize: 11.5, color: C.navy, lineSpacing: 18 });
  });
  txt(s, '这三个缺陷，77 个后端测试用例一个都不可能发现——它们分别是前端状态时序、CSS 渲染和资源引用问题。', {
    x: M.x, y: 6.55, w: 11.93, h: 0.4, fontSize: 12, italic: true, color: C.gray,
  });
  pageNo(s);
}

// =====================================================================
// P-35 第二轮：真实模型联调 4 个缺陷
// =====================================================================
{
  const s = lightSlide('工程质量 · 第二轮验证', '真实大模型联调：4 个缺陷');
  const bugs = [
    ['Rerank 模型名硬编码', '按文档实现，模型名写死成 Cohere 的取值。接上硅基流动后精排从未成功——而失败被降级逻辑静默吞掉，可以潜伏很久。'],
    ['回答被截断甚至为空', '推理型模型的思考内容同样计入 max_tokens。未显式设置时用服务商默认值（常见 512），思考一长正文就被吃掉。'],
    ['并发触发限流掐断主流', '标题生成与主回答流并发，同一 Key 触发服务商并发限制，主回答流被服务端提前关闭，只输出 25 个字。'],
    ['推理模型让改写与标题必然超时', '生成 15 字标题：推理型主模型 19.9 秒，小模型 1.8 秒。3 秒与 8 秒的预算每次都超——功能没中断，但形同虚设。'],
  ];
  bugs.forEach((b, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M.x + col * 6.15, y = 1.78 + row * 2.05;
    card(s, x, y, 5.78, 1.85, { fill: i === 3 ? 'FDF6E8' : C.mist, line: i === 3 ? C.gold : C.line });
    badge(s, x + 0.3, y + 0.28, String(i + 4), { d: 0.48, size: 14, fill: i === 3 ? C.gold : C.navy, color: i === 3 ? C.navy : C.white });
    txt(s, b[0], { x: x + 0.92, y: y + 0.3, w: 4.6, h: 0.4, fontSize: 15, bold: true, color: C.navy });
    txt(s, b[1], { x: x + 0.3, y: y + 0.9, w: 5.2, h: 0.85, fontSize: 11.5, color: C.gray, lineSpacing: 18 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 5.95, w: 11.93, h: 1.0, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '缺陷 7 不是 bug，是设计缺口', { x: M.x + 0.42, y: 6.1, w: 4.5, h: 0.32, fontSize: 14, bold: true, color: C.gold });
  txt(s, '3 秒的改写预算在文档写作时是合理的，推理模型普及后就不再成立。解法：新增「辅助任务模型」配置项——主回答用大模型保证质量，改写与标题交给小模型。配置后改写 2.4 秒、标题 2.1 秒，全部成功。', {
    x: M.x + 0.42, y: 6.45, w: 11.0, h: 0.4, fontSize: 11.5, color: C.ice,
  });
  pageNo(s);
}

// =====================================================================
// P-36 三条启示
// =====================================================================
{
  const s = darkSlide();
  txt(s, '工程质量 · 方法论', { x: M.x, y: 0.55, w: 8, h: 0.3, fontSize: 13, bold: true, color: C.gold, charSpacing: 2 });
  txt(s, '这 7 个缺陷告诉我们什么', { x: M.x, y: 0.95, w: 10, h: 0.7, fontSize: 34, bold: true, color: C.white });

  const lessons = [
    ['自动化测试守护「逻辑正确」，\n守护不了「体验可用」', '缺陷 1 里后端逻辑完全正确、数据完全正确，坏的是前端状态时序；缺陷 2 是纯 CSS 渲染问题。这两类问题只能靠真的把产品用一遍来发现。'],
    ['Mock 守护「流程贯通」，\n守护不了「真实世界的复杂度」', 'Mock 的模型永远秒回、永远返回规整格式、永远不限流。而真实模型会思考 20 秒、会先吐思考内容、会限流、会截断。缺陷 4 到 7 全部只能在真实 API 上暴露。'],
    ['需求文档也会过时', '3 秒超时预算在文档写作时合理，推理模型普及后不再成立。实现者的责任不是机械照抄文档，而是在发现文档与现实脱节时，提出并落实修正方案。'],
  ];
  lessons.forEach((l, i) => {
    const x = M.x + i * 4.0;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 1.9, w: 3.75, h: 3.4, rectRadius: 0.1,
      fill: { color: C.navy }, line: { color: C.navySoft, width: 1 },
    });
    badge(s, x + 0.32, 2.18, String(i + 1), { d: 0.5, size: 14, fill: C.gold, color: C.navy });
    txt(s, l[0], { x: x + 0.32, y: 2.9, w: 3.1, h: 0.9, fontSize: 14.5, bold: true, color: C.gold, lineSpacing: 22 });
    txt(s, l[1], { x: x + 0.32, y: 3.9, w: 3.15, h: 1.25, fontSize: 11.5, color: C.ice, lineSpacing: 18 });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 5.55, w: 11.93, h: 1.05, rectRadius: 0.1,
    fill: { color: C.gold }, line: { color: C.gold, width: 1 },
  });
  txt(s, '结论：一个系统的验收标准应该是「测试通过 + 浏览器实测 + 真实依赖联调」三重验证，缺一不可。', {
    x: M.x + 0.42, y: 5.72, w: 11.0, h: 0.35, fontSize: 15, bold: true, color: C.ink,
  });
  txt(s, '为此我们把浏览器验证固化成了 npm run e2e 脚本：注册、登录、上传、问答、引用、后台、移动端共 10 个节点，全程截图。', {
    x: M.x + 0.42, y: 6.1, w: 11.0, h: 0.35, fontSize: 12, color: '6B5410',
  });
  pageNo(s, true);
}

// =====================================================================
// P-37 性能实测
// =====================================================================
{
  const s = lightSlide('性能实测', '真实链路分环节耗时');
  s.addChart(pres.ChartType.bar, [{
    name: '耗时（秒）',
    labels: ['大模型生成', '问题改写', '向量检索', '文本向量化', '标题生成', '云端精排'],
    values: [8.5, 2.4, 2.4, 2.3, 2.1, 1.9],
  }], {
    x: M.x, y: 1.8, w: 6.9, h: 3.6,
    barDir: 'bar', chartColors: [C.navy],
    showTitle: false,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 11, dataLabelColor: C.gray,
    catAxisLabelColor: C.navy, catAxisLabelFontSize: 11, catAxisLabelFontFace: F.cn,
    valAxisLabelColor: C.gray, valAxisLabelFontSize: 9,
    valGridLine: { color: C.line, size: 1 }, catGridLine: { style: 'none' },
    showLegend: false, barGapWidthPct: 40,
  });

  card(s, 7.9, 1.8, 4.73, 1.7, { fill: C.mist });
  txt(s, '使用的模型', { x: 8.2, y: 2.0, w: 4.1, h: 0.32, fontSize: 14, bold: true, color: C.navy });
  txt(s, '生成　deepseek-ai/DeepSeek-V4-Flash\n向量　Qwen/Qwen3-Embedding-8B\n精排　BAAI/bge-reranker-v2-m3\n辅助　Qwen/Qwen3-VL-8B-Instruct', {
    x: 8.2, y: 2.4, w: 4.2, h: 1.0, fontSize: 11, color: C.gray, lineSpacing: 18, fontFace: F.num,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.9, y: 3.7, w: 4.73, h: 1.7, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.navy, width: 1 }, shadow: sh(),
  });
  txt(s, '文档处理侧', { x: 8.2, y: 3.92, w: 4.1, h: 0.32, fontSize: 14, bold: true, color: C.gold });
  txt(s, '≈ 6 秒', { x: 8.2, y: 4.28, w: 4.1, h: 0.6, fontSize: 34, bold: true, color: C.white, fontFace: F.num });
  txt(s, '3 页 PDF + 1 份中文 Markdown，从上传到全部「已就绪」。远优于需求文档「100 页 30 秒」的指标。', {
    x: 8.2, y: 4.9, w: 4.2, h: 0.45, fontSize: 11, color: C.ice, lineSpacing: 16,
  });

  card(s, M.x, 5.65, 11.93, 0.95, { fill: C.white, line: C.line });
  txt(s, '所有数据来自 usage_logs 表的真实记录。系统把每一次外部调用的耗时都记了下来，管理后台随时可查——能被测量的问题，才是能被解决的问题。', {
    x: M.x + 0.4, y: 5.88, w: 11.1, h: 0.5, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-38 SLA 实话
// =====================================================================
{
  const s = lightSlide('性能实测 · 坦诚说明', '关于检索时延指标，我要说一句实话');
  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 1.75, w: 11.93, h: 1.25, rectRadius: 0.1,
    fill: { color: 'FBF2F0' }, line: { color: C.red, width: 1.5 }, shadow: sh(),
  });
  txt(s, '需求文档规定：语义检索 + 云端 Rerank 端到端应在 2 秒以内。', {
    x: M.x + 0.45, y: 1.95, w: 7.5, h: 0.4, fontSize: 15, color: C.navy,
  });
  txt(s, '当前实测：向量检索 2.4 秒 + Rerank 1.9 秒 ≈ 4.3 秒　——　这个指标目前没有达标。', {
    x: M.x + 0.45, y: 2.4, w: 11.0, h: 0.4, fontSize: 16, bold: true, color: C.red,
  });

  txt(s, '原因分析', { x: M.x, y: 3.2, w: 4, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  const causes = [
    ['网络往返是大头', '测试环境在容器内，出网经过一层代理，再到服务商还有公网往返。2.3 秒的 Embedding 调用里绝大部分是网络时间，不是计算时间。'],
    ['Embedding 走云端 API', '每次提问都要发一次 HTTP 请求。'],
    ['Rerank 同样是云端调用', '同理，受网络条件直接影响。'],
  ];
  causes.forEach((c, i) => {
    const y = 3.7 + i * 0.92;
    card(s, M.x, y, 5.78, 0.82, { fill: C.mist, shadow: false });
    badge(s, M.x + 0.25, y + 0.17, String(i + 1), { d: 0.45, size: 13 });
    txt(s, c[0], { x: M.x + 0.85, y: y + 0.08, w: 4.6, h: 0.3, fontSize: 13, bold: true, color: C.navy });
    txt(s, c[1], { x: M.x + 0.85, y: y + 0.38, w: 4.7, h: 0.4, fontSize: 10.5, color: C.gray, lineSpacing: 15 });
  });

  txt(s, '优化路径（按性价比排序）', { x: 7.15, y: 3.2, w: 5, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  const fixes = [
    ['同区域部署', '零代码改动，预计收益最大'],
    ['本地 Embedding 模型', '需要 GPU，可把向量化压到毫秒级'],
    ['查询向量缓存', '重复或相似问题直接命中'],
    ['Top-N 调优', '20 降到 10，减少 Rerank 输入量'],
  ];
  fixes.forEach((f, i) => {
    const y = 3.7 + i * 0.68;
    card(s, 7.15, y, 5.48, 0.58, { fill: C.white, line: C.line, shadow: false });
    badge(s, 7.35, y + 0.09, String(i + 1), { d: 0.4, size: 12, fill: C.gold, color: C.navy });
    txt(s, f[0], { x: 7.88, y, w: 2.0, h: 0.58, valign: 'middle', fontSize: 12.5, bold: true, color: C.navy });
    txt(s, f[1], { x: 9.9, y, w: 2.6, h: 0.58, valign: 'middle', fontSize: 10.5, color: C.gray });
  });
  txt(s, '如实说明比粉饰过去更重要。这个数字是可测量、可归因、可优化的。', {
    x: M.x, y: 6.5, w: 11.93, h: 0.4, fontSize: 13, italic: true, bold: true, color: C.gold,
  });
  pageNo(s);
}

// =====================================================================
// P-39 并发能力
// =====================================================================
{
  const s = lightSlide('性能实测', '并发能力与部署');
  const arch = [
    ['文档解析线程池', '默认 4 个 worker，可配置。解析不阻塞问答。'],
    ['SSE 流式连接', '每个连接占用一个线程，FastAPI 自动调度。'],
    ['数据库连接池', '默认 10 个连接，最大溢出 20，开启预检与回收。'],
  ];
  arch.forEach((a, i) => {
    const x = M.x + i * 4.0;
    card(s, x, 1.8, 3.75, 1.5);
    badge(s, x + 0.3, 2.05, String(i + 1), { d: 0.45, size: 13 });
    txt(s, a[0], { x: x + 0.9, y: 2.08, w: 2.7, h: 0.32, fontSize: 14, bold: true, color: C.navy });
    txt(s, a[1], { x: x + 0.3, y: 2.65, w: 3.2, h: 0.55, fontSize: 11.5, color: C.gray, lineSpacing: 17 });
  });

  card(s, M.x, 3.55, 5.78, 2.6, { fill: C.mist });
  txt(s, '生产部署建议', { x: M.x + 0.38, y: 3.78, w: 5.0, h: 0.35, fontSize: 16, bold: true, color: C.navy });
  bullets(s, [
    'Gunicorn 启动 4 个 Uvicorn worker',
    'Nginx 反向代理，client_max_body_size 60m',
    '--timeout 必须大于 LLM_TIMEOUT，否则长回答会被 worker 提前中断',
    '全站 HTTPS，含 API 调用与流式推送',
  ], { x: M.x + 0.42, y: 4.25, w: 5.1, h: 1.7, fontSize: 12 });

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.15, y: 3.55, w: 5.48, h: 2.6, rectRadius: 0.1,
    fill: { color: 'FBF2F0' }, line: { color: C.red, width: 1 }, shadow: sh(),
  });
  txt(s, '一个必须注意的坑', { x: 7.5, y: 3.78, w: 4.8, h: 0.35, fontSize: 16, bold: true, color: C.red });
  txt(s, 'Nginx 必须关闭对 /api/ 的缓冲：', { x: 7.5, y: 4.25, w: 4.8, h: 0.32, fontSize: 12.5, color: C.navy });
  s.addShape(pres.ShapeType.roundRect, {
    x: 7.5, y: 4.6, w: 4.78, h: 0.45, rectRadius: 0.06, fill: { color: C.ink }, line: { color: C.ink, width: 1 },
  });
  txt(s, 'proxy_buffering off;', {
    x: 7.62, y: 4.6, w: 4.5, h: 0.45, valign: 'middle', fontSize: 12, color: C.gold, fontFace: 'Courier New',
  });
  txt(s, '否则 SSE 的增量文本会被 Nginx 攒着不发，流式效果完全失效——用户会等很久，然后一次性看到全部文字。这个坑我们在部署文档里写清楚了。', {
    x: 7.5, y: 5.2, w: 4.8, h: 0.85, fontSize: 11.5, color: C.gray, lineSpacing: 18,
  });
  pageNo(s);
}

// =====================================================================
// P-40 演示脚本
// =====================================================================
{
  const s = lightSlide('现场演示', '八分钟演示脚本');
  const demo = [
    ['注册与登录', '30 秒', '故意输入不支持的邮箱后缀，展示明确的中文校验提示'],
    ['上传文献', '1 分钟', '拖入 3 页英文 PDF + 中文 Markdown，观察状态流转到「已就绪」'],
    ['第一次提问', '2 分钟', '文字逐字出现、侧边栏标题自动生成、回答中出现可点击角标'],
    ['验证溯源', '1 分钟', '点击引用卡片，弹窗显示原文并标注「第 2 页」，对照 PDF 核实'],
    ['多轮追问', '1.5 分钟', '问「那它在机器翻译上成绩如何」，验证代词被正确解析'],
    ['中文文档引用', '1 分钟', '引用标注为「第 1 个片段」而非页码——Markdown 没有页码'],
    ['管理后台', '1.5 分钟', '用户管理、配置脱敏掩码、运行监控的真实调用数据'],
    ['响应式', '30 秒', '拖窄窗口，布局自动切换为移动端抽屉式导航'],
  ];
  demo.forEach((d, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M.x + col * 6.15, y = 1.78 + row * 1.2;
    card(s, x, y, 5.78, 1.05, { fill: C.mist, shadow: false });
    badge(s, x + 0.25, y + 0.28, String(i + 1), { d: 0.48, size: 14 });
    txt(s, d[0], { x: x + 0.85, y: y + 0.14, w: 2.6, h: 0.32, fontSize: 14.5, bold: true, color: C.navy });
    txt(s, d[1], { x: x + 3.5, y: y + 0.16, w: 2.0, h: 0.28, align: 'right', fontSize: 11, color: C.gold, bold: true });
    txt(s, d[2], { x: x + 0.85, y: y + 0.5, w: 4.7, h: 0.45, fontSize: 11, color: C.gray, lineSpacing: 16 });
  });
  pageNo(s);
  s.addNotes('演示前务必确认：后端与前端服务已启动、模型配置已保存、预置账号可用。');
}

// =====================================================================
// P-41 应急预案
// =====================================================================
{
  const s = lightSlide('现场演示', '演示应急预案');
  const plans = [
    ['网络不通 / API 超时', '切换到离线 Mock 模式（DEV_MOCK_AI=true），全链路依然可完整演示，只是回答内容是模板。提前准备好录屏作为最后兜底。'],
    ['上传后长时间不就绪', '说明 Embedding API 异常。直接切到预置账号，里面有提前上传好并已就绪的文档。'],
    ['回答生成很慢', '这是真实情况，不要慌。顺势讲解流式输出的价值，以及运行监控里能看到的耗时分布。'],
    ['被问到不会的问题', '诚实回答「这一点我们还没有验证，会后补充数据给您」。不要编造——这和产品本身的价值观是一致的。'],
  ];
  plans.forEach((p, i) => {
    const y = 1.8 + i * 1.25;
    card(s, M.x, y, 11.93, 1.1, { fill: i === 3 ? 'FDF6E8' : C.mist, line: i === 3 ? C.gold : C.line });
    s.addShape(pres.ShapeType.roundRect, {
      x: M.x + 0.3, y: y + 0.3, w: 2.85, h: 0.5, rectRadius: 0.25,
      fill: { color: i === 3 ? C.gold : C.navy }, line: { color: i === 3 ? C.gold : C.navy, width: 1 },
    });
    txt(s, p[0], { x: M.x + 0.3, y: y + 0.3, w: 2.85, h: 0.5, align: 'center', valign: 'middle', fontSize: 12, bold: true, color: i === 3 ? C.navy : C.white });
    txt(s, p[1], { x: M.x + 3.4, y: y + 0.2, w: 8.2, h: 0.75, valign: 'middle', fontSize: 12, color: C.gray, lineSpacing: 19 });
  });
  txt(s, '本页为讲者备忘，现场不展示。', { x: M.x, y: 6.85, w: 6, h: 0.3, fontSize: 10, italic: true, color: C.grayLight });
  pageNo(s);
}

// =====================================================================
// P-42 三重价值
// =====================================================================
{
  const s = lightSlide('项目价值', '三重价值');
  const vals = [
    ['直接的使用价值', '对研究者而言，它把「读几十篇文献找一句话」压缩成「问一句话，拿到带出处的答案」。而且因为可溯源，这个答案是可验证的，可以直接用于学术工作。'],
    ['架构的可迁移价值', '这套架构不是学术专用的。知识库换成企业文档，它就是企业知识管理；换成法律条文和判例，它就是法律检索助手；换成产品手册和工单，它就是智能客服。'],
    ['工程方法论的价值', '最值得沉淀的可能不是代码，而是「自动化测试 + 浏览器实测 + 真实依赖联调」的三重验证方法，以及 7 个缺陷背后的教训——它们对任何要交付到生产的 AI 系统都适用。'],
  ];
  vals.forEach((v, i) => {
    const x = M.x + i * 4.0;
    card(s, x, 1.8, 3.75, 3.9, { fill: i === 2 ? 'FDF6E8' : C.mist, line: i === 2 ? C.gold : C.line });
    badge(s, x + 0.32, 2.1, String(i + 1), { d: 0.58, size: 17, fill: i === 2 ? C.gold : C.navy, color: i === 2 ? C.navy : C.white });
    txt(s, v[0], { x: x + 0.32, y: 2.92, w: 3.1, h: 0.4, fontSize: 17, bold: true, color: C.navy });
    txt(s, v[1], { x: x + 0.32, y: 3.5, w: 3.15, h: 1.95, fontSize: 12, color: C.gray, lineSpacing: 20 });
  });
  txt(s, '因为做了模型层与向量库层的抽象，迁移成本非常低。', {
    x: M.x, y: 5.9, w: 11.93, h: 0.4, fontSize: 13, italic: true, color: C.gray,
  });
  pageNo(s);
}

// =====================================================================
// P-43 后续规划
// =====================================================================
{
  const s = lightSlide('后续规划', '三个阶段的演进路线');
  const phases = [
    ['短期', '1–2 个月', ['性能优化，把检索链路压到 2 秒以内', '补齐前端自动化测试', '支持 PPTX、HTML、EPUB 格式'], C.navy],
    ['中期', '3–6 个月', ['混合检索：向量 + BM25 融合', '知识库分组，按课题指定检索范围', '多模态：利用论文中的图表信息'], C.navySoft],
    ['长期', '6 个月以上', ['引用图谱：文献引用关系可视化', '协作知识库：课题组共享 + 细粒度权限', '私有化部署：数据不出内网'], C.gray],
  ];
  phases.forEach((p, i) => {
    const x = M.x + i * 4.0;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 1.8, w: 3.75, h: 0.75, rectRadius: 0.08,
      fill: { color: p[3] }, line: { color: p[3], width: 1 },
    });
    txt(s, p[0], { x: x + 0.3, y: 1.8, w: 1.5, h: 0.75, valign: 'middle', fontSize: 18, bold: true, color: C.white });
    txt(s, p[1], { x: x + 1.8, y: 1.8, w: 1.7, h: 0.75, valign: 'middle', align: 'right', fontSize: 12, color: C.ice });
    card(s, x, 2.65, 3.75, 2.9, { fill: C.mist, shadow: false });
    p[2].forEach((t, j) => {
      const y = 2.9 + j * 0.85;
      badge(s, x + 0.3, y + 0.05, String(j + 1), { d: 0.36, size: 11, fill: C.white, color: C.navy });
      txt(s, t, { x: x + 0.78, y: y - 0.02, w: 2.75, h: 0.7, fontSize: 11.5, color: C.gray, lineSpacing: 17 });
    });
  });
  card(s, M.x, 5.8, 11.93, 0.85, { fill: 'F0F7F4', line: 'D6E8E0' });
  txt(s, '混合检索是优先级最高的一项：纯向量检索对精确匹配（具体数字、人名、专有名词）不敏感，融合 BM25 关键词检索能补上这个短板。', {
    x: M.x + 0.4, y: 6.0, w: 11.1, h: 0.5, fontSize: 12.5, color: C.gray, lineSpacing: 19,
  });
  pageNo(s);
}

// =====================================================================
// P-44 结语
// =====================================================================
{
  const s = darkSlide();
  txt(s, '结语', { x: M.x, y: 1.3, w: 8, h: 0.3, fontSize: 13, bold: true, color: C.gold, charSpacing: 2 });
  txt(s, '把时间还给\n真正需要人做的事', {
    x: M.x, y: 1.75, w: 9.5, h: 1.7, fontSize: 44, bold: true, color: C.white, lineSpacing: 56,
  });
  txt(s, '我们没有办法让研究者不读文献——理解和思考的工作，机器替代不了，也不该替代。', {
    x: M.x, y: 3.65, w: 9.3, h: 0.4, fontSize: 15, color: C.ice,
  });
  txt(s, '但我们可以把「在几十篇 PDF 里找那一句话」这件事，从两个星期压缩到几秒钟。\n把节省下来的时间，还给理解、质疑与创新。', {
    x: M.x, y: 4.15, w: 9.3, h: 0.85, fontSize: 15, color: C.ice, lineSpacing: 26,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: M.x, y: 5.25, w: 11.93, h: 1.0, rectRadius: 0.1,
    fill: { color: C.navy }, line: { color: C.gold, width: 1 },
  });
  txt(s, '这个系统的每一行代码、每一个数字，都可以现场验证。', {
    x: M.x + 0.42, y: 5.42, w: 11.0, h: 0.35, fontSize: 15, bold: true, color: C.gold,
  });
  txt(s, '77 个测试用例可以当场跑，端到端脚本可以当场跑，真实问答可以当场演示，监控数据可以当场调出来。', {
    x: M.x + 0.42, y: 5.8, w: 11.0, h: 0.35, fontSize: 12.5, color: C.ice,
  });
  txt(s, '谢　谢', { x: M.x, y: 6.5, w: 4, h: 0.5, fontSize: 22, bold: true, color: C.white, charSpacing: 8 });
  pageNo(s, true);
  s.addNotes('放慢语速。说完「谢谢」后鞠躬，等掌声结束再进入问答环节。');
}

pres.writeFile({ fileName: '产品演示.pptx' }).then(() => {
  console.log(`✔ 已生成 产品演示.pptx，共 ${P.count} 页`);
});
