import sys
from datetime import datetime
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QListWidget, QMainWindow, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Viewer, ViewerEventType, ViewerTool
from common import ensure_sample_file

SAMPLES = {
    "World": ("world_4326.zip", "world_4326", "world_4326.shp", {"fillColor": "#D8E5E1", "lineColor": "#607D78"}),
    "States": ("usa_states.zip", "usa_states", "usa_states.shp", {"fillColor": "#A9C8DB", "lineColor": "#356780"}),
    "Cities": ("world_cities_4326.zip", "world_cities_4326", "world_cities_4326.shp", {"pointColor": "#D95D39", "pointSize": 7.0}),
}

class LayerEventsWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_list = QListWidget(self)
        self.log = QTextEdit(self)
        self.log.setReadOnly(True)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("LayerEvents")
        self.resize(1200, 800)
        self.create_layout()
        self.viewer.set_event_callback(self.on_viewer_event)

    def create_layout(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        buttons = QHBoxLayout()
        for name in SAMPLES:
            button = QPushButton(f"Add {name}", root)
            button.setProperty("layerName", name)
            button.clicked.connect(self.add_requested_layer)
            buttons.addWidget(button)
        self.remove_button = QPushButton("Remove Selected", root)
        self.toggle_button = QPushButton("Toggle Visible", root)
        self.up_button = QPushButton("Move Up", root)
        self.down_button = QPushButton("Move Down", root)
        for button in (self.remove_button, self.toggle_button, self.up_button, self.down_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.remove_button.clicked.connect(self.remove_selected)
        self.toggle_button.clicked.connect(self.toggle_selected)
        self.up_button.clicked.connect(self.move_up)
        self.down_button.clicked.connect(self.move_down)
        content = QHBoxLayout()
        content.addWidget(self.viewer_widget, 3)
        side = QVBoxLayout()
        side.addWidget(self.layer_list, 1)
        side.addWidget(self.log, 2)
        content.addLayout(side, 1)
        layout.addLayout(buttons)
        layout.addLayout(content, 1)
        self.setCentralWidget(root)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()

    def append_log(self, message: str) -> None:
        self.log.append(f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  {message}")

    def refresh_layer_list(self, selected: int = -1) -> None:
        self.layer_list.clear()
        for index, info in enumerate(self.viewer.layers_info()):
            visible = "[x]" if info.get("visible", True) else "[ ]"
            self.layer_list.addItem(f"{visible} {self.viewer.layer_display_text(index)}")
        if self.layer_list.count():
            self.layer_list.setCurrentRow(selected if 0 <= selected < self.layer_list.count() else 0)

    def add_requested_layer(self) -> None:
        button = self.sender()
        if button is not None:
            self.add_layer(str(button.property("layerName")))

    def add_layer(self, name: str) -> None:
        info = self.viewer.layer_info_by_name(name)
        if info.get("isValid", False):
            self.append_log(f"Action skipped: {name} already exists")
            return
        zip_name, folder, required_file, style = SAMPLES[name]
        try:
            path = ensure_sample_file(app=self.app, zip_url=f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{zip_name}", zip_name=zip_name, target_folder=folder, required_file=required_file, title="LayerEvents")
            self.append_log(f"Action: addLayerFromPath({path})")
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_name(0, name)
            self.viewer.set_layer_style(0, style)
            self.viewer.refresh_layers()
        except Exception as error:
            QMessageBox.critical(self, "LayerEvents", f"Layer could not be loaded:\n\n{error}")

    def remove_selected(self) -> None:
        index = self.layer_list.currentRow()
        if index >= 0:
            self.append_log(f"Action: removeLayer({self.viewer.layer_display_text(index)})")
            self.viewer.remove_layer(index)

    def toggle_selected(self) -> None:
        index = self.layer_list.currentRow()
        if index >= 0:
            visible = not bool(self.viewer.layer_info(index).get("visible", True))
            self.append_log(f"Action: setLayerVisible({index}, {str(visible).lower()})")
            self.viewer.set_layer_visible(index, visible)

    def move_up(self) -> None:
        self.move_selected(-1)

    def move_down(self) -> None:
        self.move_selected(1)

    def move_selected(self, delta: int) -> None:
        source = self.layer_list.currentRow()
        target = source + delta
        if source >= 0 and 0 <= target < self.viewer.layer_count():
            self.append_log(f"Action: moveLayer({source} -> {target})")
            self.viewer.move_layer(source, target)

    def on_viewer_event(self, event) -> None:
        self.append_log(f"Signal: {event.event_type.name.lower()}({event.int_value}, {event.text})")
        if event.event_type in {ViewerEventType.LAYERS_CHANGED, ViewerEventType.LAYER_ADDED, ViewerEventType.LAYER_REMOVED, ViewerEventType.LAYER_VISIBILITY_CHANGED, ViewerEventType.LAYER_ORDER_CHANGED}:
            self.refresh_layer_list()

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("LayerEvents")
    app.setWindowIcon(icon)
    window = LayerEventsWindow(app)
    window.show()
    window.initialize_viewer()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
