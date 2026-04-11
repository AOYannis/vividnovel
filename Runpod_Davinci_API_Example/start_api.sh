#!/bin/bash
set -e

# ── Configuration ──────────────────────────────────────────────────────────
export DAVINCI_API_KEY="${DAVINCI_API_KEY:-dvk-$(openssl rand -hex 16)}"
export DAVINCI_MODE="${DAVINCI_MODE:-distill}"  # "distill" (fast 256p) or "sr_540p" (540p with SR)
export CUDA_HOME=/usr/local/cuda-12.8
export PATH=/usr/local/cuda-12.8/bin:$PATH

echo "============================================="
echo "  daVinci-MagiHuman API Server"
echo "============================================="
echo "Mode:    $DAVINCI_MODE"
echo "API Key: $DAVINCI_API_KEY"
echo ""
echo "Endpoints (via RunPod proxy):"
echo "  GET  /status    - Server & GPU status"
echo "  GET  /health    - Health check"
echo "  POST /generate  - Generate video"
echo "  GET  /jobs      - List past generations"
echo "============================================="

# Install uvicorn if needed
pip install --break-system-packages -q uvicorn fastapi python-multipart 2>/dev/null

# Copy API server to workspace (if not already there)
cp -f /workspace/api_server.py /workspace/api_server.py 2>/dev/null || true

cd /workspace/daVinci-MagiHuman

# Run with uvicorn on port 8888 (exposed by RunPod as HTTPS)
exec python3 -m uvicorn api_server:app \
    --host 0.0.0.0 \
    --port 8888 \
    --workers 1 \
    --app-dir /workspace \
    --log-level info
