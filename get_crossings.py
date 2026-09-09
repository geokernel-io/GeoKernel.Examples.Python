import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

LEFT = [(-6.0, -2.2), (-4.2, 1.6), (-2.0, -0.5), (0.2, 2.1), (2.4, -0.7), (5.8, 2.2)]
RIGHT = [(-6.2, 1.9), (-3.8, -1.6), (-1.4, 1.5), (1.2, -1.9), (3.2, 1.3), (5.8, -1.2)]
FULL_EXTENT = Extent(-7.0, -3.2, 6.8, 3.2)

class GetCrossingsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("GetCrossings")
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
        row.addWidget(QLabel("Operation: GetCrossings(left, right)", bar))
        run = QPushButton("Run GetCrossings", bar)
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
        self.render(False)
        self.viewer.set_view_extent(FULL_EXTENT)

    def run(self):
        self.render(True)

    def render(self, show):
        extent = self.viewer.get_view_extent() if show else None
        self.viewer.clear_shapes()
        self.viewer.add_polyline_shape(LEFT, {"lineColor": "#2F80C2", "lineWidth": 3})
        self.viewer.add_polyline_shape(RIGHT, {"lineColor": "#D95D39", "lineWidth": 3})
        lines = [
            "GetCrossings(left, right)",
            "The two polylines are arranged to cross at multiple segment intersections.",
            "",
            f"Left vertices: {len(LEFT)}",
            f"Right vertices: {len(RIGHT)}",
        ]
        if show:
            crossings = self.viewer.polyline_crossings(LEFT, RIGHT)
            lines.extend(("", f"Crossing count: {len(crossings)}"))
            for index, p in enumerate(crossings, 1):
                x = float(p["x"])
                y = float(p["y"])
                self.viewer.add_point_shape(
                    x,
                    y,
                    {
                        "pointColor": "#F9C74F",
                        "pointSize": 12,
                        "lineColor": "#D95D39",
                        "lineWidth": 2,
                    },
                )
                lines.append(f"P{index}: ({x:.3f}, {y:.3f})")
            self.statusBar().showMessage(
                f"GetCrossings found {len(crossings)} point(s)."
            )
        else:
            lines.extend(
                ("", "Click Run GetCrossings to calculate intersection points.")
            )
            self.statusBar().showMessage(
                "Source polylines are ready. Click Run GetCrossings."
            )
        self.details.setPlainText("\n".join(lines))
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        if extent is not None:
            self.viewer.set_view_extent(extent)

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = GetCrossingsWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
