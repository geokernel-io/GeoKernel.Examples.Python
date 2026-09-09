import struct
import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QDockWidget, QListWidget, QListWidgetItem, QMainWindow, QMessageBox
from geokernel import ClassificationMethod, ColorRampMode, CoordinateSystemFactory, Extent, SymbolStyleTarget, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

SIZE_FIELD = "POP_CLASS_SIZE"
MINIMUM_POINT_SIZE = 3.0
MAXIMUM_POINT_SIZE = 36.0
CLASS_LABELS = (
    "Less than 50,000",
    "50,000 to 100,000",
    "100,000 to 250,000",
    "250,000 to 500,000",
    "500,000 to 1,000,000",
    "1,000,000 to 5,000,000",
)
CITY_STYLE = {
    "pointColor": "#48D95F35",
    "pointSize": MINIMUM_POINT_SIZE,
    "lineColor": "#AF8A3A24",
    "lineWidth": 0.9,
}

def population_class_size(population_class: str) -> float:
    value = population_class.strip().casefold()
    for index, label in enumerate(CLASS_LABELS, start=1):
        if value == label.casefold():
            return float(index)
    return 0.0

def read_dbf_records(path: Path) -> list[dict]:
    with path.open("rb") as file:
        header = file.read(32)
        record_count = struct.unpack_from("<I", header, 4)[0]
        header_length = struct.unpack_from("<H", header, 8)[0]
        record_length = struct.unpack_from("<H", header, 10)[0]
        fields = []

        while file.tell() < header_length - 1:
            descriptor = file.read(32)
            if not descriptor or descriptor[0] == 0x0D:
                break
            name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
            fields.append((name, chr(descriptor[11]), descriptor[16], descriptor[17]))

        file.seek(header_length)
        records = []
        for _ in range(record_count):
            record = file.read(record_length)
            if len(record) != record_length:
                break
            if record[0:1] == b"*":
                records.append({})
                continue

            attributes = {}
            offset = 1
            for name, field_type, length, decimals in fields:
                text = record[offset : offset + length].decode("cp1252", errors="replace").strip()
                offset += length
                if field_type in ("N", "F") and text:
                    attributes[name] = float(text) if decimals or "." in text else int(text)
                else:
                    attributes[name] = text
            records.append(attributes)
        return records

def read_point_records(path: Path) -> list[tuple[float, float] | None]:
    points = []
    with path.open("rb") as file:
        file.seek(100)
        while True:
            record_header = file.read(8)
            if len(record_header) != 8:
                break
            content_length = struct.unpack(">I", record_header[4:])[0] * 2
            content = file.read(content_length)
            if len(content) != content_length:
                break
            shape_type = struct.unpack_from("<I", content, 0)[0]
            if shape_type == 0:
                points.append(None)
            elif shape_type == 1:
                points.append(struct.unpack_from("<dd", content, 4))
            else:
                raise ValueError(f"Expected a point shapefile, found shape type {shape_type}.")
    return points

class GraduatedRendererSizeWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("GraduatedRendererSize")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)

        self.legend = QListWidget(self)
        self.legend_dock = QDockWidget("POP_CLASS size classes", self)
        self.legend_dock.setWidget(self.legend)
        self.legend_dock.setMinimumWidth(245)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.legend_dock)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.legend.addItem("Preparing USA cities sample data...")

        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/usa_cities.zip",
                zip_name="usa_cities.zip",
                target_folder="usa_cities",
                required_file="usa_cities.shp",
                title="GraduatedRendererSize",
            )
            self.viewer.add_open_street_map_layer()
            points = read_point_records(path)
            attributes = read_dbf_records(path.with_suffix(".dbf"))
            self.create_city_layer(points, attributes)
            self.apply_renderer()
            self.update_legend()
            self.apply_city_extent(points)
            self.statusBar().showMessage("Graduated size renderer applied: POP_CLASS")
        except Exception as error:
            self.legend.clear()
            self.legend.addItem("Graduated size renderer could not be created.")
            self.statusBar().showMessage("Graduated size renderer could not be created.")
            QMessageBox.critical(self, "GraduatedRendererSize", str(error))

    def create_city_layer(
        self,
        points: list[tuple[float, float] | None],
        attributes: list[dict],
    ) -> None:
        city_points = []
        city_attributes = []
        for point, row in zip(points, attributes):
            if point is None or not row:
                continue
            row[SIZE_FIELD] = population_class_size(str(row.get("POP_CLASS", "")))
            city_points.append(point)
            city_attributes.append(row)

        if not city_points:
            raise RuntimeError("No city points could be loaded.")

        layer_index = self.viewer.add_attributed_point_layer(
            "Cities - graduated size by POP_CLASS",
            city_points,
            city_attributes,
            CITY_STYLE,
            source_epsg=4326,
        )
        if layer_index < 0:
            raise RuntimeError("Cities memory layer could not be created.")

    def apply_renderer(self) -> None:
        if not self.viewer.apply_graduated_renderer(
            0,
            SIZE_FIELD,
            ClassificationMethod.EQUAL_INTERVAL,
            6,
            "Plasma",
            color_ramp_mode=ColorRampMode.DISCRETE,
            style_target=SymbolStyleTarget.SIZE_OR_WIDTH,
            start_size=MINIMUM_POINT_SIZE,
            end_size=MAXIMUM_POINT_SIZE,
        ):
            raise RuntimeError("Could not create graduated size renderer from POP_CLASS.")

        renderer = self.viewer.layer_symbol_renderer(0)
        for range_item in renderer.get("ranges", []):
            style = range_item.get("style", {})
            point_size = float(style.get("pointSize", MINIMUM_POINT_SIZE))
            style["pointColor"] = self.with_alpha(
                str(style.get("pointColor", "#D95F35")), 72
            )
            style["lineColor"] = self.with_alpha(
                str(style.get("lineColor", "#8A3A24")), 175
            )
            style["lineWidth"] = min(2.2, max(0.9, point_size * 0.07))
        renderer["defaultStyle"] = CITY_STYLE
        if not self.viewer.set_layer_symbol_renderer(0, renderer):
            raise RuntimeError("Graduated size renderer styles could not be updated.")
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()

    def with_alpha(self, color_name: str, alpha: int) -> str:
        color = QColor(color_name)
        if not color.isValid():
            color = QColor("#D95F35")
        color.setAlpha(alpha)
        return color.name(QColor.NameFormat.HexArgb)

    def update_legend(self) -> None:
        renderer = self.viewer.layer_symbol_renderer(0)
        self.legend.clear()
        for index, range_item in enumerate(renderer.get("ranges", [])):
            if not range_item.get("enabled", True):
                continue
            label = (
                CLASS_LABELS[index]
                if index < len(CLASS_LABELS)
                else str(range_item.get("label", ""))
            )
            item = QListWidgetItem(self.legend_icon(range_item.get("style", {})), label)
            item.setSizeHint(QSize(210, 44))
            self.legend.addItem(item)

    def legend_icon(self, style: dict) -> QIcon:
        pixmap = QPixmap(72, 42)
        pixmap.fill(Qt.GlobalColor.transparent)
        point_size = min(
            MAXIMUM_POINT_SIZE,
            max(MINIMUM_POINT_SIZE, float(style.get("pointSize", MINIMUM_POINT_SIZE))),
        )

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(
            QPen(
                QColor(str(style.get("lineColor", "#AF8A3A24"))),
                max(1.0, float(style.get("lineWidth", 0.9))),
            )
        )
        painter.setBrush(QColor(str(style.get("pointColor", "#48D95F35"))))
        painter.drawEllipse(
            36.0 - point_size / 2.0,
            21.0 - point_size / 2.0,
            point_size,
            point_size,
        )
        painter.end()
        return QIcon(pixmap)

    def apply_city_extent(self, points: list[tuple[float, float] | None]) -> None:
        valid_points = [point for point in points if point is not None]
        minimum_x = min(point[0] for point in valid_points)
        minimum_y = min(point[1] for point in valid_points)
        maximum_x = max(point[0] for point in valid_points)
        maximum_y = max(point[1] for point in valid_points)
        transformer = CoordinateSystemFactory()
        projected_minimum = transformer.transform_point(4326, 3857, minimum_x, minimum_y)
        projected_maximum = transformer.transform_point(4326, 3857, maximum_x, maximum_y)
        width = projected_maximum[0] - projected_minimum[0]
        height = projected_maximum[1] - projected_minimum[1]
        padding_x = max(500000.0, width * 0.12)
        padding_y = max(500000.0, height * 0.12)
        self.viewer.set_view_extent(
            Extent(
                projected_minimum[0] - padding_x,
                projected_minimum[1] - padding_y,
                projected_maximum[0] + padding_x,
                projected_maximum[1] + padding_y,
            )
        )

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GraduatedRendererSize")
    app.setWindowIcon(application_icon())
    window = GraduatedRendererSizeWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
