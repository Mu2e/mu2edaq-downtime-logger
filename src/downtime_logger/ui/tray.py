"""
System tray icon. Color reflects current state: green=UP, red=DOWN,
yellow=UNKNOWN. Click "Show window" to bring the main UI forward.
"""
from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def _solid_icon(color: QColor) -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(color)
    p.setPen(QColor(40, 40, 40))
    p.drawEllipse(2, 2, 28, 28)
    p.end()
    return QIcon(pm)


_GREEN = QColor(80, 180, 80)
_RED = QColor(200, 60, 60)
_YELLOW = QColor(220, 200, 60)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, on_show, on_quit, on_toggle_enabled, parent=None) -> None:
        super().__init__(parent)
        self.setIcon(_solid_icon(_YELLOW))
        self.setToolTip("DAQ Downtime Logger — initializing")

        menu = QMenu()
        show_act = QAction("Show window", menu)
        show_act.triggered.connect(on_show)
        menu.addAction(show_act)

        self._enable_act = QAction("Enable monitoring", menu)
        self._enable_act.setCheckable(True)
        self._enable_act.toggled.connect(on_toggle_enabled)
        menu.addAction(self._enable_act)
        menu.addSeparator()

        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(on_quit)
        menu.addAction(quit_act)
        self.setContextMenu(menu)

    @Slot(bool)
    def set_enabled_mode(self, enabled: bool) -> None:
        if self._enable_act.isChecked() != enabled:
            blocked = self._enable_act.blockSignals(True)
            self._enable_act.setChecked(enabled)
            self._enable_act.blockSignals(blocked)

    @Slot(float, bool)
    def on_score(self, score: float, is_down: bool) -> None:
        suffix = "" if self._enable_act.isChecked() else "  [monitoring disabled]"
        if is_down:
            self.setIcon(_solid_icon(_RED))
            self.setToolTip(f"DAQ DOWN — score {score:.2f}{suffix}")
        else:
            self.setIcon(_solid_icon(_GREEN))
            self.setToolTip(f"DAQ up — score {score:.2f}{suffix}")
