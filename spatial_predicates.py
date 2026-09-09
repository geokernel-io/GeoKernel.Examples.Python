import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QTextEdit, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

def rectangle(x1, y1, x2, y2):
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]

CASES = [
    (
        "Contains(left, right)",
        rectangle(-8.2, 3.5, -4.8, 6.3),
        rectangle(-7.4, 4.1, -5.7, 5.5),
        "T*****FF*",
    ),
    (
        "Within(left, right)",
        rectangle(-2.8, 4.1, -1.1, 5.5),
        rectangle(-3.6, 3.5, -0.2, 6.3),
        "T*F**F***",
    ),
    (
        "Touches(left, right)",
        rectangle(1.2, 3.6, 3.4, 6.1),
        rectangle(3.4, 3.6, 5.6, 6.1),
        "FT*******",
    ),
    (
        "Overlaps(left, right)",
        rectangle(-8.2, -2.0, -5.0, 0.8),
        rectangle(-6.3, -0.8, -3.1, 2.0),
        "T*T***T**",
    ),
    (
        "Cross(left, right)",
        [(-2.9, -1.7), (0.4, 1.6)],
        [(-2.9, 1.6), (0.4, -1.7)],
        "F***T****",
    ),
    (
        "Disjoint(left, right)",
        rectangle(1.4, -2.0, 3.0, -0.2),
        rectangle(4.2, 0.2, 5.8, 2.0),
        "FF*FF****",
    ),
]
FULL_EXTENT = Extent(-9.2, -3.2, 6.8, 7.2)

class SpatialPredicatesWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.widget = self.viewer.qt_widget()
        self.setWindowTitle("SpatialPredicates")
        self.setWindowIcon(application_icon())
        self.resize(980, 680)
        self.details = QTextEdit(self)
        self.details.setReadOnly(True)
        root = QWidget(self)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.widget, 1)
        row.addWidget(self.details)
        self.setCentralWidget(root)

    def initialize_viewer(self):
        self.viewer.resize(self.widget.width(), self.widget.height())
        self.viewer.show()
        lines = [
            "Spatial predicate examples",
            "Each pair is arranged so the named predicate should evaluate to true.",
            "",
        ]
        for index, (title, left, right, pattern) in enumerate(CASES):
            method = (
                self.viewer.relate_polylines_pattern
                if index == 4
                else self.viewer.relate_polygon_rings_pattern
            )
            result = method(left, right, pattern)
            lines.extend((title, f"  result: {str(result).lower()}", ""))
            style_a = {
                "fillColor": "#BFD7EA",
                "fillOpacity": 120,
                "lineColor": "#2F80C2",
                "lineWidth": 2,
            }
            style_b = {
                "fillColor": "#F6D6AD",
                "fillOpacity": 120,
                "lineColor": "#D95D39",
                "lineWidth": 2,
            }
            if index == 4:
                self.viewer.add_polyline_shape(left, style_a)
                self.viewer.add_polyline_shape(right, style_b)
            else:
                self.viewer.add_polygon_shape(left, style_a)
                self.viewer.add_polygon_shape(right, style_b)
        self.details.setPlainText("\n".join(lines))
        self.viewer.set_view_extent(FULL_EXTENT)
        self.statusBar().showMessage("Spatial predicates evaluated.")

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = SpatialPredicatesWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
