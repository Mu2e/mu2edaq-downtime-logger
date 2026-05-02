"""
Tails one or more log files for regex matches. ``down_patterns`` flip the
state to DOWN; ``up_patterns`` flip it to UP. Handles log rotation by
re-opening when the inode changes or the file shrinks.

Pure-Python tail loop driven by a ``QTimer`` — no third-party tail dep
needed and no extra thread machinery beyond the QThread the detector is
already running on.
"""
from __future__ import annotations

import logging
import os
import re
from typing import IO

from PySide6.QtCore import QTimer, Slot

from ..core.event import DetectorState
from .base import Detector

log = logging.getLogger(__name__)


class _Tail:
    def __init__(self, path: str) -> None:
        self.path = path
        self._fh: IO[str] | None = None
        self._inode: int | None = None

    def _open(self, seek_to_end: bool) -> None:
        try:
            self._fh = open(self.path, "r", errors="replace")
            if seek_to_end:
                self._fh.seek(0, os.SEEK_END)
            self._inode = os.fstat(self._fh.fileno()).st_ino
        except OSError as e:
            log.debug("tail open failed for %s: %s", self.path, e)
            self._fh = None
            self._inode = None

    def _rotation_state(self) -> str:
        """Returns 'ok', 'rotated', or 'closed' (file vanished)."""
        if self._fh is None:
            return "closed"
        try:
            disk_inode = os.stat(self.path).st_ino
            cur_pos = self._fh.tell()
            file_size = os.fstat(self._fh.fileno()).st_size
        except OSError:
            return "rotated"
        if disk_inode != self._inode or cur_pos > file_size:
            return "rotated"
        return "ok"

    def read_new(self) -> list[str]:
        first_open = self._fh is None
        state = self._rotation_state()
        if first_open or state != "ok":
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None
            # First open: skip historical content (don't replay startup logs).
            # On rotation: read from the top of the new file.
            self._open(seek_to_end=first_open)
            if self._fh is None:
                return []
        try:
            data = self._fh.read()
        except OSError:
            return []
        if not data:
            return []
        return data.splitlines()

    def close(self) -> None:
        if self._fh:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None


class LogfileDetector(Detector):
    def __init__(
        self,
        detector_id: str,
        path: str | None = None,
        paths: list[str] | None = None,
        down_patterns: list[str] | None = None,
        up_patterns: list[str] | None = None,
        poll_s: float = 1.0,
        **_: object,
    ) -> None:
        super().__init__(detector_id)
        all_paths: list[str] = []
        if path:
            all_paths.append(path)
        if paths:
            all_paths.extend(paths)
        if not all_paths:
            raise ValueError(f"{detector_id}: must specify path or paths")

        self._tails = [_Tail(p) for p in all_paths]
        self._down_re = [re.compile(p) for p in (down_patterns or [])]
        self._up_re = [re.compile(p) for p in (up_patterns or [])]
        self._poll_ms = int(poll_s * 1000)
        self._timer: QTimer | None = None

    @Slot()
    def start(self) -> None:
        self._timer = QTimer()
        self._timer.setInterval(self._poll_ms)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        log.info("logfile detector %s watching %s",
                 self.detector_id, [t.path for t in self._tails])

    @Slot()
    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
        for t in self._tails:
            t.close()

    @Slot()
    def _tick(self) -> None:
        for t in self._tails:
            for line in t.read_new():
                self._scan_line(t.path, line)

    def _scan_line(self, path: str, line: str) -> None:
        for r in self._down_re:
            if r.search(line):
                self._emit_state(DetectorState.DOWN, f"{path}: {line[:128]}")
                return
        for r in self._up_re:
            if r.search(line):
                self._emit_state(DetectorState.UP, f"{path}: {line[:128]}")
                return
