import math
import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QSlider, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

LINE = [(-4.5, 0.0), (4.5, 0.0)]
POINT = (0.0, 0.35)
FULL_EXTENT = Extent(-5.2, -1.8, 5.2, 2.4)

class ToleranceConfigWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("ToleranceConfig")
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
        self.slider.setRange(0, 100)
        self.slider.setValue(25)
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
        self.details.setMinimumWidth(300)
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
        info = self.viewer.line_point_tolerance_info(LINE, *POINT, tolerance)
        intersects = bool(info.get("intersects", False))
        crossings = info.get("crossings", [])
        active = bool(crossings) or intersects
        circle = [
            (
                POINT[0] + tolerance * math.cos(i * math.tau / 48),
                POINT[1] + tolerance * math.sin(i * math.tau / 48),
            )
            for i in range(49)
        ]
        color = "#2A9D8F" if active else "#D95D39"
        self.viewer.clear_shapes()
        self.viewer.add_polyline_shape(LINE, {"lineColor": "#2F80C2", "lineWidth": 3})
        self.viewer.add_point_shape(
            *POINT, {"pointColor": "#F9C74F", "pointSize": 11, "lineColor": color}
        )
        if tolerance > 0:
            self.viewer.add_polyline_shape(circle, {"lineColor": color, "lineWidth": 2})
        result = (
            "The point is accepted as touching/intersecting the line within tolerance."
            if active
            else "The point is outside the configured tolerance."
        )
        self.details.setPlainText(
            f"GisTopology::SetTolerance\n\nScenario:\n- Baseline is y = 0.\n- Test point is at (0.00, 0.35).\n- Point-to-line distance is 0.35 map units.\n\nConfigured tolerance: {tolerance:.2f}\nGetCrossings(line, point): {len(crossings)} point(s)\nIntersect(line, point): {str(intersects).lower()}\n\nResult:\n{result}"
        )
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.viewer.set_view_extent(extent)
        self.statusBar().showMessage(f"Topology tolerance: {tolerance:.2f} map units.")

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = ToleranceConfigWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
