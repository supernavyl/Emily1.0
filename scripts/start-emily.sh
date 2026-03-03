#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Emily full-stack startup script
# Brings up all services in dependency order:
#   1. Docker infra (Qdrant, SearXNG, Prometheus, Grafana, Jaeger)
#   2. TabbyAPI (text/voice inference)
#   3. Ollama (embedding/vision fallback only)
#   4. FastAPI web API
#   5. Emily core (voice OS)
#
# Usage:
#   ./scripts/start-emily.sh          # start everything
#   ./scripts/start-emily.sh infra    # docker + tabbyapi (+ ollama fallback services)
#   ./scripts/start-emily.sh api      # API server only
#   ./scripts/start-emily.sh core     # Emily voice OS only
#   ./scripts/start-emily.sh chat     # Desktop chat app only
#   ./scripts/start-emily.sh status   # health check all services
#   ./scripts/start-emily.sh stop     # stop everything
# ─────────────────────────────────────────────────────────────

set -euo pipefail

EMILY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$EMILY_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[emily]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; }
sep()  { echo -e "${CYAN}────────────────────────────────────────${NC}"; }

is_port_in_use() {
    local port="$1"
    if command -v ss > /dev/null 2>&1; then
        ss -ltn 2>/dev/null | grep -qE "[\[\: ]${port}[[:space:]]"
        return $?
    fi
    return 1
}

# ── Docker infrastructure ──────────────────────────────────
start_infra() {
    sep
    log "Starting Docker infrastructure..."
    docker compose up -d
    log "Waiting for services to become healthy..."
    sleep 3

    local services=("emily-qdrant:6333" "emily-searxng:8888" "emily-prometheus:9090" "emily-grafana:3000" "emily-jaeger:16686")
    for svc in "${services[@]}"; do
        local name="${svc%%:*}"
        local port="${svc##*:}"
        if curl -sf "http://localhost:$port" > /dev/null 2>&1 || curl -sf "http://localhost:$port/healthz" > /dev/null 2>&1; then
            log "  ✓ $name (port $port)"
        else
            warn "  ✗ $name (port $port) — not ready yet"
        fi
    done
}

# ── Ollama ─────────────────────────────────────────────────
start_ollama() {
    sep
    if pgrep -x ollama > /dev/null 2>&1; then
        log "Ollama already running (PID $(pgrep -x ollama))"
    else
        log "Starting Ollama..."
        ollama serve &
        sleep 2
        log "Ollama started"
    fi

    log "Loaded models:"
    ollama list 2>/dev/null | head -15
}

