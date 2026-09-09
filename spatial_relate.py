import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

LEFT = [(-4.0, -1.4), (0.7, -1.4), (0.7, 2.0), (-4.0, 2.0), (-4.0, -1.4)]
RIGHT = [(-1.0, -2.1), (3.9, -2.1), (3.9, 1.3), (-1.0, 1.3), (-1.0, -2.1)]
FULL_EXTENT = Extent(-5.1, -3.0, 5.0, 3.0)
PATTERNS = [
    ("Intersects", "T********"),
    ("Disjoint", "FF*FF****"),
    ("Contains", "T*****FF*"),
    ("Within", "T*F**F***"),
    ("Touches", "FT*******"),
    ("Overlaps", "T*T***T**"),
]

class SpatialRelateWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("SpatialRelate")
        self.setWindowIcon(application_icon())
        self.resize(980, 680)
        self.create_ui()

    def create_ui(self):
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QWidget(root)
        row = QHBoxLayout(bar)
        full = QPushButton("Full Extent", bar)
        full.clicked.connect(lambda: self.viewer.set_view_extent(FULL_EXTENT))
        row.addWidget(full)
        row.addWidget(QLabel("Operation: Relate(left, right)", bar))
        run = QPushButton("Run Relate", bar)
        run.clicked.connect(self.run)
        row.addWidget(run)
        row.addStretch()
        content = QWidget(root)
        split = QHBoxLayout(content)
        split.setContentsMargins(0, 0, 0, 0)
        split.addWidget(self.widget, 1)
        self.details = QTextEdit(content)
        self.details.setReadOnly(True)
        self.details.setMinimumWidth(290)
        split.addWidget(self.details)
        layout.addWidget(bar)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def initialize_viewer(self):
        self.initialized = True
        self.viewer.resize(self.widget.width(), self.widget.height())
        self.viewer.show()
        self.viewer.add_polygon_shape(
            LEFT,
            {
                "fillColor": "#BFD7EA",
                "fillOpacity": 125,
                "lineColor": "#2F80C2",
                "lineWidth": 2,
            },
        )
        self.viewer.add_polygon_shape(
            RIGHT,
            {
                "fillColor": "#F6D6AD",
                "fillOpacity": 125,
                "lineColor": "#D95D39",
                "lineWidth": 2,
            },
        )
        self.details.setPlainText(
            "Relate(left, right)\nDE-9IM style relation string returned by GisTopology::Relate.\n\nClick Run Relate to calculate the relation matrix."
        )
        self.viewer.set_view_extent(FULL_EXTENT)

    def run(self):
        matrix = self.viewer.relate_polygon_rings(LEFT, RIGHT)
        lines = [
            "Relate(left, right)",
            "DE-9IM style relation string returned by GisTopology::Relate.",
            "",
            f"Relate matrix: {matrix}",
            "",
            "Pattern matches:",
        ]
        lines.extend(
            f"{name} ({pattern}): {self.viewer.relate_polygon_rings_pattern(LEFT, RIGHT, pattern)}"
            for name, pattern in PATTERNS
        )
        self.details.setPlainText("\n".join(lines))
        self.statusBar().showMessage(f"Relate matrix calculated: {matrix}")

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = SpatialRelateWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
