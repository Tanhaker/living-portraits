#!/usr/bin/env bash
# One-time setup for a DigitalOcean Droplet (Ubuntu). Works on GPU Droplets and on
# plain CPU Droplets. Installs the open-source models into /opt/lp:
#   GFPGAN v1.4              (Apache-2.0)  restores damaged faces
#   DDColor                  (Apache-2.0)  colourises black-and-white photos
#   Depth Anything V2 Small  (Apache-2.0)  estimates depth for the page's parallax
#   facexlib RetinaFace/ArcFace (MIT)      finds the face and checks identity
set -euo pipefail

ROOT=/opt/lp
mkdir -p "$ROOT"/{models,repos,data}
cd "$ROOT"

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg git build-essential python3-dev libgl1 > /dev/null

if ! command -v uv > /dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
export HF_HOME="$ROOT/cache/hf"

[ -x "$ROOT/venv/bin/python" ] || uv venv --python 3.10 "$ROOT/venv"
PY="$ROOT/venv/bin/python"
PIP="uv pip install --python $PY"

if command -v nvidia-smi > /dev/null && nvidia-smi > /dev/null 2>&1; then
  echo "GPU found"
  $PIP torch==2.3.0 torchvision==0.18.0 --index-url https://download.pytorch.org/whl/cu121
else
  echo "No GPU: installing CPU builds"
  $PIP torch==2.3.0 torchvision==0.18.0 --index-url https://download.pytorch.org/whl/cpu
fi

# --- GFPGAN + Real-ESRGAN ---------------------------------------------------
$PIP basicsr facexlib gfpgan realesrgan
BASICSR=$("$PY" -c "import importlib.util;print(importlib.util.find_spec('basicsr').submodule_search_locations[0])")
# basicsr imports a torchvision module that was renamed; patch it.
sed -i 's/torchvision.transforms.functional_tensor/torchvision.transforms.functional/' "$BASICSR/data/degradations.py"
[ -f models/GFPGANv1.4.pth ] || curl -sSL -o models/GFPGANv1.4.pth \
  https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth
[ -f models/RealESRGAN_x2plus.pth ] || curl -sSL -o models/RealESRGAN_x2plus.pth \
  https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth

# --- DDColor ---------------------------------------------------------------
[ -d repos/DDColor ] || git clone -q https://github.com/piddnad/DDColor repos/DDColor
$PIP timm "numpy<2" scikit-image opencv-python-headless "transformers==4.46.3" huggingface_hub
# DDColor imports one folder from its own fork of basicsr; graft it into the installed basicsr.
cp -r repos/DDColor/basicsr/archs/ddcolor_arch_utils "$BASICSR/archs/"

# --- Model weights ------------------------------------------------------------
"$PY" - <<'EOF'
from huggingface_hub import snapshot_download
snapshot_download("depth-anything/Depth-Anything-V2-Small-hf", local_dir="models/depth-anything-v2-small")
snapshot_download("piddnad/ddcolor_modelscope", local_dir="models/ddcolor_modelscope")
EOF

# --- Web server --------------------------------------------------------------
$PIP fastapi "uvicorn[standard]" python-multipart pillow

"$PY" -c "import torch; print('CUDA available:', torch.cuda.is_available())"
echo "setup done"
