"""
Main window: live status panel + history table. Past events can be edited
by double-clicking; the active event (if any) shows up at the top in bold.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QSize, Qt, Signal, Slot
from PySide6.QtGui import QAction, QFont, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_LOGO_PATH = Path(__file__).resolve().parent.parent / "resources" / "mu2edaq-logo-transparent.png"

from ..core.event import DowntimeEvent
from .popup_dialog import EventEditor
from .status_widget import StatusWidget
from .toggle_switch import ToggleSwitch


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
    event_create_requested = Signal(object)  # DowntimeEvent (id is None)
    refresh_requested = Signal()
    manual_end_requested = Signal(int)  # event id
    events_delete_requested = Signal(list)  # list[int] event ids
    enabled_toggled = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mu2e DAQ Downtime Logger")
        self.resize(1000, 720)

        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        title_bar = QHBoxLayout()
        self._mode_label = QLabel()
        self._mode_label.setStyleSheet("font-weight: bold;")
        title_bar.addWidget(self._mode_label)
        self._mode_switch = ToggleSwitch()
        self._mode_switch.toggled.connect(self.enabled_toggled)
        self._mode_switch.toggled.connect(self._on_enabled_changed_local)
        title_bar.addWidget(self._mode_switch)
        title_bar.addStretch(1)
        if _LOGO_PATH.exists():
            pixmap = QPixmap(str(_LOGO_PATH))
            if not pixmap.isNull():
                logo = QLabel()
                logo.setPixmap(
                    pixmap.scaled(
                        QSize(64, 64),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                logo.setToolTip("Mu2e DAQ")
                title_bar.addWidget(
                    logo, 0,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                )
        root.addLayout(title_bar)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)

        # --- top: live status -------------------------------------------------
        self.status = StatusWidget()
        self.status.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status.customContextMenuRequested.connect(self._on_status_context_menu)
        splitter.addWidget(self.status)

        # --- bottom: history --------------------------------------------------
        bottom = QWidget()
        bl = QVBoxLayout(bottom)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Downtime history</b>"))
        header.addStretch(1)
        self._new_btn = QPushButton("New event…")
        self._new_btn.clicked.connect(self._open_create_dialog)
        header.addWidget(self._new_btn)
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
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.cellDoubleClicked.connect(self._on_row_activated)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        bl.addWidget(self._table)

        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self._events: list[DowntimeEvent] = []
        self._on_enabled_changed_local(False)

    @Slot(bool)
    def set_enabled_mode(self, enabled: bool) -> None:
        """External (state-machine) signal: reflect mode on the switch."""
        if self._mode_switch.isChecked() != enabled:
            blocked = self._mode_switch.blockSignals(True)
            self._mode_switch.setChecked(enabled)
            self._mode_switch.blockSignals(blocked)
        self._on_enabled_changed_local(enabled)

    @Slot(bool)
    def _on_enabled_changed_local(self, enabled: bool) -> None:
        if enabled:
            self._mode_label.setText("Monitoring: ENABLED")
            self._mode_label.setStyleSheet("font-weight: bold; color: #226622;")
        else:
            self._mode_label.setText("Monitoring: DISABLED (idle)")
            self._mode_label.setStyleSheet("font-weight: bold; color: #aa6611;")

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

    @Slot(QPoint)
    def _on_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self._table)

        # Rows currently highlighted in the selection model.
        selected_rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        clicked_row = self._table.indexAt(pos).row()

        # If the right-click landed outside the current selection, treat it as
        # a single-row operation on just the clicked row.
        if clicked_row not in selected_rows:
            selected_rows = [clicked_row] if clicked_row >= 0 else []

        evs: list[DowntimeEvent] = [
            self._events[r] for r in selected_rows if 0 <= r < len(self._events)
        ]

        if len(evs) == 1:
            ev = evs[0]
            edit_action = QAction("Edit…", menu)
            edit_action.triggered.connect(
                lambda: self._on_row_activated(selected_rows[0], 0)
            )
            menu.addAction(edit_action)
            if ev.is_open and ev.id is not None:
                end_action = QAction("End downtime now", menu)
                end_action.triggered.connect(lambda: self._confirm_end(ev.id))
                menu.addAction(end_action)
            if ev.id is not None:
                menu.addSeparator()
                delete_action = QAction("Delete event…", menu)
                delete_action.triggered.connect(lambda: self._confirm_delete(evs))
                menu.addAction(delete_action)
            menu.addSeparator()
        elif len(evs) > 1:
            # For multi-select, offer end only when exactly one open event is
            # selected (only one event can be active in the state machine at a
            # time, so offering bulk-end on several open rows would be confusing).
            open_evs = [e for e in evs if e.is_open and e.id is not None]
            if len(open_evs) == 1:
                eid = open_evs[0].id
                end_action = QAction(f"End downtime now (event #{eid})", menu)
                end_action.triggered.connect(lambda: self._confirm_end(eid))
                menu.addAction(end_action)
            deletable = [e for e in evs if e.id is not None]
            if deletable:
                menu.addSeparator()
                delete_action = QAction(f"Delete {len(deletable)} events…", menu)
                delete_action.triggered.connect(lambda: self._confirm_delete(deletable))
                menu.addAction(delete_action)
            menu.addSeparator()

        new_action = QAction("New event…", menu)
        new_action.triggered.connect(self._open_create_dialog)
        menu.addAction(new_action)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    @Slot(QPoint)
    def _on_status_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self.status)
        new_action = QAction("New event…", menu)
        new_action.triggered.connect(self._open_create_dialog)
        menu.addAction(new_action)
        menu.exec(self.status.mapToGlobal(pos))

    def _open_create_dialog(self) -> None:
        ev = DowntimeEvent(
            started_at=datetime.now(timezone.utc),
            opened_by="manual",
            score_at_open=0.0,
        )
        editor = EventEditor(ev, title="New downtime event", parent=self)
        editor.saved.connect(self.event_create_requested)
        editor.exec()

    def _confirm_end(self, event_id: int) -> None:
        ans = QMessageBox.question(
            self,
            "End downtime",
            f"End downtime event #{event_id} now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.manual_end_requested.emit(event_id)

    def _confirm_delete(self, evs: list[DowntimeEvent]) -> None:
        ids = [e.id for e in evs if e.id is not None]
        if not ids:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        if len(ids) == 1:
            ev = evs[0]
            box.setWindowTitle("Permanently delete event?")
            box.setText(f"<b>Permanently delete downtime event #{ev.id}?</b>")
            box.setInformativeText(
                f"Started: {_fmt_dt(ev.started_at)}<br>"
                f"Cause: {ev.cause or '(none)'}<br><br>"
                "<b>This cannot be undone.</b> The event row will be removed "
                "from the database and the shift history. Detector reading "
                "logs are not affected.<br><br>"
                "Only delete events that were created in error (e.g. test runs "
                "or false triggers). For real downtime, edit the record instead."
            )
        else:
            id_list = ", ".join(f"#{i}" for i in ids)
            box.setWindowTitle(f"Permanently delete {len(ids)} events?")
            box.setText(f"<b>Permanently delete {len(ids)} downtime events?</b>")
            box.setInformativeText(
                f"Events: {id_list}<br><br>"
                "<b>This cannot be undone.</b> All selected event rows will be "
                "removed from the database and the shift history. Detector "
                "reading logs are not affected."
            )
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        yes = box.button(QMessageBox.StandardButton.Yes)
        yes.setText("Delete permanently")
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self.events_delete_requested.emit(ids)
