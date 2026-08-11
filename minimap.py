import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from geokernel import OverlayAnchor, Viewer, ViewerTool
from common import ensure_sample_file

class MinimapWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_mini_map_anchor(OverlayAnchor.TOP_RIGHT)
        self.viewer.set_mini_map_visible(True)
        self.viewer_widget = self.viewer.qt_widget()
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("Minimap")
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)

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
                title="Minimap",
            )
            self.viewer.add_layer(str(world_layer))
            self.viewer.full_extent()
        except Exception as error:
            QMessageBox.critical(self, "Minimap", f"World layer could not be loaded:\n\n{error}")

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("Minimap")
    app.setWindowIcon(app_icon)
    window = MinimapWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
