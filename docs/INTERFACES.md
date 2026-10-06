---
title: mu2edaq-downtime-logger interfaces
group: monitoring
tier: A
audience: expert
summary: Detector and storage plugin contracts, per-detector wire grammars, HTTP API, scoring semantics and the verdict on the dashboard ZMQ claim for mu2edaq-downtime-logger
---

# Interfaces — mu2edaq-downtime-logger

All paths are relative to the package root unless prefixed with a sibling package
name. Line numbers refer to commit `f017f81`.

## 1. Detector plugin contract

A detector is a `QObject` subclass of `downtime_logger.detectors.base.Detector`
(`src/downtime_logger/detectors/base.py:26`). It is named in YAML as
`module.path:ClassName` and loaded with plain `importlib`
(`src/downtime_logger/core/plugin_loader.py:14-31`); there are no entry points.

**Constructor.** `instantiate(spec.plugin, detector_id=spec.id, **spec.options)`
(`src/downtime_logger/app.py:117`), on the GUI thread. All five shipped detectors
end their signature with `**_: object`
(e.g. `src/downtime_logger/detectors/zeromq_detector.py:35`), so a misspelt option
is silently ignored and the default used. `weight` is a sibling of `options` in
YAML and goes to the state machine (`app.py:118`), never to the detector.
A constructor exception (bad regex, missing required option) is **not** isolated:
it propagates out of `Controller.__init__` and the application exits with a
traceback.

**Lifecycle.**

| Method | Thread | Contract |
|---|---|---|
| `start()` | the detector's own `QThread`, via `QMetaObject.invokeMethod(..., QueuedConnection)` (`app.py:137-139`) | Create every socket, `QTimer` and `QSocketNotifier` here. Objects created in `__init__` keep GUI-thread affinity because `moveToThread` (`app.py:122`) happens after construction. |
| `stop()` | the detector thread, from `thread.finished` with `DirectConnection` (`app.py:129`) | Tear down. Base default is a no-op (`base.py:43-46`). Called from `_cleanup` → `QThread.quit()` (`app.py:275-279`), which only runs on the `aboutToQuit` path — see §9. |

**Emitting.** `self._emit_state(state, detail)` (`base.py:50-56`) emits
`state_changed(str id, str state, str detail)`, connected with an explicit
`QueuedConnection` to `StateMachine.on_state_changed` on the GUI thread
(`app.py:126-128`). Repeats of the current state are suppressed after the first
emission (`base.py:51-52`), so the state machine recomputes only on transitions; a
change of `detail` alone is not propagated.

**Failure convention.** A detector that cannot determine anything should report
`UNKNOWN`, which abstains from the score (`core/metric.py:60-61`). `SoapDetector`
does this for WSDL and call failures (`soap_detector.py:96,102`) and for
unrecognised values (`:113`); `UdpDetector` does it on bind failure
(`udp_detector.py:50`). The two heartbeat detectors report `DOWN` when the
heartbeat stops (`zeromq_detector.py:100-101`, `udp_detector.py:85-87`), which is
the intended meaning of a missing heartbeat — but for ZeroMQ it is also what an
unreachable or incompatible peer looks like, because libzmq reports neither to
the application (§3).

**Exception isolation.** An exception escaping `start()` or a timer slot is
printed by PySide6 and swallowed; the Qt loop and the sibling detectors continue.
Reproduced on this branch with a plugin whose `start()` raises: the log shows
`started detector bad (...)` (`app.py:140-141` logs before `start()` has run), a
traceback, and the detector stays `unknown` while its sibling keeps reporting.
Nothing else records the failure (DTL-005).

## 2. What each detector expects on the wire

### `zeromq_detector:ZmqDetector`

* **Socket:** `zmq.SUB` (`zeromq_detector.py:50`), `SUBSCRIBE` to `topic`
  (default `""`, all frames) (`:51`), **connect** to `endpoint` (`:52`). The peer
  must **bind** a `zmq.PUB`. The ZMQ FD is wrapped in a `QSocketNotifier`
  (`:54-56`); `_on_readable` drains with `NOBLOCK` until `zmq.Again` (`:80-85`),
  which is the correct handling of the edge-triggered `ZMQ_FD`.
