"""Living Portraits API. One GPU, one queue: photos are processed in order."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_LOCAL = Path(__file__).resolve().parent.parent / ".local"
DATA = Path(os.environ.get("LP_DATA", _LOCAL / "data" if _LOCAL.is_dir() else "/opt/lp/data"))
WEB = Path(__file__).resolve().parent.parent / "web"
MAX_BYTES = 15 * 1024 * 1024
DATA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Living Portraits")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

jobs: dict[str, dict] = {}
work: queue.Queue[str] = queue.Queue()
pipeline = None


def _save(job: dict) -> None:
    (DATA / job["id"] / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2))


def _load_existing() -> None:
    for f in DATA.glob("*/job.json"):
        job = json.loads(f.read_text())
        if job["status"] in ("queued", "running"):
            job["status"] = "failed"
            job["error"] = "Server restarted while this photo was being processed."
        jobs[job["id"]] = job


def _worker() -> None:
    global pipeline
    from pipeline import Pipeline

    pipeline = Pipeline()
    print(f"models loaded in {pipeline.load_seconds}s", flush=True)
    while True:
        job_id = work.get()
        job = jobs[job_id]
        job["status"] = "running"

        def step(name: str) -> None:
            job["step"] = name
            _save(job)

        try:
            src = DATA / job_id / job["source"]
            job.update(pipeline.run(src, DATA / job_id, animate=job["animate"], on_step=step))
            job["status"] = "done"
        except Exception as e:  # report the failure to the page instead of hanging
            job["status"] = "failed"
            job["error"] = str(e)
        job["step"] = None
        job["finished_at"] = time.time()
        _save(job)


@app.on_event("startup")
def start() -> None:
    _load_existing()
    threading.Thread(target=_worker, daemon=True).start()


@app.get("/api/health")
def health():
    return {"ready": pipeline is not None, "queue": work.qsize()}


@app.post("/api/portraits")
async def create(photo: UploadFile = File(...), name: str = Form(""), memory: str = Form(""),
                 animate: bool = Form(True), share: bool = Form(False)):
    body = await photo.read()
    if len(body) > MAX_BYTES:
        raise HTTPException(413, "Please use a photo under 15 MB.")
    ext = Path(photo.filename or "photo.jpg").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"):
        raise HTTPException(415, "Please upload a JPG, PNG or WebP photo.")
    job_id = uuid.uuid4().hex[:12]
    (DATA / job_id).mkdir()
    (DATA / job_id / f"original{ext}").write_bytes(body)
    job = {"id": job_id, "status": "queued", "step": None, "source": f"original{ext}",
           "name": name.strip()[:80], "memory": memory.strip()[:500], "animate": animate,
           "share": share, "created_at": time.time()}
    jobs[job_id] = job
    _save(job)
    work.put(job_id)
    return {"id": job_id, "position": work.qsize()}


@app.get("/api/portraits/{job_id}")
def get(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Not found")
    return job


@app.get("/api/gallery")
def gallery():
    done = [j for j in jobs.values() if j["status"] == "done" and j.get("share")]
    return sorted(done, key=lambda j: -j["created_at"])[:24]


@app.get("/files/{job_id}/{name}")
def files(job_id: str, name: str):
    path = (DATA / job_id / name).resolve()
    if DATA.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path)


if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
