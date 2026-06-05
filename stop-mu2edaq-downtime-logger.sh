#!/usr/bin/env bash
# Stop mu2edaq-downtime-logger cleanly, escalating to SIGKILL if needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/mu2edaq-downtime-logger.pid"
GRACEFUL_TIMEOUT=10   # seconds to wait for clean shutdown before SIGKILL

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Stop the mu2edaq-downtime-logger application.

Options:
  --timeout SECS  Seconds to wait for graceful shutdown (default: $GRACEFUL_TIMEOUT)
  --force         Send SIGKILL immediately without attempting graceful shutdown
  -h, --help      Show this help message
EOF
}

FORCE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --timeout) GRACEFUL_TIMEOUT="$2"; shift 2 ;;
        --force)   FORCE=1;               shift   ;;
        -h|--help) usage; exit 0                  ;;
        *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

cd "$SCRIPT_DIR"

if [[ ! -f "$PID_FILE" ]]; then
    echo "No PID file found at $PID_FILE — application may not be running."
    exit 0
fi

PID="$(cat "$PID_FILE")"

if ! kill -0 "$PID" 2>/dev/null; then
    echo "Process $PID is not running. Removing stale PID file."
    rm -f "$PID_FILE"
    exit 0
fi

if [[ $FORCE -eq 1 ]]; then
    echo "--- Sending SIGKILL to PID $PID"
    kill -9 "$PID" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "--- Done."
    exit 0
fi

echo "--- Sending SIGTERM to PID $PID (waiting up to ${GRACEFUL_TIMEOUT}s)"
kill -TERM "$PID" 2>/dev/null || true

ELAPSED=0
while kill -0 "$PID" 2>/dev/null; do
    if [[ $ELAPSED -ge $GRACEFUL_TIMEOUT ]]; then
        echo "--- Process did not exit after ${GRACEFUL_TIMEOUT}s; sending SIGKILL"
        kill -9 "$PID" 2>/dev/null || true
        break
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

rm -f "$PID_FILE"

# Clean up temp files the app may have created in /tmp.
TMP_TEST_DIR="/tmp/daq-test"
if [[ -d "$TMP_TEST_DIR" ]]; then
    echo "--- Cleaning up $TMP_TEST_DIR"
    rm -rf "$TMP_TEST_DIR"
fi

echo "--- mu2edaq-downtime-logger stopped."
