import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Extent, Viewer, ViewerTool
from common import application_icon

PRESETS = (
    (
        "Point",
        '{\n  "type": "Point",\n  "coordinates": [-122.4194, 37.7749]\n}',
    ),
    (
        "LineString",
        "{\n"
        '  "type": "LineString",\n'
        '  "coordinates": [\n'
        "    [-122.4194, 37.7749],\n"
        "    [-121.8863, 37.3382],\n"
        "    [-121.4944, 38.5816],\n"
        "    [-120.7401, 37.6391]\n"
        "  ]\n"
        "}",
    ),
    (
        "Polygon",
        "{\n"
        '  "type": "Polygon",\n'
        '  "coordinates": [[\n'
        "    [-123.25, 37.15],\n"
        "    [-122.15, 36.95],\n"
        "    [-121.55, 37.65],\n"
        "    [-122.05, 38.35],\n"
        "    [-123.05, 38.15],\n"
        "    [-123.25, 37.15]\n"
        "  ]]\n"
        "}",
    ),
    (
        "MultiPolygon",
        "{\n"
        '  "type": "MultiPolygon",\n'
        '  "coordinates": [\n'
        "    [[\n"
        "      [-123.25, 37.15],\n"
        "      [-122.25, 36.95],\n"
        "      [-121.85, 37.65],\n"
        "      [-122.45, 38.20],\n"
        "      [-123.15, 37.95],\n"
        "      [-123.25, 37.15]\n"
        "    ]],\n"
        "    [[\n"
        "      [-121.60, 36.75],\n"
        "      [-120.70, 36.70],\n"
        "      [-120.45, 37.35],\n"
        "      [-121.25, 37.65],\n"
        "      [-121.60, 36.75]\n"
        "    ]]\n"
        "  ]\n"
        "}",
    ),
)

class GeoJsonReadWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.transformer = CoordinateSystemFactory()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("GeoJsonRead")
        self.setWindowIcon(application_icon())
        self.resize(1120, 760)
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
        input_layout.addWidget(QLabel("Preset:", input_bar))

        self.preset_combo = QComboBox(input_bar)
        self.preset_combo.addItems(preset[0] for preset in PRESETS)
        self.preset_combo.currentIndexChanged.connect(self.change_preset)
        input_layout.addWidget(self.preset_combo)

        read_button = QPushButton("Read GeoJSON", input_bar)
        read_button.clicked.connect(self.read_geojson)
        input_layout.addWidget(read_button)
        input_layout.addStretch(1)

        body = QWidget(root)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        left_panel = QWidget(body)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.json_edit = QTextEdit(left_panel)
        self.json_edit.setMinimumHeight(180)
        self.json_edit.setPlainText(PRESETS[0][1])
        left_layout.addWidget(self.json_edit)
        left_layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(body)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(400)

        body_layout.addWidget(left_panel, 1)
        body_layout.addWidget(self.details_view)
        root_layout.addWidget(input_bar)
        root_layout.addWidget(body, 1)
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
            if self.viewer.add_open_street_map_layer() < 0:
                raise RuntimeError("OpenStreetMap layer could not be added.")
            self.read_geojson()
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("GeoJsonRead initialization failed.")

    def read_geojson(self) -> None:
        input_json = self.json_edit.toPlainText().strip()
        try:
            geometry = self.viewer.read_geojson_geometry(input_json)
            shape_class = str(geometry.get("shapeClass", ""))
            parts = self.geometry_parts(geometry)
            if shape_class not in {"Point", "Polyline", "Polygon"} or not parts:
                raise ValueError("GeoJSON reader returned an empty shape.")

            self.clear_geometry_layers()
            self.add_geometry(shape_class, parts)
            self.refresh_viewer()
            view_extent = self.projected_extent(parts)
            self.viewer.set_view_extent(view_extent)
            self.details_view.setPlainText(
                self.details_text(input_json, shape_class, parts, view_extent)
            )
            vertex_count = sum(len(part) for part in parts)
            self.statusBar().showMessage(
                "GisGeoJsonReader::read parsed "
                f"{shape_class} with {vertex_count} vertices."
            )
        except Exception as error:
            self.clear_geometry_layers()
            self.details_view.setPlainText(f"GeoJSON parse failed:\n{error}")
            self.statusBar().showMessage("GeoJSON parse failed.")

    def geometry_parts(self, geometry: dict) -> list[list[tuple[float, float]]]:
        return [
            [(float(point["x"]), float(point["y"])) for point in part]
            for part in geometry.get("parts", [])
        ]

    def clear_geometry_layers(self) -> None:
        for name in (
            "GeoJSON Point",
            "GeoJSON LineString",
            "GeoJSON Polygon",
        ):
            self.viewer.remove_layer_by_name(name)
        self.refresh_viewer()

    def refresh_viewer(self) -> None:
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()

    def add_geometry(
        self,
        shape_class: str,
        parts: list[list[tuple[float, float]]],
    ) -> None:
        if shape_class == "Point":
            index = self.viewer.add_point_layer(
                "GeoJSON Point",
                [parts[0][0]],
                {
                    "pointColor": "#D95D39",
                    "lineColor": "#8C321D",
                    "pointSize": 14.0,
                    "lineWidth": 1.5,
                },
            )
        elif shape_class == "Polyline":
            index = self.viewer.add_polyline_layer(
                "GeoJSON LineString",
                parts,
                {
                    "lineColor": "#E4572E",
                    "lineWidth": 4.0,
                    "pointColor": "#F3A712",
                    "pointSize": 7.0,
                },
            )
        else:
            index = self.viewer.add_polygon_layer(
                "GeoJSON Polygon",
                parts,
                {
                    "fillColor": "#88D18A",
                    "fillOpacity": 128,
                    "lineColor": "#1F7A4D",
                    "lineWidth": 2.5,
                },
            )

        if index < 0:
            raise RuntimeError(f"GeoJSON {shape_class} layer could not be created.")
        if not self.viewer.set_layer_coordinate_system_preset(
            index,
            CoordinateSystemPreset.WGS84,
        ):
            raise RuntimeError(
                f"GeoJSON {shape_class} layer CRS could not be set to EPSG:4326."
            )

    def projected_extent(
        self,
        parts: list[list[tuple[float, float]]],
    ) -> Extent:
        projected = [
            self.transformer.transform_point(4326, 3857, longitude, latitude)
            for part in parts
            for longitude, latitude in part
        ]
        minimum_x = min(point[0] for point in projected)
        minimum_y = min(point[1] for point in projected)
        maximum_x = max(point[0] for point in projected)
        maximum_y = max(point[1] for point in projected)
        padding_x = max(250_000.0, (maximum_x - minimum_x) * 0.35)
        padding_y = max(250_000.0, (maximum_y - minimum_y) * 0.35)
        return Extent(
            minimum_x - padding_x,
            minimum_y - padding_y,
            maximum_x + padding_x,
            maximum_y + padding_y,
        )

    def details_text(
        self,
        input_json: str,
        shape_class: str,
        parts: list[list[tuple[float, float]]],
        view_extent: Extent,
    ) -> str:
        points = [point for part in parts for point in part]
        minimum_x = min(point[0] for point in points)
        minimum_y = min(point[1] for point in points)
        maximum_x = max(point[0] for point in points)
        maximum_y = max(point[1] for point in points)
        return "\n".join(
            (
                "GeoJsonRead sample",
                "",
                "API",
                "GisGeoJsonReader::read(jsonString)",
                "",
                "Input GeoJSON geometry",
                input_json,
                "",
                "Parsed shape",
                f"Shape class: {shape_class}",
                f"Parts: {len(parts)}",
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
            )
        )

    def change_preset(self, index: int) -> None:
        self.json_edit.setPlainText(PRESETS[index][1])
        if self.initialized:
            self.read_geojson()

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GeoJsonRead")
    app.setWindowIcon(application_icon())
    window = GeoJsonReadWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
