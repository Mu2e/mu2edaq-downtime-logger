"""
Embedded read-only HTTP server. Runs in a daemon thread, independent of
the Qt event loop. Two layers:

* JSON API (``/api/status``, ``/api/events``, ``/api/events/<id>``) — for
  programmatic clients / dashboards.
* HTML page (``/``) — auto-refreshing status view a shifter can open from
  another machine.

Read-only on purpose. Editing event details should happen on the console
machine through the Qt UI; opening that up over plain HTTP is a footgun.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from ..core.event import DetectorReading, DowntimeEvent
from ..storage.base import StorageBackend
from .snapshot import SnapshotStore, StatusSnapshot

log = logging.getLogger(__name__)


# --- serialization ----------------------------------------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _reading_to_dict(r: DetectorReading) -> dict:
    return {
        "detector_id": r.detector_id,
        "state": r.state.value,
        "weight": r.weight,
        "ts": _iso(r.ts),
        "detail": r.detail,
    }


def _event_to_dict(e: DowntimeEvent) -> dict:
    return {
        "id": e.id,
        "started_at": _iso(e.started_at),
        "ended_at": _iso(e.ended_at),
        "duration_seconds": e.duration_seconds,
        "opened_by": e.opened_by,
        "score_at_open": e.score_at_open,
        "category": e.category,
        "subsystem": e.subsystem,
        "cause": e.cause,
        "notes": e.notes,
        "is_open": e.is_open,
    }


def _snapshot_to_dict(s: StatusSnapshot) -> dict:
    return {
        "score": s.score,
        "is_down": s.is_down,
        "updated_at": _iso(s.updated_at),
        "readings": [_reading_to_dict(r) for r in s.readings.values()],
        "current_event": _event_to_dict(s.current_event) if s.current_event else None,
    }


# --- HTML rendering ---------------------------------------------------------

_HTML = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<title>Mu2e DAQ Downtime — {status_word}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 1.5rem; background: #fafafa; color: #222; }}
  h1 {{ margin-top: 0; }}
  .banner {{ padding: 1rem; border-radius: 6px; font-size: 1.4rem; font-weight: bold;
            color: white; background: {banner_color}; margin-bottom: 1rem; }}
  table {{ border-collapse: collapse; margin: 0.5rem 0; background: white; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.7rem; text-align: left; }}
  th {{ background: #eee; }}
  .state-up {{ background: #d4f0d4; }}
  .state-down {{ background: #f0d4d4; }}
  .state-unknown {{ background: #f0ecc4; }}
  .footer {{ color: #666; font-size: 0.85rem; margin-top: 1rem; }}
  .ongoing {{ font-weight: bold; }}
</style>
</head><body>
<h1>Mu2e DAQ Downtime Logger</h1>
<nav style="margin-bottom:0.8rem;">
  <a href="/" style="margin-right:1rem;color:#226622;font-weight:bold;text-decoration:none;">Live Status</a>
  <a href="/report" style="margin-right:1rem;color:#226622;font-weight:bold;text-decoration:none;">Summary &amp; Report</a>
</nav>
<div class="banner">{status_word} — score {score:.2f}</div>

<h2>Detectors</h2>
{detector_table}

<h2>Active event</h2>
{active_event}

<h2>Recent events</h2>
{event_table}

<div class="footer">
  Updated {updated_at} &middot;
  page auto-refreshes every {refresh}s &middot;
  JSON: <a href="/api/status">/api/status</a>, <a href="/api/events">/api/events</a>
</div>
</body></html>
"""


