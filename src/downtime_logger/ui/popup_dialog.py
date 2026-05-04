"""
Non-modal popup raised when a downtime event opens. The shifter can either
fill it in immediately and click Save, or dismiss it and edit later from
the main window's history table.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.event import DowntimeEvent

CATEGORIES = [
    "", "Hardware", "Software", "Network", "Beam",
    "Cooling", "Power", "Operator", "Other",
]


class EventEditor(QDialog):
    """Editor for a single DowntimeEvent. Reusable for active and past events."""

    saved = Signal(object)  # DowntimeEvent

    def __init__(
        self,
        event: DowntimeEvent,
        title: str = "Downtime event",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._event = event

        layout = QVBoxLayout(self)

        header = QLabel(self._format_header(event))
        header.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(header)

        form = QFormLayout()
        layout.addLayout(form)

        self._category = QComboBox()
        self._category.addItems(CATEGORIES)
        self._category.setEditable(True)
        if event.category:
            self._category.setCurrentText(event.category)
        form.addRow("Category", self._category)

        self._subsystem = QLineEdit(event.subsystem or "")
        form.addRow("Subsystem", self._subsystem)

        self._cause = QLineEdit(event.cause or "")
        self._cause.setPlaceholderText("One-line summary of root cause")
        form.addRow("Cause", self._cause)

        self._notes = QPlainTextEdit(event.notes or "")
        self._notes.setPlaceholderText("Free-form notes (optional)")
        form.addRow("Notes", self._notes)

        self._started_edit = QDateTimeEdit()
        self._started_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._started_edit.setCalendarPopup(True)
        self._started_edit.setDateTime(
            QDateTime.fromSecsSinceEpoch(int(event.started_at.timestamp()))
        )
        form.addRow("Started at", self._started_edit)

        end_row = QWidget()
        end_layout = QHBoxLayout(end_row)
        end_layout.setContentsMargins(0, 0, 0, 0)
        self._ended_edit = QDateTimeEdit()
        self._ended_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._ended_edit.setCalendarPopup(True)
        if event.ended_at is not None:
            self._ended_edit.setDateTime(
                QDateTime.fromSecsSinceEpoch(int(event.ended_at.timestamp()))
            )
        else:
            self._ended_edit.setDateTime(QDateTime.currentDateTime())
        self._ongoing = QCheckBox("Ongoing")
        self._ongoing.setChecked(event.ended_at is None)
        self._ongoing.toggled.connect(
            lambda checked: self._ended_edit.setEnabled(not checked)
        )
        self._ended_edit.setEnabled(not self._ongoing.isChecked())
        end_layout.addWidget(self._ended_edit, 1)
        end_layout.addWidget(self._ongoing)
        form.addRow("Ended at", end_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Dismiss")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.resize(480, 360)

    @staticmethod
    def _format_header(event: DowntimeEvent) -> str:
        started = event.started_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        if event.ended_at is None:
            duration = "<b>ongoing</b>"
        else:
            duration = f"{event.duration_seconds:.0f}s"
        return (
            f"<b>Started:</b> {started}<br>"
            f"<b>Opened by:</b> {event.opened_by or '?'}<br>"
            f"<b>Score at open:</b> {event.score_at_open:.2f}<br>"
            f"<b>Duration:</b> {duration}"
        )

    def downtime_event(self) -> DowntimeEvent:
        return self._event

    def _on_save(self) -> None:
        self._event.category = self._category.currentText().strip() or None
        self._event.subsystem = self._subsystem.text().strip() or None
        self._event.cause = self._cause.text().strip() or None
        self._event.notes = self._notes.toPlainText().strip() or None
        self._event.started_at = datetime.fromtimestamp(
            self._started_edit.dateTime().toSecsSinceEpoch(), tz=timezone.utc
        )
        if self._ongoing.isChecked():
            self._event.ended_at = None
        else:
            self._event.ended_at = datetime.fromtimestamp(
                self._ended_edit.dateTime().toSecsSinceEpoch(), tz=timezone.utc
            )
        self.saved.emit(self._event)
        self.accept()


class NewEventPopup(EventEditor):
    """Popup variant — non-modal so it can be dismissed without blocking."""

    def __init__(self, event: DowntimeEvent, parent=None) -> None:
        super().__init__(event, title="DAQ DOWN — new downtime event", parent=parent)
        self.setModal(False)

    def update_running_event(self, event: Optional[DowntimeEvent]) -> None:
        """Refresh header (e.g. when DAQ recovers and ended_at is set)."""
        if event is None:
            return
        self._event = event
        # Header is the only thing that changes from outside the dialog.
        for child in self.findChildren(QLabel):
            child.setText(self._format_header(event))
            break