* **Grammar:** each frame is decoded with `errors="replace"`, stripped and
  lowercased (`:90`), then tested with Python substring containment (`:91-97`):
  * DOWN if it contains any of `stopped stop down halted abort aborted` (`:24`);
  * else UP if it contains any of `running run up started active` (`:25`);
  * else UP as a heartbeat, detail `heartbeat: <first 64 chars>` (`:96-97`).

  Matching is not word-bounded (DTL-011): `shutdown`, `countdown`,
  `downstream` read DOWN; `setup`, `truncated`, `prerun` read UP. There is no
  branch that maps an unrecognised payload to DOWN or UNKNOWN.
* **Watchdog:** periodic `QTimer` of `heartbeat_timeout_s` (default 10 s, `:34`),
  armed unconditionally in `start()` (`:58-61`), restarted after every drain
  (`:86-87`); on expiry emits DOWN, detail `no zmq messages within timeout`
  (`:100-101`).
* **Intended producer:** `tools/zmq_publish.py`, which **binds** `zmq.PUB` on
  `tcp://*:5555` by default (`tools/zmq_publish.py:12,27-28`) and sends
  `RUN STATE running` / `RUN STATE stopped` / `heartbeat tick` (`:32-36`).
  Tests use the same pattern (`tests/test_detector_zmq.py:13-20`).

### `udp_detector:UdpDetector`

`QUdpSocket` **bound** to `bind:port` with `ShareAddress|ReuseAddressHint`
(`udp_detector.py:41-46`); defaults `0.0.0.0:9000`, timeout 15 s (`:26-28`). Same
token sets, same substring semantics, same heartbeat fallback (`:18-19,73-81`),
same restart-on-receive watchdog (`:82-83`) and DOWN on expiry (`:85-87`). Any
host that can reach the port can set the detector's state; there is no
authentication or source filter. The datagram text becomes the reading's `detail`
verbatim (`:77,79`), which is rendered unescaped into the HTML status page
(DTL-015). Producer: `tools/udp_broadcast.py` (`DAQ STATE running` etc.,
`tools/udp_broadcast.py:24-28`).

### `soap_detector:SoapDetector`

`zeep.Client(wsdl)` built lazily on the first poll (`soap_detector.py:82-90`),
then `getattr(client.service, operation)(**args)` every `poll_s`
(`:99-100`). The response is walked by the dotted `state_path` (`_dig`,
`:29-38`), stringified and lowercased (`:107`), and compared by **exact set
membership** with `down_values`/`up_values` (`:108-113`). Defaults: operation
`getRunState`, `state_path` `runState`, down `stopped idle halted`, up
`running active` (`:46-60`). Any exception yields UNKNOWN and drops the cached
client so the next poll refetches the WSDL (`:101-104`). The call is synchronous
on the detector thread, so a slow server delays only this detector. Producer:
`tools/soap_server.py`; no other SOAP run-control endpoint with this interface
exists in the superproject.

### `disk_detector:DiskActivityDetector`

No network. A `watchdog.Observer` sets `_last_event_ts = time.time()` on any
non-directory event (`disk_detector.py:31-38,93-94`) — from the observer's own
thread, a plain float store. A `QTimer` compares the age against `idle_seconds`
(`:96-105`). `start()` seeds the timestamp with the newest mtime under the paths
(`:65`, `_scan_latest_mtime` `:107-121`). Missing paths are skipped
(`os.path.isdir`, `:111`; `observer.schedule` failure logged, `:70-74`); if all
are missing the seed is `0.0` and the first tick reports DOWN with a detail such
as `no writes in 1791314693.9s` (seconds since the epoch).

### `logfile_detector:LogfileDetector`

Pure-Python tail (`logfile_detector.py:25-85`) on a `QTimer`. Rotation is
detected by inode change or by the read position exceeding the size (`:52-53`)
and the new file is read from the top. **A file the tail does not currently hold
open is opened at EOF** (`:57,68`): this covers the first open at startup — the
intent — but also a file that is created after the detector started and a file
that is absent at one poll during rotation. Lines written to such a file before
the next poll are skipped (reproduced; DTL-018). Each line is tested against
`down_patterns` then `up_patterns` with `re.search`; first match wins (`:136-144`).
A file that never exists leaves the detector UNKNOWN.

