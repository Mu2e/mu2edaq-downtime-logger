#!/usr/bin/env bash
# Bootstrap mu2edaq-downtime-logger: create/update venv and install dependencies.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
PYTHON="${PYTHON:-python3}"

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Prepare the Python virtual environment and install / update all dependencies.

Options:
  --postgres    Also install psycopg2-binary (PostgreSQL backend support)
  --dev         Also install dev/test dependencies (pytest, pytest-qt)
  --recreate    Delete and recreate the venv from scratch
  -h, --help    Show this help message
EOF
}

EXTRAS=""
RECREATE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --postgres) EXTRAS="${EXTRAS},postgres" ;;
        --dev)      EXTRAS="${EXTRAS},dev"      ;;
        --recreate) RECREATE=1                  ;;
        -h|--help)  usage; exit 0               ;;
        *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
    shift
done

# Strip leading comma if any extras were set
EXTRAS="${EXTRAS#,}"

cd "$SCRIPT_DIR"

if [[ $RECREATE -eq 1 && -d "$VENV_DIR" ]]; then
    echo "--- Removing existing venv at $VENV_DIR"
    rm -rf "$VENV_DIR"
fi

if [[ ! -d "$VENV_DIR" ]]; then
    echo "--- Creating virtual environment with $PYTHON"
    "$PYTHON" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "--- Upgrading pip/setuptools/wheel"
pip install --quiet --upgrade pip setuptools wheel

if [[ -n "$EXTRAS" ]]; then
    echo "--- Installing package with extras: [$EXTRAS]"
    pip install --upgrade -e ".[$EXTRAS]"
else
    echo "--- Installing package"
    pip install --upgrade -e .
fi

echo "--- Bootstrap complete."
echo "    Activate the environment with:  source venv/bin/activate"
echo "    Then run:  mu2edaq-downtime-logger --config config/local.yaml"
