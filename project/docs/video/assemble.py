"""合成最终视频。

三件事：
1. 桌面段（1280×720）与移动段（430×760，居中裱在深色底上）统一编码后拼接；
2. 音轨按**画面实际时长**逐段补静音——真实模型生成耗时不定，段落画面常长于旁白，
   若按旁白时长硬拼，后半段口型与画面会整体错位；
3. 混流为 H.264 + AAC 的 mp4。
"""
import json
import pathlib
import subprocess
import sys

import imageio_ffmpeg

HERE = pathlib.Path(__file__).parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1280, 720
BG = "0x12193F"
PREROLL = 1.15  # 录制开始到第 01 段字幕出现的前导时长

# 移动段在整体顺序中的位置：桌面段的 13_admin_stats 之后、15_outro 之前
MOBILE_ID = "14_mobile"

# 段内剪辑：真实模型生成耗时不定，多轮追问那段等待过长（画面 42s / 旁白 19s），
# 从生成过程中间剪掉一截，保留"逐字流式输出"的观感即可。
TRIMS = []  # 本轮各段耗时正常，无需剪辑


def run(args, **kw):
    proc = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error"] + args,
                          capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        print("ffmpeg 失败：", " ".join(args)[:200])
        print(proc.stderr[-1500:])
        sys.exit(1)


def only(pattern):
    files = sorted(HERE.glob(pattern))
    if not files:
        sys.exit(f"未找到 {pattern}")
    return files[0]


def probe_duration(path):
    proc = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True)
    import re
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def main():
    desktop = only("raw_desktop/*.webm")
    mobile = only("raw_mobile/*.webm")
    tl_desktop = json.loads((HERE / "timeline_desktop.json").read_text(encoding="utf-8"))
    tl_mobile = json.loads((HERE / "timeline_mobile.json").read_text(encoding="utf-8"))
    mobile_actual = tl_mobile[0]["actual"]

    work = HERE / "work"
    work.mkdir(exist_ok=True)

    # ---------- 1. 切分桌面段：13 之前 / 15 片尾 ----------
    outro = next(e for e in tl_desktop if e["id"] == "15_outro")
    cut = PREROLL + outro["start"]           # 片尾开始的绝对时刻
    print(f"桌面段总长 {probe_duration(desktop):.1f}s，片尾起点 {cut:.2f}s")

    # 主体段按 TRIMS 拆成若干片再拼，跳过冗长的等待
    keep, pos = [], 0.0
    for tr in TRIMS:
        e = next(x for x in tl_desktop if x["id"] == tr["id"])
        a = PREROLL + e["start"] + tr["at"]
        keep.append((pos, a))
        pos = a + tr["cut"]
        e["actual"] -= tr["cut"]
        print(f"  剪掉 {tr['id']} 内 {a:.1f}s–{pos:.1f}s 共 {tr['cut']:.0f}s")
    keep.append((pos, cut))

    main_parts = []
    for i, (a, b) in enumerate(keep):
        name = f"a_main{i}.mp4"
        print(f"→ 编码主体片段 {i + 1}/{len(keep)}（{a:.1f}s–{b:.1f}s）…")
        run(["-ss", f"{a:.3f}", "-i", str(desktop), "-t", f"{b - a:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "22",
             "-pix_fmt", "yuv420p", "-r", "25", "-an", str(work / name)])
        main_parts.append(name)

    print("→ 编码片尾段…")
    run(["-ss", f"{cut:.3f}", "-i", str(desktop), "-t", f"{outro['actual']:.3f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "22",
         "-pix_fmt", "yuv420p", "-r", "25", "-an", str(work / "c_outro.mp4")])

    # ---------- 2. 移动段：等比缩放后居中裱底 ----------
    print("→ 编码移动段（居中裱底）…")
    run(["-i", str(mobile), "-t", f"{mobile_actual:.3f}",
         "-vf", f"scale=-2:{H-40},pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:{BG}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "22",
         "-pix_fmt", "yuv420p", "-r", "25", "-an", str(work / "b_mobile.mp4")])

    # ---------- 3. 拼接三段 ----------
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{work / n}'\n" for n in
                           main_parts + ["b_mobile.mp4", "c_outro.mp4"]), encoding="utf-8")
    print("→ 拼接视频…")
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(work / "video.mp4")])

    # ---------- 4. 按画面实际时长铺音轨 ----------
    order = [e for e in tl_desktop if e["id"] != "15_outro"]
    order.append({"id": MOBILE_ID, "actual": mobile_actual,
                  "narration": tl_mobile[0]["narration"]})
    order.append(outro)

    parts = []
    for i, e in enumerate(order):
        parts.append(f"file '{HERE / 'audio' / (e['id'] + '.mp3')}'")
        gap = e["actual"] - e["narration"]
        if gap > 0.05:
            sil = work / f"sil_{i:02d}.mp3"
            run(["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                 "-t", f"{gap:.3f}", "-c:a", "libmp3lame", "-q:a", "5", str(sil)])
            parts.append(f"file '{sil}'")
        print(f"   {e['id']:<18} 旁白 {e['narration']:5.1f}s + 静音 {max(0, gap):5.1f}s = {e['actual']:5.1f}s")

    alist = work / "audio_concat.txt"
    alist.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print("→ 拼接音轨…")
    run(["-f", "concat", "-safe", "0", "-i", str(alist),
         "-c:a", "libmp3lame", "-q:a", "2", str(work / "track.mp3")])

    # ---------- 5. 混流 ----------
    out = HERE / "RAG学术知识引擎-产品演示.mp4"
    print("→ 混流输出…")
    run(["-i", str(work / "video.mp4"), "-itsoffset", f"{PREROLL}", "-i", str(work / "track.mp3"),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ac", "1",
         "-movflags", "+faststart", "-shortest", str(out)])

    print(f"\n✔ {out.name}  时长 {probe_duration(out):.1f}s  "
          f"大小 {out.stat().st_size/1048576:.1f} MB")


if __name__ == "__main__":
    main()
