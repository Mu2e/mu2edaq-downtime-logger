"""
Polls a SOAP endpoint for run state. The exact operation/field varies per
deployment, so this detector lets you configure both:

    operation: getRunState           # SOAP operation to invoke
    args: {}                         # kwargs passed to the operation
    state_path: "result.runState"    # dotted path into the response
    down_values: ["Stopped", "Idle"]
    up_values: ["Running"]

If the call raises (network down, WSDL fetch failed, etc.) we emit UNKNOWN
rather than DOWN — the metric weights "up vs down" only over known
detectors, so a flapping SOAP service doesn't pollute the score.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QTimer, Slot
from zeep import Client

from ..core.event import DetectorState
from .base import Detector

log = logging.getLogger(__name__)


def _dig(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


class SoapDetector(Detector):
    def __init__(
        self,
        detector_id: str,
        wsdl: str,
        operation: str = "getRunState",
        args: dict[str, Any] | None = None,
        state_path: str = "runState",
        down_values: list[str] | None = None,
        up_values: list[str] | None = None,
        poll_s: float = 5.0,
        **_: object,
    ) -> None:
        super().__init__(detector_id)
        self._wsdl = wsdl
        self._operation = operation
        self._args = args or {}
        self._state_path = state_path
        self._down_values = {v.lower() for v in (down_values or ["stopped", "idle", "halted"])}
        self._up_values = {v.lower() for v in (up_values or ["running", "active"])}
        self._poll_ms = int(poll_s * 1000)

        self._client: Client | None = None
        self._timer: QTimer | None = None

    @Slot()
    def start(self) -> None:
        self._timer = QTimer()
        self._timer.setInterval(self._poll_ms)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        # Don't block startup on a slow WSDL fetch — defer to first tick.
        QTimer.singleShot(0, self._poll)
        log.info("soap detector %s polling %s every %dms",
                 self.detector_id, self._wsdl, self._poll_ms)

    @Slot()
    def stop(self) -> None:
        if self._timer:
            self._timer.stop()

    def _ensure_client(self) -> Client | None:
        if self._client is not None:
            return self._client
        try:
            self._client = Client(self._wsdl)
        except Exception as e:  # zeep raises a wide variety of exceptions
            log.warning("zeep client init failed for %s: %s", self._wsdl, e)
            return None
        return self._client

    @Slot()
    def _poll(self) -> None:
        client = self._ensure_client()
        if client is None:
            self._emit_state(DetectorState.UNKNOWN, "wsdl unreachable")
            return
        try:
            op = getattr(client.service, self._operation)
            response = op(**self._args)
        except Exception as e:
            self._emit_state(DetectorState.UNKNOWN, f"call failed: {e}")
            self._client = None  # force re-init next tick
            return

        value = _dig(response, self._state_path)
        text = str(value).strip().lower() if value is not None else ""
        if text in self._down_values:
            self._emit_state(DetectorState.DOWN, text)
        elif text in self._up_values:
            self._emit_state(DetectorState.UP, text)
        else:
            self._emit_state(DetectorState.UNKNOWN, f"unrecognized: {text!r}")
