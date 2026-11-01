"""Cut the raw demo take to the narration: one scene per narration paragraph, zoomed on the
action, with captions and a closing title card.

    python server/edit_demo.py --take .local/take --voice .local/voiceover2.wav --out docs/media/demo
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
_BIN = ROOT / ".local" / "bin" / "ffmpeg.exe"
FFMPEG = str(_BIN) if _BIN.exists() else "ffmpeg"
W, H, FPS = 1920, 1080, 30
FONTS = Path("C:/Windows/Fonts")
SANS = str(FONTS / "segoeui.ttf")
SERIF_ITALIC = str(FONTS / "georgiai.ttf")

# scene name -> (event that starts it, event that ends it, how to fit it to the narration)
SCENES = [
    ("altar", "altar", "gallery", "trim"),
    ("gallery", "gallery", "place", "fit"),
    ("place", "place", "working", "fit"),
    ("working", "working", "return", "fit"),
    ("return", "return", "credit", "trim"),
    ("credit", "credit", "candle", "trim"),
    ("candle", "candle", "end", "trim"),
]
# how much room to leave around each scene's element when zooming (1 = tight)
MARGIN = {"altar": 1.15, "gallery": 1.05, "place": 1.08, "working": 1.6, "return": 1.15, "credit": 2.4, "candle": 1.15}


def ff(*args):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *map(str, args)], check=True)


def speech_paragraphs(voice: Path, gap=0.9):
    """Speech intervals separated by pauses longer than `gap` seconds (the 1.2 s breaks)."""
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(voice), "-af", f"silencedetect=noise=-42dB:d={gap}",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    total = float(re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).groups()[2]) + \
        60 * float(re.search(r"Duration: (\d+):(\d+):([\d.]+)", out).groups()[1])
    speech, cursor = [], 0.0
    for s, e in zip(starts, ends + [total]):
        if s > cursor + 0.05:
            speech.append([cursor, s])
        cursor = e
    if cursor < total - 0.05:
        speech.append([cursor, total])
    return speech


def crop_for(box, margin):
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    cw = max(w * margin, h * margin * 16 / 9, 760)
    cw = min(cw, W)
    ch = cw * 9 / 16
    left = min(max(cx - cw / 2, 0), W - cw)
    top = min(max(cy - ch / 2, 0), H - ch)
    return [round(v) // 2 * 2 for v in (cw, ch, left, top)]


def caption(text: str, path: Path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(SANS, 40)
    words, lines, line = text.split(), [], ""
    for wd in words:
        trial = f"{line} {wd}".strip()
        if d.textlength(trial, font=font) > 1300 and line:
            lines.append(line)
            line = wd
        else:
            line = trial
    lines.append(line)
    lh = 56
    bh = lh * len(lines) + 36
    bw = max(d.textlength(l, font=font) for l in lines) + 72
    x0, y0 = (W - bw) / 2, H - bh - 64
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=18, fill=(8, 9, 13, 190))
    for i, l in enumerate(lines):
        tw = d.textlength(l, font=font)
        d.text(((W - tw) / 2, y0 + 18 + i * lh), l, font=font, fill=(240, 236, 228, 255))
    img.save(path)


def end_card(path: Path):
    img = Image.new("RGB", (W, H), (11, 13, 18))
    d = ImageDraw.Draw(img)
    glow = Image.new("RGB", (W, H), (11, 13, 18))
    gd = ImageDraw.Draw(glow)
    for r in range(520, 0, -8):  # soft candlelight behind the title
        a = (520 - r) / 520
        gd.ellipse([W / 2 - r * 1.5, H / 2 - 40 - r, W / 2 + r * 1.5, H / 2 - 40 + r],
                   fill=(int(11 + 30 * a), int(13 + 18 * a), int(18 + 4 * a)))
    img = Image.blend(img, glow, 1.0)
    d = ImageDraw.Draw(img)
    title = ImageFont.truetype(SERIF_ITALIC, 112)
    sub = ImageFont.truetype(SANS, 44)
    small = ImageFont.truetype(SANS, 32)
    for text, font, y, fill in [
        ("Living Portraits", title, 360, (240, 200, 140)),
        ("Bring them back to the altar.", sub, 520, (236, 232, 225)),
        ("Open-source models on a DigitalOcean Droplet", small, 640, (167, 161, 150)),
        ("http://139.59.7.49    github.com/Tanhaker/living-portraits", small, 690, (167, 161, 150)),
    ]:
        tw = d.textlength(text, font=font)
        d.text(((W - tw) / 2, y), text, font=font, fill=fill)
    img.save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--take", type=Path, default=ROOT / ".local" / "take")
    ap.add_argument("--voice", type=Path, required=True)
    ap.add_argument("--script", type=Path, default=ROOT / "docs" / "voiceover-script.md")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "media" / "demo")
    ap.add_argument("--starts", help="comma-separated paragraph start times, then the end of the last word")
    args = ap.parse_args()

    take = json.loads(args.take.with_suffix(".json").read_text())
    ev = {e["name"]: e for e in take["events"]}
    raw = args.take.with_suffix(".mp4")

    # Narration text per scene, from the table in the script.
    texts = [re.split(r"\s*\|\s*", row.strip("| "))[2] for row in args.script.read_text(encoding="utf-8").splitlines()
             if re.match(r"\| \d\.", row)]
    if args.starts:  # when a sentence pause is as long as a paragraph break, give the starts explicitly
        t = [float(x) for x in args.starts.split(",")]
        paras = [[a, b] for a, b in zip(t, t[1:])]
    else:
        paras = speech_paragraphs(args.voice)
    if len(paras) != len(texts):
        raise SystemExit(f"found {len(paras)} spoken paragraphs, expected {len(texts)}: {paras}")

    lead = 0.6  # silence before the first word
    audio_start = paras[0][0] - lead
    bounds = [0.0] + [p[0] - audio_start - 0.35 for p in paras[1:]] + [paras[-1][1] - audio_start + 1.8]
    durations = [b - a for a, b in zip(bounds, bounds[1:])]
    print("scene durations:", [round(d, 2) for d in durations])

    tmp = Path(tempfile.mkdtemp())
    parts = []
    for i, (name, start_ev, end_ev, mode) in enumerate(SCENES):
        a, b = ev[start_ev]["t"], ev[end_ev]["t"]
        length, target = b - a, durations[i]
        speed = 1.0
        if mode == "fit" or length < target:
            speed = max(0.6, min(length / target, 3.0))
        # the altar is still scrolling into view when the Return starts; use where it settles
        where = ev["candle"]["box"] if name == "return" else ev[start_ev]["box"]
        cw, ch, left, top = crop_for(where, MARGIN[name])
        cap = tmp / f"cap{i}.png"
        caption(texts[i], cap)
        fade_in = 0.6 if i == 0 else 0.25
        vf = (f"[0:v]trim={a:.3f}:{a + target * speed + 0.1:.3f},setpts=(PTS-STARTPTS)/{speed:.4f},"
              f"crop={cw}:{ch}:{left}:{top},scale={W}:{H}:flags=lanczos,"
              f"tpad=stop_mode=clone:stop_duration={target:.3f},trim=0:{target:.3f},fps={FPS},"
              f"fade=t=in:st=0:d={fade_in},fade=t=out:st={target - 0.25:.3f}:d=0.25[v];"
              f"[v][1:v]overlay=0:0[out]")
        part = tmp / f"part{i}.mp4"
        ff("-i", raw, "-loop", "1", "-i", cap, "-filter_complex", vf, "-map", "[out]", "-t", f"{target:.3f}",
           "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", FPS, part)
        parts.append(part)
        print(f"scene {i + 1} {name}: raw {length:.1f}s -> {target:.1f}s (speed {speed:.2f})")

    card = tmp / "card.png"
    end_card(card)
    last = durations[-1]
    part = tmp / "part_end.mp4"
    ff("-loop", "1", "-i", card, "-vf", f"fps={FPS},fade=t=in:st=0:d=0.5,fade=t=out:st={last - 1.0:.3f}:d=1.0",
       "-t", f"{last:.3f}", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", part)
    parts.append(part)

    (tmp / "parts.txt").write_text("\n".join(f"file '{p.as_posix()}'" for p in parts))
    silent = tmp / "silent.mp4"
    ff("-f", "concat", "-safe", "0", "-i", tmp / "parts.txt", "-c", "copy", silent)
    total = sum(durations)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    final = args.out.with_suffix(".mp4")
    ff("-i", silent, "-ss", f"{audio_start:.3f}", "-i", args.voice,
       "-filter_complex", f"[1:a]atrim=0:{total:.3f},afade=t=out:st={total - 1.2:.3f}:d=1.2,loudnorm=I=-16:TP=-1.5[a]",
       "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final)
    shutil.rmtree(tmp)
    print(f"{total:.1f}s -> {final}")


if __name__ == "__main__":
    main()
