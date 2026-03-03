#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# TabbyAPI verification script for Emily
# Checks TabbyAPI installation, loaded models, and connectivity
# ─────────────────────────────────────────────────────────────

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[verify]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; }
sep()  { echo -e "${CYAN}────────────────────────────────────────${NC}"; }

TABBY_URL="http://localhost:5000"
TABBY_DIR="$HOME/TabbyAPI"
MODEL_DIR="$HOME/models/tabby"

sep
log "TabbyAPI Verification for Emily"
sep

# ── 1. Check TabbyAPI installation ────────────────────────────
log "Checking TabbyAPI installation..."

if [ ! -d "$TABBY_DIR" ]; then
    err "TabbyAPI directory not found: $TABBY_DIR"
    echo ""
    echo "Install TabbyAPI:"
    echo "  cd ~/ && git clone https://github.com/therealownage/TabbyAPI.git"
    echo "  cd TabbyAPI && python3.11 -m venv venv"
    echo "  source venv/bin/activate && pip install -r requirements.txt"
    echo ""
    echo "See: docs/TABBYAPI_SETUP.md"
    exit 1
fi
log "  ✓ TabbyAPI directory: $TABBY_DIR"

if [ ! -f "$TABBY_DIR/venv/bin/python" ]; then
    err "TabbyAPI virtualenv not found: $TABBY_DIR/venv"
    echo ""
    echo "Create virtualenv:"
    echo "  cd $TABBY_DIR"
    echo "  python3.11 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi
log "  ✓ Virtualenv: $TABBY_DIR/venv"

if [ ! -f "$TABBY_DIR/config.yml" ]; then
    warn "config.yml not found — using default config"
    warn "  Copy config: cp $TABBY_DIR/config_sample.yml $TABBY_DIR/config.yml"
else
    log "  ✓ Config: $TABBY_DIR/config.yml"
fi

# ── 2. Check model directory ──────────────────────────────────
sep
log "Checking abliterated model files..."

if [ ! -d "$MODEL_DIR" ]; then
    err "Model directory not found: $MODEL_DIR"
    echo ""
    echo "Create model directory and download abliterated EXL2 models:"
    echo "  mkdir -p $MODEL_DIR"
    echo "  cd $MODEL_DIR"
    echo ""
    echo "Qwen2.5-14B-Instruct-abliterated (4.65bpw EXL2):"
    echo "  huggingface-cli download bartowski/Qwen2.5-14B-Instruct-abliterated-exl2 \\"
    echo "    --revision 4.65bpw \\"
    echo "    --local-dir Qwen2.5-14B-Instruct-abliterated \\"
    echo "    --local-dir-use-symlinks False"
    echo ""
    echo "QwQ-32B-abliterated (4.0bpw EXL2):"
    echo "  huggingface-cli download huihui-ai/QwQ-32B-abliterated-exl2 \\"
    echo "    --revision 4.0bpw \\"
    echo "    --local-dir QwQ-32B-abliterated \\"
    echo "    --local-dir-use-symlinks False"
    echo ""
    echo "See: docs/TABBYAPI_SETUP.md"
    exit 1
fi
log "  ✓ Model directory: $MODEL_DIR"

