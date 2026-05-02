"""
End-to-end tests for the embedded web server. Spins up a real HTTP
server on an ephemeral 127.0.0.1 port, fires requests via
urllib.request, and asserts on the responses.
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from downtime_logger.core.event import DetectorReading, DetectorState, DowntimeEvent
from downtime_logger.storage.sqlite_backend import SQLiteBackend
from downtime_logger.web.server import WebServer
from downtime_logger.web.snapshot import SnapshotStore


@pytest.fixture
def storage(tmp_path):
    b = SQLiteBackend(path=str(tmp_path / "events.db"))
    yield b
    b.close()


@pytest.fixture
def snapshot():
    s = SnapshotStore()
    s.update_score(0.42, is_down=False)
    s.update_readings({
        "a": DetectorReading("a", DetectorState.UP, 0.5, detail="ok"),
        "b": DetectorReading("b", DetectorState.DOWN, 0.5, detail="bad"),
    })
    return s


@pytest.fixture
def server(snapshot, storage):
    w = WebServer(
        snapshot=snapshot,
        storage=storage,
        bind="127.0.0.1",
        port=0,  # ephemeral
        refresh_seconds=2,
    )
    w.start()
    yield w
    w.stop()


def _get(server: WebServer, path: str) -> tuple[int, str]:
    url = f"http://127.0.0.1:{server.port}{path}"
    with urllib.request.urlopen(url, timeout=2) as resp:
        return resp.getcode(), resp.read().decode()


def test_html_status_page(server):
    code, body = _get(server, "/")
    assert code == 200
    assert "Mu2e DAQ Downtime Logger" in body
    assert "score 0.42" in body
    assert "DAQ UP" in body  # is_down=False


def test_api_status_returns_current_state(server):
    code, body = _get(server, "/api/status")
    assert code == 200
    payload = json.loads(body)
    assert payload["score"] == pytest.approx(0.42)
    assert payload["is_down"] is False
    assert {r["detector_id"] for r in payload["readings"]} == {"a", "b"}
    assert payload["current_event"] is None


def test_api_events_lists_recent(server, storage):
    base = datetime.now(timezone.utc)
    e1 = DowntimeEvent(started_at=base - timedelta(minutes=10), opened_by="zmq")
    e1.ended_at = base - timedelta(minutes=9)
    storage.open_event(e1)
    storage.close_event(e1)

    e2 = DowntimeEvent(started_at=base - timedelta(minutes=2), opened_by="udp")
    storage.open_event(e2)  # ongoing

    code, body = _get(server, "/api/events")
    assert code == 200
    events = json.loads(body)
    assert len(events) == 2
    # ordering: most-recent first
    assert events[0]["opened_by"] == "udp"
    assert events[0]["is_open"] is True
    assert events[1]["opened_by"] == "zmq"
    assert events[1]["is_open"] is False


def test_api_event_by_id(server, storage):
    e = DowntimeEvent(opened_by="logfile", score_at_open=0.9)
    storage.open_event(e)
    code, body = _get(server, f"/api/events/{e.id}")
    assert code == 200
    payload = json.loads(body)
    assert payload["id"] == e.id
    assert payload["opened_by"] == "logfile"
    assert payload["score_at_open"] == pytest.approx(0.9)


def test_api_event_404(server):
    url = f"http://127.0.0.1:{server.port}/api/events/9999"
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(url, timeout=2)
    assert exc.value.code == 404


def test_unknown_path_404(server):
    url = f"http://127.0.0.1:{server.port}/nope"
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(url, timeout=2)
    assert exc.value.code == 404


def test_healthz(server):
    code, body = _get(server, "/healthz")
    assert code == 200
    assert body.strip() == "ok"


def test_active_event_appears_in_status(server, snapshot):
    e = DowntimeEvent(id=7, opened_by="zmq, udp", score_at_open=0.8)
    snapshot.set_current_event(e)
    snapshot.update_score(0.8, is_down=True)
    code, body = _get(server, "/api/status")
    assert code == 200
    payload = json.loads(body)
    assert payload["is_down"] is True
    assert payload["current_event"]["id"] == 7
    assert payload["current_event"]["opened_by"] == "zmq, udp"


def test_html_renders_down_banner(server, snapshot):
    snapshot.update_score(0.9, is_down=True)
    code, body = _get(server, "/")
    assert code == 200
    assert "DAQ DOWN" in body


import urllib.error  # noqa: E402 — referenced from inside test bodies
