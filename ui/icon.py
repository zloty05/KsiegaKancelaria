"""Generuje ikonę aplikacji (symbol § — paragraf) rysowaną w kodzie QPainter."""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap


def app_icon(size: int = 64) -> QIcon:
    """Zwraca QIcon z symbolem § na ciemnozielonym tle z zaokrąglonymi rogami."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Tło — zaokrąglony kwadrat.
    painter.setBrush(QBrush(QColor("#006266")))
    painter.setPen(Qt.PenStyle.NoPen)
    radius = size * 0.18
    painter.drawRoundedRect(QRect(0, 0, size, size), radius, radius)

    # Symbol paragrafu.
    painter.setPen(QColor("#ffffff"))
    font = QFont("Georgia", int(size * 0.6))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(
        QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "§"
    )
    painter.end()

    return QIcon(pixmap)
