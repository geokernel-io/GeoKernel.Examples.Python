import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon

MODES = (
    ("Point", "Drawn Point", ShapeType.POINT, ViewerTool.ADD_POINT),
    ("Polyline", "Drawn Polyline", ShapeType.POLYLINE, ViewerTool.ADD_POLYLINE),
    ("Polygon", "Drawn Polygon", ShapeType.POLYGON, ViewerTool.ADD_POLYGON),
)

class WktWriteWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.transformer = CoordinateSystemFactory()
        self.viewer = Viewer()
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_indexes: dict[str, int] = {}
        self.drawing_sketch = False
        self.initialized = False

        self.setWindowTitle("WktWrite")
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
        input_layout.addWidget(QLabel("Geometry:", input_bar))

        self.mode_combo = QComboBox(input_bar)
        self.mode_combo.addItems(mode[0] for mode in MODES)
        self.mode_combo.currentIndexChanged.connect(self.change_mode)
        input_layout.addWidget(self.mode_combo)

        clear_button = QPushButton("Clear", input_bar)
        clear_button.clicked.connect(self.clear_geometries)
        input_layout.addWidget(clear_button)

        self.hint_label = QLabel(input_bar)
        input_layout.addWidget(self.hint_label, 1)

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(content)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(450)
        content_layout.addWidget(self.details_view)

        root_layout.addWidget(input_bar)
        root_layout.addWidget(content, 1)
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
            self.create_edit_layers()
            self.activate_selected_mode()
            self.viewer.set_view_extent(self.initial_view_extent())
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("WktWrite initialization failed.")

    def create_edit_layers(self) -> None:
        styles = (
            {"pointColor": "#D95D39", "lineColor": "#8C321D", "pointSize": 13.0},
            {"lineColor": "#E4572E", "lineWidth": 3.4},
            {
                "fillColor": "#88D18A",
                "fillOpacity": 128,
                "lineColor": "#1F7A4D",
                "lineWidth": 2.4,
            },
        )
        for mode, style in zip(MODES, styles):
            if self.viewer.add_empty_vector_layer(mode[1], mode[2], style) < 0:
                raise RuntimeError(f"{mode[1]} layer could not be created.")

        self.resolve_layer_indexes()
        for layer_name, index in self.layer_indexes.items():
            if not self.viewer.set_layer_coordinate_system_preset(
                index, CoordinateSystemPreset.WGS84
            ):
                raise RuntimeError(f"{layer_name} CRS could not be set to EPSG:4326.")

    def resolve_layer_indexes(self) -> None:
        names = {mode[1] for mode in MODES}
        self.layer_indexes = {
            str(layer.get("name", "")): index
            for index, layer in enumerate(self.viewer.layers_info())
            if str(layer.get("name", "")) in names
        }
        if len(self.layer_indexes) != len(MODES):
            raise RuntimeError("Editable WKT layers could not be resolved.")

    def active_mode(self) -> tuple:
        return MODES[self.mode_combo.currentIndex()]

    def active_layer_index(self) -> int:
        return self.layer_indexes.get(self.active_mode()[1], -1)

    def activate_selected_mode(self) -> None:
        mode = self.active_mode()
        index = self.active_layer_index()
        if index < 0:
            return
        if not self.viewer.is_layer_editing(index) and not self.viewer.begin_edit_layer(
            index
        ):
            raise RuntimeError(f"{mode[1]} could not enter edit mode.")
        if not self.viewer.set_active_edit_layer_index(index):
            raise RuntimeError(f"{mode[1]} could not be activated.")

        self.viewer.set_tool(mode[3])
        help_text = self.help_text(self.mode_combo.currentIndex())
        self.hint_label.setText(help_text)
        self.statusBar().showMessage(help_text)
        if self.viewer.layer_feature_count(index) == 0:
            self.show_empty_details()

    def change_mode(self, index: int) -> None:
        self.drawing_sketch = False
        if self.initialized:
            self.clear_geometries()

    def clear_geometries(self) -> None:
        if not self.initialized:
            return
        self.drawing_sketch = False
        for index in self.layer_indexes.values():
            if self.viewer.is_layer_editing(index):
                self.viewer.rollback_edit_layer(index)
        self.viewer.invalidate_render_cache(False, True)
        self.viewer.refresh_layers()
        self.activate_selected_mode()
        self.statusBar().showMessage("Drawn geometries cleared.")

    def handle_map_mouse_press(self) -> None:
        if not self.initialized or self.viewer.get_tool() != self.active_mode()[3]:
            return
        mode_index = self.mode_combo.currentIndex()
        if mode_index != 0 and self.drawing_sketch:
            return

        layer_index = self.active_layer_index()
        if self.viewer.layer_feature_count(layer_index) > 0:
            self.viewer.rollback_edit_layer(layer_index)
            self.viewer.begin_edit_layer(layer_index)
            self.viewer.set_active_edit_layer_index(layer_index)
            self.viewer.set_tool(self.active_mode()[3])
            self.viewer.invalidate_render_cache(False, True)
            self.viewer.refresh_layers()
        if mode_index != 0:
            self.drawing_sketch = True

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.MAP_MOUSE_DOWN:
            self.handle_map_mouse_press()
            return

        if event.event_type != ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            return
        layer_index = self.active_layer_index()
        if layer_index < 0 or self.viewer.layer_feature_count(layer_index) == 0:
            return
        self.drawing_sketch = False
        self.write_active_wkt()

    def write_active_wkt(self) -> None:
        layer_index = self.active_layer_index()
        wkt = self.viewer.write_layer_last_shape_wkt(layer_index)
        if not wkt:
            self.show_empty_details()
            self.statusBar().showMessage("No drawn geometry is available.")
            return

        api_name = self.api_name(self.mode_combo.currentIndex())
        self.details_view.setPlainText(
            "\n".join(
                (
                    "WktWrite sample",
                    "",
                    "API",
                    api_name,
                    "",
                    "Selected geometry",
                    self.active_mode()[0],
                    f"Layer feature count: {self.viewer.layer_feature_count(layer_index)}",
                    "",
                    "Output WKT",
                    wkt,
                    "",
                    "Workflow",
                    "1. Choose geometry type.",
                    "2. Draw geometry on map.",
                    "3. WKT is written automatically when drawing finishes.",
                )
            )
        )
        self.statusBar().showMessage(f"{api_name} wrote the drawn geometry.")

    def show_empty_details(self) -> None:
        self.details_view.setPlainText(
            f"{self.api_name(self.mode_combo.currentIndex())}\n\n"
            "Draw a geometry first. WKT will be written automatically."
        )

    def api_name(self, mode_index: int) -> str:
        return (
            "GisWktWriter::writePoint(shape)",
            "GisWktWriter::writePolyline(shape)",
            "GisWktWriter::writePolygon(shape)",
        )[mode_index]

    def help_text(self, mode_index: int) -> str:
        return (
            "Click on the map to draw a point. WKT is written automatically.",
            "Click line vertices, then press Enter or double-click to finish.",
            "Click polygon vertices, then press Enter or double-click to finish.",
        )[mode_index]

    def initial_view_extent(self) -> Extent:
        minimum = self.transformer.transform_point(4326, 3857, -124.8, 32.0)
        maximum = self.transformer.transform_point(4326, 3857, -114.0, 42.5)
        return Extent(minimum[0], minimum[1], maximum[0], maximum[1])

    def closeEvent(self, event) -> None:
        try:
            for index in self.layer_indexes.values():
                if self.viewer.is_layer_editing(index):
                    self.viewer.rollback_edit_layer(index)
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WktWrite")
    app.setWindowIcon(application_icon())
    window = WktWriteWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
