from datetime import datetime, timedelta, timezone

import pytest

from downtime_logger.core.event import DetectorReading, DetectorState, DowntimeEvent
from downtime_logger.storage.sqlite_backend import SQLiteBackend


@pytest.fixture
def backend(tmp_path):
    b = SQLiteBackend(path=str(tmp_path / "events.db"))
    yield b
    b.close()


def test_open_assigns_id(backend):
    e = DowntimeEvent(opened_by="zmq", score_at_open=0.8)
    new_id = backend.open_event(e)
    assert new_id == e.id == 1


def test_close_persists_ended_at(backend):
    e = DowntimeEvent(opened_by="zmq", score_at_open=0.8)
    backend.open_event(e)
    e.ended_at = e.started_at + timedelta(seconds=42)
    backend.close_event(e)
    fetched = backend.get_event(e.id)
    assert fetched.ended_at is not None
    assert abs(fetched.duration_seconds - 42.0) < 1e-3


def test_update_event_persists_fields(backend):
    e = DowntimeEvent(opened_by="udp", score_at_open=0.7)
    backend.open_event(e)
    e.category = "Hardware"
    e.subsystem = "DTC"
    e.cause = "fiber unplugged"
    e.notes = "found by mid-shift round"
    backend.update_event(e)
    fetched = backend.get_event(e.id)
    assert fetched.category == "Hardware"
    assert fetched.subsystem == "DTC"
    assert fetched.cause == "fiber unplugged"
    assert fetched.notes == "found by mid-shift round"


def test_list_events_orders_recent_first(backend):
    base = datetime.now(timezone.utc)
    for i in range(3):
        backend.open_event(DowntimeEvent(
            started_at=base + timedelta(minutes=i), opened_by=f"d{i}"
        ))
    rows = backend.list_events()
    assert [r.opened_by for r in rows] == ["d2", "d1", "d0"]


def test_log_readings_persists_all(backend):
    readings = [
        DetectorReading("a", DetectorState.DOWN, 0.5),
        DetectorReading("b", DetectorState.UP, 0.5),
    ]
    backend.log_readings(score=0.5, readings=readings)
    # Second insert with different score:
    backend.log_readings(score=0.0, readings=[
        DetectorReading("a", DetectorState.UP, 0.5),
    ])
    # Quick smoke check: re-opening the DB and counting rows.
    from sqlalchemy import select, func
    from downtime_logger.storage.sqlite_backend import _ReadingRow
    from sqlalchemy.orm import Session
    with Session(backend._engine) as s:
        count = s.scalar(select(func.count()).select_from(_ReadingRow))
    assert count == 3
