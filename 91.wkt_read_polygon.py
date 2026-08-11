import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Extent, Viewer, ViewerTool
from common import application_icon

POLYGON_WKT = (
    "POLYGON((-123.25 37.15, -122.15 36.95, -121.55 37.65, "
    "-122.05 38.35, -123.05 38.15, -123.25 37.15))"
)
MULTIPOLYGON_WKT = (
    "MULTIPOLYGON(((-123.25 37.15, -122.25 36.95, -121.85 37.65, "
    "-122.45 38.20, -123.15 37.95, -123.25 37.15)),"
    "((-121.60 36.75, -120.70 36.70, -120.45 37.35, "
    "-121.25 37.65, -121.60 36.75)))"
)

class WktReadPolygonWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.transformer = CoordinateSystemFactory()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.polygon_layer_index = -1
        self.initialized = False

        self.setWindowTitle("WktReadPolygon")
        self.setWindowIcon(application_icon())
        self.resize(1120, 720)
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

        input_layout.addWidget(QLabel("Mode:", input_bar))
        self.mode_combo = QComboBox(input_bar)
        self.mode_combo.addItems(("Polygon", "MultiPolygon"))
        self.mode_combo.currentIndexChanged.connect(self.change_mode)
        input_layout.addWidget(self.mode_combo)

        input_layout.addWidget(QLabel("WKT:", input_bar))
        self.wkt_edit = QLineEdit(POLYGON_WKT, input_bar)
        self.wkt_edit.returnPressed.connect(self.read_polygon)
        input_layout.addWidget(self.wkt_edit, 1)

        self.read_button = QPushButton("Read Polygon", input_bar)
        self.read_button.clicked.connect(self.read_polygon)
        input_layout.addWidget(self.read_button)

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
        self.details_view.setMinimumWidth(400)
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
            self.read_polygon()
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("WktReadPolygon initialization failed.")

    def read_polygon(self) -> None:
        input_wkt = self.wkt_edit.text().strip()
        multi_polygon = self.mode_combo.currentIndex() == 1

        try:
            data = self.viewer.read_wkt_polygon(input_wkt, multi_polygon)
            rings = [
                [(float(point["x"]), float(point["y"])) for point in ring]
                for ring in data
            ]
            if not rings or any(len(ring) < 4 for ring in rings):
                raise ValueError(
                    "A polygon must contain at least one valid closed ring."
                )

            view_extent = self.projected_extent(rings)
            self.replace_polygon_layer(rings)
            self.details_view.setPlainText(
                self.details_text(input_wkt, rings, view_extent, multi_polygon)
            )
            self.viewer.set_view_extent(view_extent)

            api_name = self.api_name(multi_polygon)
            vertex_count = sum(len(ring) for ring in rings)
            self.statusBar().showMessage(
                f"{api_name} parsed {len(rings)} rings and {vertex_count} vertices."
            )
        except Exception as error:
            self.remove_polygon_layer()
            self.details_view.setPlainText(f"WKT parse failed:\n{error}")
            self.statusBar().showMessage("WKT parse failed.")

    def replace_polygon_layer(
        self,
        rings: list[list[tuple[float, float]]],
    ) -> None:
        self.remove_polygon_layer()
        self.polygon_layer_index = self.viewer.add_polygon_layer(
            "WKT Polygon",
            rings,
            {
                "fillColor": "#88D18A",
                "fillOpacity": 128,
                "lineColor": "#1F7A4D",
                "lineWidth": 2.5,
            },
        )
        if self.polygon_layer_index < 0:
            raise RuntimeError("WKT polygon layer could not be created.")
        if not self.viewer.set_layer_coordinate_system_preset(
            self.polygon_layer_index,
            CoordinateSystemPreset.WGS84,
        ):
            raise RuntimeError("WKT polygon layer CRS could not be set to EPSG:4326.")

    def remove_polygon_layer(self) -> None:
        if self.polygon_layer_index < 0:
            return
        self.viewer.remove_layer(self.polygon_layer_index)
        self.polygon_layer_index = -1

    def projected_extent(
        self,
        rings: list[list[tuple[float, float]]],
    ) -> Extent:
        projected_points = [
            self.transformer.transform_point(4326, 3857, longitude, latitude)
            for ring in rings
            for longitude, latitude in ring
        ]
        minimum_x = min(point[0] for point in projected_points)
        minimum_y = min(point[1] for point in projected_points)
        maximum_x = max(point[0] for point in projected_points)
        maximum_y = max(point[1] for point in projected_points)
        padding_x = max(300_000.0, (maximum_x - minimum_x) * 0.35)
        padding_y = max(300_000.0, (maximum_y - minimum_y) * 0.35)
        return Extent(
            minimum_x - padding_x,
            minimum_y - padding_y,
            maximum_x + padding_x,
            maximum_y + padding_y,
        )

    def centroid(
        self,
        rings: list[list[tuple[float, float]]],
    ) -> tuple[float, float]:
        weighted_x = 0.0
        weighted_y = 0.0
        total_cross = 0.0
        for ring in rings:
            for first, second in zip(ring, ring[1:]):
                cross = first[0] * second[1] - second[0] * first[1]
                total_cross += cross
                weighted_x += (first[0] + second[0]) * cross
                weighted_y += (first[1] + second[1]) * cross

        if abs(total_cross) < 1e-12:
            points = [point for ring in rings for point in ring[:-1]]
            return (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )
        return (
            weighted_x / (3.0 * total_cross),
            weighted_y / (3.0 * total_cross),
        )

    def details_text(
        self,
        input_wkt: str,
        rings: list[list[tuple[float, float]]],
        view_extent: Extent,
        multi_polygon: bool,
    ) -> str:
        points = [point for ring in rings for point in ring]
        minimum_x = min(point[0] for point in points)
        minimum_y = min(point[1] for point in points)
        maximum_x = max(point[0] for point in points)
        maximum_y = max(point[1] for point in points)
        centroid_x, centroid_y = self.centroid(rings)
        round_trip_wkt = self.viewer.write_wkt_polygon(rings)
        return "\n".join(
            (
                "WktReadPolygon sample",
                "",
                "API",
                self.api_name(multi_polygon),
                "",
                "Input WKT",
                input_wkt,
                "",
                "Parsed polygon",
                f"Parts/rings: {len(rings)}",
                f"Vertices: {len(points)}",
                "Lon/lat extent: "
                f"({minimum_x:.6f}, {minimum_y:.6f}) - "
                f"({maximum_x:.6f}, {maximum_y:.6f})",
                f"Centroid: {centroid_x:.6f}, {centroid_y:.6f}",
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

    def api_name(self, multi_polygon: bool) -> str:
        if multi_polygon:
            return "GisWktReader::readMultiPolygon(wkt)"
        return "GisWktReader::readPolygon(wkt)"

    def change_mode(self, index: int) -> None:
        multi_polygon = index == 1
        self.wkt_edit.setText(MULTIPOLYGON_WKT if multi_polygon else POLYGON_WKT)
        self.read_button.setText(
            "Read MultiPolygon" if multi_polygon else "Read Polygon"
        )
        if self.initialized:
            self.read_polygon()

    def reset_sample(self) -> None:
        multi_polygon = self.mode_combo.currentIndex() == 1
        self.wkt_edit.setText(MULTIPOLYGON_WKT if multi_polygon else POLYGON_WKT)
        self.read_polygon()

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WktReadPolygon")
    app.setWindowIcon(application_icon())
    window = WktReadPolygonWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
