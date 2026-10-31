"""Copy evaluation results into web/examples/ so the page works with the server switched off.

    python server/export_examples.py .local/results .local/results_unnamed --names "Kasturba_Gandhi=Kasturba Gandhi|memory"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web" / "examples"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path, nargs="+")
    ap.add_argument("--names", nargs="*", default=[], help="folder=Display name|memory")
    args = ap.parse_args()

    entries = {}
    for n in args.names:
        folder, rest = n.split("=", 1)
        name, _, memory = rest.partition("|")
        entries[folder] = (name, memory)

    summary, folders = {}, []
    for res in args.results:
        summary.update({r["photo"].rsplit(".", 1)[0]: r for r in json.loads((res / "summary.json").read_text())})
        folders += [p for p in res.iterdir() if (p / "final.jpg").exists()]
    if entries:  # keep the order given on the command line
        order = list(entries)
        folders = sorted((p for p in folders if p.name in entries), key=lambda p: order.index(p.name))
    WEB.mkdir(parents=True, exist_ok=True)
    for old in WEB.iterdir():
        old.unlink()
    items = []
    for folder in folders:
        slug = re.sub(r"[^a-z0-9]+", "-", folder.name.lower()).strip("-")[:40]
        for kind, ext in (("before", "jpg"), ("final", "jpg"), ("depth", "png")):
            shutil.copy(folder / f"{kind}.{ext}", WEB / f"{slug}-{kind}.{ext}")
        r = summary.get(folder.name, {})
        name, memory = entries.get(folder.name, (folder.name.replace("_", " "), ""))
        items.append({
            "name": name, "memory": memory,
            "before": f"{slug}-before.jpg", "final": f"{slug}-final.jpg", "depth": f"{slug}-depth.png",
            "face": r.get("face"), "identity": r.get("identity"),
        })
        print("exported", name)
    (WEB / "examples.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