## 3. The dashboard ZMQ claim — verdict: **reclassified (S2 → S3)**

`mu2edaq-dashboard/docs/INTERFACES.md` §1.5 and staged issue DASH-002 claim that
this package's ZMQ detector "can never work against the dashboard bus" and that the
watchdog "reports the DAQ permanently DOWN". Checked from this side:

**(1) Socket-type mismatch — confirmed.** The dashboard binds `zmq.PULL`
(`mu2edaq-dashboard/dashboard.py:240,242`) on `ZMQ_PORT = 5555`
(`mu2edaq-dashboard/dashboard.py:33`, `mu2edaq-dashboard/config/dashboard_config.yaml:19`);
its producers `PUSH`-connect (`mu2edaq-dashboard/sender.py:278-280`). This
detector opens `zmq.SUB` and connects (`zeromq_detector.py:50-52`) to
`tcp://daq01:5555` (`config/config.example.yaml:35`). Reproduced with pyzmq 27.1.0 /
libzmq 4.3.5: a SUB connected to a PULL bind receives 0 of 5 frames while the PULL
receives all 5 from a PUSH peer; the SUB's socket monitor shows
`CONNECTED` then `DISCONNECTED` (ZMTP rejects the socket-type pair), and
`connect()` itself returns without error — also for the unresolvable
`tcp://daq01:5555`. Nothing is logged.

Second reproduction, with the package's own `ZmqDetector` started on a `QThread`
exactly as `app.py:120-139` does, `heartbeat_timeout_s: 3`, and a feeder sending
dashboard-schema JSON every 250 ms to a PUSH→PULL pair and to a PUB:

```
( 0.26 s) sub_to_pub    up    '{"timestamp": ..., "source": "daq", "type"...'
( 2.86 s) sub_to_daq01  down  'no zmq messages within timeout'
( 2.91 s) sub_to_pull   down  'no zmq messages within timeout'
PULL received from PUSH: 39
```

The SUB→PULL detector goes DOWN exactly at its timeout, so the ZMTP reconnect
cycle does not activate the `QSocketNotifier` and does not restart the watchdog
(`zeromq_detector.py:86-87` would otherwise mask the failure).

**(2) Grammar — the claim is wrong in its detail.** The dashboard bus carries
one-frame JSON objects keyed `event_category`, `error_level`, `subsystem`,
`timestamp`, `message` (`mu2edaq-dashboard/dashboard.py:163-167`,
`mu2edaq-dashboard/docs/INTERFACES.md` §1.3). The detector would not ignore or
reject them: anything without a token is a **heartbeat → UP**
(`zeromq_detector.py:95-97`). The canonical dashboard example
(`"Front-end board timeout on channel 7"`) contains no token and reads UP; a
message text containing `shutdown` or `down` reads DOWN. So the grammar mismatch
would make the detector report "the log bus has traffic", not "the DAQ is
running" — semantically meaningless, but not a cause of DOWN. The DOWN comes only
from (1).

**(3) Consequence through the weighted score — overstated.** With the example
weights (zmq 0.5, udp 0.3, soap 0.4, disk 0.6, log 0.4; Σ 2.2; trip 0.6,
clear 0.2) and `WeightedRatioMetric` (`core/metric.py:52-72`), evaluated with the
package's own class:

| Readings | Score | Trips from UP | Stays DOWN once open |
|---|---|---|---|
| zmq DOWN, other four UP | 0.227 | no | **yes** |
| zmq DOWN, udp+disk UP, soap+log UNKNOWN | 0.357 | no | **yes** |
| zmq DOWN, disk UP, rest UNKNOWN | 0.455 | no | **yes** |
| zmq DOWN, udp UP, rest UNKNOWN | 0.625 | **yes** | yes |
| zmq DOWN + disk DOWN, udp UP, soap+log UNKNOWN | 0.786 | **yes** | yes |
| zmq UP + disk DOWN, udp UP, soap+log UNKNOWN | 0.429 | no | yes |
| zmq DOWN + disk DOWN, other three UP | 0.500 | no | yes |

