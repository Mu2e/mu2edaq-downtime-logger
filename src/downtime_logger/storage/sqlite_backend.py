from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
)

from ..core.event import DetectorReading, DowntimeEvent
from .base import StorageBackend


class _Base(DeclarativeBase):
    pass


class _DowntimeRow(_Base):
    __tablename__ = "downtime_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    opened_by: Mapped[str] = mapped_column(String(255), default="")
    score_at_open: Mapped[float] = mapped_column(Float, default=0.0)
    category: Mapped[Optional[str]] = mapped_column(String(64))
    subsystem: Mapped[Optional[str]] = mapped_column(String(64))
    cause: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(String(4096))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class _ReadingRow(_Base):
    __tablename__ = "detector_state_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detector_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(String(1024))


def _to_event(row: _DowntimeRow) -> DowntimeEvent:
    return DowntimeEvent(
        id=row.id,
        started_at=row.started_at,
        ended_at=row.ended_at,
        opened_by=row.opened_by,
        score_at_open=row.score_at_open,
        category=row.category,
        subsystem=row.subsystem,
        cause=row.cause,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SQLiteBackend(StorageBackend):
    """
    Default backend. Swap to Postgres/MySQL by writing a tiny subclass that
    builds a different SQLAlchemy URL — the schema is portable.
    """

    def __init__(self, path: str = "events.db", echo: bool = False) -> None:
        db_path = Path(path).expanduser().resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so the embedded web server can read the DB
        # from its own thread; SQLAlchemy's pool serializes access.
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            echo=echo,
            future=True,
            connect_args={"check_same_thread": False},
        )
        _Base.metadata.create_all(self._engine)

    def open_event(self, event: DowntimeEvent) -> int:
        with Session(self._engine) as s:
            row = _DowntimeRow(
                started_at=event.started_at,
                ended_at=event.ended_at,
                opened_by=event.opened_by,
                score_at_open=event.score_at_open,
                category=event.category,
                subsystem=event.subsystem,
                cause=event.cause,
                notes=event.notes,
                created_at=event.created_at,
                updated_at=event.updated_at,
            )
            s.add(row)
            s.commit()
            event.id = row.id
            return row.id

    def close_event(self, event: DowntimeEvent) -> None:
        if event.id is None:
            return
        with Session(self._engine) as s:
            row = s.get(_DowntimeRow, event.id)
            if row is None:
                return
            row.ended_at = event.ended_at
            row.updated_at = datetime.now(timezone.utc)
            s.commit()

    def update_event(self, event: DowntimeEvent) -> None:
        if event.id is None:
            return
        with Session(self._engine) as s:
            row = s.get(_DowntimeRow, event.id)
            if row is None:
                return
            row.category = event.category
            row.subsystem = event.subsystem
            row.cause = event.cause
            row.notes = event.notes
            row.ended_at = event.ended_at
            row.updated_at = datetime.now(timezone.utc)
            event.updated_at = row.updated_at
            s.commit()

    def get_event(self, event_id: int) -> Optional[DowntimeEvent]:
        with Session(self._engine) as s:
            row = s.get(_DowntimeRow, event_id)
            return _to_event(row) if row else None

    def list_events(self, limit: int = 200) -> list[DowntimeEvent]:
        with Session(self._engine) as s:
            stmt = (
                select(_DowntimeRow)
                .order_by(_DowntimeRow.started_at.desc())
                .limit(limit)
            )
            return [_to_event(r) for r in s.scalars(stmt).all()]

    def log_readings(self, score: float, readings: Iterable[DetectorReading]) -> None:
        now = datetime.now(timezone.utc)
        with Session(self._engine) as s:
            for r in readings:
                s.add(
                    _ReadingRow(
                        ts=now,
                        detector_id=r.detector_id,
                        state=r.state.value,
                        weight=r.weight,
                        score=score,
                        detail=r.detail,
                    )
                )
            s.commit()

    def close(self) -> None:
        self._engine.dispose()
