"""
Listens on a ZMQ SUB socket for run-status messages. Two contracts supported:

1. **Explicit**: messages of the form ``RUN STATE running`` or
   ``RUN STATE stopped`` flip the state immediately.
2. **Heartbeat**: any message resets a watchdog; if no message arrives within
   ``heartbeat_timeout_s``, the detector flips to DOWN.

The two modes coexist — explicit "stopped" wins immediately; heartbeat covers
the case where the publisher dies entirely.
"""
from __future__ import annotations

import logging

import zmq
from PySide6.QtCore import QSocketNotifier, QTimer, Slot

from ..core.event import DetectorState
from .base import Detector

log = logging.getLogger(__name__)

_DOWN_TOKENS = {"stopped", "stop", "down", "halted", "abort", "aborted"}
_UP_TOKENS = {"running", "run", "up", "started", "active"}


class ZmqDetector(Detector):
    def __init__(
        self,
        detector_id: str,
        endpoint: str,
        topic: str = "",
        heartbeat_timeout_s: float = 10.0,
        **_: object,
    ) -> None:
        super().__init__(detector_id)
        self._endpoint = endpoint
        self._topic = topic.encode() if isinstance(topic, str) else topic
        self._timeout_ms = int(heartbeat_timeout_s * 1000)

        self._ctx: zmq.Context | None = None
        self._sock: zmq.Socket | None = None
        self._notifier: QSocketNotifier | None = None
        self._watchdog: QTimer | None = None

    @Slot()
    def start(self) -> None:
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.SUB)
        self._sock.setsockopt(zmq.SUBSCRIBE, self._topic)
        self._sock.connect(self._endpoint)

        fd = self._sock.getsockopt(zmq.FD)
        self._notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read)
        self._notifier.activated.connect(self._on_readable)

        self._watchdog = QTimer()
        self._watchdog.setInterval(self._timeout_ms)
        self._watchdog.timeout.connect(self._on_heartbeat_timeout)
        self._watchdog.start()

        log.info("zmq detector %s connected to %s", self.detector_id, self._endpoint)

    @Slot()
    def stop(self) -> None:
        if self._watchdog:
            self._watchdog.stop()
        if self._notifier:
            self._notifier.setEnabled(False)
        if self._sock:
            self._sock.close(0)
            self._sock = None

    @Slot()
    def _on_readable(self, *_: object) -> None:
        if self._sock is None:
            return
        # Edge-triggered FD; drain everything available.
        while True:
            try:
                msg = self._sock.recv(flags=zmq.NOBLOCK)
            except zmq.Again:
                break
            self._handle_message(msg)
        if self._watchdog:
            self._watchdog.start()  # reset

    def _handle_message(self, msg: bytes) -> None:
        text = msg.decode(errors="replace").strip().lower()
        if any(t in text for t in _DOWN_TOKENS):
            self._emit_state(DetectorState.DOWN, text)
        elif any(t in text for t in _UP_TOKENS):
            self._emit_state(DetectorState.UP, text)
        else:
            # Unknown payload still counts as a heartbeat -> UP-ish presence.
            self._emit_state(DetectorState.UP, f"heartbeat: {text[:64]}")

    @Slot()
    def _on_heartbeat_timeout(self) -> None:
        self._emit_state(DetectorState.DOWN, "no zmq messages within timeout")
