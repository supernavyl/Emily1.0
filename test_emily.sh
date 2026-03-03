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

# 3. Check TabbyAPI
echo "🤖 TabbyAPI Check..."
if curl -sf http://localhost:5000/v1/models >/dev/null 2>&1; then
    model=$(curl -s http://localhost:5000/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "unknown")
    echo "   ✓ TabbyAPI running"
    echo "   Model: $model"
else
    echo "   ✗ TabbyAPI not running"
    echo "   Starting TabbyAPI..."
    bash check_tabby.sh || {
        echo "   ✗ Failed to start TabbyAPI"
        echo "   Run manually: bash check_tabby.sh"
        exit 1
    }
fi
echo ""

# 4. Check Ollama
echo "👁️  Ollama Check..."
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "   ✓ Ollama running"
else
    echo "   ⚠ Ollama not running (vision/embedding unavailable)"
    echo "   Start: ollama serve &"
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

# 6. Check audio devices
echo "🎧 Audio Devices..."
python3 -c "
import sounddevice as sd
devices = sd.query_devices()
yeti = devices[32] if len(devices) > 32 else None
usb = devices[43] if len(devices) > 43 else None
if yeti and 'Yeti' in yeti['name']:
    print('   ✓ Yeti Nano (device 32)')
else:
    print('   ✗ Yeti Nano not at device 32')
    exit(1)
if usb and 'USB' in usb['name']:
    print('   ✓ USB Headphones (device 43)')
else:
    print('   ✗ USB Headphones not at device 43')
    exit(1)
" || {
    echo "   ✗ Audio device check failed"
    echo "   Run: python test_audio.py"
    exit 1
}
echo ""

# 7. Check Python dependencies
echo "📦 Dependencies..."
python3 -c "
import sys
deps = ['torch', 'faster_whisper', 'kokoro', 'sounddevice', 'httpx']
missing = []
for dep in deps:
    try:
        __import__(dep.replace('-', '_'))
    except ImportError:
        missing.append(dep)
if missing:
    print(f'   ✗ Missing: {', '.join(missing)}')
    print('   Run: uv sync')
    sys.exit(1)
print('   ✓ All dependencies installed')
" || exit 1
echo ""

echo "══════════════════════════════════════════════════════════"
echo "  ✅ ALL CHECKS PASSED"
echo "══════════════════════════════════════════════════════════"
echo ""
echo "  Starting Emily voice system..."
echo "  - Yeti Nano (device 32) for input"
echo "  - USB Headphones (device 43) for output"
echo "  - TabbyAPI on GPU for LLM"
echo ""
echo "  Press Ctrl+C to stop"
echo ""
echo "══════════════════════════════════════════════════════════"
echo ""

# Start Emily
python main.py --no-gui
