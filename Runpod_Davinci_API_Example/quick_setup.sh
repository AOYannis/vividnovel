#!/bin/bash
set -e
echo "=== daVinci Quick Setup ==="
START=$(date +%s)

export CUDA_HOME=/usr/local/cuda-12.8
export PATH=$CUDA_HOME/bin:$PATH
SITE=$(python3 -c 'import site; print(site.getsitepackages()[0])')

# 1. Install all daVinci requirements first (this pulls in torch + everything)
echo "[1/5] Installing daVinci requirements..."
cd /workspace/daVinci-MagiHuman
pip install --break-system-packages -q -r requirements.txt 2>/dev/null
pip install --break-system-packages -q --no-deps -r requirements-nodeps.txt 2>/dev/null
pip install --break-system-packages -q more-itertools unfoldNd 2>/dev/null

# 2. Clean torch and reinstall correct version (requirements may install wrong one)
echo "[2/5] Fixing torch version..."
pip uninstall --break-system-packages torch torchvision torchaudio -y > /dev/null 2>&1 || true
rm -rf $SITE/torch
pip install --break-system-packages -q 'torch==2.10.0' 'torchvision==0.25.0' 'torchaudio==2.10.0' --index-url https://download.pytorch.org/whl/cu128
pip install --break-system-packages -q --no-deps 'triton==3.5.0'

# 3. Re-install packages that torch uninstall may have broken
echo "[3/5] Re-installing flash-attn + MagiCompiler..."
pip install --break-system-packages -q --no-deps /workspace/wheels/flash_attn*.whl 2>/dev/null || \
  (echo "  No cached wheel, building from source (~90 min)..." && \
   MAX_JOBS=8 pip install --break-system-packages --no-build-isolation flash-attn && \
   mkdir -p /workspace/wheels && pip wheel --no-build-isolation --no-deps flash-attn -w /workspace/wheels/)
cd /workspace/MagiCompiler && pip install --break-system-packages -q .
pip install --break-system-packages -q graphviz depyf

# 4. Pin transformers + reinstall any deps broken by torch swap
echo "[4/5] Pinning transformers + API deps..."
pip install --break-system-packages -q 'transformers==4.56.0' 'huggingface-hub>=0.34.0,<1.0'
pip install --break-system-packages -q uvicorn fastapi python-multipart pydantic-settings
pip install --break-system-packages -q diffusers accelerate einops timm scipy numba soundfile imageio imageio-ffmpeg

# 5. HF login
echo "[5/5] HuggingFace login..."
python3 -c "from huggingface_hub import login; login(token='${HF_TOKEN:?HF_TOKEN env var required}')"

# Verify
echo ""
echo "=== Verifying ==="
python3 -c '
import torch; print("  torch:", torch.__version__)
import triton; print("  triton:", triton.__version__)
import flash_attn; print("  flash_attn:", flash_attn.__version__)
from magi_compiler import magi_compile; print("  MagiCompiler: OK")
import transformers; print("  transformers:", transformers.__version__)
import diffusers; print("  diffusers: OK")
import uvicorn; print("  uvicorn: OK")
'

END=$(date +%s)
echo ""
echo "=== Setup complete in $((END - START)) seconds ==="
echo ""
echo "Launch API:"
echo '  cd /workspace/daVinci-MagiHuman && DAVINCI_API_KEY=$YOUR_DAVINCI_API_KEY DAVINCI_MODE=distill CUDA_HOME=/usr/local/cuda-12.8 nohup python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8888 --workers 1 --app-dir /workspace --log-level info > /workspace/api_server.log 2>&1 &'
