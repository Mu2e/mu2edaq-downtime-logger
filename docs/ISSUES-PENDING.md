# Staged issues — mu2edaq-downtime-logger

Sept 2026 DAQ mega-review (`mu2e-sept-mega-review`). First drafted 2026-09-30 by
an agent that was terminated mid-run; verified, corrected and completed
2026-10-06. GitHub writes are not permitted in this review (contract §9.1), so
every finding is staged here in the §6 body format for the orchestrator's filing
script. Target repository for all of them: `Mu2e/mu2edaq-downtime-logger`
(public, issues enabled). Label each with `mega-review` plus its category.

**Dedup.** `gh issue list -R Mu2e/mu2edaq-downtime-logger --state all --limit 300`
returns three issues, none carrying a mega-review fingerprint:
#6 (open) "bootstrap.sh does not install the mu2edaq-discovery sibling, so a fresh
bootstrap fails"; #4 (closed) "requires-python ">=3.10" blocks install on
AlmaLinux 9"; #1 (closed) discovery support. No staged finding overlaps #1 or #6.
DTL-010 shares two title tokens with closed #4 and is filed new (rule 3: closed,
no fingerprint). Note for the orchestrator: #6 appears to be resolved on `main`
by `c9a44ed` (bootstrap installs the sibling, `bootstrap.sh:58-62`) and `f017f81`
(dependency no longer declared, `pyproject.toml:20-25`) but is still open.

**Count.** Fifteen individual issues and one roll-up (DTL-020) carrying five S4
items, per contract §0.5.

**Changes from the 2026-09-30 draft.** DTL-002 table and latch statement
corrected (disk alone is 0.273, not 0.333; soap/log/udp do not latch with all
five known). DTL-003 raised S3 → S2 after reproducing the editor drift and
retitled. DTL-004 lowered S3 → S4 (insert cost does not grow with an unindexed
rowid table). DTL-001 evidence corrected (launcher path, grammar sub-claim).
DTL-007 corrected (README does list `/report`) and rolled up with DTL-008/009.
DTL-011 example corrected (`current` does not contain `run`). DTL-012..018 new or
renumbered as listed in `docs/ARCHITECTURE.md`.

**Second pass (2026-10-06, resuming agent).** Line citations, the score table
and the external facts (dashboard, crs-app, snapshot-viewer, discovery, DNS)
re-checked against source. DTL-021 (S2) new and reproduced with the real
`Controller`. To stay within fifteen, DTL-012 (S4) moved into the DTL-020
roll-up. DTL-001 gained a second reproduction through the package's own
`ZmqDetector` on a `QThread`. DTL-014 gained the *New event…* route to an
unclosable row.

---

## DTL-001 — [config] ZeroMQ detector is a SUB socket aimed at a port the dashboard binds as PULL

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `config/config.example.yaml:35`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
The example config connects the ZeroMQ detector's `zmq.SUB` socket to
`tcp://daq01:5555`. Port 5555 is where `mu2edaq-dashboard` binds `zmq.PULL`; SUB
cannot pair with PULL, so the detector receives nothing and reports DOWN after
`heartbeat_timeout_s`. `daq01` itself does not resolve. No deployed configuration
uses this block today.

## Evidence
```
$ grep -n 'zmq.SUB\|connect(' src/downtime_logger/detectors/zeromq_detector.py
50:        self._sock = self._ctx.socket(zmq.SUB)
52:        self._sock.connect(self._endpoint)
$ grep -n 'endpoint' config/config.example.yaml
35:      endpoint: "tcp://daq01:5555"
$ grep -n 'zmq.PULL\|sock.bind' ../mu2edaq-dashboard/dashboard.py
240:    sock = context.socket(zmq.PULL)
242:        sock.bind(f"tcp://{ZMQ_HOST}:{zmq_port}")
```

Reproduced with pyzmq 27.1.0 / libzmq 4.3.5: a SUB connected to a PULL bind
received 0 of 5 frames while the PULL received all 5 from a PUSH peer; the SUB
monitor showed `CONNECTED` then `DISCONNECTED`. `connect("tcp://daq01:5555")`
returns without error although the host does not resolve.

Through the package's own `ZmqDetector` on a `QThread` (wired as `app.py:120-139`),
`heartbeat_timeout_s: 3`, a feeder sending dashboard-schema JSON every 250 ms:
```
( 0.26 s) sub_to_pub    up    '{"timestamp": ...'      # control: PUB peer
( 2.86 s) sub_to_daq01  down  'no zmq messages within timeout'
( 2.91 s) sub_to_pull   down  'no zmq messages within timeout'
PULL received from PUSH: 39
```

Two parts of the cross-package report (Mu2e/mu2edaq-dashboard DASH-002) do not
hold:
- *Grammar.* Unrecognised frames are heartbeats and read **UP**
  (`zeromq_detector.py:95-97`). The canonical dashboard JSON contains no token and
  would read UP; a message containing `shutdown` would read DOWN. Not a cause of
  DOWN.