One stuck ZMQ detector **does not** by itself drive the verdict to DOWN when the
disk detector reports; it is outvoted. Exhaustively over the 81 UP/DOWN/UNKNOWN
assignments of the other four detectors, holding ZMQ at DOWN instead of UP changes
the trip decision in 39. As the only DOWN detector it trips only when the disk
detector is UNKNOWN as well (zmq DOWN, udp UP, rest UNKNOWN: 0.625); while disk
reports UP it cannot (at most 0.5/1.1 = 0.455). Over the 16
UP/UNKNOWN assignments of the other four, **none** brings the score to or below
`clear_threshold` while ZMQ is DOWN. The real consequences are two:

* **Events cannot auto-close.** While an event is open the metric holds it while
  `score > clear_threshold` (`metric.py:68-69`). The stuck detector alone holds
  `0.5/2.2 = 0.227 > 0.2`, so every event opened after the detector died stays open
  until a shifter ends it by hand. This is a property of the weight/threshold
  pairing and is filed as DTL-002 (S2).
* **The trip margin shrinks.** With SOAP and logfile UNKNOWN — the normal state
  of the example config, since `daq01:8080` does not resolve and the log detector
  is UNKNOWN until its first matching line — a 60 s gap in disk writes
  (0.786) now opens an event that would otherwise score 0.429.

"Permanently DOWN" is accurate for the detector's own reading and for the
degenerate configuration where it is the only known detector; it is not accurate
for the five-detector verdict.

**(4) Is `daq01` a live host? — No; stale placeholder.**

* `daq01` and `daq01.fnal.gov` do not resolve from a host with the `fnal.gov`
  search domain; `mu2edaq01.fnal.gov` does (131.225.237.102).
* Superproject-wide (`grep -rn daq01 … --include='*.yaml' --include='*.py'
  --include='*.md'`), the bare host appears only in (a) this file, introduced in the
  initial commit `c532477` and never edited; (b) three byte-identical snapshots of
  it in `mu2edaq-config/config-{main,t00.02.00-rc,t00.03.01}/mu2edaq-downtime-logger/config.example.yaml`
  (`current -> config-main`), which nothing loads — this application has no
  config search path and no `MU2EDAQ_CONFIG` support; (c) test fixtures in other
  packages (`mu2edaq-shifter-tools/tests/conftest.py:99`,
  `mu2edaq-file-reaper/tests/test_cli.py:236`,
  `mu2edaq-reverse-proxy/tests/test_sshutil.py:28`, …); and (d)
  `DAQ-ControlRoom-Testing.md:261`, which records it as an *unreachable* detector
  target that slows startup in the test harness. Every real host reference uses
  `mu2edaq0N.fnal.gov` (e.g. `mu2edaq-resource-manager/config/resources.yaml:522`).
* The two `daq01` endpoints are exactly the defaults of this package's own mock
  producers: `tools/zmq_publish.py:12` binds `tcp://*:5555` and
  `tools/soap_server.py` serves `:8080/RunControl?wsdl`. The example was written
  against the mocks; the collisions with the dashboard's 5555 and
  `mu2edaq-resource-manager`'s 8080 (`mu2edaq-resource-manager/README.md:23`) are
  port coincidences.
* The deployed launch path does not load this file.
  `mu2edaq-controlroom-setup/config/apps.yaml:47-55` registers the app with no
  arguments, `mu2edaq-controlroom-setup/server/crs-app:114-118` `execve`s the start
  script with `argv = [script]`, and `start-mu2edaq-downtime-logger.sh:9,28`
  defaults to `config/local.yaml`, which has no ZMQ or SOAP detector
  (`config/local.yaml:22-46`). **The ZMQ detector does not run anywhere today.**
* `README.md:45-47` does present `config.example.yaml` as "pointing at the real
  DAQ" — the route by which someone would deploy it (DTL-006).

