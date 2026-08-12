import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QToolBar
from geokernel import OverlayAnchor, Viewer, ViewerTool
from common import ensure_sample_file

SAMPLE_DATA_BASE_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/"

class MeasureWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.local_icon_dir = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_scale_bar_anchor(OverlayAnchor.BOTTOM_LEFT)
        self.viewer.set_scale_bar_visible(True)
        self.viewer_widget = self.viewer.qt_widget()
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("Measure")
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_measure_toolbar()

    def create_measure_toolbar(self) -> None:
        self.toolbar = QToolBar("Measure", self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(32, 32))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(self.toolbar)
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.pan_action = self.add_tool("Pan.png", "Pan", self.activate_pan, True)
        self.distance_action = self.add_tool("measure-distance.png", "Distance", self.activate_distance, True)
        self.area_action = self.add_tool("measure-area.png", "Area", self.activate_area, True)
        self.tool_group.addAction(self.pan_action)
        self.tool_group.addAction(self.distance_action)
        self.tool_group.addAction(self.area_action)
        self.toolbar.addSeparator()
        self.add_tool("Delete.png", "Clear", self.viewer.clear_measure)
        self.add_tool("FullExtent.png", "Full Extent", self.viewer.full_extent)
        self.pan_action.setChecked(True)

    def add_tool(self, icon_name: str, text: str, callback, checkable: bool = False) -> QAction:
        icon_path = self.local_icon_dir / icon_name
        action = QAction(QIcon(str(icon_path)), text, self)
        action.setToolTip(text)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        self.toolbar.addAction(action)
        return action

    def activate_pan(self) -> None:
        self.viewer.set_measure_tool_active(False)
        self.viewer.set_tool(ViewerTool.PAN)

    def activate_distance(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.start_measure_distance()

    def activate_area(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.start_measure_area()

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            self.load_layer("world_4326.zip", "world_4326", "world_4326.shp")
            self.load_layer("world_cities_4326.zip", "world_cities_4326", "world_cities_4326.shp")
            self.viewer.full_extent()
        except Exception as error:
            QMessageBox.critical(self, "Measure", f"Layers could not be loaded:\n\n{error}")

    def load_layer(self, zip_name: str, target_folder: str, required_file: str) -> None:
        path = ensure_sample_file(
            app=self.app,
            zip_url=f"{SAMPLE_DATA_BASE_URL}{zip_name}",
            zip_name=zip_name,
            target_folder=target_folder,
            required_file=required_file,
            title="Measure",
        )
        self.viewer.add_layer(str(path))

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("Measure")
    app.setWindowIcon(app_icon)
    window = MeasureWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
