import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QMainWindow, QMessageBox, QVBoxLayout, QWidget
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file

PALETTE = ("#BFD6E5", "#C9D5C9", "#D8CDA7", "#D7B79B", "#D6C6E3", "#B9D8C5")

class LayerZoomToWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_combo = QComboBox(self)
        self.layer_combo.setMinimumWidth(220)
        self.layer_combo.addItem("-")
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("Layer ZoomTo")
        self.resize(1200, 800)
        self.create_layout()
        self.layer_combo.currentTextChanged.connect(self.zoom_to_selected_layer)

    def create_layout(self) -> None:
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        top_panel = QWidget(central_widget)
        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(6)
        top_layout.addWidget(self.layer_combo)
        top_layout.addStretch(1)
        layout.addWidget(top_panel)
        layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central_widget)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            first_path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/california_cities.zip",
                zip_name="california_cities.zip",
                target_folder="california_cities",
                required_file="alameda.shp",
                title="LayerZoomTo",
            )
            city_files = sorted(first_path.parent.glob("*.shp"))
            for path in city_files:
                self.layer_combo.addItem(self.display_name(path))
            for index, path in enumerate(city_files):
                self.add_city_layer(path, PALETTE[index % len(PALETTE)])
            self.viewer.refresh_layers()
            self.viewer.full_extent()
        except Exception as error:
            QMessageBox.critical(self, "LayerZoomTo", f"Layers could not be loaded:\n\n{error}")

    def display_name(self, path: Path) -> str:
        return path.stem.replace("_", " ").title()

    def add_city_layer(self, path: Path, fill_color: str) -> None:
        self.viewer.add_layer(str(path))
        self.viewer.set_layer_name(0, self.display_name(path))
        self.viewer.set_layer_style(0, {
            "fillColor": fill_color,
            "fillOpacity": 150,
            "lineColor": "#5F7772",
            "lineWidth": 0.8,
            "showLabels": True,
            "labelFontSize": 12.0,
            "labelAllowOverlap": True,
            "labelAvoidObstacles": False,
            "labelField": "NAME",
            "labelColor": "#000000",
            "labelHaloEnabled": True,
            "labelHaloColor": "#FFFF00",
            "labelHaloWidth": 2.0,
        })

    def layer_index_by_name(self, name: str) -> int:
        layer = self.viewer.layer_info_by_name(name)
        if layer.get("isValid", False):
            return int(layer.get("index", -1))
        return -1

    def zoom_to_selected_layer(self, text: str) -> None:
        if text == "-":
            self.viewer.full_extent()
            return
        index = self.layer_index_by_name(text)
        if index >= 0:
            self.viewer.zoom_to_layer(index)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("LayerZoomTo")
    app.setWindowIcon(app_icon)
    window = LayerZoomToWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
