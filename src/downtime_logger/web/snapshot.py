"""
Thread-safe view of the current state-machine state. The Qt thread writes;
the HTTP server thread reads. Storage queries (event lists) are issued
directly against the storage backend in the request thread — SQLAlchemy
gives each thread its own connection.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..core.event import DetectorReading, DowntimeEvent


@dataclass
class StatusSnapshot:
    score: float = 0.0
    is_down: bool = False
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    readings: dict[str, DetectorReading] = field(default_factory=dict)
    current_event: Optional[DowntimeEvent] = None


class SnapshotStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snap = StatusSnapshot()

    def update_score(self, score: float, is_down: bool) -> None:
        with self._lock:
            self._snap.score = score
            self._snap.is_down = is_down
            self._snap.updated_at = datetime.now(timezone.utc)

    def update_readings(self, readings: dict[str, DetectorReading]) -> None:
        with self._lock:
            self._snap.readings = dict(readings)
            self._snap.updated_at = datetime.now(timezone.utc)

    def set_current_event(self, event: Optional[DowntimeEvent]) -> None:
        with self._lock:
            self._snap.current_event = event
            self._snap.updated_at = datetime.now(timezone.utc)

    def get(self) -> StatusSnapshot:
        with self._lock:
            # Shallow copy so the caller doesn't see further mutations.
            return StatusSnapshot(
                score=self._snap.score,
                is_down=self._snap.is_down,
                updated_at=self._snap.updated_at,
                readings=dict(self._snap.readings),
                current_event=self._snap.current_event,
            )
