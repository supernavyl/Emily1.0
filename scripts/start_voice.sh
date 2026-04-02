#!/usr/bin/env bash
# start_voice.sh — Full Emily voice startup with GPU validation
set -e

echo "══════════════════════════════════════════════"
echo "  Emily Voice Startup"
echo "══════════════════════════════════════════════"

# 1. Clear stale Python cache
echo ""
echo "Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -name '*.pyc' -delete 2>/dev/null || true

# 2. Check GPU is visible
echo ""
echo "Checking GPU..."
if ! command -v nvidia-smi &>/dev/null; then
    echo "  nvidia-smi not found — install NVIDIA drivers"
    exit 1
fi
nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader
echo ""

# 3. Check Ollama (needed for LLM + vision + embedding)
echo "Checking Ollama..."
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "  Ollama running"
    curl -sf http://localhost:11434/api/tags | uv run python -c "
import sys, json
try:
    models = [m['name'] for m in json.load(sys.stdin).get('models', [])]
    for m in models: print(f'    - {m}')
except: pass
" 2>/dev/null || true
else
    echo "  Ollama not running — voice LLM needs it"
    echo "    Start: ollama serve"
fi

# 4. Check Qdrant
echo ""
echo "Checking Qdrant..."
if curl -sf http://localhost:6333/healthz >/dev/null 2>&1; then
    echo "  Qdrant running"
else
    echo "  Qdrant not running — starting via docker..."
    docker compose up -d qdrant 2>/dev/null || echo "  Could not start Qdrant"
fi

# 5. Start Emily
echo ""
echo "══════════════════════════════════════════════"
echo "  Starting Emily voice..."
echo "  STT: Moonshine ONNX (CPU)"
echo "  LLM: Ollama via EmilyLLMProvider"
echo "  TTS: Kokoro"
echo "══════════════════════════════════════════════"
echo ""
exec uv run python main.py --no-gui "$@"
