import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QToolBar
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file

SAMPLE_DATA_BASE_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/"

SAMPLES = (
    ("World raster", "world_8km_png.zip", "world_8km_png", "world_8km.png", None),
    (
        "Countries",
        "world_4326.zip",
        "world_4326",
        "world_4326.shp",
        {"fillColor": "#35475B", "fillOpacity": 172, "lineColor": "#B7E8FF", "lineWidth": 0.85},
    ),
    (
        "Cities",
        "world_cities_4326.zip",
        "world_cities_4326",
        "world_cities_4326.shp",
        {"pointColor": "#1D8FC7", "lineColor": "#74C3E8", "lineWidth": 0.9, "pointSize": 4.2},
    ),
)

class AddLayersWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = Path(__file__).resolve().parent / "images"
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("AddLayers")
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_navigation_toolbar()

    def create_navigation_toolbar(self) -> None:
        self.toolbar = QToolBar("Navigation", self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(32, 32))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(self.toolbar)
        self.add_tool("ZoomIn.png", "Zoom In", self.viewer.zoom_in)
        self.add_tool("ZoomOut.png", "Zoom Out", self.viewer.zoom_out)
        self.add_tool("FullExtent.png", "Full Extent", self.viewer.full_extent)
        self.toolbar.addSeparator()
        self.add_tool("RectangularZoom.png", "Zoom Rect", self.activate_zoom_box)
        self.add_tool("Pan.png", "Pan", self.activate_pan)

    def add_tool(self, icon_name: str, text: str, callback) -> QAction:
        action = QAction(QIcon(str(self.icon_dir.joinpath(icon_name))), text, self)
        action.setToolTip(text)
        action.triggered.connect(callback)
        self.toolbar.addAction(action)
        return action

    def activate_zoom_box(self) -> None:
        self.viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            self.viewer.clear_layers()
            for name, zip_name, target_folder, required_file, style in SAMPLES:
                self.load_layer(name, zip_name, target_folder, required_file, style)
            self.viewer.refresh_layers()
            self.viewer.full_extent()
        except Exception as error:
            QMessageBox.critical(self, "AddLayers", f"Layers could not be loaded:\n\n{error}")

    def load_layer(
        self,
        name: str,
        zip_name: str,
        target_folder: str,
        required_file: str,
        style: dict[str, object] | None,
    ) -> None:
        path = ensure_sample_file(
            app=self.app,
            zip_url=f"{SAMPLE_DATA_BASE_URL}{zip_name}",
            zip_name=zip_name,
            target_folder=target_folder,
            required_file=required_file,
            title="AddLayers",
        )
        self.viewer.add_layer(str(path))
        self.viewer.set_layer_name(0, name)
        if style is not None:
            self.viewer.set_layer_style(0, style)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("AddLayers")
    app.setWindowIcon(app_icon)
    window = AddLayersWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
