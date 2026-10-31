# Local setup for a Windows laptop with an NVIDIA GPU. Mirrors setup.sh.
# Everything (venv, caches, model weights) stays inside .local/ on this drive.
# "Continue": Windows PowerShell 5 turns any native-tool stderr (progress bars) into errors.
# Failures are caught by checking $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$Root = Join-Path $PSScriptRoot "..\.local" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $Root) { $Root = New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot "..\.local") }
$Root = "$Root"
foreach ($d in "models", "repos", "data", "bin", "cache") { New-Item -ItemType Directory -Force (Join-Path $Root $d) | Out-Null }

$env:UV_CACHE_DIR = Join-Path $Root "cache\uv"
$env:HF_HOME = Join-Path $Root "cache\hf"
$Py = Join-Path $Root "venv\Scripts\python.exe"
Set-Location $Root

if (-not (Test-Path $Py)) { uv venv --python 3.10 venv; if ($LASTEXITCODE) { throw "venv failed" } }
function Pip { uv pip install --python $Py @args; if ($LASTEXITCODE) { throw "pip failed: $args" } }

Pip torch==2.3.0 torchvision==0.18.0 --index-url https://download.pytorch.org/whl/cu121

Pip huggingface_hub imageio-ffmpeg opencv-python "transformers==4.46.3"

# ffmpeg without touching the system PATH: copy imageio's bundled binary into .local\bin
$ff = & $Py -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
Copy-Item $ff (Join-Path $Root "bin\ffmpeg.exe") -Force

# GFPGAN + Real-ESRGAN
Pip basicsr facexlib gfpgan realesrgan
$basicsr = & $Py -c "import importlib.util; print(importlib.util.find_spec('basicsr').submodule_search_locations[0])"
$deg = Join-Path $basicsr "data\degradations.py"
(Get-Content $deg) -replace 'torchvision\.transforms\.functional_tensor', 'torchvision.transforms.functional' | Set-Content -Encoding utf8 $deg
if (-not (Test-Path models\GFPGANv1.4.pth)) { curl.exe -sSL -o models\GFPGANv1.4.pth https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth }
if (-not (Test-Path models\RealESRGAN_x2plus.pth)) { curl.exe -sSL -o models\RealESRGAN_x2plus.pth https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth }

# DDColor
if (-not (Test-Path repos\DDColor)) { git clone -q https://github.com/piddnad/DDColor repos\DDColor }
Pip timm "numpy<2" huggingface_hub scikit-image fastapi "uvicorn[standard]" python-multipart pillow
# DDColor imports one folder from its own fork of basicsr; graft it into the installed basicsr.
Copy-Item -Recurse -Force repos\DDColor\basicsr\archs\ddcolor_arch_utils (Join-Path $basicsr "archs\")
& $Py -c "from huggingface_hub import snapshot_download as d; d('piddnad/ddcolor_modelscope', local_dir='models/ddcolor_modelscope'); d('depth-anything/Depth-Anything-V2-Small-hf', local_dir='models/depth-anything-v2-small')"

& $Py -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
Write-Output "setup done"
