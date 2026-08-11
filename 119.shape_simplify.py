import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QSlider, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

RING = [
    (-5.8, -1.8),
    (-5.4, -0.6),
    (-4.9, 0.2),
    (-4.2, 1.0),
    (-3.5, 1.6),
    (-2.7, 1.9),
    (-2.0, 1.5),
    (-1.2, 2.1),
    (-0.3, 1.7),
    (0.5, 2.0),
    (1.4, 1.2),
    (2.2, 1.4),
    (3.0, 0.6),
    (3.8, 0.9),
    (4.7, 0.1),
    (5.2, -0.9),
    (4.2, -1.4),
    (3.1, -1.1),
    (2.1, -1.8),
    (1.1, -1.3),
    (0.1, -2.0),
    (-0.9, -1.5),
    (-1.9, -2.1),
    (-2.8, -1.5),
    (-3.8, -1.9),
    (-4.7, -1.2),
    (-5.8, -1.8),
]
FULL_EXTENT = Extent(-7.2, -3.0, 6.8, 3.1)

class ShapeSimplifyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("ShapeSimplify")
        self.setWindowIcon(application_icon())
        self.resize(980, 680)
        self.create_ui()

    def create_ui(self):
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QWidget(root)
        row = QHBoxLayout(bar)
        row.addWidget(QLabel("Tolerance:", bar))
        self.slider = QSlider(Qt.Orientation.Horizontal, bar)
        self.slider.setRange(0, 200)
        self.slider.setValue(45)
        self.slider.setFixedWidth(180)
        self.slider.valueChanged.connect(self.render)
        row.addWidget(self.slider)
        self.value = QLabel(bar)
        row.addWidget(self.value)
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
        self.render()
        self.viewer.set_view_extent(FULL_EXTENT)

    def render(self):
        if not self.initialized:
            return
        extent = self.viewer.get_view_extent()
        tolerance = self.slider.value() / 100
        self.value.setText(f"{tolerance:.2f} units")
        result = self.viewer.simplify_polygon_ring(RING, tolerance)
        simple = [(float(p["x"]), float(p["y"])) for p in result]
        self.viewer.clear_shapes()
        self.viewer.add_polygon_shape(
            RING,
            {
                "fillColor": "#CBD5E1",
                "fillOpacity": 75,
                "lineColor": "#64748B",
                "lineWidth": 2,
            },
        )
        if simple:
            self.viewer.add_polygon_shape(
                simple,
                {
                    "fillColor": "#F9C74F",
                    "fillOpacity": 100,
                    "lineColor": "#D95D39",
                    "lineWidth": 3,
                },
            )
        self.details.setPlainText(
            f"shape.simplify(tolerance)\nAlgorithm: Douglas-Peucker\n\nTolerance: {tolerance:.2f} map units\nSource polygon vertices: {len(RING)}\nSimplified polygon vertices: {len(simple)}\nRemoved vertices: {len(RING) - len(simple)}"
        )
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.viewer.set_view_extent(extent)
        self.statusBar().showMessage(
            f"Simplify applied with tolerance {tolerance:.2f}."
        )

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = ShapeSimplifyWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
