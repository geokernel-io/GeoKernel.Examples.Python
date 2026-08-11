import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file

class LayerExtentWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("LayerExtent")
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/california.zip",
                zip_name="california.zip",
                target_folder="california",
                required_file="california.shp",
                title="LayerExtent",
            )
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_name(0, "California")
            self.viewer.set_layer_style(0, {"fillColor": "#D8E5E1", "fillOpacity": 210, "lineColor": "#6F8883", "lineWidth": 0.9})
            self.add_extent_rectangle()
            self.viewer.refresh_layers()
            self.viewer.full_extent()
        except Exception as error:
            QMessageBox.critical(self, "LayerExtent", f"Layer extent could not be created:\n\n{error}")

    def add_extent_rectangle(self) -> None:
        extent = self.viewer.layer_projected_extent(0)
        if extent is None:
            raise RuntimeError("Layer extent is empty.")
        rectangle = [[
            (extent.x_min, extent.y_min), (extent.x_max, extent.y_min),
            (extent.x_max, extent.y_max), (extent.x_min, extent.y_max),
            (extent.x_min, extent.y_min),
        ]]
        result = self.viewer.add_polygon_layer("Layer Extent", rectangle, {"fillColor": "#FFFFFF", "fillOpacity": 0, "lineColor": "#E2453D", "lineWidth": 2.2})
        if result < 0:
            raise RuntimeError("Layer extent rectangle could not be created.")

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("LayerExtent")
    app.setWindowIcon(icon)
    window = LayerExtentWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