**(5) Is there a shipped PUB producer on 5555? — Only the package's own mock.**
`grep` for `zmq.PUB` / `socket_type::pub` across the superproject finds
`tools/zmq_publish.py:27` (5555, run-state text — the intended peer),
`tests/test_detector_zmq.py:16` (random port), `mu2edaq-trigger-scalers/tools/zmq_sender.cpp:126`
(a test sender defaulting to `tcp://0.0.0.0:5556`, trigger counts, not run state)
and `artdaq-mu2e/test/Generators/ZmqPubSub_test.cc:20,37` (unit test). No
production component publishes run state over ZeroMQ PUB. SUB is the correct
socket type for the producer this detector was written against; what is missing
is a real producer.

**Conclusion.** Mechanism confirmed; grammar sub-claim wrong (unrecognised frames
read UP); consequence overstated (outvoted for tripping, but blocks auto-close via
DTL-002); target host is a stale placeholder in an example file that no deployed
path loads. Severity **S3** (DTL-001), not S2. The fix belongs here (replace the
endpoint, document the PUB requirement); the dashboard should not change socket
type. DASH-002 should be reduced to a cross-reference to DTL-001.

## 4. Scoring semantics

```
score = Σ weightᵢ (state = DOWN) / Σ weightᵢ (state ∈ {UP, DOWN})
```

`core/metric.py:57-66`. UNKNOWN abstains (`:60-61`). With no known detector the
score is `0.0` (`:66`): total blindness reads as UP. Weights are not normalised;
only ratios matter.

**Hysteresis** (`:68-71`): while not down, request DOWN when
`score >= trip_threshold`; while down, stay down while `score > clear_threshold`.

**Latch condition.** A single stuck-DOWN detector `i` holds the score at
`wᵢ / Σ w_known`. If that exceeds `clear_threshold`, no event can auto-close.
With all five example detectors known: zmq 0.227 and disk 0.273 latch; soap and
log 0.182 and udp 0.136 do not — but soap or log latch as soon as any other
detector is UNKNOWN (e.g. 0.4/1.8 = 0.222), and every detector latches when it is
the only one known. In `config/local.yaml` (three detectors of weight 1.0,
clear 0.2) every single detector latches (1/3 = 0.333). DTL-002.

**Debounce and gating** live in the state machine. A requested change arms a
single-shot `QTimer` of `debounce_seconds` (`state_machine.py:145-146`); returning
to the current state before expiry cancels it (`:137-140`). On expiry a flip into
DOWN is dropped while monitoring is disabled (`:155-159`); flips out of DOWN are
always applied. Monitoring defaults to **disabled** (`state_machine.py:40`,
constructed without the argument at `app.py:51`; DTL-016).

**Recorded times.** `started_at` is the time of debounce expiry
(`state_machine.py:175-178` uses the `DowntimeEvent` default), not of the first
crossing; `ended_at` likewise (`:185`). Both lag by `debounce_seconds` plus the
detecting detector's own latency (heartbeat timeout, `idle_seconds`), so
durations are approximately right and absolute times late by up to ~65 s with the
example disk settings.

`opened_by` is the sorted, comma-joined list of detectors that were DOWN at open
(`state_machine.py:169-174`), or `manual` for events created in the UI
(`app.py:199-200`).

`score_changed(score, target)` (`state_machine.py:135`) carries the metric's
*request*, not the state machine's state. The tray, the status widget and the web
snapshot (`app.py:85-89`) all display that request, so the web banner reads
"DAQ DOWN" while monitoring is disabled and no event is open (DTL-016).

## 5. Storage plugin contract

`downtime_logger.storage.base.StorageBackend` (`src/downtime_logger/storage/base.py:10`):
seven abstract methods and a concrete no-op `close()`. Selected by `storage.plugin`
and constructed with `**storage.options` (`app.py:41-43`).

| Method | Contract |
|---|---|
| `open_event(event) -> int` | Persist; set `event.id` in place and return it (`sqlite_backend.py:111-112`). The controller relies on the mutation. |
| `close_event(event)` | Write `ended_at`; no-op if `event.id is None` (`:114-123`). |
| `update_event(event)` | SQLite writes `category`, `subsystem`, `cause`, `notes`, `ended_at`, `updated_at` (`:132-138`). **Not `started_at`**, although the editor dialog offers it (DTL-017). `ended_at` is taken from the dialog verbatim, including `None` when *Ongoing* is checked; the DAQ DOWN popup keeps that box checked after the event closes, so its Save reopens the row (DTL-021). |
| `get_event(id)` | `Optional[DowntimeEvent]`. |
| `delete_event(id) -> bool` | Hard delete; no soft-delete or audit row. |
| `list_events(limit=200)` | Newest first by `started_at`. |
| `list_events_in_range(start, end, limit=5000)` | Overlapping `[start, end]`, oldest first; `ended_at IS NULL` always overlaps (`:172-181`). |
| `log_readings(score, readings)` | One `detector_state_log` row per detector per recompute (`:187-201`). |

