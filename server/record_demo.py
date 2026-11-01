"""Record a timed demo of the live site as an MP4 (1920x1080), optionally with a voice-over.

    python server/record_demo.py --url http://139.59.7.49 --out docs/media/demo --voice voiceover.mp3

Frames come from Chrome's screencast (CDP), so the video is sharp and the WebGL portrait
plays at full quality. Scene times line up with docs/voiceover-script.md.
"""

from __future__ import annotations

import argparse
import base64
import math
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
_BIN = ROOT / ".local" / "bin" / "ffmpeg.exe"
FFMPEG = str(_BIN) if _BIN.exists() else "ffmpeg"
UPLOAD = ROOT / "samples" / "Kasturba_Gandhi.jpg"  # restores fast enough on CPU to finish on camera


def glide(page, x0, y0, x1, y1, seconds, steps=60):
    """Move the pointer smoothly (ease in-out) so the portrait's depth follows it."""
    for i in range(steps + 1):
        t = i / steps
        e = 0.5 - math.cos(math.pi * t) / 2
        page.mouse.move(x0 + (x1 - x0) * e, y0 + (y1 - y0) * e)
        time.sleep(seconds / steps)


def portrait_centre(page):
    box = page.locator("#portrait").bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, box["width"], box["height"]


def click_gallery(page, index):
    page.locator("#gallery button").nth(index).scroll_into_view_if_needed()
    time.sleep(0.6)
    page.locator("#gallery button").nth(index).click()


def scenes(page):
    """(start second, action) pairs, matching the narration."""
    def replay():
        # Clicking with the mouse would scroll the button into view and crop the portrait.
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'}); document.querySelector('#replay').click()")

    def drift_a():
        x, y, w, h = portrait_centre(page)
        glide(page, x - w * 0.3, y - h * 0.2, x + w * 0.35, y + h * 0.1, 4.5)

    def drift_b():
        x, y, w, h = portrait_centre(page)
        glide(page, x + w * 0.35, y + h * 0.1, x - w * 0.35, y + h * 0.25, 3.5)

    def drift_c():
        x, y, w, h = portrait_centre(page)
        glide(page, x - w * 0.35, y - h * 0.25, x + w * 0.3, y - h * 0.1, 3.0)

    def milk_seller(): click_gallery(page, 2)
    def ornaments(): click_gallery(page, 1)

    def place_photo():
        page.locator("#place").scroll_into_view_if_needed()
        time.sleep(0.8)
        page.set_input_files("#photo", str(UPLOAD))
        time.sleep(0.6)
        page.fill("#name", "")
        page.type("#name", "Kasturba Gandhi", delay=40)

    def submit(): page.click("#submit")

    def drift_d():
        x, y, w, h = portrait_centre(page)
        glide(page, x - w * 0.3, y, x + w * 0.3, y - h * 0.15, 3.0)

    def light(): page.evaluate("document.querySelector('#light').click()")

    return [
        (0.0, replay),
        (8.0, drift_a),
        (17.0, replay),
        (21.0, drift_b),
        (24.0, milk_seller),
        (28.3, ornaments),
        (33.0, place_photo),
        (35.5, submit),
        (51.5, drift_d),
        (56.0, light),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://139.59.7.49")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "media" / "demo")
    ap.add_argument("--seconds", type=float, default=63.0)
    ap.add_argument("--voice", type=Path)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    frames: list[tuple[float, Path]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed,
                                    args=["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist",
                                          "--autoplay-policy=no-user-gesture-required"])
        ctx = browser.new_context(viewport={"width": 1366, "height": 768}, device_scale_factor=1920 / 1366)
        page = ctx.new_page()
        page.goto(f"{args.url}/?rec=1", wait_until="networkidle")
        page.wait_for_function("document.querySelector('#r-name').textContent.length > 0", timeout=60000)
        page.add_style_tag(content=(
            "html { scroll-behavior: smooth; } ::-webkit-scrollbar { display: none; }"
            # fit the whole altar inside a 16:9 frame
            ".hero { min-height: 0; padding: 18px 0 40px; } .frame { width: min(300px, 100%); }"
            ".remembered { min-height: 0; margin-bottom: 10px; } .hint { display: none; } .candles { margin-top: 24px; } .light { margin: 0 0 8px; }"))
        time.sleep(2.5)

        cdp = ctx.new_cdp_session(page)

        def on_frame(ev):
            path = tmp / f"{len(frames):05d}.jpg"
            path.write_bytes(base64.b64decode(ev["data"]))
            frames.append((ev["metadata"]["timestamp"], path))
            cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})

        cdp.on("Page.screencastFrame", on_frame)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080})

        start = time.monotonic()
        for at, action in scenes(page):
            while time.monotonic() - start < at:
                page.wait_for_timeout(20)
            action()
        while time.monotonic() - start < args.seconds:
            page.wait_for_timeout(50)
        cdp.send("Page.stopScreencast")
        browser.close()

    # Turn the timestamped frames into a constant 30 fps video.
    t0 = frames[0][0]
    lines = []
    for (ts, path), nxt in zip(frames, frames[1:] + [(t0 + args.seconds, None)]):
        lines += [f"file '{path.as_posix()}'", f"duration {max(nxt[0] - ts, 0.001):.4f}"]
    lines.append(f"file '{frames[-1][1].as_posix()}'")
    (tmp / "list.txt").write_text("\n".join(lines))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    silent = args.out.with_name(args.out.name + "-silent.mp4")
    fade = f"fade=t=in:st=0:d=0.8,fade=t=out:st={args.seconds - 1.5:.2f}:d=1.5"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                    "-vf", f"fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,{fade}",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", str(silent)], check=True)
    print(f"{len(frames)} frames -> {silent}")

    if args.voice:
        final = args.out.with_suffix(".mp4")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(args.voice),
                        "-filter_complex", f"[1:a]adelay=400|400,afade=t=out:st={args.seconds - 1.5:.2f}:d=1.5,loudnorm=I=-16:TP=-1.5[a]",
                        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                        "-movflags", "+faststart", str(final)], check=True)
        print("with voice-over ->", final)
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
