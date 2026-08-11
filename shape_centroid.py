import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QTextEdit,
    QToolBar,
)
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

RING = [(-4.0, -2.0), (3.0, -2.0), (4.0, 1.0), (1.0, 4.0), (-3.0, 3.0), (-4.0, -2.0)]
VIEW_EXTENT = Extent(-5.0, -3.0, 5.0, 5.0)


class ShapeCentroidWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("ShapeCentroid")
        self.setWindowIcon(application_icon())
        self.resize(1100, 760)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Centroid", self)
        toolbar.setMovable(False)
        calculate = toolbar.addAction("Calculate Centroid")
        full_extent = toolbar.addAction("Full Extent")
        calculate.triggered.connect(self.calculate)
        full_extent.triggered.connect(self.show_extent)
        self.addToolBar(toolbar)
        self.details = QTextEdit(self)
        self.details.setReadOnly(True)
        dock = QDockWidget("Centroid details", self)
        dock.setWidget(self.details)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.render_source()
        self.show_extent()
        self.details.setPlainText(
            "Click Calculate Centroid to calculate centroid and label point."
        )

    def render_source(self) -> None:
        self.viewer.clear_shapes()
        self.viewer.add_polygon_shape(
            RING,
            {
                "fillColor": "#A8DADC",
                "fillOpacity": 150,
                "lineColor": "#167895",
                "lineWidth": 2.0,
            },
        )

    def calculate(self) -> None:
        info = self.viewer.polygon_centroid_info(RING)
        centroid = info.get("centroid", {})
        label_point = info.get("labelPoint", {})
        cx, cy = float(centroid.get("x", 0.0)), float(centroid.get("y", 0.0))
        lx, ly = float(label_point.get("x", 0.0)), float(label_point.get("y", 0.0))
        self.render_source()
        self.viewer.add_point_shape(
            cx, cy, {"pointColor": "#E4572E", "pointSize": 11.0}
        )
        self.viewer.add_point_shape(lx, ly, {"pointColor": "#2A9D8F", "pointSize": 9.0})
        self.details.setPlainText(
            "GisShape::centroid / labelPoint\n\n"
            f"Centroid: ({cx:.3f}, {cy:.3f})\n"
            f"Centroid inside: {info.get('centroidInside')}\n\n"
            f"Label point: ({lx:.3f}, {ly:.3f})\n"
            f"Label point inside: {info.get('labelPointInside')}"
        )
        self.viewer.invalidate_render_cache(True, True)
        self.statusBar().showMessage("Centroid and label point calculated.")

    def show_extent(self) -> None:
        self.viewer.set_view_extent(VIEW_EXTENT)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = ShapeCentroidWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