def _render_detector_table(readings: dict[str, DetectorReading]) -> str:
    if not readings:
        return "<p><i>(no detectors registered)</i></p>"
    rows = ["<tr><th>ID</th><th>State</th><th>Weight</th><th>Last update</th><th>Detail</th></tr>"]
    for did in sorted(readings):
        r = readings[did]
        rows.append(
            f'<tr class="state-{r.state.value}">'
            f"<td>{did}</td><td>{r.state.value}</td>"
            f"<td>{r.weight:.2f}</td><td>{_iso(r.ts) or ''}</td>"
            f"<td>{(r.detail or '')[:200]}</td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def _render_active_event(event: Optional[DowntimeEvent]) -> str:
    if event is None:
        return "<p><i>none — DAQ is up</i></p>"
    return (
        f"<table><tr><th>Started</th><td>{_iso(event.started_at)}</td></tr>"
        f"<tr><th>Opened by</th><td>{event.opened_by}</td></tr>"
        f"<tr><th>Score at open</th><td>{event.score_at_open:.2f}</td></tr>"
        f"<tr><th>Category</th><td>{event.category or ''}</td></tr>"
        f"<tr><th>Subsystem</th><td>{event.subsystem or ''}</td></tr>"
        f"<tr><th>Cause</th><td>{event.cause or ''}</td></tr>"
        f"<tr><th>Notes</th><td>{(event.notes or '').replace(chr(10),'<br>')}</td></tr>"
        "</table>"
    )


def _render_event_table(events: list[DowntimeEvent]) -> str:
    if not events:
        return "<p><i>no events recorded</i></p>"
    rows = [
        "<tr><th>ID</th><th>Started</th><th>Ended</th><th>Duration (s)</th>"
        "<th>Category</th><th>Subsystem</th><th>Cause</th></tr>"
    ]
    for e in events:
        cls = ' class="ongoing"' if e.is_open else ""
        dur = "ongoing" if e.is_open else f"{e.duration_seconds:.0f}"
        rows.append(
            f"<tr{cls}><td>{e.id}</td><td>{_iso(e.started_at)}</td>"
            f"<td>{_iso(e.ended_at) or ''}</td><td>{dur}</td>"
            f"<td>{e.category or ''}</td><td>{e.subsystem or ''}</td>"
            f"<td>{e.cause or ''}</td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


_REPORT_HTML = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Mu2e DAQ Downtime — Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 1.5rem; background: #fafafa; color: #222; }}
  h1, h2 {{ margin-top: 0; }}
  h2 {{ margin-top: 1.2rem; }}
  nav {{ margin-bottom: 1rem; }}
  nav a {{ margin-right: 1rem; color: #226622; font-weight: bold; text-decoration: none; }}
  nav a:hover {{ text-decoration: underline; }}
  form {{ background: white; border: 1px solid #ccc; border-radius: 6px;
          padding: 1rem 1.2rem; display: flex; flex-wrap: wrap;
          align-items: flex-end; gap: 0.8rem; margin-bottom: 1.2rem; }}
  form label {{ display: flex; flex-direction: column; font-size: 0.9rem;
                font-weight: bold; gap: 0.2rem; }}
  form input[type=datetime-local] {{ padding: 0.35rem 0.5rem; border: 1px solid #bbb;
                                      border-radius: 4px; font-size: 0.95rem; }}
  form button {{ padding: 0.4rem 1.1rem; background: #226622; color: white;
                  border: none; border-radius: 4px; font-size: 0.95rem; cursor: pointer; }}
  form button:hover {{ background: #1a4f1a; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 0.8rem; margin-bottom: 1.2rem; }}
  .card {{ background: white; border: 1px solid #ccc; border-radius: 6px;
            padding: 0.7rem 1.2rem; min-width: 160px; }}
  .card .label {{ font-size: 0.8rem; color: #555; }}
  .card .value {{ font-size: 1.6rem; font-weight: bold; color: #226622; }}
  .card.warn .value {{ color: #aa2222; }}
  table {{ border-collapse: collapse; margin: 0.5rem 0; background: white;
           width: 100%; max-width: 960px; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.7rem; text-align: left; }}
  th {{ background: #eee; }}
  tr.ongoing {{ font-weight: bold; background: #fff8e1; }}
  .footer {{ color: #666; font-size: 0.85rem; margin-top: 1.5rem; }}
  .none {{ color: #888; font-style: italic; }}
</style>
</head><body>
<h1>Mu2e DAQ Downtime Logger</h1>
<nav>
  <a href="/">&#8592; Live Status</a>
  <a href="/report">Summary &amp; Report</a>
</nav>

<h2>Date / Time Range</h2>
<form method="get" action="/report">
  <label>From
    <input type="datetime-local" name="from" value="{from_val}" required>
  </label>
  <label>To
    <input type="datetime-local" name="to" value="{to_val}" required>
  </label>
  <button type="submit">Apply</button>
</form>

<h2>Summary</h2>
<div class="cards">
  <div class="card{warn_cls}">
    <div class="label">Total downtime events</div>
    <div class="value">{total_events}</div>
  </div>
  <div class="card{warn_cls}">
    <div class="label">Total downtime</div>
    <div class="value">{total_downtime}</div>
  </div>
  <div class="card">
    <div class="label">Avg duration</div>
    <div class="value">{avg_duration}</div>
  </div>
  <div class="card">
    <div class="label">Longest event</div>
    <div class="value">{longest}</div>
  </div>
</div>

<h2>By Category</h2>
{by_category}

<h2>By Subsystem</h2>
{by_subsystem}

<h2>All Events in Range</h2>
{event_table}

<div class="footer">
  Range: {from_val} &ndash; {to_val} UTC &middot;
  JSON: <a href="/api/report?from={from_val}&amp;to={to_val}">/api/report</a>
</div>
</body></html>
"""


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _as_utc(dt: datetime) -> datetime:
    """Ensure a datetime is UTC-aware, treating naive datetimes as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _clamp_duration(event: DowntimeEvent, start: datetime, end: datetime) -> float:
    """Effective duration of an event clamped to [start, end]."""
    ev_start = max(_as_utc(event.started_at), start)
    ev_end = _as_utc(event.ended_at) if event.ended_at else end
    ev_end = min(ev_end, end)
    return max(0.0, (ev_end - ev_start).total_seconds())


def _render_breakdown_table(rows: list[tuple[str, int, float]]) -> str:
    if not rows:
        return '<p class="none">no data</p>'
    html = (
        "<table><tr><th>Value</th><th>Events</th>"
        "<th>Total downtime</th><th>Avg duration</th></tr>"
    )
    for label, count, total_s in sorted(rows, key=lambda r: r[2], reverse=True):
        avg_s = total_s / count if count else 0
        html += (
            f"<tr><td>{label or '<i>unset</i>'}</td>"
            f"<td>{count}</td>"
            f"<td>{_fmt_duration(total_s)}</td>"
            f"<td>{_fmt_duration(avg_s)}</td></tr>"
        )
    return html + "</table>"


def _render_report_event_table(events: list[DowntimeEvent], start: datetime, end: datetime) -> str:
    if not events:
        return '<p class="none">no events in this range</p>'
    rows = [
        "<tr><th>ID</th><th>Started</th><th>Ended</th>"
        "<th>Duration (clamped)</th><th>Category</th>"
        "<th>Subsystem</th><th>Cause</th></tr>"
    ]
    for e in events:
        cls = ' class="ongoing"' if e.is_open else ""
        dur = _fmt_duration(_clamp_duration(e, start, end))
        rows.append(
            f"<tr{cls}><td>{e.id}</td><td>{_iso(e.started_at)}</td>"
            f"<td>{_iso(e.ended_at) or '<i>ongoing</i>'}</td><td>{dur}</td>"
            f"<td>{e.category or ''}</td><td>{e.subsystem or ''}</td>"
            f"<td>{e.cause or ''}</td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def _build_report_data(
    events: list[DowntimeEvent],
    start: datetime,
    end: datetime,
) -> dict:
    """Compute aggregate statistics for the report."""
    total_s = sum(_clamp_duration(e, start, end) for e in events)
    closed = [e for e in events if not e.is_open]
    avg_s = (sum(_clamp_duration(e, start, end) for e in closed) / len(closed)) if closed else 0.0
    longest_s = max((_clamp_duration(e, start, end) for e in events), default=0.0)

    by_cat: dict[str, list[float]] = {}
    by_sub: dict[str, list[float]] = {}
    for e in events:
        dur = _clamp_duration(e, start, end)
        by_cat.setdefault(e.category or "", []).append(dur)
        by_sub.setdefault(e.subsystem or "", []).append(dur)

    return {
        "total_events": len(events),
        "total_seconds": total_s,
        "avg_seconds": avg_s,
        "longest_seconds": longest_s,
        "by_category": [(k, len(v), sum(v)) for k, v in by_cat.items()],
        "by_subsystem": [(k, len(v), sum(v)) for k, v in by_sub.items()],
    }


def _dt_to_local_input(dt: datetime) -> str:
    """Format a UTC datetime as a datetime-local input value (no timezone suffix)."""
    return dt.strftime("%Y-%m-%dT%H:%M")


def render_report_page(events: list[DowntimeEvent], start: datetime, end: datetime) -> str:
    stats = _build_report_data(events, start, end)
    warn_cls = " warn" if stats["total_events"] > 0 else ""
    return _REPORT_HTML.format(
        from_val=_dt_to_local_input(start),
        to_val=_dt_to_local_input(end),
        warn_cls=warn_cls,
        total_events=stats["total_events"],
        total_downtime=_fmt_duration(stats["total_seconds"]),
        avg_duration=_fmt_duration(stats["avg_seconds"]) if stats["avg_seconds"] else "—",
        longest=_fmt_duration(stats["longest_seconds"]) if stats["longest_seconds"] else "—",
        by_category=_render_breakdown_table(stats["by_category"]),
        by_subsystem=_render_breakdown_table(stats["by_subsystem"]),
        event_table=_render_report_event_table(events, start, end),
    )


def render_page(snap: StatusSnapshot, events: list[DowntimeEvent], refresh: int) -> str:
    if snap.is_down:
        status_word, color = "DAQ DOWN", "#aa2222"
    else:
        status_word, color = "DAQ UP", "#226622"
    return _HTML.format(
        refresh=refresh,
        status_word=status_word,
        banner_color=color,
        score=snap.score,
        detector_table=_render_detector_table(snap.readings),
        active_event=_render_active_event(snap.current_event),
        event_table=_render_event_table(events),
        updated_at=_iso(snap.updated_at) or "",
    )


# --- HTTP wiring ------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    server_version = "DowntimeLogger/0.1"

    # Set by WebServer on the server instance:
    snapshot: SnapshotStore
    storage: StorageBackend
    refresh_seconds: int
    history_limit: int

    def log_message(self, fmt, *args):  # quieter than default stderr spam
        log.debug("[web] " + fmt, *args)

    def do_GET(self):  # noqa: N802 — http.server method name
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                self._html()
            elif path == "/report":
                self._report_html(qs)
            elif path == "/api/status":
                self._json(_snapshot_to_dict(self.server.snapshot.get()))
            elif path == "/api/events":
                events = self.server.storage.list_events(
                    limit=self.server.history_limit
                )
                self._json([_event_to_dict(e) for e in events])
            elif path.startswith("/api/events/"):
                try:
                    eid = int(path.rsplit("/", 1)[1])
                except ValueError:
                    self._send(404, b"not found", "text/plain")
                    return
                event = self.server.storage.get_event(eid)
                if event is None:
                    self._send(404, b"not found", "text/plain")
                    return
                self._json(_event_to_dict(event))
            elif path == "/api/report":
                self._report_json(qs)
            elif path == "/healthz":
                self._send(200, b"ok\n", "text/plain")
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as e:
            log.exception("web handler error")
            self._send(500, f"internal error: {e}".encode(), "text/plain")

    def _html(self) -> None:
        snap = self.server.snapshot.get()
        events = self.server.storage.list_events(limit=self.server.history_limit)
        body = render_page(snap, events, self.server.refresh_seconds).encode()
        self._send(200, body, "text/html; charset=utf-8")

    def _parse_range(self, qs: dict) -> tuple[datetime, datetime]:
        """Return (start, end) UTC datetimes from query string, defaulting to last 7 days."""
        now = datetime.now(timezone.utc)
        default_start = now - timedelta(days=7)

        def _parse(val: str) -> datetime:
            # datetime-local inputs emit "YYYY-MM-DDTHH:MM" without timezone.
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            raise ValueError(f"unparseable datetime: {val!r}")

        start_str = qs.get("from", [None])[0]
        end_str = qs.get("to", [None])[0]
        start = _parse(start_str) if start_str else default_start
        end = _parse(end_str) if end_str else now
        if start > end:
            start, end = end, start
        return start, end

    def _report_html(self, qs: dict) -> None:
        start, end = self._parse_range(qs)
        events = self.server.storage.list_events_in_range(start, end)
        body = render_report_page(events, start, end).encode()
        self._send(200, body, "text/html; charset=utf-8")

    def _report_json(self, qs: dict) -> None:
        start, end = self._parse_range(qs)
        events = self.server.storage.list_events_in_range(start, end)
        stats = _build_report_data(events, start, end)
        payload = {
            "range": {"from": _iso(start), "to": _iso(end)},
            "summary": {
                "total_events": stats["total_events"],
                "total_seconds": stats["total_seconds"],
                "avg_seconds": stats["avg_seconds"],
                "longest_seconds": stats["longest_seconds"],
            },
            "by_category": [
                {"category": k, "events": c, "total_seconds": s}
                for k, c, s in stats["by_category"]
            ],
            "by_subsystem": [
                {"subsystem": k, "events": c, "total_seconds": s}
                for k, c, s in stats["by_subsystem"]
            ],
            "events": [_event_to_dict(e) for e in events],
        }
        self._json(payload)

    def _json(self, obj) -> None:
        body = json.dumps(obj, default=str).encode()
        self._send(200, body, "application/json")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    snapshot: SnapshotStore
    storage: StorageBackend
    refresh_seconds: int
    history_limit: int


class WebServer:
    def __init__(
        self,
        snapshot: SnapshotStore,
        storage: StorageBackend,
        bind: str = "0.0.0.0",
        port: int = 8088,
        refresh_seconds: int = 5,
        history_limit: int = 200,
    ) -> None:
        self._snapshot = snapshot
        self._storage = storage
        self._bind = bind
        self._port = port
        self._refresh_seconds = refresh_seconds
        self._history_limit = history_limit

        self._server: Optional[_Server] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        if self._server is None:
            return self._port
        return self._server.server_address[1]

    def start(self) -> None:
        self._server = _Server((self._bind, self._port), _Handler)
        self._server.snapshot = self._snapshot
        self._server.storage = self._storage
        self._server.refresh_seconds = self._refresh_seconds
        self._server.history_limit = self._history_limit

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="downtime-web",
            daemon=True,
        )
        self._thread.start()
        log.info("web server listening on %s:%d", self._bind, self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
