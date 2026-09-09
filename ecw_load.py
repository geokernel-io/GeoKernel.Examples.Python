import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMessageBox, QTextEdit, QToolBar
from geokernel import Viewer, ViewerTool
from common import application_icon, ensure_sample_file

class EcwLoadWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).resolve().parent / "images"
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("EcwLoad")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        self.details_view = QTextEdit(self)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(360)
        details_dock = QDockWidget("ECW metadata", self)
        details_dock.setWidget(self.details_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        toolbar = QToolBar("ECW navigation", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)

        self.add_action(toolbar, "ZoomIn.png", "Zoom In", self.viewer.zoom_in)
        self.add_action(toolbar, "ZoomOut.png", "Zoom Out", self.viewer.zoom_out)
        self.add_action(
            toolbar,
            "FullExtent.png",
            "Full Extent",
            self.viewer.full_extent,
        )
        toolbar.addSeparator()

        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)

        self.zoom_box_action = self.add_action(
            toolbar,
            "RectangularZoom.png",
            "Zoom Rect",
            self.activate_zoom_box,
        )
        self.zoom_box_action.setCheckable(True)
        tool_group.addAction(self.zoom_box_action)

        self.pan_action = self.add_action(
            toolbar,
            "Pan.png",
            "Pan",
            self.activate_pan,
        )
        self.pan_action.setCheckable(True)
        self.pan_action.setChecked(True)
        tool_group.addAction(self.pan_action)
        self.tool_group = tool_group

    def add_action(self, toolbar, icon_name: str, text: str, callback) -> QAction:
        action = QAction(QIcon(str(self.icons.joinpath(icon_name))), text, self)
        action.setToolTip(text)
        action.triggered.connect(callback)
        toolbar.addAction(action)
        return action

    def initialize_viewer(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.viewer.resize(
            self.viewer_widget.width(),
            self.viewer_widget.height(),
        )
        self.viewer.show()

        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url=(
                    "https://github.com/geokernel-io/GeoKernel.SampleData/"
                    "releases/download/v1/world_8km_ecw.zip"
                ),
                zip_name="world_8km_ecw.zip",
                target_folder="world_8km_ecw",
                required_file="world_8km.ecw",
                title="EcwLoad",
            )
            self.viewer.add_layer(str(path))
            self.show_metadata(path)
            self.viewer.full_extent()
        except Exception as error:
            QMessageBox.critical(
                self,
                "EcwLoad",
                f"ECW could not be loaded:\n{error}",
            )

    def show_metadata(self, path: Path) -> None:
        info = self.viewer.layer_info(0)
        coordinate_system = info.get("coordinateSystem", {})
        projected_extent = info.get("projectedExtent", {})
        file_size = path.stat().st_size if path.exists() else 0
        epsg_code = coordinate_system.get("epsgCode") or "unknown"

        lines = [
            "ECW load sample",
            "",
            "File",
            f"Path: {path}",
            f"Exists: {'yes' if path.exists() else 'no'}",
            f"Size: {file_size} bytes",
            "",
            "Raster layer",
            f"Name: {info.get('name', path.stem)}",
            f"EPSG: {epsg_code}",
            "Coordinate system: " + str(coordinate_system.get("name", "unknown")),
            "Layer extent: " + self.extent_text(projected_extent),
            "",
            "SDK flow",
            "viewer.add_layer(path)",
            "viewer.layer_info(index)",
            "viewer.full_extent()",
        ]
        self.details_view.setPlainText("\n".join(lines))
        self.statusBar().showMessage(f"ECW loaded: {path.name}")

    def extent_text(self, extent: dict) -> str:
        if not extent:
            return "unknown"
        return (
            f"({extent.get('xMin', 0):.2f}, {extent.get('yMin', 0):.2f}) - "
            f"({extent.get('xMax', 0):.2f}, {extent.get('yMax', 0):.2f})"
        )

    def activate_zoom_box(self) -> None:
        self.viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("EcwLoad")
    app.setWindowIcon(application_icon())
    window = EcwLoadWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
