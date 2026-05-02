from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class DetectorState(str, Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class DetectorReading:
    detector_id: str
    state: DetectorState
    weight: float
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    detail: Optional[str] = None


@dataclass
class DowntimeEvent:
    id: Optional[int] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    opened_by: str = ""
    score_at_open: float = 0.0
    category: Optional[str] = None
    subsystem: Optional[str] = None
    cause: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()
