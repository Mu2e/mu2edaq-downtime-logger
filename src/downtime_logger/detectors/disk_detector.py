"""
Watches one or more directories for fresh writes. If no file in any of the
watched paths has been modified within ``idle_seconds``, the detector flips
to DOWN. As soon as a fresh modification appears, it flips to UP.

Two layers cooperate:

* watchdog ``FileSystemEventHandler`` — fires on every modify/create/move,
  cheap and immediate.
* a periodic poll — handles the "nothing happened recently" case (watchdog
  alone won't tell us "no events for a minute") and acts as a backstop in
  case the inotify/FSEvents stream silently dies.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Iterable

from PySide6.QtCore import QTimer, Slot
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..core.event import DetectorState
from .base import Detector

log = logging.getLogger(__name__)


class _Bumper(FileSystemEventHandler):
    def __init__(self, on_event) -> None:
        self._on_event = on_event

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._on_event(event.src_path)


class DiskActivityDetector(Detector):
    def __init__(
        self,
        detector_id: str,
        paths: list[str],
        idle_seconds: float = 60.0,
        poll_s: float = 5.0,
        recursive: bool = True,
        **_: object,
    ) -> None:
        super().__init__(detector_id)
        self._paths = list(paths)
        self._idle_s = float(idle_seconds)
        self._poll_ms = int(poll_s * 1000)
        self._recursive = recursive

        self._last_event_ts = 0.0
        self._observer: Observer | None = None
        self._timer: QTimer | None = None

    @Slot()
    def start(self) -> None:
        # Seed with the latest mtime we can find, so a long-quiet directory
        # trips DOWN immediately rather than waiting idle_seconds first.
        self._last_event_ts = self._scan_latest_mtime(self._paths) or 0.0

        handler = _Bumper(self._on_fs_event)
        self._observer = Observer()
        for p in self._paths:
            try:
                self._observer.schedule(handler, p, recursive=self._recursive)
            except Exception as e:
                log.warning("disk detector %s could not watch %s: %s",
                            self.detector_id, p, e)
        self._observer.start()

        self._timer = QTimer()
        self._timer.setInterval(self._poll_ms)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        QTimer.singleShot(0, self._tick)
        log.info("disk detector %s watching %s", self.detector_id, self._paths)

    @Slot()
    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None

    def _on_fs_event(self, path: str) -> None:
        self._last_event_ts = time.time()

    @Slot()
    def _tick(self) -> None:
        idle_for = time.time() - self._last_event_ts
        if idle_for > self._idle_s:
            self._emit_state(
                DetectorState.DOWN,
                f"no writes in {idle_for:.1f}s (threshold {self._idle_s:.0f}s)",
            )
        else:
            self._emit_state(DetectorState.UP, f"last write {idle_for:.1f}s ago")

    @staticmethod
    def _scan_latest_mtime(paths: Iterable[str]) -> float | None:
        latest: float | None = None
        for root in paths:
            if not os.path.isdir(root):
                continue
            for dirpath, _dirs, files in os.walk(root):
                for f in files:
                    try:
                        m = os.path.getmtime(os.path.join(dirpath, f))
                    except OSError:
                        continue
                    if latest is None or m > latest:
                        latest = m
        return latest
