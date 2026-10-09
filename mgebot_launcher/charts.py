from __future__ import annotations
import datetime
import math

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget, QToolTip


class SessionChart(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values: list[float] = []
        self.labels: list[str] = []
        self.points: list[QPointF] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(170)
        self.setAccessibleName("Damage per minute across recent sessions")

    def set_sessions(self, sessions: list[dict]) -> None:
        rows = [s for s in reversed(sessions[:24]) if s["active_seconds"] > 0]
        self.values = [max(0, s["damage_out"]) * 60 / s["active_seconds"] for s in rows]
        self.labels = [datetime.datetime.fromtimestamp(s["started"]).strftime("%d.%m %H:%M") for s in rows]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(44, 10, max(1, self.width() - 62), max(1, self.height() - 46))
        painter.fillRect(self.rect(), QColor("#14111b"))
        self.points = []
        if not self.values:
            return
        highest = max(100.0, math.ceil(max(self.values) * 1.1 / 100) * 100)
        for fraction in (0.0, 0.5, 1.0):
            y = area.bottom() - area.height() * fraction
            painter.setPen(QPen(QColor("#30243f"), 1))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(QColor("#b8aec5"))
            painter.drawText(QRectF(0, y - 8, 36, 18), Qt.AlignmentFlag.AlignRight, str(round(highest * fraction)))
        path = QPainterPath()
        points = []
        for i, value in enumerate(self.values):
            x = area.left() + area.width() * (i / max(1, len(self.values) - 1) if len(self.values) > 1 else 0.5)
            point = QPointF(x, area.bottom() - area.height() * value / highest)
            points.append(point)
            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        painter.setPen(QPen(QColor("#bb99e5"), 2.4))
        painter.drawPath(path)
        painter.setBrush(QColor("#e4cef9"))
        painter.setPen(Qt.PenStyle.NoPen)
        for point in points:
            painter.drawEllipse(point, 3, 3)
        self.points = points
        painter.setPen(QColor("#b8aec5"))
        painter.drawText(QRectF(area.left(), area.bottom() + 9, 120, 20), Qt.AlignmentFlag.AlignLeft, self.labels[0])
        painter.drawText(QRectF(area.right() - 120, area.bottom() + 9, 120, 20), Qt.AlignmentFlag.AlignRight, self.labels[-1])

    def mouseMoveEvent(self, event):
        for n, point in enumerate(self.points):
            if abs(event.position().x() - point.x()) < 12 and abs(event.position().y() - point.y()) < 18:
                QToolTip.showText(event.globalPosition().toPoint(), f"{self.labels[n]}\n{round(self.values[n], 1)} DPM", self)
                return
        QToolTip.hideText()
