"""
Main window: live status panel + history table. Past events can be edited
by double-clicking; the active event (if any) shows up at the top in bold.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.event import DowntimeEvent
from .popup_dialog import EventEditor
from .status_widget import StatusWidget


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_dur(ev: DowntimeEvent) -> str:
    d = ev.duration_seconds
    if d is None:
        return "ongoing"
    if d < 60:
        return f"{d:.0f}s"
    if d < 3600:
        return f"{d/60:.1f}m"
    return f"{d/3600:.2f}h"


class MainWindow(QMainWindow):
    """
    Pure-view widget. Persisting edits is the app layer's responsibility —
    we surface ``event_save_requested`` and let the controller call
    ``storage.update_event``.
    """

    event_save_requested = Signal(object)  # DowntimeEvent
    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mu2e DAQ Downtime Logger")
        self.resize(1000, 720)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.setCentralWidget(splitter)

        # --- top: live status -------------------------------------------------
        self.status = StatusWidget()
        splitter.addWidget(self.status)

        # --- bottom: history --------------------------------------------------
        bottom = QWidget()
        bl = QVBoxLayout(bottom)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Downtime history</b>"))
        header.addStretch(1)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested)
        header.addWidget(self._refresh_btn)
        bl.addLayout(header)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["ID", "Started", "Ended", "Duration", "Category", "Subsystem", "Cause"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.cellDoubleClicked.connect(self._on_row_activated)
        bl.addWidget(self._table)

        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self._events: list[DowntimeEvent] = []

    # --- slots -----------------------------------------------------------

    @Slot(list)
    def set_events(self, events: list[DowntimeEvent]) -> None:
        self._events = list(events)
        self._table.setRowCount(len(self._events))
        bold = QFont()
        bold.setBold(True)
        for row, ev in enumerate(self._events):
            cells = [
                QTableWidgetItem(str(ev.id) if ev.id else ""),
                QTableWidgetItem(_fmt_dt(ev.started_at)),
                QTableWidgetItem(_fmt_dt(ev.ended_at)),
                QTableWidgetItem(_fmt_dur(ev)),
                QTableWidgetItem(ev.category or ""),
                QTableWidgetItem(ev.subsystem or ""),
                QTableWidgetItem(ev.cause or ""),
            ]
            for c in cells:
                c.setFlags(c.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if ev.is_open:
                    c.setFont(bold)
            for col, c in enumerate(cells):
                self._table.setItem(row, col, c)

    @Slot(int, int)
    def _on_row_activated(self, row: int, _col: int) -> None:
        if row < 0 or row >= len(self._events):
            return
        ev = self._events[row]
        editor = EventEditor(ev, title=f"Edit event #{ev.id or ''}", parent=self)
        editor.saved.connect(self.event_save_requested)
        editor.exec()
