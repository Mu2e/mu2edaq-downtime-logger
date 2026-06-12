from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable, Optional

from ..core.event import DetectorReading, DowntimeEvent


class StorageBackend(ABC):
    """
    Persistence contract. Implementations must be safe to call from the Qt
    main thread; if a backend is slow it should do its own threading.
    """

    @abstractmethod
    def open_event(self, event: DowntimeEvent) -> int:
        """Persist a newly opened event. Returns the assigned id."""

    @abstractmethod
    def close_event(self, event: DowntimeEvent) -> None:
        ...

    @abstractmethod
    def update_event(self, event: DowntimeEvent) -> None:
        """Update editable fields (category, subsystem, cause, notes)."""

    @abstractmethod
    def get_event(self, event_id: int) -> Optional[DowntimeEvent]:
        ...

    @abstractmethod
    def delete_event(self, event_id: int) -> bool:
        """Permanently remove an event. Returns True if a row was deleted."""

    @abstractmethod
    def list_events(self, limit: int = 200) -> list[DowntimeEvent]:
        """Most-recent-first."""

    @abstractmethod
    def list_events_in_range(
        self,
        start: datetime,
        end: datetime,
        limit: int = 5000,
    ) -> list[DowntimeEvent]:
        """Events that overlap [start, end], oldest-first."""

    @abstractmethod
    def log_readings(self, score: float, readings: Iterable[DetectorReading]) -> None:
        ...

    def close(self) -> None:
        """Tear down connections, if any."""
