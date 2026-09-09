import json
import sys
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon

class MousePressFilter(QObject):
    def __init__(self, window: "GeoJsonWriteWindow") -> None:
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.window.handle_map_mouse_press()
        return super().eventFilter(watched, event)

class GeoJsonWriteWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.transformer = CoordinateSystemFactory()
        self.viewer = Viewer()
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.polygon_layer_index = -1
        self.drawing_sketch = False
        self.initialized = False

        self.mouse_filter = MousePressFilter(self)
        self.viewer_widget.installEventFilter(self.mouse_filter)

        self.setWindowTitle("GeoJsonWrite")
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

        clear_button = QPushButton("Clear", input_bar)
        clear_button.clicked.connect(self.clear_polygon)
        input_layout.addWidget(clear_button)
        input_layout.addWidget(
            QLabel(
                "Click polygon vertices, then press Enter or double-click to "
                "finish. GeoJSON is written automatically.",
                input_bar,
            ),
            1,
        )

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(content)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(430)
        content_layout.addWidget(self.details_view)

        root_layout.addWidget(input_bar)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)
        self.show_empty_details()

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

            self.polygon_layer_index = self.viewer.add_empty_vector_layer(
                "Drawn Polygon",
                ShapeType.POLYGON,
                {
                    "fillColor": "#88D18A",
                    "fillOpacity": 128,
                    "lineColor": "#1F7A4D",
                    "lineWidth": 2.4,
                },
            )
            if self.polygon_layer_index < 0:
                raise RuntimeError("Drawn Polygon layer could not be created.")
            if not self.viewer.set_layer_coordinate_system_preset(
                self.polygon_layer_index,
                CoordinateSystemPreset.WGS84,
            ):
                raise RuntimeError("Drawn Polygon CRS could not be set to EPSG:4326.")

            self.activate_polygon_tool()
            self.viewer.set_view_extent(self.initial_view_extent())
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("GeoJsonWrite initialization failed.")

    def activate_polygon_tool(self) -> None:
        if self.polygon_layer_index < 0:
            return
        if not self.viewer.is_layer_editing(self.polygon_layer_index):
            if not self.viewer.begin_edit_layer(self.polygon_layer_index):
                raise RuntimeError("Polygon layer could not enter edit mode.")
        if not self.viewer.set_active_edit_layer_index(self.polygon_layer_index):
            raise RuntimeError("Polygon layer could not be activated.")
        self.viewer.set_tool(ViewerTool.ADD_POLYGON)
        self.statusBar().showMessage(
            "Add Polygon active. Finish with Enter or double-click."
        )

    def clear_polygon(self) -> None:
        if self.polygon_layer_index < 0:
            return
        self.drawing_sketch = False
        if self.viewer.is_layer_editing(self.polygon_layer_index):
            self.viewer.rollback_edit_layer(self.polygon_layer_index)
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.show_empty_details()
        self.activate_polygon_tool()
        self.statusBar().showMessage("Polygon cleared.")

    def handle_map_mouse_press(self) -> None:
        if (
            not self.initialized
            or self.viewer.get_tool() != ViewerTool.ADD_POLYGON
            or self.drawing_sketch
        ):
            return

        if self.viewer.layer_feature_count(self.polygon_layer_index) > 0:
            self.clear_polygon()
        self.drawing_sketch = True

    def on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            return
        if self.polygon_layer_index < 0:
            return
        if self.viewer.layer_feature_count(self.polygon_layer_index) == 0:
            return

        self.drawing_sketch = False
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.write_geojson()

    def write_geojson(self) -> None:
        geojson = self.viewer.write_layer_last_shape_geojson(self.polygon_layer_index)
        if not geojson:
            self.show_empty_details()
            return

        document = json.loads(geojson)
        rings = document.get("coordinates", [])
        points = [point for ring in rings for point in ring]
        minimum_x = min(point[0] for point in points)
        minimum_y = min(point[1] for point in points)
        maximum_x = max(point[0] for point in points)
        maximum_y = max(point[1] for point in points)

        self.details_view.setPlainText(
            "\n".join(
                (
                    "GeoJsonWrite sample",
                    "",
                    "API",
                    "GisGeoJsonWriter::writePolygonString(shape)",
                    "",
                    "Drawn polygon",
                    f"Rings: {len(rings)}",
                    f"Vertices: {len(points)}",
                    "Lon/lat extent: "
                    f"({minimum_x:.6f}, {minimum_y:.6f}) - "
                    f"({maximum_x:.6f}, {maximum_y:.6f})",
                    "",
                    "Output GeoJSON",
                    geojson,
                    "",
                    "Workflow",
                    "1. Click polygon vertices on the map.",
                    "2. Press Enter or double-click to finish.",
                    "3. GeoJSON is written automatically.",
                )
            )
        )
        self.statusBar().showMessage(
            "GisGeoJsonWriter::writePolygonString wrote polygon GeoJSON."
        )

    def show_empty_details(self) -> None:
        self.details_view.setPlainText(
            "GisGeoJsonWriter::writePolygonString(shape)\n\n"
            "Draw a polygon on the map. The GeoJSON string will appear here."
        )

    def initial_view_extent(self) -> Extent:
        minimum = self.transformer.transform_point(4326, 3857, -124.8, 32.0)
        maximum = self.transformer.transform_point(4326, 3857, -114.0, 42.5)
        return Extent(minimum[0], minimum[1], maximum[0], maximum[1])

    def closeEvent(self, event) -> None:
        try:
            if self.polygon_layer_index >= 0 and self.viewer.is_layer_editing(
                self.polygon_layer_index
            ):
                self.viewer.rollback_edit_layer(self.polygon_layer_index)
        except Exception:
            pass
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GeoJsonWrite")
    app.setWindowIcon(application_icon())
    window = GeoJsonWriteWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
