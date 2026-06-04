"""Powiadomienie toast — niemodalne okienko w prawym dolnym rogu ekranu.

Animacja: fade in (200 ms), widoczne 5 s, fade out (500 ms). Klikalny przycisk
„Otwórz" uruchamia folder. Kolejne toasty przesuwają poprzednie w górę.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

MARGIN = 20  # margines od krawędzi ekranu
SPACING = 10  # odstęp między toastami
TOAST_WIDTH = 380
VISIBLE_MS = 5000
FADE_IN_MS = 200
FADE_OUT_MS = 500

# Lista aktualnie widocznych toastów (do układania w stos).
_active_toasts: list["ToastNotification"] = []


class ToastNotification(QWidget):
    """Pojedyncze powiadomienie toast."""

    def __init__(
        self,
        title: str,
        message: str,
        folder_path: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._folder_path = folder_path

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(TOAST_WIDTH)

        self._build_ui(title, message, folder_path)
        self.adjustSize()

    def _build_ui(self, title: str, message: str, folder_path: str | None) -> None:
        frame = QFrame(self)
        frame.setObjectName("toastFrame")
        frame.setStyleSheet(
            """
            #toastFrame {
                background-color: #2d3436;
                border: 1px solid #00b894;
                border-radius: 10px;
            }
            QLabel { color: #ffffff; }
            QLabel#title { font-size: 14px; font-weight: bold; }
            QLabel#msg { color: #dfe6e9; font-size: 12px; }
            QPushButton {
                background-color: #00b894; color: white; border: none;
                border-radius: 6px; padding: 6px 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #00cec9; }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        inner = QVBoxLayout(frame)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(6)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("title")
        inner.addWidget(lbl_title)

        lbl_msg = QLabel(message)
        lbl_msg.setObjectName("msg")
        lbl_msg.setWordWrap(True)
        inner.addWidget(lbl_msg)

        if folder_path:
            row = QHBoxLayout()
            row.addStretch()
            btn = QPushButton("Otwórz")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self._open_folder)
            row.addWidget(btn)
            inner.addLayout(row)

    def _open_folder(self) -> None:
        if self._folder_path and os.path.exists(self._folder_path):
            os.startfile(self._folder_path)  # type: ignore[attr-defined]
        self._start_fade_out()

    # --- animacje / pozycjonowanie ---------------------------------------

    def show_toast(self) -> None:
        """Pokazuje toast z animacją fade-in i ustawia timer auto-zamknięcia."""
        _active_toasts.append(self)
        self.setWindowOpacity(0.0)
        self.show()
        self._reposition_all()

        self._fade_in = QPropertyAnimation(self, b"windowOpacity")
        self._fade_in.setDuration(FADE_IN_MS)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade_in.start()

        QTimer.singleShot(VISIBLE_MS, self._start_fade_out)

    def _start_fade_out(self) -> None:
        if self not in _active_toasts:
            return
        self._fade_out = QPropertyAnimation(self, b"windowOpacity")
        self._fade_out.setDuration(FADE_OUT_MS)
        self._fade_out.setStartValue(self.windowOpacity())
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade_out.finished.connect(self._on_closed)
        self._fade_out.start()

    def _on_closed(self) -> None:
        if self in _active_toasts:
            _active_toasts.remove(self)
        self.close()
        self.deleteLater()
        # Po usunięciu — przesuń pozostałe.
        for t in _active_toasts:
            t._reposition_all()

    def _reposition_all(self) -> None:
        """Układa wszystkie aktywne toasty w stos od prawego dolnego rogu w górę."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.right() - TOAST_WIDTH - MARGIN
        y = geo.bottom() - MARGIN
        for t in reversed(_active_toasts):
            y -= t.height()
            t.move(QPoint(x, y))
            y -= SPACING


def show_toast(
    title: str, message: str, folder_path: str | None = None
) -> ToastNotification:
    """Wygodna funkcja: tworzy i pokazuje toast."""
    toast = ToastNotification(title, message, folder_path)
    toast.show_toast()
    return toast
