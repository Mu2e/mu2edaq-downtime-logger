"""
Smoke tests: instantiate each Qt widget and exercise its public slots
without showing a real window. Catches import errors and basic wiring
mistakes; not a substitute for manual UI review.
"""
from datetime import datetime, timedelta, timezone

from downtime_logger.core.event import DetectorReading, DetectorState, DowntimeEvent
from downtime_logger.ui.main_window import MainWindow
from downtime_logger.ui.popup_dialog import EventEditor, NewEventPopup
from downtime_logger.ui.status_widget import StatusWidget


def _readings():
    return {
        "a": DetectorReading("a", DetectorState.DOWN, 0.5, detail="oops"),
        "b": DetectorReading("b", DetectorState.UP, 0.3, detail=""),
        "c": DetectorReading("c", DetectorState.UNKNOWN, 0.2, detail=""),
    }


def test_status_widget_updates(qtbot):
    w = StatusWidget()
    qtbot.addWidget(w)
    w.on_score(0.62, True)
    w.on_readings(_readings())
    assert "0.62" in w._score_label.text()
    assert w._table.rowCount() == 3


def test_main_window_lists_events(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    base = datetime.now(timezone.utc)
    events = [
        DowntimeEvent(id=1, started_at=base - timedelta(minutes=5),
                      ended_at=base - timedelta(minutes=4), opened_by="zmq"),
        DowntimeEvent(id=2, started_at=base - timedelta(minutes=2),
                      opened_by="udp"),  # ongoing
    ]
    w.set_events(events)
    assert w._table.rowCount() == 2
    assert w._table.item(0, 0).text() == "1"
    assert "ongoing" in w._table.item(1, 3).text()


def test_event_editor_save_emits_signal(qtbot):
    ev = DowntimeEvent(id=42, opened_by="x")
    dlg = EventEditor(ev)
    qtbot.addWidget(dlg)

    captured: list = []
    dlg.saved.connect(lambda e: captured.append(e))

    dlg._cause.setText("cooling failure")
    dlg._notes.setPlainText("hot aisle alarm")
    dlg._on_save()

    assert captured and captured[0] is ev
    assert ev.cause == "cooling failure"
    assert ev.notes == "hot aisle alarm"


def test_new_event_popup_is_non_modal(qtbot):
    ev = DowntimeEvent(opened_by="zmq")
    p = NewEventPopup(ev)
    qtbot.addWidget(p)
    assert p.isModal() is False
