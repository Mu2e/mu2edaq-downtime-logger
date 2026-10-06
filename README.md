# mu2edaq-downtime-logger

Monitors the Mu2e DAQ system and records downtime events. Detection is plugin-based
(any combination of ZeroMQ, UDP, SOAP, disk-activity, and log-file scanners feeds a
weighted score). When the score crosses a configurable threshold a dismissible popup
prompts the shifter for details; the event is closed automatically when the DAQ
recovers and persisted to a swappable storage backend (SQLite by default).

## Quick start

```bash
./bootstrap.sh                  # create venv and install all dependencies
./start-mu2edaq-downtime-logger.sh   # start in background (local config)
./stop-mu2edaq-downtime-logger.sh    # stop cleanly
```

## Install

### Using bootstrap (recommended)

```bash
./bootstrap.sh           # runtime deps only
./bootstrap.sh --dev     # + pytest / pytest-qt
./bootstrap.sh --postgres  # + psycopg2-binary (PostgreSQL backend)
./bootstrap.sh --recreate  # delete and rebuild the venv from scratch
```

### Manual

```bash
python -m venv venv && source venv/bin/activate

# Editable install (uses pyproject.toml):
pip install -e .[dev]

# Or via requirements files:
pip install -r requirements.txt           # runtime only
pip install -r requirements-dev.txt       # runtime + test deps
pip install -r requirements-postgres.txt  # runtime + psycopg2
```

## Run

```bash
# Foreground, pointing at the real DAQ:
source venv/bin/activate
mu2edaq-downtime-logger --config config/config.example.yaml

# Background (with PID file and log):
./start-mu2edaq-downtime-logger.sh --config config/config.example.yaml
./start-mu2edaq-downtime-logger.sh --foreground   # stay in terminal
./start-mu2edaq-downtime-logger.sh --log-file /var/log/downtime.log

# Stop:
./stop-mu2edaq-downtime-logger.sh
./stop-mu2edaq-downtime-logger.sh --timeout 30
./stop-mu2edaq-downtime-logger.sh --force   # immediate SIGKILL
```

The start script automatically runs `bootstrap.sh` if no virtual environment is
present, so a fresh machine only needs `./start-mu2edaq-downtime-logger.sh`.

## Configuration

See `config/config.example.yaml` for the full schema.
`config/local.yaml` is a ready-to-use desktop development config that needs no
external DAQ infrastructure.

Top-level keys:

| Key | Purpose |
|-----|---------|
| `storage` | Storage backend plugin (default: SQLite) |
| `metric` | Scoring / threshold module |
| `detectors` | List of detector plugins, each with a `weight` and `options` |
| `webserver` | Optional read-only HTTP interface |

Plugins are referenced as `module.path:ClassName`. To add a new detector, drop a
module anywhere on `PYTHONPATH` that subclasses
`downtime_logger.detectors.base.Detector` and point at it from YAML.

### Key metric options

| Option | Default | Description |
|--------|---------|-------------|
| `trip_threshold` | 0.6 | Weighted score ≥ this opens a downtime event |
| `clear_threshold` | 0.2 | Score ≤ this while an event is open closes it |
| `debounce_seconds` | 5 | Quiet period before state changes are acted on |

## Architecture

```
detectors (QThreads) --signals--> StateMachine --DowntimeEvent--> Storage
                                       |                            ^
                                       +--> Qt UI (popup + history) |
                                       +--> SnapshotStore <-- WebServer (thread)
```

- **Detectors** run each in their own `QThread`, emitting `state_changed` signals.
- **StateMachine** lives on the Qt main thread; its debounce `QTimer` requires it.
- **WebServer** runs in a daemon thread; it reads from `SnapshotStore` (thread-safe)
  and queries storage directly (SQLAlchemy gives each thread its own connection).
- **Storage** is called only from the Qt main thread (or with SQLAlchemy's
  `check_same_thread=False` when the web server reads).

## Qt interface

The main window has two panels:

**Live status (top)** — current detector states, weighted score, and active event.
Right-click for a context menu with a manual "New event…" option.

**Downtime history (bottom)** — table of all recorded events, most-recent first.
- Double-click a row to open the event editor.
- Right-click for a context menu: **Edit…**, **End downtime now** (open events),
  **Delete event…**, **New event…**.
- Select multiple rows with Shift+click or Ctrl+click to apply context menu
  operations to all selected events at once. Bulk-delete shows a confirmation
  dialog listing all affected event IDs. "End downtime now" is offered for
  multi-selections only when exactly one of the selected events is currently active.

Delete operations are intentionally restricted to the Qt application.

## Web interface

When `webserver.enabled: true` in the config the application serves a read-only
HTTP interface on the configured port.

### Live status page

`GET /` — auto-refreshing HTML page showing current score, detector states, active
event, and recent event history. Refreshes every `refresh_seconds` seconds.

### Summary and report page

`GET /report` — date/time range picker with aggregate statistics for the selected
window:

- Summary cards: total events, total downtime, average duration, longest event.
- Breakdown by category and by subsystem (event count + total / average downtime).
- Full event table with durations clamped to the selected range (an event that
  started before the range window only counts the time that falls within it).

### JSON API

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Current score, per-detector states, active event |
| `GET /api/events` | Recent events (up to `history_limit`) |
| `GET /api/events/<id>` | Single event by ID |
| `GET /api/report?from=YYYY-MM-DDTHH:MM&to=YYYY-MM-DDTHH:MM` | Aggregate statistics and event list for a time range |
| `GET /healthz` | Liveness probe (returns `ok`) |

Editing event details is intentionally **not** exposed over HTTP — that happens
through the Qt UI on the console machine.

## Diagnostic tools

The `tools/` directory contains scripts that emit the messages each detector
consumes. Use them to verify a deployment without live DAQ hardware. See
`tools/README.md` for usage examples.

| Tool | Simulates |
|------|-----------|
| `tools/zmq_publish.py` | ZmqDetector heartbeats / state messages |
| `tools/udp_broadcast.py` | UdpDetector heartbeat datagrams |
| `tools/soap_server.py` | SoapDetector run-control SOAP endpoint |
| `tools/disk_writer.py` | DiskActivityDetector file modifications |
| `tools/log_writer.py` | LogfileDetector log-line patterns |

## Man pages

Man pages live under `man/manN/`, one page per command, named after the
command itself:

| Section | Pages |
|---------|-------|
| `man1` | `mu2edaq-downtime-logger`, `start-mu2edaq-downtime-logger.sh`, `stop-mu2edaq-downtime-logger.sh`, `bootstrap.sh`, and the tools `zmq_publish.py`, `udp_broadcast.py`, `soap_server.py`, `disk_writer.py`, `log_writer.py` |
| `man3` | `downtime_logger` (detector, metric and storage plugin interfaces) |
| `man5` | `mu2edaq-downtime-logger.yaml` (configuration file) |
| `man7` | `mu2edaq-downtime-logger-api` (HTTP API and detector wire protocols) |

To view without installing:

```bash
man -l man/man1/mu2edaq-downtime-logger.1
man -l man/man5/mu2edaq-downtime-logger.yaml.5
man -l man/man7/mu2edaq-downtime-logger-api.7
```

Or put the tree on the search path:

```bash
MANPATH="$PWD/man:$(manpath)" man start-mu2edaq-downtime-logger.sh
```

Design, interface and operations notes are in `docs/`.

## Tests

```bash
source venv/bin/activate
pytest
```
