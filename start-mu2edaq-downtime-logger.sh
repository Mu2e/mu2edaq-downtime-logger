#!/usr/bin/env bash
# Start mu2edaq-downtime-logger, activating the venv and bootstrapping if needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
PID_FILE="$SCRIPT_DIR/mu2edaq-downtime-logger.pid"
LOG_FILE="$SCRIPT_DIR/mu2edaq-downtime-logger.log"
DEFAULT_CONFIG="$SCRIPT_DIR/config/local.yaml"

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [-- EXTRA_ARGS...]

Start the mu2edaq-downtime-logger application.

Options:
  --config FILE     Path to YAML config (default: config/local.yaml)
  --log-level LVL   Log level: DEBUG, INFO, WARNING, ERROR  (default: INFO)
  --log-file FILE   Redirect output to FILE instead of stdout
  --foreground      Run in the foreground instead of background
  -h, --help        Show this help message

Any arguments after -- are passed directly to the application.
EOF
}

CONFIG="$DEFAULT_CONFIG"
LOG_LEVEL="INFO"
FOREGROUND=0
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)     CONFIG="$2";    shift 2 ;;
        --log-level)  LOG_LEVEL="$2"; shift 2 ;;
        --log-file)   LOG_FILE="$2";  shift 2 ;;
        --foreground) FOREGROUND=1;   shift   ;;
        -h|--help)    usage; exit 0           ;;
        --)           shift; EXTRA_ARGS=("$@"); break ;;
        *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

cd "$SCRIPT_DIR"

# Ensure venv exists; run bootstrap if not.
if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
    echo "--- Virtual environment not found; running bootstrap first."
    bash "$SCRIPT_DIR/bootstrap.sh"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Guard against a stale PID file.
if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(cat "$PID_FILE")"
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "mu2edaq-downtime-logger is already running (PID $OLD_PID)." >&2
        exit 1
    else
        echo "Removing stale PID file (PID $OLD_PID no longer running)."
        rm -f "$PID_FILE"
    fi
fi

CMD=(mu2edaq-downtime-logger --config "$CONFIG" --log-level "$LOG_LEVEL" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}")

if [[ $FOREGROUND -eq 1 ]]; then
    exec "${CMD[@]}"
fi

echo "--- Starting mu2edaq-downtime-logger in background"
echo "    Config:    $CONFIG"
echo "    Log:       $LOG_FILE"
echo "    PID file:  $PID_FILE"

nohup "${CMD[@]}" >> "$LOG_FILE" 2>&1 &
APP_PID=$!
echo "$APP_PID" > "$PID_FILE"
echo "--- Started with PID $APP_PID"
