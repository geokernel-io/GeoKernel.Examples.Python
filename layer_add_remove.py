import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QToolBar
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file

SAMPLES = {
    "World": {
        "zip_name": "world_4326.zip",
        "target_folder": "world_4326",
        "required_file": "world_4326.shp",
        "style": {"fillColor": "#D8E5E1", "fillOpacity": 210, "lineColor": "#7B918D", "lineWidth": 0.8},
    },
    "States": {
        "zip_name": "usa_states.zip",
        "target_folder": "usa_states",
        "required_file": "usa_states.shp",
        "style": {"fillColor": "#A9C8DB", "fillOpacity": 100, "lineColor": "#356780", "lineWidth": 1.2},
    },
    "Cities": {
        "zip_name": "usa_cities.zip",
        "target_folder": "usa_cities",
        "required_file": "usa_cities.shp",
        "style": {"pointColor": "#D95D39", "pointSize": 7.0},
    },
}

class LayerAddRemoveWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("LayerAddRemove")
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        self.toolbar = QToolBar("Layers", self)
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        for name in ("World", "States", "Cities"):
            action = self.toolbar.addAction(f"Add {name}")
            action.setData(name)
            action.triggered.connect(self.handle_add_layer)
        self.toolbar.addSeparator()
        for name in ("World", "States", "Cities"):
            action = self.toolbar.addAction(f"Remove {name}")
            action.setData(name)
            action.triggered.connect(self.handle_remove_layer)
        self.toolbar.addSeparator()
        self.toolbar.addAction("Clear Layers").triggered.connect(self.viewer.clear_layers)

    def handle_add_layer(self) -> None:
        action = self.sender()
        if action is not None:
            self.add_layer(str(action.data()))

    def handle_remove_layer(self) -> None:
        action = self.sender()
        if action is not None:
            self.viewer.remove_layer_by_name(str(action.data()))

    def add_layer(self, name: str) -> bool:
        existing_layer = self.viewer.layer_info_by_name(name)
        if existing_layer.get("isValid", False) and existing_layer.get("index", -1) >= 0:
            return True
        sample = SAMPLES[name]
        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url=(
                    "https://github.com/geokernel-io/GeoKernel.SampleData/"
                    f"releases/download/v1/{sample['zip_name']}"
                ),
                zip_name=str(sample["zip_name"]),
                target_folder=str(sample["target_folder"]),
                required_file=str(sample["required_file"]),
                title="LayerAddRemove",
            )
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_name(0, name)
            self.viewer.set_layer_style(0, sample["style"])
            self.viewer.refresh_layers()
            return True
        except Exception as error:
            QMessageBox.critical(self, "LayerAddRemove", f"Layer could not be loaded:\n{name}\n\n{error}")
            return False

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        if self.add_layer("World"):
            self.viewer.full_extent()

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("LayerAddRemove")
    app.setWindowIcon(app_icon)
    window = LayerAddRemoveWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
