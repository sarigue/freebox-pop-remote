"""Custom remote-control widgets."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QToolButton, QWidget


class DPad(QWidget):
    def __init__(self, send_key, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._send_key = send_key
        self.setObjectName("transparentPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(218, 218)

        self.up = self._button("▲", "DPAD_UP", 70, 12, 78, 58)
        self.left = self._button("◀", "DPAD_LEFT", 12, 70, 58, 78)
        self.ok = self._button("OK", "DPAD_CENTER", 72, 72, 74, 74, center=True)
        self.right = self._button("▶", "DPAD_RIGHT", 148, 70, 58, 78)
        self.down = self._button("▼", "DPAD_DOWN", 70, 148, 78, 58)

    def _button(
        self,
        text: str,
        key: str,
        x: int,
        y: int,
        w: int,
        h: int,
        center: bool = False,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setGeometry(x, y, w, h)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if center:
            button.setObjectName("dpadCenter")
        else:
            button.setObjectName("dpadPart")
        button.clicked.connect(lambda _checked=False, k=key: self._send_key(k))
        return button

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#55585d"), 1))
        painter.setBrush(QColor("#17191b"))
        painter.drawEllipse(4, 4, 210, 210)
        super().paintEvent(event)


class RemoteButton(QPushButton):
    def __init__(
        self,
        text: str,
        *,
        object_name: str = "remoteButton",
        fixed_height: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName(object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if fixed_height is not None:
            self.setFixedHeight(fixed_height)


class GoogleVoiceButton(QPushButton):
    """Push-to-talk button displaying the Google Assistant logo."""

    # Google Assistant logo geometry, normalized from its 512 x 512 mark.
    # Colors are the standard Google blue, green, red and yellow.
    _DOTS = (
        (156.268, 167.705, 156.268, "#4285F4"),
        (480.238, 182.950, 31.762, "#34A853"),
        (391.305, 260.449, 63.523, "#EA4335"),
        (391.305, 424.339, 76.228, "#FBBC05"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("voiceButton")
        self.setFixedSize(56, 42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Maintenir pour parler")

    def set_voice_active(self, active: bool) -> None:
        self.setProperty("voiceActive", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # Keep the complete square logo centered in the 56 x 42 button.
        side = 25.0
        left = (self.width() - side) / 2.0
        top = (self.height() - side) / 2.0
        scale = side / 512.0

        if not self.isEnabled():
            painter.setOpacity(0.35)

        for cx, cy, radius, color in self._DOTS:
            painter.setBrush(QColor(color))
            painter.drawEllipse(
                QPointF(left + cx * scale, top + cy * scale),
                radius * scale,
                radius * scale,
            )
