from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .event import DetectorReading, DetectorState, DowntimeEvent
from .metric import Metric

log = logging.getLogger(__name__)


class StateMachine(QObject):
    """
    Owns the current set of detector readings, recomputes the metric on every
    update, and emits open/close signals when the binary state flips. A
    debounce window prevents flapping detectors from creating spurious events.

    Signals are designed to be wired straight to storage and to the UI:

        readings_changed     -> status widget refreshes
        score_changed        -> live score display
        event_opened         -> popup + storage.open()
        event_closed         -> close popup + storage.close()
    """

    readings_changed = Signal(dict)          # {detector_id: DetectorReading}
    score_changed = Signal(float, bool)      # score, is_down
    event_opened = Signal(object)            # DowntimeEvent
    event_closed = Signal(object)            # DowntimeEvent
    enabled_changed = Signal(bool)

    def __init__(
        self,
        metric: Metric,
        debounce_seconds: float = 5.0,
        parent: Optional[QObject] = None,
        enabled: bool = False,
    ) -> None:
        super().__init__(parent)
        self._metric = metric
        self._readings: dict[str, DetectorReading] = {}
        self._is_down = False
        self._current_event: Optional[DowntimeEvent] = None
        self._last_score = 0.0
        self._enabled = enabled

        self._debounce_ms = int(debounce_seconds * 1000)
        self._pending_target: Optional[bool] = None
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._apply_pending)

    # --- public surface ---------------------------------------------------

    def register_detector(self, detector_id: str, weight: float) -> None:
        self._readings[detector_id] = DetectorReading(
            detector_id=detector_id,
            state=DetectorState.UNKNOWN,
            weight=weight,
        )

    @Slot(str, str, str)
    def on_state_changed(self, detector_id: str, state: str, detail: str = "") -> None:
        existing = self._readings.get(detector_id)
        if existing is None:
            log.warning("Reading from unregistered detector %s", detector_id)
            return
        existing.state = DetectorState(state)
        existing.detail = detail or None
        existing.ts = datetime.now(timezone.utc)
        self._recompute()

    @property
    def current_event(self) -> Optional[DowntimeEvent]:
        return self._current_event

    @property
    def enabled(self) -> bool:
        return self._enabled

    @Slot(bool)
    def set_enabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = bool(enabled)
        log.info("monitoring %s", "enabled" if self._enabled else "disabled")
        self.enabled_changed.emit(self._enabled)
        if not self._enabled:
            # Drop any pending trip; on re-enable a fresh recompute decides.
            self._pending_target = None
            self._debounce_timer.stop()
        else:
            # Re-evaluate now so a stuck-down condition trips immediately
            # rather than waiting for the next detector update.
            self._recompute()

    def close_current_event(self, when: Optional[datetime] = None) -> Optional[DowntimeEvent]:
        """
        Force-close the active event (manual end). If detectors are still
        reporting DOWN, a fresh event will open after the next debounce.
        """
        if self._current_event is None:
            return None
        self._pending_target = None
        self._debounce_timer.stop()
        self._is_down = False
        self._current_event.ended_at = when or datetime.now(timezone.utc)
        self._current_event.updated_at = self._current_event.ended_at
        closed = self._current_event
        self._current_event = None
        log.info(
            "Downtime event manually closed (id=%s, duration=%.1fs)",
            closed.id, closed.duration_seconds or 0.0,
        )
        self.event_closed.emit(closed)
        return closed

    @property
    def readings(self) -> dict[str, DetectorReading]:
        return dict(self._readings)

    @property
    def last_score(self) -> float:
        return self._last_score

    # --- internals --------------------------------------------------------

    def _recompute(self) -> None:
        score, target = self._metric.evaluate(self._readings, self._is_down)
        self._last_score = score
        self.readings_changed.emit(dict(self._readings))
        self.score_changed.emit(score, target)

        if target == self._is_down:
            self._pending_target = None
            self._debounce_timer.stop()
            return

        if self._pending_target == target and self._debounce_timer.isActive():
            return

        self._pending_target = target
        self._debounce_timer.start(self._debounce_ms)

    @Slot()
    def _apply_pending(self) -> None:
        if self._pending_target is None or self._pending_target == self._is_down:
            return
        target = self._pending_target
        self._pending_target = None

        if target and not self._enabled:
            # Disabled: don't trip into a new downtime. Closing existing
            # events is still allowed so a stale event from before disable
            # can resolve naturally.
            return

        self._is_down = target

        if target:
            self._open_event()
        else:
            self._close_event()

    def _open_event(self) -> None:
        opener = ", ".join(
            sorted(
                rid for rid, r in self._readings.items()
                if r.state is DetectorState.DOWN
            )
        ) or "unknown"
        self._current_event = DowntimeEvent(
            opened_by=opener,
            score_at_open=self._last_score,
        )
        log.info("Downtime event opened by [%s] score=%.3f", opener, self._last_score)
        self.event_opened.emit(self._current_event)

    def _close_event(self) -> None:
        if self._current_event is None:
            return
        self._current_event.ended_at = datetime.now(timezone.utc)
        self._current_event.updated_at = self._current_event.ended_at
        log.info(
            "Downtime event closed (id=%s, duration=%.1fs)",
            self._current_event.id,
            self._current_event.duration_seconds or 0.0,
        )
        closed = self._current_event
        self._current_event = None
        self.event_closed.emit(closed)
