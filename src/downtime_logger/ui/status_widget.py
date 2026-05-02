"""
Live per-detector state + overall score, shown in the main window.
"""
from __future__ import annotations

from typing import Mapping

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.event import DetectorReading, DetectorState

_STATE_COLORS = {
    DetectorState.UP: QColor(160, 220, 160),
    DetectorState.DOWN: QColor(230, 150, 150),
    DetectorState.UNKNOWN: QColor(220, 220, 160),
}


class StatusWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self._score_label = QLabel("Score: —")
        self._score_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(self._score_label)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Detector", "State", "Weight", "Detail"])
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

    @Slot(float, bool)
    def on_score(self, score: float, is_down: bool) -> None:
        flag = "DOWN" if is_down else "UP"
        self._score_label.setText(f"Score: {score:.2f}   ({flag})")
        self._score_label.setStyleSheet(
            "font-size: 16pt; font-weight: bold; color: "
            + ("#aa2222" if is_down else "#226622")
            + ";"
        )

    @Slot(dict)
    def on_readings(self, readings: Mapping[str, DetectorReading]) -> None:
        ids = sorted(readings.keys())
        self._table.setRowCount(len(ids))
        for row, did in enumerate(ids):
            r = readings[did]
            cells = [
                QTableWidgetItem(did),
                QTableWidgetItem(r.state.value),
                QTableWidgetItem(f"{r.weight:.2f}"),
                QTableWidgetItem(r.detail or ""),
            ]
            color = _STATE_COLORS.get(r.state)
            for c in cells:
                c.setFlags(c.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if color is not None:
                    c.setBackground(color)
            for col, cell in enumerate(cells):
                self._table.setItem(row, col, cell)
