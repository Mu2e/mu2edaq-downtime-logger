---
title: mu2edaq-downtime-logger operations
group: monitoring
tier: A
audience: shifter
summary: Running, observing, stopping and tuning mu2edaq-downtime-logger on a control-room console
---

# Operations — mu2edaq-downtime-logger

## What this is

A desktop application, not a daemon. It needs a display (`QApplication` at
`src/downtime_logger/__main__.py:31`; tray icon at `src/downtime_logger/app.py:76-81`)
unless run with `QT_QPA_PLATFORM=offscreen`. There is no systemd unit. Closing the
main window leaves it running in the tray (`__main__.py:32`).

## Starting

```bash
./bootstrap.sh --dev                                    # venv + package (+ pytest)
./start-mu2edaq-downtime-logger.sh --config /path/to/site.yaml
./start-mu2edaq-downtime-logger.sh --foreground --log-level DEBUG   # local test
```

`start-mu2edaq-downtime-logger.sh` `cd`s to the package (`:45`), bootstraps if
`venv/bin/activate` is missing (`:48-51`), refuses to start over a live PID file and
removes a stale one (`:57-66`), and backgrounds with `nohup`, appending to
`mu2edaq-downtime-logger.log` and writing `mu2edaq-downtime-logger.pid` (`:79-81`).
Both are gitignored (`.gitignore:19-20`). A background start returns 0 before the
application has parsed its config; check the log.

**Without `--config` the script runs `config/local.yaml`** (`:9,28`), a workstation
test file: UDP on 127.0.0.1:9000, disk detector on `/tmp/daq-test`, log detector on
`/tmp/daq-test/run.log`, web view on **127.0.0.1:8001**. The control-room launcher
`crs-app start downtime-logger` passes no arguments
(`mu2edaq-controlroom-setup/server/crs-app:114-118`), so a control-room console
gets exactly this file. Its exported `CRS_PORT_HTTP=8088` is ignored. With that
file nothing feeds the UDP port and `/tmp/daq-test` does not exist, so the score
is 1.0 and enabling monitoring opens an event that never closes (reproduced:
`readings: udp_heartbeat down, local_disk down, local_log unknown; score 1.0`).
Until DTL-013 is fixed, start it by hand with a site configuration.

Port 8001 is also `mu2edaq-snapshot-viewer`'s server port
(`mu2edaq-snapshot-viewer/config/server.yaml:9-10`). If both run on one host, the
second to start fails to bind; for this application that aborts startup with a
traceback in the log.

`--config`/`-c` is required by the application itself
(`src/downtime_logger/__main__.py:17`). There is no default search path, no
`MU2EDAQ_*` environment variable and no `.env`.

## Monitoring is OFF after every start

`StateMachine(enabled=False)` is the default (`core/state_machine.py:40`) and the
controller does not override it (`app.py:51`); there is no config key or option.
While disabled, detectors run and the score is shown, but a request to open an
event is dropped at the end of the debounce window (`state_machine.py:155-159`).

Enable it with the *Monitoring* switch in the main window or *Enable monitoring*
in the tray menu. Enabling recomputes immediately (`state_machine.py:96-98`), so a
condition that is already DOWN opens an event one debounce period later.

The web view cannot tell you the switch position: `/api/status` has no enabled
field, and its `is_down` (and the "DAQ DOWN" banner on `/`) is the metric's
request, shown even when no event can open. The tray tooltip appends
`[monitoring disabled]` (`ui/tray.py:60`). After any restart — crash, reboot,
`crs-app` restart — check the switch.

## Stopping

**Use the tray menu *Quit*, or `SIGINT`.** These run `aboutToQuit` → `_cleanup`
(`app.py:112,265-283`): stop the web server, quit each detector thread with a 2 s
wait, dispose the database engine.

```bash
kill -INT "$(cat mu2edaq-downtime-logger.pid)"     # clean
./stop-mu2edaq-downtime-logger.sh --timeout 30     # SIGTERM, then SIGKILL
```

`stop-mu2edaq-downtime-logger.sh` sends `SIGTERM` (`:57`), polls once a second up
to `--timeout` (default 10), then `SIGKILL` (`:63`). The application installs no
`SIGTERM` handler (`__main__.py:51` handles `SIGINT` only), so `SIGTERM` ends the
process immediately (status 143) with no cleanup. Neither path closes an open
event; with `SIGTERM` the event stays open in the database, the next start does not
reattach it, *End downtime now* on it does nothing, and every later report counts
it as ongoing (DTL-014). Close such a row by editing it: double-click, clear
*Ongoing*, set the end time, Save.

After a `SIGTERM`/`SIGKILL` stop the script also deletes `/tmp/daq-test`
(`:72-77`) regardless of the configuration in use.

## What a shifter sees

**Normal running.** Detector table (id, state, weight, detail), the score with the
metric's request in brackets, and the event history. Tray icon green/red follows
the request.

**A downtime opens.** One debounce period after the score reaches `trip_threshold`
(5 s in the example, 2 s in `local.yaml`), the row is written
(`app.py:155-158`) and the non-modal *DAQ DOWN* popup appears with the start time
and `opened_by` (the detectors that were DOWN). Dismissing it keeps the event,
unclassified. Save writes category, subsystem, cause and notes.

**Recovery.** When the score has been at or below `clear_threshold` for one
debounce period, the event is closed and the popup header updated. If it never
closes, see the next section.

