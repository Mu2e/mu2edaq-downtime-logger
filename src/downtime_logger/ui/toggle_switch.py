"""
Compact iOS-style on/off toggle. Used to flip monitoring between the
disabled (idle) and enabled modes.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton


class ToggleSwitch(QAbstractButton):
    _W = 48
    _H = 24
    _PAD = 2

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self._W, self._H)

    def sizeHint(self) -> QSize:  # noqa: D401
        return QSize(self._W, self._H)

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        radius = rect.height() / 2
        track = QColor(46, 130, 70) if self.isChecked() else QColor(150, 150, 150)
        if not self.isEnabled():
            track.setAlpha(120)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(rect, radius, radius)

        knob_d = rect.height() - self._PAD * 2
        x = (rect.width() - knob_d - self._PAD) if self.isChecked() else self._PAD
        p.setBrush(QColor("white"))
        p.drawEllipse(x, self._PAD, knob_d, knob_d)
