# 产品演示视频 — 生成说明

本目录存放演示视频的**可复现生成脚本**。视频成品（约 5.6 MB）未纳入版本库，
按下方步骤可随时重新生成——改了界面或想换旁白，重跑一遍即可，不需要手工剪辑。

## 成品规格

| 项目 | 值 |
|------|-----|
| 时长 | 4 分 07 秒 |
| 分辨率 | 1280×720，25 fps |
| 编码 | H.264 (High) + AAC 单声道 128 kbps |
| 旁白 | 中文，硅基流动 CosyVoice2 合成 |
| 内容 | 15 个段落，全程真实模型、真实数据，无摆拍 |

## 依赖

```bash
pip install httpx imageio-ffmpeg pillow      # TTS 调用、完整版 ffmpeg、拼图
cd frontend && npm install -D playwright     # 浏览器驱动（项目已装）
```

> 注意：Playwright 自带的 ffmpeg 是 `--disable-everything` 的精简构建，
> 只能编码 VP8/webm，**不能解 mp3、不能出 mp4**。所以必须另装 `imageio-ffmpeg`
> 提供的完整静态构建。

## 生成步骤

### 0. 准备演示环境

后端与前端都要跑起来，并且**接入真实模型**（Mock 模式下回答是模板，不适合演示）：

```bash
# 后端（建议用干净的库，避免历史数据让画面显得杂乱）
cd backend
rm -rf data/video && mkdir -p data/video
DATABASE_URL="sqlite:///./data/video/app.db" \
UPLOAD_DIR="./data/video/uploads" CHROMA_DIR="./data/video/chroma" \
DEV_MOCK_AI=false SECRET_KEY="<随机长字符串>" \
.venv/bin/uvicorn app.main:app --port 8000

# 前端
cd frontend && npm run dev
```

然后用管理员账号登录后台，在「系统配置」里填好大模型、辅助任务模型、
Embedding、Rerank 四项（取值见项目 README 的实测配置表）。

### 1. 合成旁白

```bash
cd docs/video
export SF_KEY="<你的 API Key>"
export FFMPEG=$(python3 -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())")
python3 tts.py
```

逐段合成 `audio/*.mp3` 并写出 `durations.json`（每段时长）。
已存在的 mp3 会跳过，改了某段文案只需删掉对应文件重跑。

### 2. 录制画面

```bash
export CHROMIUM_PATH=/path/to/chromium        # 容器环境需要；本机装了浏览器可省略
MODE=desktop node record.mjs && mv raw raw_desktop
MODE=mobile  node record.mjs && mv raw raw_mobile
```

- **桌面段**（1280×720）：第 1–13 段与片尾第 15 段
- **移动段**（430×760）：第 14 段，单独录制后在合成阶段居中裱到深色底上

  之所以分开录，是因为 Playwright 的录制画布在创建上下文时就固定了，
  中途改视口只会让画面右侧留下大片灰色。

两次录制各自写出 `timeline_<mode>.json`，记录每段的**实际画面时长**。

### 3. 合成

```bash
python3 assemble.py
```

产出 `RAG学术知识引擎-产品演示.mp4`。

## 几个关键设计

**音轨按实际画面时长对齐。** 真实大模型的生成耗时每次都不一样——同一段追问，
实测在 19 秒到 42 秒之间波动。若按旁白时长硬拼音轨，后半段会整体错位。
所以录制时记录每段真实耗时，合成时按差值补静音。

**段内剪辑。** 如果某段等待过长（比如模型生成了 40 秒），在 `assemble.py`
的 `TRIMS` 里配置从该段第几秒起剪掉多少秒即可，脚本会同步修正音轨对齐：

```python
TRIMS = [{"id": "10_multiturn", "at": 16.5, "cut": 15.0}]
```

**前导偏移。** `PREROLL = 1.15` 是录制开始到第一段字幕出现的时间。
若改动了片头逻辑，用抽帧法重新测一下字幕切换点即可校准。

## 目录说明

| 文件 | 作用 |
|------|------|
| `narration.json` | 15 段旁白文案与字幕标题，改文案只动这里 |
| `tts.py` | 调用 CosyVoice2 合成语音，测量每段时长 |
| `record.mjs` | Playwright 录屏，注入中文字幕条，按旁白时长控制节奏 |
| `assemble.py` | 拼接画面、补静音对齐音轨、混流出 mp4 |
| `audio/` `raw_*/` `work/` | 中间产物，已在 .gitignore 中忽略 |