Two tables, `downtime_events` and `detector_state_log` (`sqlite_backend.py:33,49`),
created with `create_all` at construction (`:93`); there is no migration
mechanism. Nothing in the package reads `detector_state_log`, and nothing prunes
either table (DTL-004).

**Threads and concurrency.** The base-class docstring requires backends to be safe
from the GUI thread (`storage/base.py:11-14`). In practice the GUI thread writes
(every call in `app.py:145-249`) and each HTTP request thread reads
(`web/server.py:415,425,442,470,476`) concurrently. The engine uses
`check_same_thread=False` (`sqlite_backend.py:91`) and, under SQLAlchemy 2.0.51,
a `QueuePool` — each thread checks out its own connection. The comment at
`sqlite_backend.py:85-86` ("SQLAlchemy's pool serializes access") is wrong: the
pool does not serialise anything; SQLite file locking does. The database runs in
`journal_mode=delete` with pysqlite's 5000 ms busy timeout (both measured). Reads
and writes are single short statements, so contention beyond 5 s is not expected,
but if it happens the GUI-side call raises `database is locked`, the controller
logs it and carries on (`app.py:148-151,155-158,172-175,191-194`): an
`open_event` that fails leaves `event.id = None`, after which `close_event` and
`update_event` are no-ops — the whole event is lost while the popup is still
shown.

## 6. HTTP API

Stdlib `ThreadingHTTPServer` with `daemon_threads = True`
(`web/server.py:511-512`) on a daemon `threading.Thread` (`:552-557`). Not Flask:
the package has no Flask dependency. Read-only by design (`:10-11`); only `do_GET`
exists, so other methods get `http.server`'s 501. No authentication, no TLS,
`Cache-Control: no-store` on every response (`:506`). A bind failure in
`WebServer.start()` (`:546`) is not caught by the controller (`app.py:62-71`) and
aborts startup.

| Route | Response |
|---|---|
| `GET /`, `/index.html` | HTML status page, meta refresh `refresh_seconds` (`:77`); detector table, active event, last `history_limit` events (`:440-444`). |
| `GET /report` | HTML summary. `from`/`to` as `YYYY-MM-DDTHH:MM[:SS]`, **interpreted as UTC** (`:451-458`); default last 7 days (`:448-449`); reversed range swapped (`:464-465`); unparseable value → 500. |
| `GET /api/status` | `{score, is_down, updated_at, readings[], current_event}` (`:62-69`). `is_down` is the metric's request; the enabled flag is not exposed. |
| `GET /api/events` | Array of `history_limit` events, newest first (`:414-418`). |
| `GET /api/events/<id>` | One event or 404; non-integer id → 404 (`:419-429`). |
| `GET /api/report` | `{range, summary, by_category[], by_subsystem[], events[]}` (`:474-496`). |
| `GET /healthz` | `200 ok\n` (`:432-433`); static, reflects neither detectors nor the database. |

Report durations are clamped to the window and an open event runs to `to`
(`:276-281`). `avg_seconds` covers closed events only (`:329-330`) while
`total_seconds` includes open ones (`:328`). An event left open by a `SIGTERM`
(§9) therefore adds the whole remainder of every later window to
`total_seconds`.

All values interpolated into the two HTML templates — detector `detail`
(`:129`), `opened_by`, `category`, `subsystem`, `cause`, `notes`
(`:137-145,160-163,314-317`) — are inserted without HTML escaping; the module
never calls `html.escape` (DTL-015). A handler exception returns
`internal error: <exception text>` (`:436-438`; DTL-012).

## 7. Timezone semantics

