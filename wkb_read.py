import re
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Extent, Viewer, ViewerTool
from common import application_icon

PRESETS = {
    "Point": "010100000050FC1873D79A5EC0D0D556EC2FE34240",
    "LineString": (
        "01020000000400000050FC1873D79A5EC0D0D556EC2FE34240789CA223B9785EC0"
        "ECC039234AAB42401DC9E53FA45F5EC043AD69DE714A434041F163CC5D2F5EC0"
        "D26F5F07CED14240"
    ),
    "Polygon": (
        "010300000001000000060000000000000000D05EC033333333339342409A999999"
        "99895EC09A999999997942403333333333635EC03333333333D342403333333333"
        "835EC0CDCCCCCCCC2C43403333333333C35EC033333333331343400000000000D0"
        "5EC03333333333934240"
    ),
    "MultiPolygon": (
        "010600000002000000010300000001000000060000000000000000D05EC033333333"
        "339342400000000000905EC09A999999997942406666666666765EC03333333333D3"
        "4240CDCCCCCCCC9C5EC09A999999991943409A99999999C95EC09A99999999F942"
        "400000000000D05EC033333333339342400103000000010000000500000066666666"
        "66665EC00000000000604240CDCCCCCCCC2C5EC09A99999999594240CDCCCCCCCC1C"
        "5EC0CDCCCCCCCCAC42400000000000505EC03333333333D342406666666666665EC0"
        "0000000000604240"
    ),
}

class WkbReadWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.transformer = CoordinateSystemFactory()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.geometry_layer_index = -1
        self.initialized = False

        self.setWindowTitle("WkbRead")
        self.setWindowIcon(application_icon())
        self.resize(1120, 760)
        self.create_ui()

    def create_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        preset_bar = QWidget(root)
        preset_layout = QHBoxLayout(preset_bar)
        preset_layout.setContentsMargins(6, 4, 6, 4)
        preset_layout.setSpacing(8)
        preset_layout.addWidget(QLabel("Preset:", preset_bar))
        for name in PRESETS:
            button = QPushButton(name, preset_bar)
            button.clicked.connect(
                lambda checked=False, value=name: self.load_preset(value)
            )
            preset_layout.addWidget(button)

        read_button = QPushButton("Read WKB", preset_bar)
        read_button.clicked.connect(self.read_wkb)
        preset_layout.addWidget(read_button)
        preset_layout.addStretch(1)

        body = QWidget(root)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        left_panel = QWidget(body)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.wkb_edit = QTextEdit(left_panel)
        self.wkb_edit.setMinimumHeight(150)
        self.wkb_edit.setPlainText(PRESETS["Point"])
        left_layout.addWidget(self.wkb_edit)
        left_layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(body)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(420)

        body_layout.addWidget(left_panel, 1)
        body_layout.addWidget(self.details_view)
        root_layout.addWidget(preset_bar)
        root_layout.addWidget(body, 1)
        self.setCentralWidget(root)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            if self.viewer.add_open_street_map_layer() < 0:
                raise RuntimeError("OpenStreetMap layer could not be added.")
            self.read_wkb()
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("WkbRead initialization failed.")

    def load_preset(self, name: str) -> None:
        self.wkb_edit.setPlainText(PRESETS[name])
        if self.initialized:
            self.read_wkb()

    def parse_hex(self) -> tuple[str, bytes]:
        input_hex = re.sub(r"\s+", "", self.wkb_edit.toPlainText())
        if not input_hex:
            raise ValueError("WKB hex input is empty.")
        if len(input_hex) % 2:
            raise ValueError("WKB hex input must contain an even number of characters.")
        if re.fullmatch(r"[0-9A-Fa-f]+", input_hex) is None:
            raise ValueError("WKB input must be hexadecimal.")
        return input_hex, bytes.fromhex(input_hex)

    def read_wkb(self) -> None:
        try:
            input_hex, payload = self.parse_hex()
            geometry = self.viewer.read_wkb_geometry(payload)
            shape_class = str(geometry.get("shapeClass", ""))
            parts = self.geometry_parts(geometry)
            if not shape_class or not parts:
                raise ValueError("GisWkbReader::read returned an empty shape.")

            self.replace_geometry_layer(shape_class, parts)
            view_extent = self.projected_extent(parts)
            self.viewer.set_view_extent(view_extent)
            self.viewer.invalidate_render_cache(True, True)
            self.viewer.refresh_layers()
            vertex_count = sum(len(part) for part in parts)
            self.details_view.setPlainText(
                self.details_text(
                    input_hex,
                    len(payload),
                    shape_class,
                    len(parts),
                    vertex_count,
                    parts,
                    view_extent,
                )
            )
            self.statusBar().showMessage(
                f"GisWkbReader::read parsed {shape_class} from {len(payload)} bytes."
            )
        except Exception as error:
            self.remove_geometry_layer()
            self.details_view.setPlainText(f"WKB parse failed:\n{error}")
            self.statusBar().showMessage("WKB parse failed.")

    def geometry_parts(self, geometry: dict) -> list[list[tuple[float, float]]]:
        return [
            [(float(point["x"]), float(point["y"])) for point in part]
            for part in geometry.get("parts", [])
            if part
        ]

    def replace_geometry_layer(
        self, shape_class: str, parts: list[list[tuple[float, float]]]
    ) -> None:
        self.remove_geometry_layer()
        if shape_class == "Point":
            self.geometry_layer_index = self.viewer.add_point_layer(
                "WKB Point",
                [parts[0][0]],
                {"pointColor": "#D95D39", "lineColor": "#8C321D", "pointSize": 14.0},
            )
        elif shape_class == "Polyline":
            self.geometry_layer_index = self.viewer.add_polyline_layer(
                "WKB LineString",
                parts,
                {"lineColor": "#E4572E", "lineWidth": 4.0},
            )
        elif shape_class == "Polygon":
            self.geometry_layer_index = self.viewer.add_polygon_layer(
                "WKB Polygon",
                parts,
                {
                    "fillColor": "#88D18A",
                    "fillOpacity": 128,
                    "lineColor": "#1F7A4D",
                    "lineWidth": 2.5,
                },
            )
        else:
            raise ValueError(f"Unsupported WKB shape class: {shape_class}")

        if self.geometry_layer_index < 0:
            raise RuntimeError("Parsed WKB layer could not be created.")
        if not self.viewer.set_layer_coordinate_system_preset(
            self.geometry_layer_index, CoordinateSystemPreset.WGS84
        ):
            raise RuntimeError("WKB layer CRS could not be set to EPSG:4326.")

    def remove_geometry_layer(self) -> None:
        if self.geometry_layer_index < 0:
            return
        self.viewer.remove_layer(self.geometry_layer_index)
        self.geometry_layer_index = -1

    def projected_extent(self, parts: list[list[tuple[float, float]]]) -> Extent:
        projected = [
            self.transformer.transform_point(4326, 3857, x, y)
            for part in parts
            for x, y in part
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
        input_hex: str,
        byte_count: int,
        shape_class: str,
        part_count: int,
        vertex_count: int,
        parts: list[list[tuple[float, float]]],
        view_extent: Extent,
    ) -> str:
        points = [point for part in parts for point in part]
        lon_lat_extent = (
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        )
        return "\n".join(
            (
                "WkbRead sample",
                "",
                "API",
                "GisWkbReader::read(byteArray)",
                "",
                "Input WKB",
                f"Hex characters: {len(input_hex)}",
                f"Byte count: {byte_count}",
                "",
                "Parsed shape",
                f"Shape class: {shape_class}",
                f"Parts: {part_count}",
                f"Vertices: {vertex_count}",
                "Lon/lat extent: "
                f"({lon_lat_extent[0]:.6f}, {lon_lat_extent[1]:.6f}) - "
                f"({lon_lat_extent[2]:.6f}, {lon_lat_extent[3]:.6f})",
                "",
                "Displayed over OSM",
                "Layer CRS: EPSG:4326",
                "Viewer/OSM CRS: EPSG:3857",
                "WebMercator view extent: "
                f"({view_extent.x_min:.3f}, {view_extent.y_min:.3f}) - "
                f"({view_extent.x_max:.3f}, {view_extent.y_max:.3f})",
                "",
                "Input hex",
                input_hex,
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
    app.setApplicationName("WkbRead")
    app.setWindowIcon(application_icon())
    window = WkbReadWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
