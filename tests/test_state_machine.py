"""
State-machine tests using pytest-qt's qtbot to drive the Qt event loop so
the debounce QTimer actually fires.
"""
import pytest

from downtime_logger.core.event import DetectorState
from downtime_logger.core.metric import WeightedRatioMetric
from downtime_logger.core.state_machine import StateMachine


@pytest.fixture
def sm(qtbot):
    metric = WeightedRatioMetric(trip_threshold=0.5, clear_threshold=0.2)
    machine = StateMachine(metric=metric, debounce_seconds=0.05, enabled=True)
    machine.register_detector("a", weight=1.0)
    machine.register_detector("b", weight=1.0)
    return machine


def test_opens_event_after_debounce(qtbot, sm):
    with qtbot.waitSignal(sm.event_opened, timeout=2000) as blocker:
        sm.on_state_changed("a", DetectorState.DOWN.value, "")
        sm.on_state_changed("b", DetectorState.DOWN.value, "")
    event = blocker.args[0]
    assert event.opened_by == "a, b"
    assert event.score_at_open == 1.0
    assert event.is_open


def test_does_not_open_below_trip_threshold(qtbot, sm):
    sm.on_state_changed("a", DetectorState.DOWN.value, "")
    sm.on_state_changed("b", DetectorState.UP.value, "")
    # Score 0.5 == trip threshold so this should still trip; choose 0.4.
    sm._readings["a"].weight = 0.4
    sm._readings["b"].weight = 0.6
    sm.on_state_changed("a", DetectorState.DOWN.value, "")
    qtbot.wait(150)  # past debounce
    assert sm.current_event is None


def test_close_event_after_recovery(qtbot, sm):
    with qtbot.waitSignal(sm.event_opened, timeout=2000):
        sm.on_state_changed("a", DetectorState.DOWN.value, "")
        sm.on_state_changed("b", DetectorState.DOWN.value, "")
    with qtbot.waitSignal(sm.event_closed, timeout=2000) as blocker:
        sm.on_state_changed("a", DetectorState.UP.value, "")
        sm.on_state_changed("b", DetectorState.UP.value, "")
    closed = blocker.args[0]
    assert closed.ended_at is not None
    assert closed.duration_seconds is not None


def test_flap_within_debounce_does_not_open(qtbot, sm):
    sm.on_state_changed("a", DetectorState.DOWN.value, "")
    sm.on_state_changed("b", DetectorState.DOWN.value, "")
    qtbot.wait(20)  # less than 50ms debounce
    sm.on_state_changed("a", DetectorState.UP.value, "")
    sm.on_state_changed("b", DetectorState.UP.value, "")
    qtbot.wait(150)
    assert sm.current_event is None


def test_manual_close_emits_event_closed(qtbot, sm):
    with qtbot.waitSignal(sm.event_opened, timeout=2000):
        sm.on_state_changed("a", DetectorState.DOWN.value, "")
        sm.on_state_changed("b", DetectorState.DOWN.value, "")
    with qtbot.waitSignal(sm.event_closed, timeout=2000) as blocker:
        sm.close_current_event()
    closed = blocker.args[0]
    assert closed.ended_at is not None
    assert sm.current_event is None


def test_manual_close_when_idle_is_noop(qtbot, sm):
    assert sm.close_current_event() is None


def test_default_state_is_disabled(qtbot):
    metric = WeightedRatioMetric(trip_threshold=0.5, clear_threshold=0.2)
    machine = StateMachine(metric=metric, debounce_seconds=0.05)
    assert machine.enabled is False


def test_disabled_does_not_open_event(qtbot):
    metric = WeightedRatioMetric(trip_threshold=0.5, clear_threshold=0.2)
    machine = StateMachine(metric=metric, debounce_seconds=0.05)  # disabled by default
    machine.register_detector("a", weight=1.0)
    machine.register_detector("b", weight=1.0)

    received: list = []
    machine.event_opened.connect(received.append)
    machine.on_state_changed("a", DetectorState.DOWN.value, "")
    machine.on_state_changed("b", DetectorState.DOWN.value, "")
    qtbot.wait(150)  # past debounce
    assert received == []
    assert machine.current_event is None


def test_enable_after_trip_opens_on_next_recompute(qtbot):
    metric = WeightedRatioMetric(trip_threshold=0.5, clear_threshold=0.2)
    machine = StateMachine(metric=metric, debounce_seconds=0.05)
    machine.register_detector("a", weight=1.0)
    machine.register_detector("b", weight=1.0)
    machine.on_state_changed("a", DetectorState.DOWN.value, "")
    machine.on_state_changed("b", DetectorState.DOWN.value, "")
    qtbot.wait(150)
    assert machine.current_event is None  # disabled, no event

    machine.set_enabled(True)
    with qtbot.waitSignal(machine.event_opened, timeout=2000):
        # any further detector update re-runs the metric and trips
        machine.on_state_changed("a", DetectorState.DOWN.value, "")


def test_score_signal_emitted_on_every_change(qtbot, sm):
    received: list[tuple[float, bool]] = []
    sm.score_changed.connect(lambda s, d: received.append((s, d)))
    sm.on_state_changed("a", DetectorState.DOWN.value, "")
    sm.on_state_changed("b", DetectorState.UP.value, "")
    assert len(received) == 2
    assert received[-1][0] == pytest.approx(0.5)
