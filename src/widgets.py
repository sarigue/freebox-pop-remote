"""Custom remote-control widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
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
    """Push-to-talk button with a Google-style microphone glyph."""

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

        color = QColor("#ffffff") if self.property("voiceActive") else QColor("#e8eaed")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)

        cx = self.width() / 2.0
        top = 9.0
        mic_w = 9.0
        mic_h = 16.0
        mic = QPainterPath()
        mic.addRoundedRect(cx - mic_w / 2, top, mic_w, mic_h, 4.5, 4.5)
        painter.drawPath(mic)

        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # U-shaped receiver around the capsule.
        painter.drawArc(int(cx - 9), 14, 18, 17, 180 * 16, 180 * 16)
        painter.drawLine(int(cx), 29, int(cx), 34)
        painter.drawLine(int(cx - 6), 34, int(cx + 6), 34)
