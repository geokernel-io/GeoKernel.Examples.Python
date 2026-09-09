import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Extent, Viewer, ViewerTool
from common import application_icon

DEFAULT_WKT = (
    "LINESTRING(-122.4194 37.7749, -121.8863 37.3382, "
    "-121.4944 38.5816, -120.7401 37.6391)"
)

class WktReadPolylineWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.transformer = CoordinateSystemFactory()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.polyline_layer_index = -1
        self.initialized = False

        self.setWindowTitle("WktReadPolyline")
        self.setWindowIcon(application_icon())
        self.resize(1100, 720)
        self.create_ui()

    def create_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        input_bar = QWidget(root)
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(6, 4, 6, 4)
        input_layout.setSpacing(8)
        input_layout.addWidget(QLabel("WKT:", input_bar))

        self.wkt_edit = QLineEdit(DEFAULT_WKT, input_bar)
        self.wkt_edit.returnPressed.connect(self.read_line_string)
        input_layout.addWidget(self.wkt_edit, 1)

        read_button = QPushButton("Read LineString", input_bar)
        read_button.clicked.connect(self.read_line_string)
        input_layout.addWidget(read_button)

        reset_button = QPushButton("Reset", input_bar)
        reset_button.clicked.connect(self.reset_sample)
        input_layout.addWidget(reset_button)

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(content)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(380)
        content_layout.addWidget(self.details_view)

        root_layout.addWidget(input_bar)
        root_layout.addWidget(content, 1)
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
            osm_index = self.viewer.add_open_street_map_layer()
            if osm_index < 0:
                raise RuntimeError("OpenStreetMap layer could not be added.")
            self.read_line_string()
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("WktReadPolyline initialization failed.")

    def read_line_string(self) -> None:
        input_wkt = self.wkt_edit.text().strip()

        try:
            data = self.viewer.read_wkt_line_string(input_wkt)
            points = [(float(item["x"]), float(item["y"])) for item in data]
            if len(points) < 2:
                raise ValueError("A LineString must contain at least two vertices.")

            view_extent = self.projected_extent(points)
            self.replace_polyline_layer(points)
            self.details_view.setPlainText(
                self.details_text(input_wkt, points, view_extent)
            )
            self.viewer.set_view_extent(view_extent)
            self.statusBar().showMessage(
                f"GisWktReader::readLineString parsed {len(points)} vertices."
            )
        except Exception as error:
            self.remove_polyline_layer()
            self.details_view.setPlainText(f"WKT parse failed:\n{error}")
            self.statusBar().showMessage("WKT parse failed.")

    def replace_polyline_layer(
        self,
        points: list[tuple[float, float]],
    ) -> None:
        self.remove_polyline_layer()
        self.polyline_layer_index = self.viewer.add_polyline_layer(
            "WKT LineString",
            [points],
            {
                "lineColor": "#E4572E",
                "lineWidth": 4.0,
                "pointColor": "#F3A712",
                "pointSize": 7.0,
            },
        )
        if self.polyline_layer_index < 0:
            raise RuntimeError("WKT LineString layer could not be created.")
        if not self.viewer.set_layer_coordinate_system_preset(
            self.polyline_layer_index,
            CoordinateSystemPreset.WGS84,
        ):
            raise RuntimeError(
                "WKT LineString layer CRS could not be set to EPSG:4326."
            )

    def remove_polyline_layer(self) -> None:
        if self.polyline_layer_index < 0:
            return
        self.viewer.remove_layer(self.polyline_layer_index)
        self.polyline_layer_index = -1

    def projected_extent(
        self,
        points: list[tuple[float, float]],
    ) -> Extent:
        projected_points = [
            self.transformer.transform_point(4326, 3857, longitude, latitude)
            for longitude, latitude in points
        ]
        minimum_x = min(point[0] for point in projected_points)
        minimum_y = min(point[1] for point in projected_points)
        maximum_x = max(point[0] for point in projected_points)
        maximum_y = max(point[1] for point in projected_points)
        padding_x = max(250_000.0, (maximum_x - minimum_x) * 0.25)
        padding_y = max(250_000.0, (maximum_y - minimum_y) * 0.25)
        return Extent(
            minimum_x - padding_x,
            minimum_y - padding_y,
            maximum_x + padding_x,
            maximum_y + padding_y,
        )

    def details_text(
        self,
        input_wkt: str,
        points: list[tuple[float, float]],
        view_extent: Extent,
    ) -> str:
        minimum_x = min(point[0] for point in points)
        minimum_y = min(point[1] for point in points)
        maximum_x = max(point[0] for point in points)
        maximum_y = max(point[1] for point in points)
        round_trip_wkt = self.viewer.write_wkt_line_string(points)
        return "\n".join(
            (
                "WktReadPolyline sample",
                "",
                "API",
                "GisWktReader::readLineString(wkt)",
                "",
                "Input WKT",
                input_wkt,
                "",
                "Parsed line",
                "Parts: 1",
                f"Vertices: {len(points)}",
                "Lon/lat extent: "
                f"({minimum_x:.6f}, {minimum_y:.6f}) - "
                f"({maximum_x:.6f}, {maximum_y:.6f})",
                "",
                "Displayed over OSM",
                "Layer CRS: EPSG:4326",
                "Viewer/OSM CRS: EPSG:3857",
                "WebMercator view extent: "
                f"({view_extent.x_min:.3f}, {view_extent.y_min:.3f}) - "
                f"({view_extent.x_max:.3f}, {view_extent.y_max:.3f})",
                "",
                "Round-trip WKT",
                round_trip_wkt,
            )
        )

    def reset_sample(self) -> None:
        self.wkt_edit.setText(DEFAULT_WKT)
        self.read_line_string()

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WktReadPolyline")
    app.setWindowIcon(application_icon())
    window = WktReadPolylineWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
