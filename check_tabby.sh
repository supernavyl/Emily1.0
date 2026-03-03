#!/usr/bin/env bash
# check_tabby.sh — Check if TabbyAPI is running, start it if not
set -uo pipefail

TABBY_DIR="$HOME/TabbyAPI"
TABBY_URL="http://localhost:5000"
TABBY_LOG="$HOME/Emily1.0/logs/tabbyapi.log"
TABBY_MODEL_DIR="${TABBY_MODEL_DIR:-$HOME/models/tabby}"
DEFAULT_MODEL="${TABBY_MODEL_NAME:-Huihui-Qwen3-14B-abliterated-v2-exl2}"

echo "══════════════════════════════════════"
echo "  TabbyAPI Check"
echo "══════════════════════════════════════"

# 1. Already running?
if curl -sf "$TABBY_URL/v1/models" >/dev/null 2>&1; then
    echo "✓ TabbyAPI already running on port 5000"
    model=$(curl -s "$TABBY_URL/v1/models" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "unknown")
    echo "  Model: $model"

    # Show GPU usage
    echo ""
    nvidia-smi --query-gpu=name,memory.used,memory.free,utilization.gpu --format=csv,noheader 2>/dev/null || true
    exit 0
fi

echo "✗ TabbyAPI not running"
echo ""

# 2. Check install
if [ ! -d "$TABBY_DIR" ]; then
    echo "✗ TabbyAPI not installed at $TABBY_DIR"
    echo "  Install:"
    echo "    git clone https://github.com/theroyallab/tabbyAPI.git ~/TabbyAPI"
    echo "    cd ~/TabbyAPI && python3 -m venv venv && source venv/bin/activate"
    echo "    pip install -r requirements.txt"
    exit 1
fi

TABBY_VENV="$TABBY_DIR/venv/bin/python"
if [ ! -f "$TABBY_VENV" ]; then
    echo "✗ TabbyAPI venv not found"
    echo "  Fix: cd $TABBY_DIR && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 3. Check model
if [ ! -d "$TABBY_MODEL_DIR/$DEFAULT_MODEL" ]; then
    echo "⚠ Model not found: $TABBY_MODEL_DIR/$DEFAULT_MODEL"
    echo "  Available models in $TABBY_MODEL_DIR:"
    ls -1 "$TABBY_MODEL_DIR" 2>/dev/null || echo "    (directory doesn't exist)"
    echo ""
    echo "  Set a different model:"
    echo "    TABBY_MODEL_NAME=YourModelName bash check_tabby.sh"
    echo ""
    read -p "  Start anyway without model check? (y/N) " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

# 4. Start TabbyAPI
mkdir -p "$(dirname "$TABBY_LOG")"
echo "🚀 Starting TabbyAPI..."
echo "  Model dir: $TABBY_MODEL_DIR"
echo "  Model:     $DEFAULT_MODEL"
echo "  Log:       $TABBY_LOG"
echo ""

cd "$TABBY_DIR"
"$TABBY_VENV" main.py \
    --model-dir "$TABBY_MODEL_DIR" \
    --model-name "$DEFAULT_MODEL" \
    --disable-auth true \
    > "$TABBY_LOG" 2>&1 &

tabby_pid=$!
cd "$HOME/Emily1.0"

echo "  PID: $tabby_pid"
echo "  Waiting for model load (10-60s)..."

wait_time=0
max_wait=90
while [ $wait_time -lt $max_wait ]; do
    if curl -sf "$TABBY_URL/v1/models" >/dev/null 2>&1; then
        echo ""
        model=$(curl -s "$TABBY_URL/v1/models" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "$DEFAULT_MODEL")
        echo "✓ TabbyAPI ready!"
        echo "  Model: $model"
        echo "  URL:   $TABBY_URL"
        echo ""
        nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader 2>/dev/null || true
        exit 0
    fi
    sleep 2
    wait_time=$((wait_time + 2))
    echo -n "."
done

echo ""
echo "✗ TabbyAPI failed to start in ${max_wait}s"
echo "  Check logs: tail -50 $TABBY_LOG"
tail -20 "$TABBY_LOG" 2>/dev/null
exit 1