**Do not press Save on the popup after recovery with *Ongoing* still ticked.**
The popup is built while the event is open, so *Ongoing* is ticked; recovery
updates the header but not the checkbox, and Save then writes `ended_at = NULL`
over the closed row (DTL-021, reproduced). The row shows as ongoing again,
*End downtime now* refuses it, and every later report counts it to the end of
the window. Either untick *Ongoing* (and check the end time) before Save, or
dismiss the popup and classify the event from the history table. To repair a
reopened row: double-click it, untick *Ongoing*, set the end time, Save (on a
non-UTC console mind DTL-003).

The same applies to *New event…*: it opens with *Ongoing* ticked, the row it
creates is not held by the state machine, and *End downtime now* cannot close it;
close it by editing.

**Recorded times** are the debounce-expiry times, so the start is late by the
debounce plus the detecting detector's latency (heartbeat timeout, or
`idle_seconds` for the disk detector).

**Manual control.** *New event…* creates an event with `opened_by: manual`; *End
downtime now* closes the event the state machine holds open (only that one);
*Delete event…* is a permanent delete after a confirmation dialog, logged at
WARNING (`app.py:237`).

**Editing past events moves their end time** on any host whose local zone is not
UTC: the editor treats the stored UTC wall-clock time as local. In Chicago a Save
adds 5 h (CDT) or 6 h (CST) to `ended_at`, even if only the cause was changed
(DTL-003). Changes to *Started at* are not saved at all (DTL-017). Until fixed, run
the console with `TZ=UTC`, or record corrections in the notes instead of the time
fields. The history table also shows UTC times as if local.

**Remote view.** With `webserver.enabled`, `/` is the live page and `/report` the
summary; `from`/`to` are UTC. Read-only; editing happens on the console.

## An event that will not close

The metric keeps an open event while `score > clear_threshold`
(`core/metric.py:68-69`). One detector stuck DOWN contributes
`w / Σw(known detectors)`. With the example weights that is 0.227 for ZMQ and
0.273 for disk against `clear_threshold: 0.2`; with `local.yaml` any one of the
three gives 0.333. Such an event will stay open (DTL-002).

Find the row that is DOWN in the detector table, typically with detail
`no zmq messages within timeout`, `no udp datagrams within timeout` or
`no writes in …s`. Then, in order of preference:

1. Fix the source, or remove the dead detector and restart.
2. Lower `clear_threshold` below `min(w)/Σw` (0.136 for the example weights; use
   0.1).
3. *End downtime now*. If the metric still requests DOWN, a new event opens after
   one debounce period.

## Tuning the weights

All in `metric.options` and `detectors[].weight` (`mu2edaq-downtime-logger.yaml(5)`;
algebra in `INTERFACES.md` §4).

1. Weight direct evidence of data flow (disk writes) above corroborating signals.
2. Set `trip_threshold` just below the smallest `Σw(coalition)/Σw(all)` of the
   detector sets whose joint failure must count as downtime. Check the degraded
   case too: UNKNOWN detectors drop out of the denominator, so with SOAP and
   logfile UNKNOWN the example's ZMQ + UDP alone already reach 0.8/1.4 = 0.571 and
   ZMQ alone with only UDP reporting reaches 0.625.
3. Set `clear_threshold` strictly below `min(w)/Σw`.
4. Set `debounce_seconds` above the slowest poll period you want to absorb
   (logfile 1 s, disk 5 s, SOAP 5 s by default).

Restart to apply; there is no reload.

## Data and retention

`storage.options.path` is resolved against the working directory
(`storage/sqlite_backend.py:83`); the start script runs from the package directory,
so `./events.db` lands there.

* `downtime_events` — one row per event; the record of interest.
* `detector_state_log` — one row per detector per recompute
  (`app.py:145-151`, `sqlite_backend.py:187-201`), i.e. per detector transition or
  enable toggle. Nothing reads it, nothing prunes it, no index on `ts` (DTL-004).
  Prune out of band if it grows:

```bash
cp events.db events.db.bak
sqlite3 events.db "DELETE FROM detector_state_log WHERE ts < datetime('now','-90 days'); VACUUM;"
```

Timestamps are stored as UTC wall-clock strings without offset; `datetime('now')`
in SQLite is UTC, so the comparison above is consistent. Back up before any
manual change: event deletes are irreversible.

## Logs

`logging.basicConfig` to stderr, format `%(asctime)s %(levelname)s %(name)s
%(message)s` (`__main__.py:25-28`); in background mode appended to
`mu2edaq-downtime-logger.log` with no rotation. HTTP request logging is at DEBUG
(`web/server.py:400-401`).

Grep for these after any incident:

* `storage.* failed` — a database write or read failed and was swallowed
  (`app.py:151,158,175,194,204,234,247`). A failed `open_event` means the event
  was never stored, although the popup appeared.
* `Traceback` — a detector `start()` that raised. That detector stays `unknown`
  forever while the log still shows `started detector <id>` (DTL-005). After every
  start, confirm each configured detector leaves `unknown` within its first
  timeout or poll period.
* `manual end requested for non-active event` — a shifter tried to end an orphan
  left by `SIGTERM`.
* `UDP bind to … failed` — the UDP detector is UNKNOWN.

## Diagnostics

The `tools/` producers drive each detector without the DAQ; man pages
`zmq_publish.py(1)`, `udp_broadcast.py(1)`, `soap_server.py(1)`,
`disk_writer.py(1)`, `log_writer.py(1)`.

```bash
source venv/bin/activate
python -m tools.udp_broadcast --host 127.0.0.1 --port 9000 --state running
python -m tools.disk_writer --path /tmp/daq-test --interval 5
curl -s http://127.0.0.1:8001/api/status | python -m json.tool
```

`tools/zmq_publish.py` binds 5555 by default; on a host running
`mu2edaq-dashboard` choose another port.