- *"Permanently DOWN".* With the example weights the stuck detector is outvoted:
  0.227 with the other four UP, 0.357 with SOAP and logfile UNKNOWN, against
  `trip_threshold: 0.6`; as the only DOWN detector it trips only if the disk
  detector is UNKNOWN too. Its real effect is DTL-002: 0.227 > `clear_threshold: 0.2`,
  and no UP/UNKNOWN assignment of the other four clears an open event while it is
  DOWN; the trip margin also shrinks (a 60 s disk gap scores 0.786 instead of
  0.429 when SOAP/logfile are UNKNOWN).

Not deployed: `mu2edaq-controlroom-setup/server/crs-app:114-118` runs the start
script with no arguments, `start-mu2edaq-downtime-logger.sh:9` defaults to
`config/local.yaml`, which has no ZMQ detector (`config/local.yaml:22-46`). The
only ZMQ PUB producer for this detector in the superproject is the package's own
mock, `tools/zmq_publish.py:12` (binds `tcp://*:5555`), which is where the example
port came from.

## Why it matters
`README.md:45-47` presents `config.example.yaml` as "pointing at the real DAQ".
Whoever follows it gets a detector that connects silently, never receives, and
reports DOWN with the plausible detail `no zmq messages within timeout`
(`zeromq_detector.py:101`) — indistinguishable from a dead publisher — and, through
DTL-002, holds every later downtime event open. S3, not S2: no shipped launch path
loads the file.

## Suggested fix
Replace the endpoint with an explicit placeholder and a comment: "must be a
`ZMQ_PUB` that binds; the mu2edaq-dashboard bus on 5555 is PUSH/PULL and cannot be
read by this detector". Do not change the dashboard. If consuming the dashboard
bus is ever wanted, that is a new PULL-binding detector with a JSON parser, not a
retargeted SUB.

## Related
- Mu2e/mu2edaq-dashboard DASH-002 (staged, fingerprint `5071a0e6`), which should
  be reduced to S3 or to a cross-reference to this issue.
- DTL-002, DTL-006; `docs/INTERFACES.md` §3 has the full analysis.

<!-- mega-review-fingerprint: d86b04b4 -->

---

## DTL-002 — [metric] clear_threshold sits above the floor a single stuck detector holds, so events can never close

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `src/downtime_logger/core/metric.py:68-69`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
While an event is open, `WeightedRatioMetric` keeps it open while
`score > clear_threshold`. A detector stuck DOWN alone contributes
`wᵢ / Σw_known`. In both shipped configurations at least one detector exceeds the
shipped `clear_threshold: 0.2` on its own, so once it is stuck no event can close
by itself.

## Evidence
```
$ sed -n '66,71p' src/downtime_logger/core/metric.py
        score = (down_w / known_w) if known_w > 0 else 0.0

        if previously_down:
            is_down = score > self.clear_threshold
        else:
            is_down = score >= self.trip_threshold
$ grep -n 'clear_threshold\|weight:' config/config.example.yaml config/local.yaml
config/config.example.yaml:26:    clear_threshold: 0.2    # score <= this while open -> close event
config/config.example.yaml:33:    weight: 0.5
config/config.example.yaml:42:    weight: 0.3
config/config.example.yaml:51:    weight: 0.4
config/config.example.yaml:65:    weight: 0.6
config/config.example.yaml:78:    weight: 0.4
config/local.yaml:19:    clear_threshold: 0.2
config/local.yaml:25:    weight: 1.0
config/local.yaml:33:    weight: 1.0
config/local.yaml:41:    weight: 1.0
```

Single stuck detector, computed with the package's `WeightedRatioMetric`:

| Configuration | Stuck detector | Others | Score | Latches (> 0.2) |
|---|---|---|---|---|
| example | zmq 0.5 | four UP | 0.227 | yes |
| example | disk 0.6 | four UP | 0.273 | yes |
| example | soap or log 0.4 | four UP | 0.182 | no |
| example | soap 0.4 | three UP, log UNKNOWN | 0.222 | yes |
| example | udp 0.3 | four UP | 0.136 | no |
| local | any (1.0) | two UP | 0.333 | yes |

## Why it matters
The first downtime after any detector dies — a stopped publisher, an unmounted
data path, a missing log file that later appears — never closes. Its recorded
duration runs until a shifter notices and ends it, so the downtime accounting the
tool exists for is wrong, and the UI shows a small non-zero score that reads as
"recovering". Workaround: *End downtime now*, or lower `clear_threshold`.

## Suggested fix
1. Ship `clear_threshold: 0.1` in `config.example.yaml` (below
   `min(w)/Σw = 0.136`) and document the rule in the comment.
2. Validate in `AppConfig.from_dict`, which sees both the weights and the metric
   options: warn when `clear_threshold >= min(w)/Σw`.
3. Consider treating a detector stuck DOWN for longer than N × its timeout as
   UNKNOWN, so a dead source abstains instead of voting.

## Related
- DTL-001 (one way to get a stuck detector); `docs/INTERFACES.md` §4.

<!-- mega-review-fingerprint: 4ed1313a -->

---

## DTL-003 — [storage] SQLite returns naive datetimes, so editing a past event shifts its end time by the local UTC offset

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `src/downtime_logger/storage/sqlite_backend.py:36-37`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
Columns are `DateTime(timezone=True)`, but SQLAlchemy's SQLite dialect stores
UTC wall-clock text without an offset and returns **naive** datetimes. The Qt
editor calls `.timestamp()` on them, which Python interprets as local time. On any
console whose zone is not UTC, saving an edited past event rewrites `ended_at` by
the UTC offset — even when only the cause or notes were changed.

