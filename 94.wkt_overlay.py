import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

POINT_WKT = "POINT(-122.4194 37.7749)"
LINE_WKT = "LINESTRING(-123.0 37.1, -122.5 37.8, -121.9 37.3, -121.2 38.0)"
POLYGON_WKT = (
    "POLYGON((-123.25 37.15, -122.15 36.95, -121.55 37.65, "
    "-122.05 38.35, -123.05 38.15, -123.25 37.15))"
)
VIEW_EXTENT = Extent(-124.0, 36.4, -120.3, 38.7)

class WktOverlayWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("WktOverlay")
        self.setWindowIcon(application_icon())
        self.resize(1100, 720)
        self.create_ui()

    def create_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(root)
        self.details_view.setReadOnly(True)
        self.details_view.setMaximumHeight(170)
        layout.addWidget(self.details_view)

        self.setCentralWidget(root)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.viewer.resize(
            self.viewer_widget.width(),
            self.viewer_widget.height(),
        )
        self.viewer.show()

        try:
            self.run_sample()
            self.viewer.set_view_extent(VIEW_EXTENT)
            self.statusBar().showMessage("WktOverlay ready.")
        except Exception as error:
            self.details_view.setPlainText(f"WKT overlay failed:\n{error}")
            self.statusBar().showMessage("WktOverlay failed.")

    def run_sample(self) -> None:
        point = self.viewer.read_wkt_point(POINT_WKT)
        if point is None:
            raise RuntimeError("GisWktReader::readPoint returned no point.")

        line_data = self.viewer.read_wkt_line_string(LINE_WKT)
        line = [(float(item["x"]), float(item["y"])) for item in line_data]
        if len(line) < 2:
            raise RuntimeError("GisWktReader::readLineString returned no line.")

        polygon_data = self.viewer.read_wkt_polygon(POLYGON_WKT)
        polygon = [
            [(float(point["x"]), float(point["y"])) for point in ring]
            for ring in polygon_data
        ]
        if not polygon:
            raise RuntimeError("GisWktReader::readPolygon returned no polygon.")

        polygon_index = self.viewer.add_polygon_layer(
            "WKT Polygons",
            polygon,
            {
                "fillColor": "#88D18A",
                "fillOpacity": 128,
                "lineColor": "#1F7A4D",
                "lineWidth": 2.2,
            },
        )
        line_index = self.viewer.add_polyline_layer(
            "WKT Lines",
            [line],
            {
                "lineColor": "#E4572E",
                "lineWidth": 3.0,
            },
        )
        point_index = self.viewer.add_point_layer(
            "WKT Points",
            [point],
            {
                "pointColor": "#D95D39",
                "lineColor": "#8C321D",
                "pointSize": 12.0,
            },
        )
        if min(polygon_index, line_index, point_index) < 0:
            raise RuntimeError("One or more WKT overlay layers could not be created.")

        self.details_view.setPlainText(
            "\n".join(
                (
                    "WktOverlay sample",
                    "",
                    "API",
                    "GisWktReader::readPoint/readLineString/readPolygon",
                    "GisViewer::addLayer(layer)",
                    "",
                    "Three WKT strings are parsed and displayed as overlay layers.",
                )
            )
        )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WktOverlay")
    app.setWindowIcon(application_icon())
    window = WktOverlayWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
