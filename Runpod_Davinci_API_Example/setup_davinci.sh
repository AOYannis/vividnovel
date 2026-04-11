#!/bin/bash
set -e

echo "=== daVinci-MagiHuman Setup on RunPod ==="

# --- 1. HuggingFace Login ---
echo "[1/6] Logging into HuggingFace..."
if ! huggingface-cli whoami &>/dev/null; then
    echo "Please provide your HuggingFace token:"
    huggingface-cli login
else
    echo "Already logged in as: $(huggingface-cli whoami)"
fi

# --- 2. Create model directory on the volume (persists across restarts) ---
MODEL_DIR=/workspace/models
mkdir -p $MODEL_DIR
echo "[2/6] Models will be stored at $MODEL_DIR"

# --- 3. Download daVinci-MagiHuman weights (~216 GB) ---
echo "[3/6] Downloading daVinci-MagiHuman weights..."
huggingface-cli download GAIR/daVinci-MagiHuman \
    --local-dir $MODEL_DIR/daVinci-MagiHuman

# --- 4. Download external dependency models ---
echo "[4/6] Downloading T5-Gemma text encoder (~44 GB)..."
huggingface-cli download google/t5gemma-9b-9b-ul2 \
    --local-dir $MODEL_DIR/t5gemma-9b-9b-ul2

echo "[5/6] Downloading Stable Audio Open 1.0 (~11 GB)..."
huggingface-cli download stabilityai/stable-audio-open-1.0 \
    --local-dir $MODEL_DIR/stable-audio-open-1.0

echo "[5/6] Downloading Wan2.2 VAE..."
huggingface-cli download Wan-AI/Wan2.2-TI2V-5B \
    --local-dir $MODEL_DIR/Wan2.2-TI2V-5B

# --- 5. Clone and setup MagiCompiler + daVinci-MagiHuman ---
echo "[6/6] Setting up MagiCompiler and daVinci-MagiHuman..."
cd /workspace

if [ ! -d "MagiCompiler" ]; then
    git clone https://github.com/SandAI-org/MagiCompiler.git
    cd MagiCompiler
    pip install -r requirements.txt
    pip install .
    cd ..
fi

if [ ! -d "daVinci-MagiHuman" ]; then
    git clone https://github.com/GAIR-NLP/daVinci-MagiHuman.git
    cd daVinci-MagiHuman
    pip install -r requirements.txt
    pip install --no-deps -r requirements-nodeps.txt
    cd ..
fi

# --- 6. Update config files with model paths ---
echo "Updating config paths..."
cd /workspace/daVinci-MagiHuman

for config_file in example/base/config.json example/distill/config.json example/sr_540p/config.json example/sr_1080p/config.json; do
    if [ -f "$config_file" ]; then
        sed -i "s|/path/to/checkpoints/base|$MODEL_DIR/daVinci-MagiHuman/base|g" "$config_file"
        sed -i "s|/path/to/checkpoints/distill|$MODEL_DIR/daVinci-MagiHuman/distill|g" "$config_file"
        sed -i "s|/path/to/checkpoints/540p_sr|$MODEL_DIR/daVinci-MagiHuman/540p_sr|g" "$config_file"
        sed -i "s|/path/to/checkpoints/1080p_sr|$MODEL_DIR/daVinci-MagiHuman/1080p_sr|g" "$config_file"
        sed -i "s|/path/to/checkpoints/turbo_vae|$MODEL_DIR/daVinci-MagiHuman/turbo_vae|g" "$config_file"
        sed -i "s|/path/to/t5gemma-9b-9b-ul2|$MODEL_DIR/t5gemma-9b-9b-ul2|g" "$config_file"
        sed -i "s|/path/to/stable-audio-open-1.0|$MODEL_DIR/stable-audio-open-1.0|g" "$config_file"
        sed -i "s|/path/to/Wan2.2-TI2V-5B|$MODEL_DIR/Wan2.2-TI2V-5B|g" "$config_file"
        echo "  Updated: $config_file"
    fi
done

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To test inference (256p, fastest):"
echo "  cd /workspace/daVinci-MagiHuman"
echo "  bash example/distill/run.sh"
echo ""
echo "To test inference (540p with super-resolution):"
echo "  cd /workspace/daVinci-MagiHuman"
echo "  bash example/sr_540p/run.sh"
