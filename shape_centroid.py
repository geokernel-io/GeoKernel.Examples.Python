import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QSplitter,
    QTextEdit,
    QToolBar,
)

from geokernel import Extent, Viewer, ViewerTool

from common import application_icon


POLYGON_RING = [
    (-4.4, -2.0),
    (3.8, -2.0),
    (3.8, 2.0),
    (1.0, 2.0),
    (1.0, -0.4),
    (-1.1, -0.4),
    (-1.1, 2.0),
    (-4.4, 2.0),
    (-4.4, -2.0),
]
SAMPLE_EXTENT = Extent(-5.4, -3.0, 4.8, 3.0)

POLYGON_STYLE = {
    "fillColor": "#BFD7EA",
    "fillOpacity": 110,
    "lineColor": "#1F6F8B",
    "lineWidth": 2.2,
}
CENTROID_STYLE = {
    "pointColor": "#D95D39",
    "pointSize": 12.0,
    "lineColor": "#8F2D1B",
    "lineWidth": 1.4,
}
LABEL_POINT_STYLE = {
    "pointColor": "#2A9D8F",
    "pointSize": 12.0,
    "lineColor": "#145A4B",
    "lineWidth": 1.4,
}


def point_text(x: float, y: float) -> str:
    return f"({x:.3f}, {y:.3f})"


def bool_text(value: object) -> str:
    return str(bool(value)).lower()


class ShapeCentroidWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("ShapeCentroid")
        self.setWindowIcon(application_icon())
        self.resize(1040, 680)
        self.setMinimumSize(760, 520)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Shape centroid", self)
        toolbar.setMovable(False)
        full_extent = toolbar.addAction("Full Extent")
        full_extent.triggered.connect(self.set_sample_extent)
        toolbar.addSeparator()
        toolbar.addWidget(
            QLabel("GisShapePolygon::centroid() / labelPoint()", toolbar)
        )
        self.addToolBar(toolbar)

        self.details = QTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setMinimumWidth(350)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.viewer_widget)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([690, 350])
        self.setCentralWidget(splitter)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.render_scene()
        self.set_sample_extent()

    def render_scene(self) -> None:
        info = self.viewer.polygon_centroid_info(POLYGON_RING)
        centroid = info["centroid"]
        label_point = info["labelPoint"]
        centroid_x = float(centroid["x"])
        centroid_y = float(centroid["y"])
        label_x = float(label_point["x"])
        label_y = float(label_point["y"])

        self.viewer.clear_shapes()
        if not self.viewer.add_polygon_shape(POLYGON_RING, POLYGON_STYLE):
            raise RuntimeError("Source concave polygon could not be rendered.")
        if not self.viewer.add_point_shape(
            centroid_x, centroid_y, CENTROID_STYLE
        ):
            raise RuntimeError("Centroid point could not be rendered.")
        if not self.viewer.add_point_shape(
            label_x, label_y, LABEL_POINT_STYLE
        ):
            raise RuntimeError("Label point could not be rendered.")

        self.details.setPlainText(
            "GisShapePolygon::centroid() / labelPoint()\n\n"
            f"Centroid: {point_text(centroid_x, centroid_y)}\n"
            f"Centroid inside polygon: {bool_text(info['centroidInside'])}\n\n"
            f"Label point: {point_text(label_x, label_y)}\n"
            f"Label point inside polygon: {bool_text(info['labelPointInside'])}\n\n"
            "Visual guide:\n"
            "Blue polygon: source concave polygon\n"
            "Orange point: centroid()\n"
            "Green point: labelPoint()\n\n"
            "For concave polygons the mathematical centroid can fall outside "
            "the visible area. labelPoint() is selected as an interior point "
            "suitable for labels."
        )

        self.viewer.invalidate_render_cache(True, True)
        self.statusBar().showMessage("Centroid and label point rendered.")

    def set_sample_extent(self) -> None:
        self.viewer.set_view_extent(SAMPLE_EXTENT)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ShapeCentroid")
    app.setWindowIcon(application_icon())

    window = ShapeCentroidWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