In memory everything is UTC-aware: model defaults use `datetime.now(timezone.utc)`
(`core/event.py:20,27,35-36`), readings are stamped in UTC
(`state_machine.py:73`), the editor converts its widgets back with
`datetime.fromtimestamp(..., tz=timezone.utc)` (`ui/popup_dialog.py:141-149`).

SQLite loses the zone. Columns are `DateTime(timezone=True)`
(`sqlite_backend.py:36-37,44-45,52`), but SQLAlchemy's SQLite dialect stores
`'YYYY-MM-DD HH:MM:SS.ffffff'` without an offset and returns **naive** datetimes
holding UTC wall-clock time. Consequences, all reproduced on this branch with
`TZ=America/Chicago`:

* **Editing a past event moves its end.** The history table passes the naive
  event to `EventEditor`, which calls `.timestamp()` on it
  (`ui/popup_dialog.py:82,94`); Python interprets a naive value as *local* time,
  so the widgets show UTC wall-clock labelled as local, and Save converts that
  back as if it were real local time. A 30-minute event whose shifter edits only
  the cause is rewritten with `ended_at` 5 h later: `duration_seconds`
  1800 → 19800. `started_at` is shifted too but not persisted (DTL-017). DTL-003.
* **The Qt history table shows UTC as local.** `_fmt_dt` calls `.astimezone()`
  on the naive value (`ui/main_window.py:36-39`), which is a no-op conversion;
  an event at 09:00 CDT is listed at 14:00. The popup header has the same defect
  and appends the local zone name (`ui/popup_dialog.py:121`).
* **The JSON API mixes forms.** `/api/events` and `/api/report` serialise DB
  values without offset (`2026-10-06T14:00:00`); `/api/status` serialises
  in-memory values with `+00:00` (`web/server.py:32-33`). Both are UTC.
* `duration_seconds` on re-read events is correct (both ends naive,
  `core/event.py:43-46`), and the web report re-attaches UTC with `_as_utc`
  (`web/server.py:269-273`), so `/report` totals are right for unedited events.
* `list_events_in_range` renders aware bounds to strings without converting
  them, so a non-UTC bound selects the wrong window. Every in-tree caller passes
  UTC (`web/server.py:448,455`); latent.

On a host whose local zone is UTC none of the first three effects appear.

## 8. Service discovery

`src/downtime_logger/__main__.py:39-48`: when `webserver.enabled`, a best-effort
`mu2edaq_discovery.Responder(name="Downtime Logger", app="downtime-logger",
port=config.webserver.port, scheme="http")`. No `meta` is passed, so the
string-only `meta` rule of `mu2edaq-discovery/doc/INTERFACES.md` is satisfied
trivially. `host` is not passed; the responder advertises `socket.getfqdn()`
(`mu2edaq-discovery/src/mu2edaq_discovery/protocol.py:65`). With
`config/local.yaml` (`bind: 127.0.0.1`, `port: 8001`) the advertised
`http://<fqdn>:8001` is unreachable from every other host (DTL-013).

## 9. Process lifecycle and signals

`__main__.py:51` installs a handler for `SIGINT` only (`app.quit()`), with a
250 ms wake-up timer so Python can run it (`:52-54`). `app.quit()` emits
`aboutToQuit` → `Controller._cleanup` (`app.py:112,265-283`): web server stop,
`QThread.quit()` + 2 s `wait()` per detector, `storage.close()`. It does **not**
close an open downtime event.

`stop-mu2edaq-downtime-logger.sh:57` sends `SIGTERM`, whose default disposition
terminates the interpreter immediately: no `aboutToQuit`, no `finally`
(`__main__.py:58-60`). Reproduced: exit status 143, neither hook ran. On restart
the state machine starts with no current event (`state_machine.py:46`) and nothing
reloads open rows, so an event that was open at `SIGTERM` stays `ended_at IS NULL`
forever; *End downtime now* on it logs `manual end requested for non-active event`
and does nothing (`app.py:209-215`); every later `/report` window counts it as
ongoing to `to` (reproduced: 30 days of downtime for a window ending 30 days
later). Editing the row and clearing *Ongoing* is the only way to close it
(DTL-014).
