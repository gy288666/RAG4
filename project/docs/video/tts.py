"""调用硅基流动 CosyVoice2 逐段合成中文旁白，并测量每段时长。"""
import json
import os
import pathlib
import re
import subprocess
import sys

import httpx

HERE = pathlib.Path(__file__).parent
OUT = HERE / "audio"
OUT.mkdir(exist_ok=True)
FFMPEG = os.environ.get("FFMPEG", "/opt/pw-browsers/ffmpeg-1011/ffmpeg-linux")
KEY = os.environ["SF_KEY"]
MODEL = "FunAudioLLM/CosyVoice2-0.5B"
VOICE = f"{MODEL}:alex"


def duration(path: pathlib.Path) -> float:
    """用 ffmpeg 读取音频时长（该构建不含 ffprobe）。"""
    proc = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not m:
        raise RuntimeError(f"无法读取时长: {path}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def main():
    segments = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    result = []
    total = 0.0

    with httpx.Client(timeout=180) as client:
        for i, seg in enumerate(segments, 1):
            mp3 = OUT / f"{seg['id']}.mp3"
            if not mp3.exists():
                resp = client.post(
                    "https://api.siliconflow.cn/v1/audio/speech",
                    headers={"Authorization": f"Bearer {KEY}"},
                    json={
                        "model": MODEL,
                        "voice": VOICE,
                        "input": seg["text"],
                        "response_format": "mp3",
                        "speed": 1.0,
                        "gain": 0,
                    },
                )
                if resp.status_code != 200:
                    print(f"✖ 第 {i} 段合成失败 HTTP {resp.status_code}: {resp.text[:200]}")
                    sys.exit(1)
                mp3.write_bytes(resp.content)

            d = duration(mp3)
            total += d
            result.append({"id": seg["id"], "cap": seg["cap"], "dur": round(d, 2)})
            print(f"  [{i:02d}/{len(segments)}] {seg['id']:<18} {d:6.2f}s  {seg['cap']}")

    (HERE / "durations.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\n合计旁白时长：{total:.1f} 秒 ≈ {total/60:.1f} 分钟")


if __name__ == "__main__":
    main()
