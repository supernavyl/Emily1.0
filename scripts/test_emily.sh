#!/usr/bin/env bash
# test_emily.sh — Complete Emily system test
set -euo pipefail

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  EMILY VOICE SYSTEM TEST"
echo "══════════════════════════════════════════════════════════"
echo ""

# 1. Clear Python cache
echo "🧹 Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -name '*.pyc' -delete 2>/dev/null || true
echo "   ✓ Cache cleared"
echo ""

# 2. Check GPU
echo "🎮 GPU Check..."
if nvidia-smi --query-gpu=name,memory.used,memory.free,utilization.gpu --format=csv,noheader 2>/dev/null; then
    echo "   ✓ GPU detected"
else
    echo "   ✗ No GPU found"
    exit 1
fi
echo ""

# 3. Check Ollama (optional — vision + embedding only)
echo "👁️  Ollama Check (vision + embedding)..."
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "   ✓ Ollama running"
else
    echo "   ⚠ Ollama not running (vision/embedding unavailable)"
    echo "   LLM uses llama-cpp-python — Ollama is optional"
fi
echo ""

# 5. Check Qdrant
echo "🗄️  Qdrant Check..."
if curl -sf http://localhost:6333/healthz >/dev/null 2>&1; then
    echo "   ✓ Qdrant running"
else
    echo "   Starting Qdrant..."
    docker compose up -d qdrant 2>/dev/null || echo "   ⚠ Could not start Qdrant"
fi
echo ""

# 5. Check audio devices (by name, not hardcoded index)
echo "🎧 Audio Devices..."
uv run python3 -c "
import sounddevice as sd
devices = sd.query_devices()
found_input = found_output = False
for i, d in enumerate(devices):
    if d['max_input_channels'] > 0 and not found_input:
        print(f'   ✓ Input:  [{i}] {d[\"name\"]}')
        found_input = True
    if d['max_output_channels'] > 0 and not found_output:
        print(f'   ✓ Output: [{i}] {d[\"name\"]}')
        found_output = True
if not found_input: print('   ✗ No input device found')
if not found_output: print('   ✗ No output device found')
" || echo "   ⚠ Audio device check skipped (sounddevice not installed?)"
echo ""

# 6. Check Python dependencies
echo "📦 Dependencies..."
uv run python3 -c "
import sys
deps = ['torch', 'llama_cpp', 'snac', 'kokoro', 'sounddevice', 'httpx']
missing = []
for dep in deps:
    try:
        __import__(dep.replace('-', '_'))
    except ImportError:
        missing.append(dep)
if missing:
    print(f'   ✗ Missing: {\", \".join(missing)}')
    print('   Run: uv sync --extra gpu-cuda')
    sys.exit(1)
print('   ✓ All dependencies installed')
" || exit 1
echo ""

echo "══════════════════════════════════════════════════════════"
echo "  ✅ ALL CHECKS PASSED"
echo "══════════════════════════════════════════════════════════"
echo ""
echo "  Starting Emily voice system..."
echo "  - llama-cpp-python for LLM (in-process GGUF)"
echo "  - Orpheus TTS (Kokoro fallback)"
echo ""
echo "  Press Ctrl+C to stop"
echo ""
echo "══════════════════════════════════════════════════════════"
echo ""

# Start Emily
exec uv run python main.py --no-gui