## Evidence
```
$ grep -n 'timestamp()\|fromtimestamp' src/downtime_logger/ui/popup_dialog.py
82:            QDateTime.fromSecsSinceEpoch(int(event.started_at.timestamp()))
94:                QDateTime.fromSecsSinceEpoch(int(event.ended_at.timestamp()))
141:        self._event.started_at = datetime.fromtimestamp(
147:            self._event.ended_at = datetime.fromtimestamp(
$ grep -n 'astimezone' src/downtime_logger/ui/main_window.py
39:    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
```

Reproduced on this branch through `SQLiteBackend`, `EventEditor` and
`update_event`, event 14:00–14:30 UTC, editor touching only the cause:
```
TZ=UTC              read back tzinfo=None  duration before 1800.0  after 1800.0
TZ=America/Chicago  read back tzinfo=None  duration before 1800.0  after 19800.0
                    ended_at after edit: 2026-10-06 19:30:00
                    Qt history table shows Started 14:00 (true local 09:00)
```

Other effects of the same root cause:
- `_fmt_dt` (`ui/main_window.py:36-39`) and the popup header
  (`ui/popup_dialog.py:121`) show UTC wall-clock labelled as local time.
- `/api/events` and `/api/report` emit offset-less ISO strings while
  `/api/status` emits `+00:00` for the same kind of value (`web/server.py:32-33`).
- `list_events_in_range` compares rendered bound strings without converting the
  bounds; a non-UTC aware bound selects the wrong window (latent: every in-tree
  caller passes UTC, `web/server.py:448,455`).

## Why it matters
Shifters correct and annotate events after the fact; that is what the history
editor is for. Each Save on a closed event in Chicago adds 5 h (CDT) or 6 h (CST)
of downtime to it, silently, and repeated saves add it again. The `/report`
totals inherit the error. Workaround: run the console with `TZ=UTC`.

## Suggested fix
Return aware UTC datetimes from the backend: a small `TypeDecorator` over
`DateTime` that `.astimezone(timezone.utc).replace(tzinfo=None)` on bind and
`.replace(tzinfo=timezone.utc)` on result. That fixes the editor, the table, the
JSON and the range query at one point. Add a test that runs the editor round trip
under a non-UTC `TZ`.