# Check for expected model dirs (active config model IDs)
EXPECTED_MODELS=(
    "Huihui-Qwen3-14B-abliterated-v2-exl2"
)
for model in "${EXPECTED_MODELS[@]}"; do
    if [ -d "$MODEL_DIR/$model" ]; then
        # Check for safetensors files
        if ls "$MODEL_DIR/$model"/*.safetensors 1> /dev/null 2>&1; then
            log "  ✓ Model: $model"
        else
            warn "  ⚠ Model directory exists but no .safetensors files: $model"
        fi
    else
        warn "  ✗ Model not found: $model"
        warn "    Download from HuggingFace (see docs/TABBYAPI_SETUP.md)"
    fi
done

# ── 3. Check TabbyAPI server status ───────────────────────────
sep
log "Checking TabbyAPI server..."

if ! curl -sf "$TABBY_URL/health" > /dev/null 2>&1; then
    err "TabbyAPI not responding at $TABBY_URL"
    echo ""
    echo "Start TabbyAPI:"
    echo "  cd $TABBY_DIR"
    echo "  source venv/bin/activate"
    echo "  python main.py --model Huihui-Qwen3-14B-abliterated-v2-exl2"
    echo ""
    echo "Or via systemd:"
    echo "  sudo systemctl start tabby.service"
    echo ""
    echo "Or via Emily startup script:"
    echo "  ./scripts/start-emily.sh infra"
    exit 1
fi
log "  ✓ TabbyAPI is running at $TABBY_URL"

# ── 4. Check loaded models ────────────────────────────────────
sep
log "Querying loaded models..."

if ! command -v jq &>/dev/null; then
    warn "jq not installed — displaying raw JSON"
    MODELS_JSON=$(curl -s "$TABBY_URL/v1/models")
    echo "$MODELS_JSON"
    # Try to extract model ID without jq
    LOADED_MODEL=$(echo "$MODELS_JSON" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")
else
    MODELS_JSON=$(curl -s "$TABBY_URL/v1/models")
    echo "$MODELS_JSON" | jq '.'
    LOADED_MODEL=$(echo "$MODELS_JSON" | jq -r '.data[0].id' 2>/dev/null || echo "unknown")
fi

if [ "$LOADED_MODEL" = "unknown" ] || [ -z "$LOADED_MODEL" ]; then
    err "No model loaded in TabbyAPI"
    echo ""
    echo "Load a model:"
    echo "  curl -X POST $TABBY_URL/v1/model/load \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{\"name\": \"Huihui-Qwen3-14B-abliterated-v2-exl2\"}'"
    exit 1
fi

log "  ✓ Loaded model: $LOADED_MODEL"

# ── 5. Test inference ─────────────────────────────────────────
sep
log "Testing inference..."

TEST_PROMPT='{"model": "'"$LOADED_MODEL"'", "messages": [{"role": "user", "content": "Say hello in 3 words."}], "max_tokens": 20, "temperature": 0.7}'

RESPONSE=$(curl -s -X POST "$TABBY_URL/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "$TEST_PROMPT")

if command -v jq &>/dev/null; then
    REPLY=$(echo "$RESPONSE" | jq -r '.choices[0].message.content' 2>/dev/null || echo "")
else
    REPLY=$(echo "$RESPONSE" | grep -o '"content":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
fi

if [ -z "$REPLY" ]; then
    err "Inference test failed — no response content"
    echo ""
    echo "Raw response:"
    echo "$RESPONSE"
    exit 1
fi

log "  ✓ Inference working"
log "    Test response: $REPLY"

# ── 6. Verify Emily config ────────────────────────────────────
sep
log "Checking Emily config..."

EMILY_CONFIG="$HOME/Emily1.0/config.yaml"

if [ ! -f "$EMILY_CONFIG" ]; then
    err "Emily config not found: $EMILY_CONFIG"
    exit 1
fi

# Check tier_backend settings
if grep -q "nano:.*tabbyapi" "$EMILY_CONFIG" && \
   grep -q "voice_fast:.*tabbyapi" "$EMILY_CONFIG" && \
   grep -q "fast:.*tabbyapi" "$EMILY_CONFIG" && \
   grep -q "smart:.*tabbyapi" "$EMILY_CONFIG" && \
   grep -q "reasoning:.*tabbyapi" "$EMILY_CONFIG"; then
    log "  ✓ tier_backend configured for TabbyAPI"
else
    warn "  ⚠ tier_backend may not be fully configured for TabbyAPI"
    warn "    Verify config.yaml → llm.tier_backend → nano/voice_fast/fast/smart/reasoning = 'tabbyapi'"
fi

# Check configured model IDs for all Tabby text tiers
NANO_MODEL=$(awk '/^[[:space:]]+models:/{in_models=1; next} /^[[:space:]]+routing:/{in_models=0} in_models && /^[[:space:]]+nano:/{gsub(/"/,"",$2); print $2}' "$EMILY_CONFIG")
VOICE_FAST_MODEL=$(awk '/^[[:space:]]+models:/{in_models=1; next} /^[[:space:]]+routing:/{in_models=0} in_models && /^[[:space:]]+voice_fast:/{gsub(/"/,"",$2); print $2}' "$EMILY_CONFIG")
FAST_MODEL=$(awk '/^[[:space:]]+models:/{in_models=1; next} /^[[:space:]]+routing:/{in_models=0} in_models && /^[[:space:]]+fast:/{gsub(/"/,"",$2); print $2}' "$EMILY_CONFIG")
SMART_MODEL=$(awk '/^[[:space:]]+models:/{in_models=1; next} /^[[:space:]]+routing:/{in_models=0} in_models && /^[[:space:]]+smart:/{gsub(/"/,"",$2); print $2}' "$EMILY_CONFIG")
REASONING_MODEL=$(awk '/^[[:space:]]+models:/{in_models=1; next} /^[[:space:]]+routing:/{in_models=0} in_models && /^[[:space:]]+reasoning:/{gsub(/"/,"",$2); print $2}' "$EMILY_CONFIG")

for pair in \
  "nano:$NANO_MODEL" \
  "voice_fast:$VOICE_FAST_MODEL" \
  "fast:$FAST_MODEL" \
  "smart:$SMART_MODEL" \
  "reasoning:$REASONING_MODEL"; do
    tier="${pair%%:*}"
    model="${pair#*:}"
    if [ -n "$model" ]; then
        log "  ✓ Config tier model ($tier): $model"
    else
        warn "  ⚠ Missing model ID for tier: $tier"
    fi
done

# ── Summary ───────────────────────────────────────────────────
sep
log "TabbyAPI verification complete!"
sep
echo ""
echo "Next steps:"
echo "  1. Start Emily: python main.py"
echo "  2. Or full stack: ./scripts/start-emily.sh"
echo ""
echo "Verify Emily can reach TabbyAPI:"
echo "  python -c 'from llm.fleet import LLMFleet; import asyncio; from config import get_config; asyncio.run(LLMFleet(get_config().llm).startup())'"
echo ""
log "Ready to run!"
