import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

INITIAL_EXTENT = Extent(-151.2, 16.4, -41.6, 55.6)
LAYER_DEFINITIONS = (
    (
        "World",
        "world_4326.zip",
        "world_4326",
        "world_4326.shp",
        {
            "fillColor": "#D8E5E1",
            "fillOpacity": 225,
            "lineColor": "#7B918D",
            "lineWidth": 0.8,
        },
        0.0,
        11.0,
    ),
    (
        "States",
        "usa_states.zip",
        "usa_states",
        "usa_states.shp",
        {
            "fillColor": "#A9C8DB",
            "fillOpacity": 135,
            "lineColor": "#356780",
            "lineWidth": 1.1,
        },
        5.0,
        45.0,
    ),
    (
        "Cities",
        "usa_cities.zip",
        "usa_cities",
        "usa_cities.shp",
        {
            "pointColor": "#D95D39",
            "lineColor": "#873A24",
            "pointSize": 7.0,
            "lineWidth": 1.0,
        },
        28.0,
        0.0,
    ),
)

class ScaleBasedLayerVisibilityWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.current_scale = 0.0

        self.setWindowTitle("ScaleBasedLayerVisibility")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_layout()
        self.viewer.set_event_callback(self.on_viewer_event)

    def create_layout(self) -> None:
        central_widget = QWidget(self)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        side_panel = QWidget(central_widget)
        side_panel.setFixedWidth(280)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(8, 8, 8, 8)
        side_layout.setSpacing(8)

        self.scale_label = QLabel("Current scale: - px/map unit", side_panel)
        self.layer_list = QListWidget(side_panel)
        side_layout.addWidget(self.scale_label)
        side_layout.addWidget(QLabel("Visible scale ranges: [min - max]", side_panel))
        side_layout.addWidget(self.layer_list, 1)

        main_layout.addWidget(side_panel)
        main_layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central_widget)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.layer_list.addItem("Preparing sample data...")

        try:
            paths = []
            for name, zip_name, folder, required_file, _, _, _ in LAYER_DEFINITIONS:
                paths.append(
                    ensure_sample_file(
                        app=self.app,
                        zip_url=f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{zip_name}",
                        zip_name=zip_name,
                        target_folder=folder,
                        required_file=required_file,
                        title="ScaleBasedLayerVisibility",
                    )
                )

            for definition, path in zip(LAYER_DEFINITIONS, paths):
                name, _, _, _, style, minimum_scale, maximum_scale = definition
                self.add_layer(name, path, style, minimum_scale, maximum_scale)

            self.viewer.refresh_layers()
            self.viewer.set_view_extent(INITIAL_EXTENT)
            self.refresh_ui()
            self.statusBar().showMessage("Scale-based layer visibility is ready.")
        except Exception as error:
            self.refresh_ui()
            self.statusBar().showMessage("Scale-based layers could not be loaded.")
            QMessageBox.critical(self, "ScaleBasedLayerVisibility", str(error))

    def add_layer(
        self,
        name: str,
        path,
        style: dict,
        minimum_scale: float,
        maximum_scale: float,
    ) -> None:
        self.viewer.add_layer(str(path))
        self.viewer.set_layer_name(0, name)
        self.viewer.set_layer_style(0, style)
        if not self.viewer.set_layer_visible_scale_range(
            0, minimum_scale, maximum_scale
        ):
            raise RuntimeError(f"Visible scale range could not be set for {name}.")

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.ZOOM_CHANGED:
            self.current_scale = float(event.double_value)
        if event.event_type in {
            ViewerEventType.ZOOM_CHANGED,
            ViewerEventType.VISIBLE_EXTENT_CHANGED,
            ViewerEventType.LAYERS_CHANGED,
            ViewerEventType.LAYER_ADDED,
            ViewerEventType.LAYER_REMOVED,
            ViewerEventType.LAYER_VISIBILITY_CHANGED,
        }:
            QTimer.singleShot(0, self.refresh_ui)

    def refresh_ui(self) -> None:
        self.scale_label.setText(
            f"Current scale: {self.scale_text(self.current_scale)} px/map unit"
        )

        self.layer_list.clear()
        for layer in self.viewer.layers_info():
            minimum_scale = float(layer.get("minVisibleScale", 0.0))
            maximum_scale = float(layer.get("maxVisibleScale", 0.0))
            visible = self.is_visible_at_scale(layer, self.current_scale)
            name = str(layer.get("displayText", layer.get("name", "Layer")))
            self.layer_list.addItem(
                f"{'[x]' if visible else '[ ]'}  "
                f"[{self.scale_text(minimum_scale)} - {self.scale_text(maximum_scale)}]  "
                f"{name}"
            )

    @staticmethod
    def is_visible_at_scale(layer: dict, scale: float) -> bool:
        if not bool(layer.get("visible", True)):
            return False
        minimum_scale = float(layer.get("minVisibleScale", 0.0))
        maximum_scale = float(layer.get("maxVisibleScale", 0.0))
        if minimum_scale > 0.0 and scale < minimum_scale:
            return False
        if maximum_scale > 0.0 and scale > maximum_scale:
            return False
        return True

    @staticmethod
    def scale_text(value: float) -> str:
        if value <= 0.0:
            return "-"
        return f"{value:.2f}" if value < 10.0 else f"{value:.0f}"

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ScaleBasedLayerVisibility")
    app.setWindowIcon(application_icon())
    window = ScaleBasedLayerVisibilityWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
