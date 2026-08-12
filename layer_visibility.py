import sys
from importlib.resources import files
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QListWidget, QMainWindow, QMessageBox, QPushButton, QToolBar, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import ensure_sample_file

INITIAL_EXTENT = Extent(-151.2, 16.4, -41.6, 55.6)

SAMPLES = (
    ("World", "world_4326.zip", "world_4326", "world_4326.shp", {"fillColor": "#D8E5E1", "fillOpacity": 220, "lineColor": "#7B918D", "lineWidth": 0.8}),
    ("States", "usa_states.zip", "usa_states", "usa_states.shp", {"fillColor": "#A9C8DB", "fillOpacity": 115, "lineColor": "#356780", "lineWidth": 1.2}),
    ("Cities", "usa_cities.zip", "usa_cities", "usa_cities.shp", {"pointColor": "#D95D39", "pointSize": 7.0}),
)

class LayerVisibilityWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = files("geokernel").joinpath("assets/images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_list = QListWidget(self)
        self.visibility_button = QPushButton("Change Visibility", self)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("LayerVisibility")
        self.resize(1200, 800)
        self.create_layout()
        self.create_navigation_toolbar()
        self.connect_signals()

    def create_layout(self) -> None:
        central_widget = QWidget(self)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        side_panel = QWidget(central_widget)
        side_panel.setFixedWidth(220)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(8, 8, 8, 8)
        side_layout.setSpacing(8)
        side_layout.addWidget(self.layer_list, 1)
        side_layout.addWidget(self.visibility_button)
        main_layout.addWidget(side_panel)
        main_layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central_widget)

    def create_navigation_toolbar(self) -> None:
        self.toolbar = QToolBar("Navigation", self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(32, 32))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(self.toolbar)
        self.add_tool("ZoomIn.svg", "Zoom In", self.viewer.zoom_in)
        self.add_tool("ZoomOut.svg", "Zoom Out", self.viewer.zoom_out)
        self.add_tool("FullExtent.svg", "Full Extent", self.viewer.full_extent)
        self.toolbar.addSeparator()
        self.add_tool("RectangularZoom.svg", "Zoom Rect", self.activate_zoom_box)
        self.add_tool("Pan.svg", "Pan", self.activate_pan)

    def add_tool(self, icon_name: str, text: str, callback) -> QAction:
        action = QAction(QIcon(str(self.icon_dir.joinpath(icon_name))), text, self)
        action.setToolTip(text)
        action.triggered.connect(callback)
        self.toolbar.addAction(action)
        return action

    def connect_signals(self) -> None:
        self.layer_list.currentRowChanged.connect(self.update_visibility_button)
        self.visibility_button.clicked.connect(self.toggle_selected_layer)

    def activate_zoom_box(self) -> None:
        self.viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def layer_is_visible(self, index: int) -> bool:
        return bool(self.viewer.layer_info(index).get("visible", True))

    def refresh_layer_list(self, selected_index: int = -1) -> None:
        self.layer_list.clear()
        layer_count = self.viewer.layer_count()
        for index in range(layer_count):
            marker = "[x]" if self.layer_is_visible(index) else "[ ]"
            self.layer_list.addItem(f"{marker} {self.viewer.layer_display_text(index)}")
        if layer_count:
            row = selected_index if 0 <= selected_index < layer_count else 0
            self.layer_list.setCurrentRow(row)
        self.update_visibility_button()

    def update_visibility_button(self, selected_index: int = -1) -> None:
        index = self.layer_list.currentRow()
        if index < 0:
            self.visibility_button.setEnabled(False)
            self.visibility_button.setText("Change Visibility")
            return
        self.visibility_button.setEnabled(True)
        state = "Hide" if self.layer_is_visible(index) else "Show"
        self.visibility_button.setText(f"Change Visibility: {state}")

    def toggle_selected_layer(self) -> None:
        index = self.layer_list.currentRow()
        if index < 0:
            return
        self.viewer.set_layer_visible(index, not self.layer_is_visible(index))
        self.refresh_layer_list(index)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.load_layers()

    def load_layers(self) -> None:
        try:
            for name, zip_name, target_folder, required_file, style in SAMPLES:
                self.load_layer(name, zip_name, target_folder, required_file, style)
            self.viewer.refresh_layers()
            self.refresh_layer_list()
            self.viewer.set_view_extent(INITIAL_EXTENT)
        except Exception as error:
            QMessageBox.critical(self, "LayerVisibility", f"Layers could not be loaded:\n\n{error}")

    def load_layer(self, name: str, zip_name: str, target_folder: str, required_file: str, style: dict[str, object]) -> None:
        path = ensure_sample_file(
            app=self.app,
            zip_url=f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{zip_name}",
            zip_name=zip_name,
            target_folder=target_folder,
            required_file=required_file,
            title="LayerVisibility",
        )
        self.viewer.add_layer(str(path))
        self.viewer.set_layer_name(0, name)
        self.viewer.set_layer_style(0, style)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("LayerVisibility")
    app.setWindowIcon(app_icon)
    window = LayerVisibilityWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
