"""Record one raw demo take of the live site, logging when each scene starts and where the
important elements are on screen. server/edit_demo.py then cuts, zooms and narrates it.

    python server/record_demo.py --url http://139.59.7.49 --out .local/take

Frames come from Chrome's screencast (CDP), so the WebGL portrait plays at full quality.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
_BIN = ROOT / ".local" / "bin" / "ffmpeg.exe"
FFMPEG = str(_BIN) if _BIN.exists() else "ffmpeg"
UPLOAD = ROOT / "samples" / "unnamed" / "unnamed_3.jpg"
VIEW_W, VIEW_H = 1366, 768
SCALE = 1920 / VIEW_W

# Make the recording read well at 1080p: whole altar on screen, no scrollbar.
RECORDING_CSS = (
    "html { scroll-behavior: smooth; } ::-webkit-scrollbar { display: none; }"
    ".hero { min-height: 0; padding: 18px 0 40px; } .frame { width: min(300px, 100%); }"
    ".remembered { min-height: 0; margin-bottom: 10px; } .candles { margin-top: 24px; } .light { margin: 0 0 8px; }"
)


def glide(page, x0, y0, x1, y1, seconds, steps=60):
    """Move the pointer smoothly (ease in-out) so the portrait's depth follows it."""
    for i in range(steps + 1):
        e = 0.5 - math.cos(math.pi * i / steps) / 2
        page.mouse.move(x0 + (x1 - x0) * e, y0 + (y1 - y0) * e)
        time.sleep(seconds / steps)


def box(page, selector):
    b = page.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect();"
                      " return [r.x, r.y, r.width, r.height]; }", selector)
    return [round(v * SCALE) for v in b]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://139.59.7.49")
    ap.add_argument("--out", type=Path, default=ROOT / ".local" / "take")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    frames: list[tuple[float, Path]] = []
    events: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"])
        ctx = browser.new_context(viewport={"width": VIEW_W, "height": VIEW_H}, device_scale_factor=SCALE)
        page = ctx.new_page()
        page.goto(f"{args.url}/?rec=2", wait_until="networkidle")
        page.wait_for_function("document.querySelector('#r-name').textContent.length > 0", timeout=60000)
        page.add_style_tag(content=RECORDING_CSS)
        time.sleep(2.5)

        cdp = ctx.new_cdp_session(page)

        def on_frame(ev):
            path = tmp / f"{len(frames):05d}.jpg"
            path.write_bytes(base64.b64decode(ev["data"]))
            frames.append((ev["metadata"]["timestamp"], path))
            cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})

        cdp.on("Page.screencastFrame", on_frame)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080})
        while not frames:
            page.wait_for_timeout(20)
        t0 = frames[0][0]
        now = lambda: time.time() - t0  # screencast timestamps are wall-clock seconds

        def mark(name, selector=None, **extra):
            events.append({"name": name, "t": round(now(), 2), **({"box": box(page, selector)} if selector else {}), **extra})

        # 1. The altar: the c. 1910 portrait returns.
        page.evaluate("window.scrollTo(0, 0); document.querySelector('#replay').click()")
        mark("altar", ".altar")
        page.wait_for_timeout(5500)
        x, y = box(page, "#portrait")[:2]
        b = box(page, "#portrait")
        cx, cy = (b[0] + b[2] / 2) / SCALE, (b[1] + b[3] / 2) / SCALE
        glide(page, cx - 80, cy - 60, cx + 90, cy + 40, 3.0)

        # 2. Remembered: the gallery of unnamed portraits.
        page.evaluate("document.querySelector('#remembered').scrollIntoView({behavior: 'smooth', block: 'center'})")
        page.wait_for_timeout(900)
        mark("gallery", "#remembered")
        g = box(page, "#gallery")
        gy = (g[1] + g[3] * 0.4) / SCALE
        glide(page, 120, gy, 1100, gy, 5.0, steps=80)

        # 3. Place a photo: choose it, give it a name.
        page.evaluate("document.querySelector('#place').scrollIntoView({behavior: 'smooth', block: 'center'})")
        page.wait_for_timeout(1000)
        mark("place", "#place")
        page.wait_for_timeout(700)
        page.set_input_files("#photo", str(UPLOAD))
        page.wait_for_timeout(1200)
        page.click("#name")
        page.type("#name", "A woman in a sari, 1880s", delay=55)
        page.click("#memory")
        page.type("#memory", "Her name was not recorded.", delay=45)
        page.wait_for_timeout(800)

        # 4. Working: the DigitalOcean server mends, colours and finds depth.
        page.click("#submit")
        page.wait_for_timeout(300)
        mark("working", "#working")
        page.wait_for_function("document.querySelector('#working').hidden === true", timeout=120000)

        # 5. The Return of her photo.
        page.wait_for_timeout(700)  # app scrolls the altar into view and starts the Return
        mark("return", ".altar")
        page.wait_for_timeout(6800)
        b = box(page, "#portrait")
        cx, cy = (b[0] + b[2] / 2) / SCALE, (b[1] + b[3] / 2) / SCALE
        glide(page, cx - 90, cy - 70, cx + 90, cy + 50, 2.6)
        glide(page, cx + 90, cy + 50, cx - 70, cy + 70, 2.4)

        # 6. Honesty: where it came from, and how close the face is.
        mark("credit", ".remembered")
        page.wait_for_timeout(5000)

        # 7. Light a candle.
        mark("candle", ".altar")
        page.wait_for_timeout(600)
        page.evaluate("document.querySelector('#light').click()")
        page.wait_for_timeout(4500)
        mark("end")

        cdp.send("Page.stopScreencast")
        browser.close()

    duration = frames[-1][0] - t0 + 0.04
    lines = []
    for (ts, path), nxt in zip(frames, frames[1:] + [(t0 + duration, None)]):
        lines += [f"file '{path.as_posix()}'", f"duration {max(nxt[0] - ts, 0.001):.4f}"]
    lines.append(f"file '{frames[-1][1].as_posix()}'")
    (tmp / "list.txt").write_text("\n".join(lines))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    video = args.out.with_suffix(".mp4")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                    "-vf", "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", str(video)], check=True)
    args.out.with_suffix(".json").write_text(json.dumps({"duration": duration, "events": events}, indent=2))
    print(f"{len(frames)} frames, {duration:.1f}s -> {video}")
    for e in events:
        print(e)


if __name__ == "__main__":
    main()
