import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QToolBar
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file

FILL_COLORS = ("#D8E5E1", "#D9C7A5", "#C7D7EA", "#D7C5DE")
OUTLINE_COLORS = ("#6F8883", "#A24A3D", "#356780", "#6F4D8C")
OPACITIES = (210, 160, 110, 235)

class LayerRefreshWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.fill_index = self.outline_index = self.opacity_index = 0
        self.style = {"fillColor": FILL_COLORS[0], "fillOpacity": OPACITIES[0], "lineColor": OUTLINE_COLORS[0], "lineWidth": 0.9}
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("LayerRefresh")
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Layer Refresh", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.fill_action = toolbar.addAction("Change Fill")
        self.outline_action = toolbar.addAction("Change Outline")
        self.opacity_action = toolbar.addAction("Change Opacity")
        toolbar.addSeparator()
        self.refresh_action = toolbar.addAction("Refresh Layer")
        self.actions = (self.fill_action, self.outline_action, self.opacity_action, self.refresh_action)
        for action in self.actions:
            action.setEnabled(False)
        self.fill_action.triggered.connect(self.change_fill)
        self.outline_action.triggered.connect(self.change_outline)
        self.opacity_action.triggered.connect(self.change_opacity)
        self.refresh_action.triggered.connect(self.viewer.refresh_layers)

    def change_fill(self) -> None:
        self.fill_index = (self.fill_index + 1) % len(FILL_COLORS)
        self.style["fillColor"] = FILL_COLORS[self.fill_index]
        self.apply_style()

    def change_outline(self) -> None:
        self.outline_index = (self.outline_index + 1) % len(OUTLINE_COLORS)
        self.style["lineColor"] = OUTLINE_COLORS[self.outline_index]
        self.style["lineWidth"] = 0.9 if self.outline_index == 0 else 1.6
        self.apply_style()

    def change_opacity(self) -> None:
        self.opacity_index = (self.opacity_index + 1) % len(OPACITIES)
        self.style["fillOpacity"] = OPACITIES[self.opacity_index]
        self.apply_style()

    def apply_style(self) -> None:
        self.viewer.set_layer_style(0, self.style)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            path = ensure_sample_file(app=self.app, zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/california.zip", zip_name="california.zip", target_folder="california", required_file="california.shp", title="LayerRefresh")
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_name(0, "California")
            self.apply_style()
            for action in self.actions:
                action.setEnabled(True)
            self.viewer.refresh_layers()
            self.viewer.full_extent()
        except Exception as error:
            QMessageBox.critical(self, "LayerRefresh", f"Layer could not be loaded:\n\n{error}")

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("LayerRefresh")
    app.setWindowIcon(icon)
    window = LayerRefreshWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
