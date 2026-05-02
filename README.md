# mu2edaq-downtime-logger

Monitors the Mu2e DAQ system and records downtime events. Detection is plugin-based
(any combination of ZeroMQ, UDP, SOAP, disk-activity, and log-file scanners feeds a
weighted score). When the score crosses a configurable threshold a dismissible popup
prompts the shifter for details; the event is closed automatically when the DAQ
recovers and persisted to a swappable storage backend (SQLite by default).

## Install

```bash
python -m venv .venv && source .venv/bin/activate

# Editable install (recommended for developers — uses pyproject.toml):
pip install -e .[dev]

# Or via requirements files:
pip install -r requirements.txt          # runtime only
pip install -r requirements-dev.txt      # runtime + test deps
pip install -r requirements-postgres.txt # runtime + psycopg2
```

## Run

```bash
mu2edaq-downtime-logger --config config/config.example.yaml
```

## Configuration

See `config/config.example.yaml` for the full schema. Top-level keys:

- `storage` — a single storage backend plugin (default: SQLite)
- `metric` — the scoring/threshold module (default: `WeightedRatioMetric`)
- `detectors` — list of enabled detector plugins, each with a `weight` and `options`

Plugins are referenced as `module.path:ClassName`. Add a new detector by dropping a
module under `downtime_logger.detectors` (or any importable location) that subclasses
`Detector`, then point at it from YAML.

## Architecture

```
detectors (QThreads) --signals--> StateMachine --DowntimeEvent--> Storage
                                       |                            ^
                                       +--> Qt UI (popup + history) |
                                       +--> SnapshotStore <-- WebServer (thread)
                                                                 (read-only HTTP)
```

## Remote view

When `webserver.enabled: true` in the config, the application also serves a
read-only status page and JSON API on the configured port:

- `GET /` — auto-refreshing HTML status page
- `GET /api/status` — current score, per-detector states, active event
- `GET /api/events` — recent events
- `GET /api/events/<id>` — single event
- `GET /healthz` — liveness probe

Editing event details is intentionally *not* exposed over HTTP — that
happens through the Qt UI on the console machine.

The `Metric` class is intentionally isolated in `core/metric.py`; replace it (or
swap implementations via YAML) without touching detectors, storage, or UI.

## Tests

```bash
pytest
```
