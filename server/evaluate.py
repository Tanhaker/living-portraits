"""Run every photo in a folder through the pipeline and record honest numbers.

    python server/evaluate.py samples/ --out results/

Writes results/<photo>/ (before, final, depth), a side-by-side comparison
image per photo, and results/summary.md with speed and identity scores.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import Pipeline  # noqa: E402

IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


def side_by_side(before: np.ndarray, after: np.ndarray, height: int = 640) -> np.ndarray:
    def fit(img):
        return cv2.resize(img, (int(img.shape[1] * height / img.shape[0]), height), interpolation=cv2.INTER_AREA)

    gap = np.full((height, 12, 3), 20, np.uint8)
    return np.hstack([fit(before), gap, fit(after)])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path, default=Path("results"))
    args = ap.parse_args()

    photos = sorted(p for p in args.folder.iterdir() if p.suffix.lower() in IMAGES)
    pipe = Pipeline()
    print(f"models loaded in {pipe.load_seconds}s")

    rows = []
    for p in photos:
        out = args.out / p.stem
        t = time.time()
        try:
            r = pipe.run(p, out)
        except Exception as e:  # keep going; report the failure in the table
            print(f"FAIL {p.name}: {e}")
            rows.append({"photo": p.name, "error": str(e)})
            continue
        r["photo"] = p.name
        r["wall_seconds"] = round(time.time() - t, 2)
        before = cv2.imread(str(p))
        after = cv2.imread(str(out / "final.jpg"))
        cv2.imwrite(str(out / "compare.jpg"), side_by_side(before, after))
        rows.append(r)
        print(f"{p.name}: identity={r['identity']} timings={r['timings']}")

    ok = [r for r in rows if "error" not in r]
    ids = [r["identity"] for r in ok if r["identity"] is not None]
    lines = [
        "# Evaluation",
        "",
        f"- photos: {len(rows)} ({len(ok)} succeeded)",
        f"- model load: {pipe.load_seconds}s (once per server start)",
    ]
    if ok:
        lines.append(f"- median time per photo: {statistics.median(r['timings']['total'] for r in ok):.1f}s")
    if ids:
        lines.append(f"- identity similarity (ArcFace cosine, original vs restored): "
                     f"median {statistics.median(ids):.2f}, min {min(ids):.2f}")
    lines += ["", "| photo | b&w | restore s | colour s | depth s | identity |", "|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['photo']} | – | – | – | – | failed: {r['error'][:60]} |")
            continue
        t = r["timings"]
        lines.append(f"| {r['photo']} | {'yes' if r['was_black_and_white'] else 'no'} | {t.get('restore', '–')} | "
                     f"{t.get('colourise', '–')} | {t.get('depth', '–')} | {r['identity']} |")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
