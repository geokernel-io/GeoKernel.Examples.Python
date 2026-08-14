import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

WEB_MERCATOR_LIMIT = 20037508.342789244
WEB_MERCATOR_EXTENT = Extent(
    -WEB_MERCATOR_LIMIT,
    -WEB_MERCATOR_LIMIT,
    WEB_MERCATOR_LIMIT,
    WEB_MERCATOR_LIMIT,
)

class WebMercatorWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).resolve().parent / "images"
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("WebMercator")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_ui()

    def create_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        details = QLabel(
            "EPSG:3857 - WGS 84 / Pseudo-Mercator"
            "    |    Projected coordinates in meters"
            "    |    Meters per unit: 1",
            central,
        )
        details.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(details)
        layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central)

        self.create_navigation_toolbar()
        self.coordinate_status = QLabel("Preparing world sample data...", self)
        self.statusBar().addPermanentWidget(self.coordinate_status, 1)

    def create_navigation_toolbar(self) -> None:
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)

        self.add_tool(toolbar, "ZoomIn.png", "Zoom In", self.viewer.zoom_in)
        self.add_tool(toolbar, "ZoomOut.png", "Zoom Out", self.viewer.zoom_out)
        self.add_tool(toolbar, "FullExtent.png", "Full Extent", self.show_world_extent)
        toolbar.addSeparator()
        self.add_tool(
            toolbar,
            "RectangularZoom.png",
            "Zoom Rect",
            self.activate_zoom_box,
        )
        self.add_tool(toolbar, "Pan.png", "Pan", self.activate_pan)

    def add_tool(self, toolbar, icon_name: str, text: str, callback) -> QAction:
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
            CoordinateSystemFactory().from_epsg(3857)
            path = ensure_sample_file(
                app=self.app,
                zip_url=(
                    "https://github.com/geokernel-io/GeoKernel.SampleData/"
                    "releases/download/v1/world_4326.zip"
                ),
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="WebMercator",
            )
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_name(0, "World countries - source EPSG:4326")
            if not self.viewer.set_layer_coordinate_system_preset(
                0, CoordinateSystemPreset.WGS84
            ):
                raise RuntimeError("Source layer CRS could not be set to EPSG:4326.")
            self.viewer.set_layer_style(
                0,
                {
                    "fillColor": "#D8E5E1",
                    "fillOpacity": 210,
                    "lineColor": "#6F8883",
                    "lineWidth": 0.75,
                },
            )

            if not self.viewer.set_coordinate_system_preset(
                CoordinateSystemPreset.WEB_MERCATOR
            ):
                raise RuntimeError("Viewer CRS could not be set to EPSG:3857.")
            self.show_world_extent()
            self.coordinate_status.setText(
                "Move the mouse over the map to inspect EPSG:3857 meter coordinates."
            )
        except Exception as error:
            self.coordinate_status.setText("World sample data could not be loaded.")
            QMessageBox.critical(self, "WebMercator", str(error))

    def activate_zoom_box(self) -> None:
        self.viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def show_world_extent(self) -> None:
        if self.viewer.layer_count() > 0:
            self.viewer.set_view_extent(WEB_MERCATOR_EXTENT)

    def on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.MOUSE_COORDINATES_CHANGED:
            return

        screen_x = event.screen_rectangle.left
        screen_y = event.screen_rectangle.top
        world_x = event.extent.x_min
        world_y = event.extent.y_min
        self.coordinate_status.setText(
            f"Screen: {screen_x:.0f}, {screen_y:.0f}    |    "
            f"EPSG:3857 meters: {world_x:.2f}, {world_y:.2f}"
        )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WebMercator")
    app.setWindowIcon(application_icon())

    window = WebMercatorWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
