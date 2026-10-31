"""Render "The Return" as a GIF and MP4 for posts and READMEs.

Uses the same maths as the page's WebGL shader (web/portrait.js), so the video matches
what visitors see. Works from a result folder (before.jpg, final.jpg, depth.png).

    python server/render_return.py .local/results/Kasturba_Gandhi --face 0.5,0.33 --out docs/kasturba
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

_BIN = Path(__file__).resolve().parent.parent / ".local" / "bin"
FFMPEG = str(_BIN / "ffmpeg.exe") if (_BIN / "ffmpeg.exe").exists() else "ffmpeg"


def ease(t):
    t = np.clip(t, 0, 1)
    return 1 - (1 - t) ** 3


def span(t, a, b):
    return float(ease((t - a) / (b - a)))


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--face", default="0.5,0.35", help="face centre x,y as fractions")
    ap.add_argument("--out", type=Path, required=True, help="output path without extension")
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--seconds", type=float, default=9.0)
    ap.add_argument("--fps", type=int, default=15)
    args = ap.parse_args()

    load = lambda name, flag=cv2.IMREAD_COLOR: cv2.imread(str(args.folder / name), flag)
    final = load("final.jpg")
    h0, w0 = final.shape[:2]
    w = args.width
    h = round(h0 * w / w0) // 2 * 2
    rs = lambda img: cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    after, before = rs(final), rs(load("before.jpg"))
    depth = rs(load("depth.png", cv2.IMREAD_GRAYSCALE))
    fx, fy = map(float, args.face.split(","))
    aspect = w / h

    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    u0 = ((xs + 0.5) / w - 0.5) * 0.95 + 0.5
    v0 = ((ys + 0.5) / h - 0.5) * 0.95 + 0.5
    vig = 1 - ((xs / w - 0.5) ** 2 + (ys / h - 0.5) ** 2) * 0.6

    tmp = Path(tempfile.mkdtemp())
    frames = int(args.seconds * args.fps)
    for i in range(frames):
        t = i / args.fps
        mend, bloom, settled = span(t, 0.9, 3.1), span(t, 3.2, 5.8), span(t, 5.0, 6.8)
        ox, oy = np.sin(t * 1000 / 2900 * 2.2) * 0.03, np.cos(t * 1000 / 3700 * 2.2) * 0.016

        d0 = cv2.remap(depth, u0 * w, v0 * h, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        u = u0 + ox * (d0 - 0.45) * settled
        v = v0 - oy * (d0 - 0.45) * settled
        sample = lambda img: cv2.remap(img, u * w, v * h, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        d, b, a = sample(depth), sample(before), sample(after)
        gray = (a @ np.array([0.114, 0.587, 0.299], np.float32))[..., None].repeat(3, -1)

        m = mend if mend < 1 else 1.2
        mended = (1 - smoothstep(m - 0.07, m, v))[..., None]
        sweep = (np.exp(-((v - m) / 0.014) ** 2) * (0.001 < m < 0.999))[..., None]
        r = np.sqrt(((u - fx) * aspect) ** 2 + (v - fy) ** 2)
        reach = bloom * 1.7
        coloured = (1 - smoothstep(reach - 0.2, reach, r))[..., None]

        col = b * (1 - mended) + gray * mended
        col = col * (1 - coloured * mended) + a * coloured * mended
        flick = 0.95 + 0.03 * np.sin(t * 7.1) + 0.02 * np.sin(t * 13.7 + 1.3) + 0.015 * np.sin(t * 3.3 + 0.4)
        light = (1 - settled) + settled * (0.84 + 0.24 * d) * flick
        warm = np.array([0.68, 0.87, 1.0], np.float32)  # BGR
        col = col * (1 + (warm - 1) * 0.15 * settled) * light[..., None]
        col = col + np.array([0.42, 0.76, 1.0], np.float32) * sweep * 0.5
        col = col * vig[..., None]
        cv2.imwrite(str(tmp / f"f{i:04d}.png"), (np.clip(col, 0, 1) * 255).astype(np.uint8))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    src = ["-framerate", str(args.fps), "-i", str(tmp / "f%04d.png")]
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *src, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "20", "-movflags", "+faststart", str(args.out.with_suffix(".mp4"))], check=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *src, "-vf",
                    "split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=sierra2_4a",
                    str(args.out.with_suffix(".gif"))], check=True)
    shutil.rmtree(tmp)
    for ext in (".mp4", ".gif"):
        p = args.out.with_suffix(ext)
        print(p, f"{p.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
