"""Mend -> colour -> depth. Every model here is open source and runs on hardware we control.

The face is never re-animated or re-posed. The page brings the photo back to life with
light and depth instead (see web/portrait.js), using the depth map made here.

Models are loaded once and kept in memory; each step is timed so the write-up can report
real speed and cost numbers.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

_LOCAL = Path(__file__).resolve().parent.parent / ".local"
ROOT = Path(os.environ.get("LP_ROOT", _LOCAL if _LOCAL.is_dir() else "/opt/lp"))
MODELS = ROOT / "models"
DDCOLOR = ROOT / "repos" / "DDColor"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
TEXTURE_MAX = 1400  # longest side of the images the page loads


def is_black_and_white(img_bgr: np.ndarray) -> bool:
    """Old prints are often sepia, albumen-brown or yellowed, so 'no saturation' is too strict.
    In a toned monochrome print the colour is a function of brightness alone (dark ink, pale
    paper), so fit colour against brightness and look at what is left over."""
    small = cv2.resize(img_bgr, (256, 256), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    L, a, b = lab[:, 0] / 255, lab[:, 1], lab[:, 2]
    X = np.stack([np.ones_like(L), L, L * L, L ** 3], 1)
    residual = 0.0
    for c in (a, b):
        coef, *_ = np.linalg.lstsq(X, c, rcond=None)
        residual += float(np.std(c - X @ coef))
    return residual < 4.0


def fit(img: np.ndarray, longest: int) -> np.ndarray:
    h, w = img.shape[:2]
    s = longest / max(h, w)
    return img if s >= 1 else cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


class Restorer:
    def __init__(self):
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from gfpgan import GFPGANer
        from realesrgan import RealESRGANer

        # GFPGAN downloads its face-detector weights into ./gfpgan/weights; keep them in MODELS.
        cwd = os.getcwd()
        os.chdir(MODELS)
        try:
            bg = None
            if DEVICE == "cuda":
                # On CPU, Real-ESRGAN takes minutes per photo; the face matters most, so the
                # background is simply resized instead.
                bg_model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
                bg = RealESRGANer(scale=2, model_path=str(MODELS / "RealESRGAN_x2plus.pth"), model=bg_model,
                                  tile=400, tile_pad=10, pre_pad=0, half=True)
            self.gfpgan = GFPGANer(model_path=str(MODELS / "GFPGANv1.4.pth"), upscale=2, arch="clean",
                                   channel_multiplier=2, bg_upsampler=bg)
        finally:
            os.chdir(cwd)

    def __call__(self, img_bgr: np.ndarray, strength: float = 0.6) -> np.ndarray:
        # Old scans are often huge; faces only need ~1500px for a good result.
        img_bgr = fit(img_bgr, 1500)
        # strength < 1 blends the restored face with the original, which keeps the person
        # looking like themselves instead of a generic "beautified" face.
        _, _, out = self.gfpgan.enhance(img_bgr, has_aligned=False, only_center_face=False,
                                         paste_back=True, weight=strength)
        return out


class Colorizer:
    def __init__(self, input_size: int = 512):
        sys.path.insert(0, str(DDCOLOR))
        from ddcolor import ColorizationPipeline, DDColor, build_ddcolor_model

        model = build_ddcolor_model(DDColor, model_path=str(MODELS / "ddcolor_modelscope" / "pytorch_model.bin"),
                                    input_size=input_size, model_size="large", device=torch.device(DEVICE))
        # DDColor predicts only colour (ab); light and detail (L) come from the photo itself.
        self.pipe = ColorizationPipeline(model, input_size=input_size, device=torch.device(DEVICE))

    @torch.no_grad()
    def __call__(self, img_bgr: np.ndarray, vividness: float = 0.75) -> np.ndarray:
        out = self.pipe.process(img_bgr)
        # The model's colours run hot (magenta suits, orange hands). Old photos read as more
        # truthful with gentler colour, so scale the chroma down around neutral grey.
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB).astype(np.float32)
        lab[..., 1:] = 128 + (lab[..., 1:] - 128) * vividness
        return cv2.cvtColor(lab.clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


class DepthEstimator:
    """Depth Anything V2 Small (Apache-2.0): how near each part of the photo is.
    The page uses it to give the portrait gentle parallax and candlelight."""

    def __init__(self):
        from transformers import pipeline as hf_pipeline

        self.pipe = hf_pipeline("depth-estimation", model=str(MODELS / "depth-anything-v2-small"),
                                device=0 if DEVICE == "cuda" else -1)

    @torch.no_grad()
    def __call__(self, img_bgr: np.ndarray) -> np.ndarray:
        from PIL import Image

        h, w = img_bgr.shape[:2]
        rgb = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        d = self.pipe(rgb)["predicted_depth"].squeeze().float().cpu().numpy()  # larger = nearer
        d = cv2.resize(d, (w, h), interpolation=cv2.INTER_CUBIC)
        lo, hi = np.percentile(d, 2), np.percentile(d, 98)
        d = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)
        # A soft depth map avoids tearing at edges when the page shifts the layers.
        d = cv2.GaussianBlur(d, (0, 0), sigmaX=max(w, h) * 0.006)
        return (d * 255).astype(np.uint8)


class FaceCheck:
    """Finds the main face and measures whether the restored face is still the same person
    (ArcFace cosine similarity; above ~0.5 usually means the same person)."""

    # Standard ArcFace 112x112 positions for: left eye, right eye, nose, left and right mouth corner.
    TEMPLATE = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                         [41.5493, 92.3655], [70.7299, 92.2041]], np.float32)

    def __init__(self):
        from facexlib.detection import init_detection_model
        from facexlib.recognition.arcface_arch import Backbone
        from facexlib.utils import load_file_from_url

        root = str(MODELS / "facexlib")
        self.detector = init_detection_model("retinaface_resnet50", device=DEVICE, model_rootpath=root)
        # facexlib's own init_recognition_model hard-codes CUDA, so load ArcFace by hand.
        weights = load_file_from_url(
            url="https://github.com/xinntao/facexlib/releases/download/v0.1.0/recognition_arcface_ir_se50.pth",
            model_dir="facexlib/weights", progress=False, file_name=None, save_dir=root)
        self.arcface = Backbone(num_layers=50, drop_ratio=0.6, mode="ir_se")
        self.arcface.load_state_dict(torch.load(weights, map_location="cpu"), strict=True)
        self.arcface = self.arcface.to(DEVICE).eval()

    @torch.no_grad()
    def find(self, img_bgr):
        """Returns (embedding, face centre as 0..1 fractions of width and height) or (None, None)."""
        dets = self.detector.detect_faces(img_bgr, 0.8)
        if dets is None or len(dets) == 0:
            return None, None
        d = max(dets, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
        h, w = img_bgr.shape[:2]
        centre = (float((d[0] + d[2]) / 2 / w), float((d[1] + d[3]) / 2 / h))
        points = np.array(d[5:15], np.float32).reshape(5, 2)
        m, _ = cv2.estimateAffinePartial2D(points, self.TEMPLATE)
        face = cv2.warpAffine(img_bgr, m, (112, 112), borderValue=0)
        t = torch.from_numpy(cv2.cvtColor(face, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)).float() / 255.0
        t = ((t - 0.5) / 0.5).unsqueeze(0).to(DEVICE)
        emb = self.arcface(t)[0].cpu().numpy()
        return emb / np.linalg.norm(emb), centre


def watermark(img_bgr: np.ndarray, text: str = "AI-restored") -> np.ndarray:
    out = img_bgr.copy()
    h, w = out.shape[:2]
    scale = max(0.4, w / 1600)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    org = (w - tw - int(12 * scale), h - int(12 * scale))
    cv2.putText(out, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(out, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1, cv2.LINE_AA)
    return out


class Pipeline:
    def __init__(self):
        t = time.time()
        self.restore = Restorer()
        self.colorize = Colorizer()
        self.depth = DepthEstimator()
        self.faces = FaceCheck()
        self.load_seconds = round(time.time() - t, 1)

    def run(self, src: Path, out_dir: Path, on_step=lambda step: None, **_) -> dict:
        src, out_dir = Path(src).resolve(), Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        timings = {}
        original = cv2.imread(str(src), cv2.IMREAD_COLOR)
        if original is None:
            raise ValueError("Could not read that image.")

        on_step("mending")
        t = time.time()
        restored = self.restore(original)
        timings["restore"] = round(time.time() - t, 2)

        was_bw = is_black_and_white(original)
        final = restored
        if was_bw:
            on_step("colouring")
            t = time.time()
            gray = cv2.cvtColor(cv2.cvtColor(restored, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
            final = self.colorize(gray)
            timings["colourise"] = round(time.time() - t, 2)

        # The page needs the before, after and depth images at exactly the same size.
        final = fit(final, TEXTURE_MAX)
        before = cv2.resize(original, (final.shape[1], final.shape[0]), interpolation=cv2.INTER_AREA)

        on_step("finding depth")
        t = time.time()
        depth = self.depth(final)
        timings["depth"] = round(time.time() - t, 2)

        on_step("checking it is still them")
        emb_before, _ = self.faces.find(before)
        emb_after, centre = self.faces.find(final)
        identity = None if emb_before is None or emb_after is None else float(np.dot(emb_before, emb_after))

        q = [cv2.IMWRITE_JPEG_QUALITY, 90]
        cv2.imwrite(str(out_dir / "before.jpg"), before, q)
        cv2.imwrite(str(out_dir / "final.jpg"), final, q)
        cv2.imwrite(str(out_dir / "download.jpg"), watermark(final), q)
        cv2.imwrite(str(out_dir / "depth.png"), depth)

        timings["total"] = round(sum(timings.values()), 2)
        return {
            "files": {"before": "before.jpg", "final": "final.jpg", "depth": "depth.png", "download": "download.jpg"},
            "face": {"x": round(centre[0], 4), "y": round(centre[1], 4)} if centre else {"x": 0.5, "y": 0.35},
            "size": {"w": final.shape[1], "h": final.shape[0]},
            "timings": timings,
            "was_black_and_white": was_bw,
            "identity": None if identity is None else round(identity, 3),
        }
