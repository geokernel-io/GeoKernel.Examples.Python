"""Profile plot with explicit gaps for pending or missing elevations."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class ProfileChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile = None
        self.setMinimumHeight(180)

    def set_profile(self, profile):
        self.profile = profile
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), Qt.GlobalColor.white)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(8, 20, "Elevation (m; vertical datum unverified)")
            value = self.profile or {}
            samples = value.get("samples", [])[:value.get("processed", 0)]
            heights = [s["height"] for s in samples if s["height"] is not None]
            distance = value.get("horizontal", 0)
            if not heights or distance <= 0:
                message = ("Click two or more terrain points." if value.get("pointCount", 0) < 2
                           else "No elevation samples available yet.")
                painter.drawText(60, 80, message)
                return
            plot = QRectF(65, 30, max(1, self.width() - 95), max(1, self.height() - 80))
            low, high = min(heights), max(heights)
            padding = max(.5, (high - low) * .1)
            low -= padding
            high += padding
            for i in range(5):
                x = plot.left() + plot.width() * i / 4
                y = plot.bottom() - plot.height() * i / 4
                painter.setPen(QColor("gainsboro"))
                painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
                painter.setPen(Qt.GlobalColor.black)
                painter.drawText(QPointF(3, y + 4), f"{low + (high - low) * i / 4:.1f}")
                painter.drawText(QPointF(x - 15, plot.bottom() + 18), f"{distance * i / 4:.0f}")
            painter.drawText(QPointF(plot.left(), self.height() - 8), "Horizontal distance (m)")
            painter.setPen(QPen(QColor("steelblue"), 2))
            previous = None
            for sample in samples:
                height = sample["height"]
                if height is None:
                    previous = None
                    continue
                point = QPointF(plot.left() + sample["distance"] / distance * plot.width(),
                                plot.bottom() - (height - low) / (high - low) * plot.height())
                if previous is not None:
                    painter.drawLine(previous, point)
                else:
                    painter.drawEllipse(point, 2, 2)
                previous = point
        finally:
            painter.end()
