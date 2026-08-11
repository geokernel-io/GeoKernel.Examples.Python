import math
import sys
from pathlib import Path
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QToolBar, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

WORLD_EXTENT = Extent(-180.0, -85.0, 180.0, 85.0)

class CoordinateTransformWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.transformer = CoordinateSystemFactory()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("CoordinateTransform")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_ui()

    def create_ui(self) -> None:
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget(central_widget)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        description = QLabel(
            "Move the mouse over the map to transform EPSG:4326 "
            "longitude/latitude to EPSG:3857 Web Mercator meters.",
            header,
        )
        header_layout.addWidget(description)
        header_layout.addStretch(1)
        layout.addWidget(header)
        layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central_widget)

        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        full_extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.svg")), "Full Extent", self
        )
        full_extent_action.triggered.connect(self.show_world_extent)
        toolbar.addAction(full_extent_action)

        self.coordinate_status = QLabel("Move mouse over the map.", self)
        self.statusBar().addPermanentWidget(self.coordinate_status, 1)

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
            world_path = ensure_sample_file(
                app=self.app,
                zip_url=(
                    "https://github.com/geokernel-io/GeoKernel.SampleData/"
                    "releases/download/v1/world_4326.zip"
                ),
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="CoordinateTransform",
            )
            self.viewer.add_layer(str(world_path))
            self.viewer.set_layer_name(0, "World countries")
            if not self.viewer.set_layer_coordinate_system_preset(
                0, CoordinateSystemPreset.WGS84
            ):
                raise RuntimeError("World layer coordinate system could not be set.")
            if not self.viewer.set_coordinate_system_preset(
                CoordinateSystemPreset.WGS84
            ):
                raise RuntimeError("Viewer coordinate system could not be set.")
            self.viewer.set_layer_style(
                0,
                {
                    "fillColor": "#D8E5E1",
                    "fillOpacity": 210,
                    "lineColor": "#6F8883",
                    "lineWidth": 0.75,
                },
            )
            self.show_world_extent()
            self.statusBar().showMessage("EPSG:4326 world layer loaded.")
        except Exception as error:
            QMessageBox.critical(self, "CoordinateTransform", str(error))

    def show_world_extent(self) -> None:
        self.viewer.set_view_extent(WORLD_EXTENT)

    def on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.MOUSE_COORDINATES_CHANGED:
            return

        longitude = event.extent.x_min
        latitude = event.extent.y_min
        self.show_transformed_coordinate(longitude, latitude)

    def show_transformed_coordinate(self, longitude: float, latitude: float) -> None:
        if (
            not math.isfinite(longitude)
            or not math.isfinite(latitude)
            or longitude < -180.0
            or longitude > 180.0
            or latitude <= -90.0
            or latitude >= 90.0
        ):
            self.coordinate_status.setText("Move mouse over the map.")
            return

        try:
            x, y = self.transformer.transform_point(
                4326,
                3857,
                longitude,
                latitude,
            )
            self.coordinate_status.setText(
                f"EPSG:4326 lon/lat: {longitude:.6f}, {latitude:.6f}"
                f"    ->    EPSG:3857 meters: {x:.2f}, {y:.2f}"
            )
        except (RuntimeError, ValueError):
            self.coordinate_status.setText(
                "Coordinate is outside the transformable range."
            )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("CoordinateTransform")
    app.setWindowIcon(application_icon())

    window = CoordinateTransformWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
