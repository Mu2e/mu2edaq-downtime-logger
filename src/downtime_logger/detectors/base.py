"""
Detector base class.

Each detector is a ``QObject`` that runs on its own ``QThread`` and emits
``state_changed(detector_id, state, detail)`` whenever its view of the DAQ
changes. The subclass overrides ``start()`` (called on the worker thread)
and ``stop()`` (called from the owning thread to request shutdown).

Heartbeat-style detectors (UDP, ZeroMQ, sometimes SOAP) typically arm a
``QTimer`` inside ``start()`` and flip to DOWN when the timer fires
without a recent message. Polling detectors (SOAP, disk, log) usually
just run a periodic check.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from ..core.event import DetectorState

log = logging.getLogger(__name__)


class Detector(QObject):
    state_changed = Signal(str, str, str)  # detector_id, state.value, detail

    def __init__(self, detector_id: str, **options: Any) -> None:
        super().__init__()
        self.detector_id = detector_id
        self._options = options
        self._last_state: DetectorState = DetectorState.UNKNOWN
        self._emitted_once = False

    # --- subclass surface -------------------------------------------------

    @Slot()
    def start(self) -> None:
        """Called on the worker thread; subclass should set up I/O here."""
        raise NotImplementedError

    @Slot()
    def stop(self) -> None:
        """Request shutdown. Default: no-op (works for purely-timer-driven
        detectors whose thread is reaped when the QThread quits)."""

    # --- helpers ----------------------------------------------------------

    def _emit_state(self, state: DetectorState, detail: str = "") -> None:
        if self._emitted_once and state == self._last_state:
            return
        self._last_state = state
        self._emitted_once = True
        log.debug("%s -> %s (%s)", self.detector_id, state.value, detail)
        self.state_changed.emit(self.detector_id, state.value, detail)
