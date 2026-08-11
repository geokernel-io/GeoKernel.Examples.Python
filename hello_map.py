import sys
from importlib.resources import files
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QToolBar
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file

class HelloMapWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = files("geokernel").joinpath("assets/images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()

        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("HelloMap")
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_navigation_toolbar()

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

    def activate_zoom_box(self) -> None:
        self.viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            world_layer = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="HelloMap",
            )
            self.viewer.add_layer(str(world_layer))
            self.viewer.full_extent()
        except Exception as error:
            QMessageBox.critical(self, "HelloMap", f"World layer could not be loaded:\n\n{error}")

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("HelloMap")
    app.setWindowIcon(app_icon)
    window = HelloMapWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
