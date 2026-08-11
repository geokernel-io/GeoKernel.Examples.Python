import sys
from importlib.resources import files
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QToolBar, QVBoxLayout, QWidget
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file

PROJECT_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/andalucia.zip"

class ProjectWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = files("geokernel").joinpath("assets/images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.progress_label = QLabel("Ready", self)
        self.progress_bar = QProgressBar(self)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("Project")
        self.resize(1200, 800)
        self.create_layout()
        self.create_navigation_toolbar()

    def create_layout(self) -> None:
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.viewer_widget, 1)
        progress_widget = QWidget(central_widget)
        progress_layout = QHBoxLayout(progress_widget)
        progress_layout.setContentsMargins(8, 4, 8, 4)
        progress_layout.setSpacing(8)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumWidth(260)
        progress_layout.addWidget(self.progress_label, 1)
        progress_layout.addWidget(self.progress_bar)
        layout.addWidget(progress_widget)
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

    def activate_zoom_box(self) -> None:
        self.viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.load_project()

    def load_project(self) -> None:
        self.progress_bar.setValue(0)
        self.progress_label.setText("Preparing Andalucia sample data...")
        self.app.processEvents()
        try:
            project_path = ensure_sample_file(
                app=self.app,
                zip_url=PROJECT_URL,
                zip_name="andalucia.zip",
                target_folder="andalucia",
                required_file="andalucia.geokernel",
                title="Project",
            )
            self.progress_bar.setValue(65)
            self.progress_label.setText("Loading andalucia.geokernel...")
            self.app.processEvents()
            if not self.viewer.open_project(project_path):
                raise RuntimeError(f"Project could not be loaded: {project_path}")
            self.progress_bar.setValue(100)
            self.progress_label.setText("Rendering map...")
            self.viewer.process_events()
            self.viewer_widget.update()
            QTimer.singleShot(900, self.finish_progress)
        except Exception as error:
            self.progress_bar.setValue(0)
            self.progress_label.setText("Project could not be loaded.")
            QMessageBox.critical(self, "Project", str(error))

    def finish_progress(self) -> None:
        self.progress_label.setText("Project loaded.")
        self.progress_bar.setValue(0)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("Project")
    app.setWindowIcon(app_icon)
    window = ProjectWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
