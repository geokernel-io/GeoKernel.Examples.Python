"""North-up display of native row-major visibility cells."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class ViewshedMap(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = {}
        self.setMinimumSize(320, 280)

    def set_result(self, result):
        self.result = result
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), Qt.GlobalColor.white)
            painter.setPen(Qt.GlobalColor.black)
            width = self.result.get("width", 0)
            if not width:
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                                 "Select an observer on terrain.\nThen calculate visibility.")
                return
            side = max(1, min(self.width() - 50, self.height() - 55))
            left, top, cell = (self.width() - side) / 2, 25, side / width
            colors = {1: "#dce3eb", 2: "#239b56", 3: "#d35445", 4: "#858585"}
            for i, state in enumerate(self.result["cells"]):
                if state in colors:
                    painter.fillRect(QRectF(left + (i % width) * cell,
                                            top + (i // width) * cell, cell, cell), QColor(colors[state]))
            painter.drawText(QPointF(self.width() / 2 - 12, 18), "N ↑")
            painter.drawText(QPointF(2, top + side / 2), "W")
            painter.drawText(QPointF(self.width() - 18, top + side / 2), "E")
            painter.drawText(QPointF(left, top + side + 20), f'S ↓    Radius: {self.result["radius"]:.0f} m')
            x, y = left + side / 2, top + side / 2
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
            painter.drawLine(QPointF(x - 6, y), QPointF(x + 6, y))
            painter.drawLine(QPointF(x, y - 6), QPointF(x, y + 6))
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.drawEllipse(QPointF(x, y), 4, 4)
        finally:
            painter.end()
