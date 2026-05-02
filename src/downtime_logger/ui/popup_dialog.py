"""
Non-modal popup raised when a downtime event opens. The shifter can either
fill it in immediately and click Save, or dismiss it and edit later from
the main window's history table.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
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