# ── TabbyAPI ────────────────────────────────────────────────
start_tabbyapi() {
    sep
    local TABBY_DIR="$HOME/TabbyAPI"
    local TABBY_VENV="$TABBY_DIR/venv/bin/python"
    local TABBY_MODEL_DIR="${TABBY_MODEL_DIR:-$HOME/models/tabby}"
    local DEFAULT_MODEL="${TABBY_MODEL_NAME:-Huihui-Qwen3-14B-abliterated-v2-exl2}"
    local TABBY_LOG="$EMILY_ROOT/logs/tabbyapi.log"

    # Check if TabbyAPI is already running
    if curl -sf http://localhost:5000/v1/models > /dev/null 2>&1; then
        log "TabbyAPI already running on port 5000"
        local loaded_model
        loaded_model=$(curl -s http://localhost:5000/v1/models | jq -r '.data[0].id' 2>/dev/null || echo "unknown")
        log "  Current model: $loaded_model"
        return 0
    fi

    # Verify TabbyAPI installation
    if [ ! -d "$TABBY_DIR" ]; then
        warn "TabbyAPI not found at $TABBY_DIR"
        warn "  See docs/TABBYAPI_SETUP.md for installation instructions"
        warn "  Skipping TabbyAPI startup — text/voice tiers will not be Tabby-first"
        return 1
    fi

    if [ ! -f "$TABBY_VENV" ]; then
        err "TabbyAPI virtualenv not found: $TABBY_VENV"
        warn "  Run: cd $TABBY_DIR && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        return 1
    fi

    if [ ! -f "$TABBY_MODEL_DIR/$DEFAULT_MODEL/config.json" ]; then
        err "TabbyAPI model config not found: $TABBY_MODEL_DIR/$DEFAULT_MODEL/config.json"
        warn "  Set TABBY_MODEL_NAME and TABBY_MODEL_DIR, or download the model first"
        warn "  Example: TABBY_MODEL_NAME=Huihui-Qwen3-14B-abliterated-v2-exl2 TABBY_MODEL_DIR=$HOME/models/tabby ./scripts/start-emily.sh infra"
        return 1
    fi

    log "Starting TabbyAPI ExLlamaV2 inference server..."
    cd "$TABBY_DIR"
    "$TABBY_VENV" main.py --model-dir "$TABBY_MODEL_DIR" --model-name "$DEFAULT_MODEL" --disable-auth true > "$TABBY_LOG" 2>&1 &
    local tabby_pid=$!
    cd "$EMILY_ROOT"

    log "TabbyAPI starting (PID $tabby_pid)..."
    log "  Waiting for model load (this may take 10-30s)..."

    # Wait for TabbyAPI to become ready (max 60s)
    local wait_time=0
    local max_wait=60
    while [ $wait_time -lt $max_wait ]; do
        if curl -sf http://localhost:5000/v1/models > /dev/null 2>&1; then
            local loaded_model
            loaded_model=$(curl -s http://localhost:5000/v1/models | jq -r '.data[0].id' 2>/dev/null || echo "$DEFAULT_MODEL")
            log "  ✓ TabbyAPI ready (model: $loaded_model)"
            log "    Logs: tail -f $EMILY_ROOT/logs/tabbyapi.log"
            return 0
        fi
        sleep 2
        wait_time=$((wait_time + 2))
        echo -n "."
    done

    echo ""
    err "TabbyAPI failed to start within ${max_wait}s"
    warn "  Check logs: tail -f $EMILY_ROOT/logs/tabbyapi.log"
    warn "  Text/voice tiers remain unavailable until TabbyAPI is healthy"
    return 1
}

# ── FastAPI web API ────────────────────────────────────────
start_api() {
    sep
    log "Starting FastAPI API server (port 8000)..."
    uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload &
    local api_pid=$!
    log "API server started (PID $api_pid)"
    log "  Dashboard:  http://localhost:8000"
    log "  API docs:   http://localhost:8000/docs"
    log "  Voice dash: http://localhost:8000/voice-dashboard"
}

# ── Emily core voice OS ───────────────────────────────────
start_core() {
    sep
    if pgrep -f "main\.py --no-gui|main\.py --gui" > /dev/null 2>&1; then
        log "Emily core already running (PID $(pgrep -f "main\.py --no-gui|main\.py --gui" | tr '\n' ' '))"
        return 0
    fi
    if is_port_in_use 5555 || is_port_in_use 5556; then
        err "Emily bus ports are already in use (5555/5556)"
        warn "  Run: ./scripts/start-emily.sh stop"
        warn "  Then retry: ./scripts/start-emily.sh core"
        return 1
    fi
    local CORE_LOG="$EMILY_ROOT/logs/emily.log"
    log "Starting Emily core (voice OS)..."
    uv run python main.py --no-gui >> "$CORE_LOG" 2>&1 &
    local core_pid=$!
    echo $core_pid > "$EMILY_ROOT/logs/emily.pid"
    log "Emily core started (PID $core_pid)"
    log "  Logs: tail -f $CORE_LOG"
}

# ── Emily core with GUI dashboards ────────────────────────
start_core_gui() {
    sep
    if pgrep -f "main\.py --no-gui|main\.py --gui" > /dev/null 2>&1; then
        log "Emily core already running (PID $(pgrep -f "main\.py --no-gui|main\.py --gui" | tr '\n' ' '))"
        return 0
    fi
    if is_port_in_use 5555 || is_port_in_use 5556; then
        err "Emily bus ports are already in use (5555/5556)"
        warn "  Run: ./scripts/start-emily.sh stop"
        warn "  Then retry: ./scripts/start-emily.sh gui"
        return 1
    fi
    local CORE_LOG="$EMILY_ROOT/logs/emily.log"
    log "Starting Emily core with Brain + Voice Dashboards..."
    uv run python main.py --gui >> "$CORE_LOG" 2>&1 &
    local core_pid=$!
    echo $core_pid > "$EMILY_ROOT/logs/emily.pid"
    log "Emily GUI started (PID $core_pid)"
    log "  Logs: tail -f $CORE_LOG"
}

# ── Desktop chat app ──────────────────────────────────────
start_chat() {
    sep
    log "Starting Emily desktop chat app..."
    uv run python -m emily_chat.main &
    local chat_pid=$!
    log "Desktop chat started (PID $chat_pid)"
}

# ── Health check ───────────────────────────────────────────
status_check() {
    sep
    log "Service health check:"

    # Docker
    if command -v docker &>/dev/null; then
        local containers
        containers=$(docker compose ps --format '{{.Name}} {{.Status}}' 2>/dev/null)
        if [ -n "$containers" ]; then
            while IFS= read -r line; do
                if echo "$line" | grep -qi "up"; then
                    log "  ✓ $line"
                else
                    warn "  ✗ $line"
                fi
            done <<< "$containers"
        else
            warn "  No Docker containers running"
        fi
    fi

    # Ollama
    if pgrep -x ollama > /dev/null 2>&1; then
        log "  ✓ Ollama (PID $(pgrep -x ollama))"
    else
        warn "  ✗ Ollama not running"
    fi

    # TabbyAPI
    if curl -sf http://localhost:5000/v1/models > /dev/null 2>&1; then
        local tabby_model
        tabby_model=$(curl -s http://localhost:5000/v1/models | jq -r '.data[0].id' 2>/dev/null || echo "unknown")
        log "  ✓ TabbyAPI (port 5000, model: $tabby_model)"
    else
        warn "  ✗ TabbyAPI not responding on port 5000"
    fi

    # API
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        log "  ✓ FastAPI (port 8000)"
    else
        warn "  ✗ FastAPI not responding on port 8000"
    fi


    # Metrics
    if curl -sf http://localhost:9091/metrics > /dev/null 2>&1; then
        log "  ✓ Prometheus metrics (port 9091)"
    else
        warn "  ✗ Prometheus metrics endpoint not responding"
    fi

    sep
    log "Dashboard URLs:"
    log "  Emily API:      http://localhost:8000"
    log "  API docs:       http://localhost:8000/docs"
    log "  Voice dash:     http://localhost:8000/voice-dashboard"
    log "  Grafana:        http://localhost:3000  (admin / emily_local_only)"
    log "  Prometheus:     http://localhost:9090"
    log "  Jaeger tracing: http://localhost:16686"
    log "  SearXNG:        http://localhost:8888"
    log "  Qdrant:         http://localhost:6333/dashboard"
}

# ── Stop everything ───────────────────────────────────────
stop_all() {
    sep
    log "Stopping all Emily services..."

    # Kill Python processes
    pkill -f "uvicorn api.app:app" 2>/dev/null && log "  Stopped API server" || true

    # Kill Emily core — pkill pattern covers both uv wrapper and direct python invocation
    if pgrep -f "main\.py --no-gui|main\.py --gui" > /dev/null 2>&1; then
        pkill -f "main\.py --no-gui" 2>/dev/null || true
        pkill -f "main\.py --gui" 2>/dev/null || true
        sleep 1
        # Force kill if still alive
        pkill -9 -f "main\.py --no-gui" 2>/dev/null || true
        pkill -9 -f "main\.py --gui" 2>/dev/null || true
        log "  Stopped Emily core"
    fi

    pkill -f "emily_chat.main" 2>/dev/null && log "  Stopped desktop chat" || true

    # Stop TabbyAPI
    pkill -f "TabbyAPI.*main.py" 2>/dev/null && log "  Stopped TabbyAPI" || true

    # Stop Docker
    docker compose down 2>/dev/null && log "  Stopped Docker services" || true

    log "All services stopped"
}

# ── Main ──────────────────────────────────────────────────
case "${1:-all}" in
    infra)
        start_infra
        start_tabbyapi
        start_ollama
        ;;
    api)
        start_api
        ;;
    core)
        start_core
        ;;
    gui)
        start_core_gui
        ;;
    chat)
        start_chat
        ;;
    status)
        status_check
        ;;
    stop)
        stop_all
        ;;
    all)
        start_infra
        start_tabbyapi
        start_ollama
        start_api
        start_core
        sep
        log "Emily is fully operational."
        status_check
        ;;
    *)
        echo "Usage: $0 {all|infra|api|core|gui|chat|status|stop}"
        exit 1
        ;;
esac
