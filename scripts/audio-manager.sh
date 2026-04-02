#!/usr/bin/env bash
# Emily-only Linux audio manager (PipeWire/PulseAudio via pactl).
# Does NOT change global defaults unless explicitly requested.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/logs/audio-manager.env"
cd "$ROOT_DIR"

usage() {
    cat <<'EOF'
Usage: ./scripts/audio-manager.sh <command> [args]

Commands:
  list-sinks                     List output devices (sinks)
  list-sources                   List input devices (sources)
  list-streams                   List active sink-input streams
  emily-pids                     Show running Emily process IDs
  set-input <source_substring>   Persist Emily input override (env file)
  set-output <sink_substring>    Persist Emily output override (env file)
  clear-overrides                Remove persisted Emily input/output overrides
  show-overrides                 Show current persisted overrides
  gui-help                       Show GUI workflow (pavucontrol)

Notes:
  - Persisted overrides are written to logs/audio-manager.env
  - start-emily.sh will source this file for Emily core if present
  - Selectors: numeric id or unique case-insensitive name substring
EOF
}

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Missing required command: $cmd" >&2
        exit 1
    fi
}

list_sinks() {
    pactl list short sinks
}

list_sources() {
    pactl list short sources
}

list_streams() {
    pactl list sink-inputs
}

emily_pids() {
    pgrep -f "main\.py --no-gui|main\.py --gui|uv run python main\.py" || true
}

resolve_node() {
    # Resolve a selector (numeric id or name substring) to a pactl node name.
    local selector="$1"
    local mode="$2"  # sinks or sources

    # If numeric, look up by id
    if [[ "$selector" =~ ^[0-9]+$ ]]; then
        pactl list short "$mode" | awk -v id="$selector" '$1 == id { print $2; exit }'
        return
    fi

    # Otherwise, case-insensitive substring match on the node name
    local match
    match="$(pactl list short "$mode" | awk -v pat="$selector" 'tolower($2) ~ tolower(pat) { print $2; exit }')"
    if [[ -z "$match" ]]; then
        echo "No $mode matching '$selector'" >&2
        exit 1
    fi
    echo "$match"
}

upsert_env_key() {
    local key="$1"
    local value="$2"
    mkdir -p "$(dirname "$ENV_FILE")"
    touch "$ENV_FILE"
    if grep -qE "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=\"${value}\"|" "$ENV_FILE"
    else
        echo "${key}=\"${value}\"" >> "$ENV_FILE"
    fi
}

remove_env_key() {
    local key="$1"
    if [[ -f "$ENV_FILE" ]]; then
        sed -i "/^${key}=/d" "$ENV_FILE"
    fi
}

set_input() {
    local selector="$1"
    local source_name
    source_name="$(resolve_node "$selector" sources)"
    upsert_env_key "EMILY_AUDIO__INPUT_DEVICE" "$source_name"
    echo "Saved EMILY_AUDIO__INPUT_DEVICE=$source_name"
}

set_output() {
    local selector="$1"
    local sink_name
    sink_name="$(resolve_node "$selector" sinks)"
    upsert_env_key "EMILY_AUDIO__OUTPUT_DEVICE" "$sink_name"
    echo "Saved EMILY_AUDIO__OUTPUT_DEVICE=$sink_name"
}

clear_overrides() {
    remove_env_key "EMILY_AUDIO__INPUT_DEVICE"
    remove_env_key "EMILY_AUDIO__OUTPUT_DEVICE"
    echo "Cleared Emily audio overrides."
}

show_overrides() {
    if [[ -f "$ENV_FILE" ]]; then
        cat "$ENV_FILE"
    else
        echo "No overrides file: $ENV_FILE"
    fi
}

gui_help() {
    cat <<'EOF'
GUI workflow (hybrid mode):
  1) Open pavucontrol
  2) Playback tab: move only Emily streams to your desired output
  3) Input Devices tab: choose the target mic
  4) Recording tab: ensure Emily captures from selected mic source
  5) Optional persistence:
       ./scripts/audio-manager.sh set-input <source>
       ./scripts/audio-manager.sh set-output <sink>
EOF
}

main() {
    require_cmd pactl
    local cmd="${1:-}"
    case "$cmd" in
        list-sinks) list_sinks ;;
        list-sources) list_sources ;;
        list-streams) list_streams ;;
        emily-pids) emily_pids ;;
        set-input)
            [[ $# -eq 2 ]] || { usage; exit 1; }
            set_input "$2"
            ;;
        set-output)
            [[ $# -eq 2 ]] || { usage; exit 1; }
            set_output "$2"
            ;;
        clear-overrides) clear_overrides ;;
        show-overrides) show_overrides ;;
        gui-help) gui_help ;;
        ""|-h|--help|help) usage ;;
        *)
            echo "Unknown command: $cmd" >&2
            usage
            exit 1
            ;;
    esac
}

main "$@"
