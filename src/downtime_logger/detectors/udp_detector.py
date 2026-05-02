"""
Watches a UDP port for heartbeat broadcasts. Same dual-contract as the
ZMQ detector: explicit ``stopped``/``running`` text flips state immediately,
otherwise any datagram resets a watchdog.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QTimer, Slot
from PySide6.QtNetwork import QHostAddress, QUdpSocket

from ..core.event import DetectorState
from .base import Detector

log = logging.getLogger(__name__)

_DOWN_TOKENS = {"stopped", "stop", "down", "halted", "abort", "aborted"}
_UP_TOKENS = {"running", "run", "up", "started", "active"}


class UdpDetector(Detector):
    def __init__(
        self,
        detector_id: str,
        bind: str = "0.0.0.0",
        port: int = 9000,
        heartbeat_timeout_s: float = 15.0,
        **_: object,
    ) -> None:
        super().__init__(detector_id)
        self._bind = bind
        self._port = int(port)
        self._timeout_ms = int(heartbeat_timeout_s * 1000)

        self._sock: QUdpSocket | None = None
        self._watchdog: QTimer | None = None

    @Slot()
    def start(self) -> None:
        self._sock = QUdpSocket()
        ok = self._sock.bind(
            QHostAddress(self._bind),
            self._port,
            QUdpSocket.BindFlag.ShareAddress | QUdpSocket.BindFlag.ReuseAddressHint,
        )
        if not ok:
            log.error("UDP bind to %s:%d failed: %s",
                      self._bind, self._port, self._sock.errorString())
            self._emit_state(DetectorState.UNKNOWN, "bind failed")
            return
        self._sock.readyRead.connect(self._on_datagrams)

        self._watchdog = QTimer()
        self._watchdog.setInterval(self._timeout_ms)
        self._watchdog.timeout.connect(self._on_heartbeat_timeout)
        self._watchdog.start()
        log.info("udp detector %s listening on %s:%d",
                 self.detector_id, self._bind, self._port)

    @Slot()
    def stop(self) -> None:
        if self._watchdog:
            self._watchdog.stop()
        if self._sock:
            self._sock.close()
            self._sock = None

    @Slot()
    def _on_datagrams(self) -> None:
        if self._sock is None:
            return
        while self._sock.hasPendingDatagrams():
            datagram = self._sock.receiveDatagram()
            data = bytes(datagram.data()).decode(errors="replace").strip().lower()
            if any(t in data for t in _DOWN_TOKENS):
                self._emit_state(DetectorState.DOWN, data)
            elif any(t in data for t in _UP_TOKENS):
                self._emit_state(DetectorState.UP, data)
            else:
                self._emit_state(DetectorState.UP, f"heartbeat: {data[:64]}")
        if self._watchdog:
            self._watchdog.start()  # reset

    @Slot()
    def _on_heartbeat_timeout(self) -> None:
        self._emit_state(DetectorState.DOWN, "no udp datagrams within timeout")