## Related
- DTL-017 (the same editor's `started_at` is never persisted).
- `docs/INTERFACES.md` §7.

<!-- mega-review-fingerprint: 319194e1 -->

---

## DTL-004 — [storage] detector_state_log grows without bound and has no retention path

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** enhancement
**Location:** `src/downtime_logger/storage/sqlite_backend.py:187-201`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`log_readings` appends one row per detector on every recompute. Nothing reads
the table, nothing prunes it, it has no index on `ts`, and the config schema has
no retention setting.

## Evidence
```
$ grep -rn 'detector_state_log\|_ReadingRow' src/ | grep -v 'sqlite_backend.py'
(no output)
$ grep -rn 'retention\|prune\|VACUUM\|max_rows' src/ config/
(no output)
$ grep -n 'readings_changed.connect' src/downtime_logger/app.py
84:        self._sm.readings_changed.connect(self._window.status.on_readings)
87:        self._sm.readings_changed.connect(self._on_readings_log)
88:        self._sm.readings_changed.connect(self._snapshot.update_readings)
```

`readings_changed` fires on every `_recompute` (`core/state_machine.py:134`),
i.e. on each detector transition and each enable toggle; one row per configured
detector each time.

## Why it matters
Growth is proportional to detector transitions, so it is fastest when a detector
flaps. The inserts are into a rowid table with no secondary index, so their cost
does not grow with the table, and nothing reads it; the cost is disk space and a
"useful for post-mortems" table (`app.py:147`) that no tool or procedure uses.
Hygiene, not an outage.

## Suggested fix
Either make `log_readings` opt-in (the module docstring at `app.py:8-9` already
anticipates a flag), or add `storage.options.reading_log_retention_days` and
delete older rows at startup, plus an index on `ts` if a reader is ever added.

## Related
- `docs/OPERATIONS.md` § Data and retention gives an interim pruning command.

<!-- mega-review-fingerprint: 7d76038c -->

---

## DTL-005 — [detectors] an exception in a detector's start() is invisible; the detector stays UNKNOWN forever

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/downtime_logger/app.py:137-141`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`start()` runs on the detector thread through a queued `invokeMethod`. If it
raises, PySide6 prints the traceback and returns to the event loop. The detector
is already registered, so it sits at UNKNOWN indefinitely, and the controller has
already logged `started detector <id>`.

## Evidence
```
$ sed -n '137,141p' src/downtime_logger/app.py
        QMetaObject.invokeMethod(
            det, "start", Qt.ConnectionType.QueuedConnection
        )
        log.info("started detector %s (%s, weight=%.2f)",
                 spec.id, spec.plugin, spec.weight)
```

Reproduced on this branch with a plugin whose `start()` raises, next to a UDP
detector:
```
INFO downtime_logger.app started detector bad (baddet:Bad, weight=1.00)
Traceback (most recent call last):
RuntimeError: detector start blew up
INFO downtime_logger.app started detector good (...UdpDetector, weight=1.00)
REPORT readings: {'bad': 'unknown', 'good': 'down'}
```

## Why it matters
Isolation itself is right: one bad detector does not stop the others. The defect
is that the failure looks like a detector that has not reported yet. Because
UNKNOWN leaves the denominator (`core/metric.py:60-61`), the remaining detectors
silently gain weight, shifting both trip and clear behaviour. Shipped detectors
can raise in `start()` on, e.g., a malformed ZMQ endpoint (`zmq.ZMQError` from
`connect`) or an exhausted inotify limit in `watchdog`.

## Suggested fix
Make `Detector.start` a non-virtual wrapper that calls a `_start()` hook inside
`try/except`, logs at ERROR, and emits UNKNOWN with `detail="start failed: …"` so
the reason appears in the detector table and on `/api/status`. Log `started` from
the wrapper after success.

## Related
- `docs/INTERFACES.md` §1.

<!-- mega-review-fingerprint: d5fd05de -->

---

## DTL-006 — [config] example config targets the unresolvable placeholder host daq01 for both ZMQ and SOAP

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** documentation
**Location:** `config/config.example.yaml:53`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
Both network detector blocks in the example config name host `daq01`, which does
not resolve and does not follow the `mu2edaq0N.fnal.gov` convention. The ports are
the defaults of the package's own mock producers. Nothing marks them as
placeholders, and the README calls this file the configuration for the real DAQ.

## Evidence
```
$ grep -n 'daq01' config/config.example.yaml
35:      endpoint: "tcp://daq01:5555"
53:      wsdl: "http://daq01:8080/RunControl?wsdl"
$ grep -n 'real DAQ' -A2 README.md
45:# Foreground, pointing at the real DAQ:
46-source venv/bin/activate
47-mu2edaq-downtime-logger --config config/config.example.yaml
$ python3 -c "import socket; socket.getaddrinfo('daq01', 5555)"
socket.gaierror: [Errno 8] nodename nor servname provided, or not known
```

Superproject-wide the bare host appears only in this file (unchanged since the
initial commit `c532477`), three byte-identical copies under
`mu2edaq-config/config-*/mu2edaq-downtime-logger/`, test fixtures in other
packages, and `DAQ-ControlRoom-Testing.md:261`, which lists it as an unreachable
detector target. `tools/zmq_publish.py:12` binds 5555 and `tools/soap_server.py`
serves `:8080/RunControl?wsdl` by default. The SOAP operation, `state_path` and
values match the mock; no real run-control SOAP endpoint with this interface
exists in the tree.

## Why it matters
No outage: no launch path loads this file. But it is the template a deployer
copies, and both endpoints collide with real services' ports (5555
`mu2edaq-dashboard`, 8080 `mu2edaq-resource-manager`), which turns a stale
placeholder into a misleading one (see DTL-001).

## Suggested fix
Use an obvious placeholder (`RUNCONTROL_HOST`), comment each block with the
required peer (ZMQ PUB that binds; SOAP WSDL with the named operation), state that
the SOAP names were taken from `tools/soap_server.py`, and change `README.md:45`
to "with a site configuration derived from config.example.yaml".

## Related
- DTL-001.

<!-- mega-review-fingerprint: 6a83f7e5 -->

---

## DTL-010 — [ci] CI does not test Python 3.9 although pyproject declares requires-python >=3.9

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `.github/workflows/ci.yml:16`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
`requires-python = ">=3.9"` was set deliberately for the AlmaLinux 9 system
interpreter, but the CI matrix runs 3.10, 3.11 and 3.12 only.

## Evidence
```
$ grep -n 'requires-python' pyproject.toml
10:requires-python = ">=3.9"
$ grep -n 'python-version' .github/workflows/ci.yml
16:        python-version: ["3.10", "3.11", "3.12"]
94:        with: { python-version: "3.12", cache: pip }
$ git log --oneline -1 6a82d4c
6a82d4c Lower requires-python to >=3.9 for AlmaLinux 9 (fixes #4)
```

## Why it matters
The code relies on `from __future__ import annotations` to keep PEP 604 and
PEP 585 annotations legal on 3.9. Any runtime use of 3.10+ syntax or stdlib
passes all three CI legs and fails on the production interpreter — the class of
regression #4 was about. No such construct is present today.

## Suggested fix
Add `"3.9"` to the matrix at `ci.yml:16`; if a dependency cannot be installed
there, add a 3.9 leg to the `importable` job instead.

## Related
- Mu2e/mu2edaq-downtime-logger#4 (closed) lowered the floor.

<!-- mega-review-fingerprint: 5769af3d -->

---

## DTL-011 — [detectors] ZMQ and UDP state tokens are substring-matched, so unrelated payloads flip the state

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/downtime_logger/detectors/zeromq_detector.py:91-94`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-09-30

## What
Both heartbeat detectors classify a payload with `t in text` over the lowercased
frame. Short tokens (`run`, `up`, `stop`, `down`) match inside other words, JSON
keys and paths, and an unrecognised payload is UP.

## Evidence
```
$ sed -n '24,25p' src/downtime_logger/detectors/zeromq_detector.py
_DOWN_TOKENS = {"stopped", "stop", "down", "halted", "abort", "aborted"}
_UP_TOKENS = {"running", "run", "up", "started", "active"}
$ sed -n '91,97p' src/downtime_logger/detectors/zeromq_detector.py
        if any(t in text for t in _DOWN_TOKENS):
            self._emit_state(DetectorState.DOWN, text)
        elif any(t in text for t in _UP_TOKENS):
            self._emit_state(DetectorState.UP, text)
        else:
            # Unknown payload still counts as a heartbeat -> UP-ish presence.
            self._emit_state(DetectorState.UP, f"heartbeat: {text[:64]}")
```
`udp_detector.py:18-19,76-81` is identical. Classified with these rules:
`EventBuilder shutdown requested` → DOWN (`down`); `setup complete` → UP (`up`);
`truncated fragment` → UP (`run`); the canonical mu2edaq-dashboard JSON message
→ UP (no token, heartbeat).

## Why it matters
No outage today; only the mock tools feed these detectors. On the day either is
pointed at a real publisher that emits free text or structured status, DOWN
misclassification opens spurious events (which, via DTL-002, may not close) and
UP misclassification hides real stops. The evidence ends up in `detail`, but
nothing flags the ambiguity.

## Suggested fix
Match whole words with one compiled `\b(...)\b` pattern per set, drop `run` and
`up` from the defaults, and make the token sets configurable per instance as
`SoapDetector` already does with `down_values`/`up_values`.

## Related
- DTL-001; `docs/INTERFACES.md` §2.

<!-- mega-review-fingerprint: f52b63e7 -->

---

## DTL-013 — [deploy] the control-room launch path runs the workstation test config, serving the web view on loopback:8001

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `start-mu2edaq-downtime-logger.sh:9`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`crs-app start downtime-logger` execs the start script with no arguments; the
script then defaults to `config/local.yaml`, the laptop test file. On a control-room
console the logger therefore watches `/tmp/daq-test` and 127.0.0.1:9000/udp,
serves its web view on 127.0.0.1:8001, and advertises that loopback-only port via
discovery, while the app inventory assigns 8088.

## Evidence
```
$ sed -n '47,53p' ../mu2edaq-controlroom-setup/config/apps.yaml
  - id: downtime-logger
    title: "Downtime Logger"
    repo: mu2edaq-downtime-logger
    start: start-mu2edaq-downtime-logger.sh
    stop: stop-mu2edaq-downtime-logger.sh
    install_path: ~/mu2edaq-main/mu2edaq-downtime-logger
    ports: {http: 8088}
$ sed -n '114,118p' ../mu2edaq-controlroom-setup/server/crs-app
    env = dict(os.environ)
    for pname, pvalue in app.get("ports", {}).items():
        env["CRS_PORT_%s" % pname.upper()] = str(pvalue)

    os.execve(script, [script], env)
$ grep -n 'DEFAULT_CONFIG=' start-mu2edaq-downtime-logger.sh
9:DEFAULT_CONFIG="$SCRIPT_DIR/config/local.yaml"
$ sed -n '1,2p;11,12p;27,28p;35p;43p' config/local.yaml
# Local laptop test config. No external DAQ infrastructure required;
# drive state changes with the scripts under tools/.
  bind: "127.0.0.1"
  port: 8001
      bind: "127.0.0.1"
      port: 9000
      paths: ["/tmp/daq-test"]
      path: /tmp/daq-test/run.log
$ grep -rn 'os.environ\|getenv' src/downtime_logger/
(no output: CRS_PORT_HTTP is never read)
```

Reproduced with `config/local.yaml` (web disabled for the test) on a host
without `/tmp/daq-test`: after enabling monitoring,
`udp_heartbeat down, local_disk down, local_log unknown, score 1.0`, one event
opened by `local_disk`, never closed. The discovery responder advertises
`http://<fqdn>:8001` (`__main__.py:43-44`,
`mu2edaq-discovery/src/mu2edaq_discovery/protocol.py:65`), unreachable off-host.
Port 8001 is also `mu2edaq-snapshot-viewer`'s server
(`mu2edaq-snapshot-viewer/config/server.yaml:9-10`); a bind failure aborts this
application's startup (`app.py:62-71` has no `try`).

## Why it matters
The app the control room starts does not monitor the DAQ. With monitoring off
(the default, DTL-016) it records nothing; switched on, it records one permanent
false downtime. Remote shifters following the inventory or the discovery list
cannot reach its web view. Workaround: start it by hand with `--config`.

## Suggested fix
Ship a site configuration (for example `config/controlroom.yaml`, or load from
`mu2edaq-config`) and make it the start script's default, keeping `local.yaml`
behind an explicit flag. Have the start script honour `CRS_PORT_HTTP` (passed as
a `--port` override the application gains), or set `webserver.port: 8088` and
`bind: 0.0.0.0` in the site file. Advertise the bound address, not the FQDN, when
`bind` is loopback.

## Related
- DTL-016; Mu2e/mu2edaq-controlroom-setup inventory entry `downtime-logger`.

<!-- mega-review-fingerprint: 2d4dea85 -->

---

## DTL-014 — [lifecycle] SIGTERM from the stop script orphans an open event, which then inflates every later report

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `src/downtime_logger/__main__.py:51`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
Only `SIGINT` has a handler. The stop script (and `crs-app stop`) sends
`SIGTERM`, which terminates the interpreter without `aboutToQuit` or `finally`.
An event open at that moment keeps `ended_at IS NULL`; the next start does not
reattach it, *End downtime now* refuses it, and `/report` counts it as ongoing up
to the end of every later window.

## Evidence
```
$ grep -n 'signal.signal' src/downtime_logger/__main__.py
51:    signal.signal(signal.SIGINT, lambda *_: app.quit())
$ grep -n 'kill -TERM' stop-mu2edaq-downtime-logger.sh
57:kill -TERM "$PID" 2>/dev/null || true
$ sed -n '211,214p' src/downtime_logger/app.py
        sm_event = self._sm.current_event
        if sm_event is None or sm_event.id != event_id:
            log.warning("manual end requested for non-active event %s", event_id)
            return
```

Reproduced on this branch (UDP detector, monitoring enabled, event opened, then
`SIGTERM`), then a fresh `Controller` on the same database:
```
event opened id= 1
exit status: 143                       # neither aboutToQuit nor finally ran
rows after restart: [(1, None)]
state machine current_event after restart: None
WARNING downtime_logger.app manual end requested for non-active event 1
after End-downtime-now, ended_at = None
report total_seconds over a range ending 30 days later: 2592000.9
```

Two other routes produce the same unclosable row: *New event…* opens its
editor with *Ongoing* ticked (`ui/main_window.py:268-276` builds an event with
`ended_at=None`, `ui/popup_dialog.py:98-99`), and `_on_event_create`
(`app.py:197-207`) stores it without handing it to the state machine; and DTL-021.

## Why it matters
Shutting the logger down while the DAQ is down — a maintenance stop, a host
reboot, `crs-app stop` — leaves a downtime that grows forever in every report.
The row shows as bold "ongoing" and the obvious menu action does nothing.
Workaround: edit the row, clear *Ongoing*, set the end time, Save (subject to
DTL-003 on non-UTC hosts).

## Suggested fix
Install `SIGTERM` (and `SIGHUP`) handlers that call `app.quit()`, as for
`SIGINT`. In `_cleanup`, close the active event with the shutdown time (or mark
it with a `closed_by: shutdown` note). At startup, find rows with
`ended_at IS NULL` and either reattach the newest to the state machine or close
them at their last `detector_state_log` timestamp. Let *End downtime now* close
any open row directly through storage.

## Related
- DTL-003, DTL-013; `docs/INTERFACES.md` §9.

<!-- mega-review-fingerprint: 76cf3c3d -->

---

## DTL-015 — [web] status and report pages interpolate detector detail and event text without HTML escaping

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/downtime_logger/web/server.py:129`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
All values placed into the HTML templates are formatted raw. One of them, a
detector's `detail`, is the verbatim text of a UDP datagram or ZMQ frame from
any sender that can reach the port.

## Evidence
```
$ grep -n 'html.escape\|import html' src/downtime_logger/web/server.py
(no output)
$ sed -n '127,129p' src/downtime_logger/web/server.py
            f"<td>{did}</td><td>{r.state.value}</td>"
            f"<td>{r.weight:.2f}</td><td>{_iso(r.ts) or ''}</td>"
            f"<td>{(r.detail or '')[:200]}</td></tr>"
$ sed -n '76,77p' src/downtime_logger/detectors/udp_detector.py
            if any(t in data for t in _DOWN_TOKENS):
                self._emit_state(DetectorState.DOWN, data)
```
`render_page` with a reading whose detail is
`daq stopped <script>alert(1)</script>` returns HTML containing the script
element verbatim (reproduced). Event `opened_by`, `category`, `subsystem`,
`cause` and `notes` are interpolated the same way (`server.py:137-145,160-163,
314-317`).

## Why it matters
Any host on the DAQ network can send one UDP datagram to 9000 (the example
config binds `0.0.0.0`) and have markup or script executed in every shifter
browser that has `/` open; the page auto-refreshes. There is no session to steal,
so the impact is defacement, redirection or a fake status banner on a monitoring
page. Notes typed with `<` or `&` also render wrongly. S3 rather than S1: no
credential or data path is exposed, and the page is internal.

## Suggested fix
`html.escape()` every interpolated value in `_render_*` and `render_page`
(including `did`), or switch to a template engine with autoescaping.

## Related
- DTL-012 (in roll-up DTL-020); `docs/INTERFACES.md` §2, §6.

<!-- mega-review-fingerprint: 375bb4d3 -->

---

## DTL-016 — [state] monitoring starts disabled on every launch, with no override and no indication over HTTP

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/downtime_logger/core/state_machine.py:40`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`StateMachine` defaults to `enabled=False` and the controller never sets it, so
after every start no event can open until a shifter flips the switch. There is no
config key or option, `/api/status` does not report the state, and the web banner
and `is_down` show the metric's request, so a remote page can read "DAQ DOWN"
while nothing is being recorded.

## Evidence
```
$ sed -n '40p' src/downtime_logger/core/state_machine.py
        enabled: bool = False,
$ grep -n 'StateMachine(' src/downtime_logger/app.py
51:        self._sm = StateMachine(metric=metric, debounce_seconds=debounce)
$ sed -n '155,159p' src/downtime_logger/core/state_machine.py
        if target and not self._enabled:
            # Disabled: don't trip into a new downtime. Closing existing
            # events is still allowed so a stale event from before disable
            # can resolve naturally.
            return
$ grep -n 'enabled' src/downtime_logger/web/server.py
(no output: /api/status, server.py:62-69, has no enabled field)
```
`score_changed(score, target)` (`state_machine.py:135`) feeds the snapshot
(`app.py:89`), so `/api/status.is_down` is the request, not the state.

## Why it matters
An unattended restart (crash, reboot, `crs-app` restart) silently stops downtime
recording until someone looks at the console. The Qt window and tray do show
"DISABLED", which is why this is S3: the local UI tells the truth, the remote
view does not. Combined with DTL-013 it also masks the broken deployed
configuration.

## Suggested fix
Add `monitoring.enabled_at_start` (default true for site configs) and a
`--enable/--disable` option; expose `enabled` and the state machine's actual
`is_down` (distinct from the metric request) in `/api/status` and on `/`.

## Related
- DTL-013; `docs/OPERATIONS.md` § Monitoring is OFF after every start.

<!-- mega-review-fingerprint: 75a8d236 -->

---

## DTL-017 — [storage] update_event silently discards started_at edits made in the event editor

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/downtime_logger/storage/sqlite_backend.py:125-139`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
The editor has an editable *Started at* field and writes it into the event on
Save, but `update_event` persists only category, subsystem, cause, notes and
`ended_at`. A corrected start time is shown until the next refresh and then lost.

## Evidence
```
$ grep -n '_started_edit = \|"Started at"\|_event.started_at = ' src/downtime_logger/ui/popup_dialog.py
78:        self._started_edit = QDateTimeEdit()
84:        form.addRow("Started at", self._started_edit)
141:        self._event.started_at = datetime.fromtimestamp(
$ sed -n '132,137p' src/downtime_logger/storage/sqlite_backend.py
            row.category = event.category
            row.subsystem = event.subsystem
            row.cause = event.cause
            row.notes = event.notes
            row.ended_at = event.ended_at
            row.updated_at = datetime.now(timezone.utc)
```
In the DTL-003 reproduction the editor's `started_at` moved by +5 h and the stored
value stayed at 14:00 — the only reason that run did not also corrupt the start.

## Why it matters
Recorded start times lag the real stop by the debounce plus detector latency
(up to ~65 s with the example disk settings). Shifters correcting that, or
back-dating a manual event, get no error and no effect. Fixing DTL-003 without
this would expose the start time to the same drift once it is persisted.

## Suggested fix
Persist `started_at` in `update_event` (after the DTL-003 fix), validate
`started_at <= ended_at`, or make the field read-only if starts are meant to be
immutable.

## Related
- DTL-003.

<!-- mega-review-fingerprint: 972e373d -->

---

## DTL-018 — [detectors] logfile tail skips lines written to a file created after the detector started

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/downtime_logger/detectors/logfile_detector.py:57-68`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`_Tail.read_new` opens any file it does not currently hold with
`seek_to_end=first_open`, where `first_open` means "no handle", not "first poll".
A log file that does not exist at startup, or that is absent at one poll during
rotation, is opened at EOF when it appears, so the lines already written to it
are never scanned.

## Evidence
```
$ grep -n 'first_open\|seek_to_end' src/downtime_logger/detectors/logfile_detector.py
31:    def _open(self, seek_to_end: bool) -> None:
34:            if seek_to_end:
57:        first_open = self._fh is None
59:        if first_open or state != "ok":
68:            self._open(seek_to_end=first_open)
```
Reproduced with `_Tail` directly:
```
tick1 (file absent): []
tick2 (file created with one line): []                  # RUN STOPPED lost
tick3 (second line appended): ['... RUN STARTED']
tick4 (file rotated away, absent): []
tick5 (file recreated with one line): []                # FATAL lost
```

## Why it matters
Run-control logs are typically created at run start and rotated per run, and the
first lines of a new file (start banner, early FATAL) are the ones the
`down_patterns`/`up_patterns` look for. The tool's own workflow hits it: the first
`tools/log_writer.py` call against a fresh `/tmp/daq-test/run.log` has no effect.

## Suggested fix
Track "already started" separately from "has a handle": seek to EOF only on the
very first open after `start()` when the file already existed; read from the top
for any file that appears later.

## Related
- `docs/INTERFACES.md` §2; `log_writer.py(1)` documents the workaround.

<!-- mega-review-fingerprint: 759d4a30 -->

---

## DTL-021 — [ui] saving the DAQ DOWN popup after the event auto-closed reopens it in the database

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `src/downtime_logger/ui/popup_dialog.py:161-169`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
The non-modal popup is built while the event is open, so its *Ongoing* checkbox
is ticked. When the DAQ recovers, the controller hands the closed event to
`update_running_event`, which replaces the dialog's event and its header but not
the checkbox. A Save pressed after that sets `ended_at = None` on the closed
event, and `update_event` writes the NULL over the stored end time.

## Evidence
```
$ sed -n '98,99p;144,145p' src/downtime_logger/ui/popup_dialog.py
        self._ongoing = QCheckBox("Ongoing")
        self._ongoing.setChecked(event.ended_at is None)
        if self._ongoing.isChecked():
            self._event.ended_at = None
$ sed -n '166,169p' src/downtime_logger/ui/popup_dialog.py
        # Header is the only thing that changes from outside the dialog.
        for child in self.findChildren(QLabel):
            child.setText(self._format_header(event))
            break
$ sed -n '178,179p' src/downtime_logger/app.py
        if self._popup is not None:
            self._popup.update_running_event(event)
$ sed -n '136p' src/downtime_logger/storage/sqlite_backend.py
            row.ended_at = event.ended_at
```

Reproduced on this branch with the real `Controller` (offscreen Qt, one
scripted detector, monitoring enabled, debounce 0.1 s): detector DOWN → event
opens and popup appears; detector UP → event closes; then the shifter types a
cause into the popup and presses Save (`_on_save`):
```
after trip   : [(1, '2026-10-06 20:08:18.430157', None, None)]  ongoing box: True
after recover: [(1, '2026-10-06 20:08:18.430157', '2026-10-06 20:08:18.802797', None)]
               popup._event.ended_at set, ongoing box still checked: True
after Save   : [(1, '2026-10-06 20:08:18.430157', None, 'PS trip on crate 3')]
```

## Why it matters
Classifying the downtime in the popup is the intended workflow (`README.md:5-6`,
`ui/popup_dialog.py:1-5`), and the DAQ often recovers before the shifter has
finished typing the cause. Each such Save turns a correctly closed event back into
an open one: the history shows it as ongoing, *End downtime now* refuses it
because the state machine does not hold it (`app.py:211-214`, as in DTL-014),
`/report` counts it to the end of every later window, and the next real downtime
opens a second simultaneously open row. Nothing is logged. Workaround: untick
*Ongoing* before Save, or classify from the history table; repair by editing the
row (subject to DTL-003 on non-UTC consoles).

## Suggested fix
In `update_running_event`, when `event.ended_at` is set, untick *Ongoing*
(`_ongoing.setChecked(False)`, which re-enables `_ended_edit` through the
existing toggle handler) and load `_ended_edit` from `event.ended_at`. Independently, have `Controller._on_event_save` refuse to
write `ended_at = None` for an event that is not the state machine's current
event unless the user explicitly reopened it. Add a pytest-qt test for
open → close → popup Save.

## Related
- DTL-014 (same unclosable-row outcome), DTL-003, DTL-017.

<!-- mega-review-fingerprint: e8392995 -->

---

## DTL-020 — [hygiene] roll-up of five low-severity documentation, metadata and error-handling findings

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** documentation
**Location:** `config/config.example.yaml:14`, `man/man1/`, `src/downtime_logger/web/server.py:436-438`, `pyproject.toml:12`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
Five S4 items rolled up to stay within the review's per-repo issue budget. Two
are already fixed on the `mu2e-sept-mega-review` branch.

### DTL-007 — config comment lists the HTTP endpoints but omits /report and /api/report
```
$ sed -n '13,14p' config/config.example.yaml
# Optional read-only HTTP view for remote shifters / dashboards.
# Endpoints: /, /api/status, /api/events, /api/events/<id>, /healthz
```
The routes exist (`web/server.py:410,430`) and `README.md:136,151` documents
them. Fix: add `/report` and `/api/report` to the comment. (fingerprint 300a658a)

### DTL-008 — man pages contained roff lines beginning with "./" (fixed on branch)
`mandoc -T lint` reported `skipping unknown macro: ./start\-mu2edaq…` on the
start, stop and bootstrap pages; the example commands were dropped from the
rendered output. Fixed in the mega-review man-page commit with `\&` and the pages
renamed to their command names. (fingerprint c919cff8)

### DTL-009 — .TH used "June 2026" and "Mu2e DAQ Tools" (fixed on branch)
All nine pages had an unparseable date and a non-standard manual title. Fixed in
the same commit (ISO date, `Mu2e DAQ Manual`). (fingerprint f1acc2cf)

### DTL-012 — web handler exceptions return the exception text to the client
```
$ sed -n '436,438p' src/downtime_logger/web/server.py
        except Exception as e:
            log.exception("web handler error")
            self._send(500, f"internal error: {e}".encode(), "text/plain")
```
`/report?from=x` returns `500 internal error: unparseable datetime: 'x'`; a
SQLAlchemy `OperationalError` would include SQL and the resolved database path
(`sqlite_backend.py:83`). Minor disclosure on an unauthenticated port; a malformed
`from`/`to` deserves a 400. Fix: fixed `internal error` body; map `ValueError`
from `_parse_range` to 400. (fingerprint 7a7c6702)

### DTL-019 — pyproject declares Apache-2.0 but the LICENSE file is MIT
```
$ grep -n 'license' pyproject.toml
12:license = { text = "Apache-2.0" }
$ head -1 LICENSE
MIT License
```
Commit `cafc76a` added the MIT file; the metadata was not updated, so wheels and
`pip show` report the wrong licence. Fix: `license = { text = "MIT" }`.
(fingerprint 17239c99)

## Why it matters
Each is cosmetic or already fixed; together they are the hygiene backlog.

## Suggested fix
As listed per item.

## Related
- `docs/ARCHITECTURE.md` § Review findings.

<!-- mega-review-fingerprint: a77c20ac -->
