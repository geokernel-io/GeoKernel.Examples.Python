import sys
from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import CoordinateSystemPreset, Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

WEB_MERCATOR_LIMIT = 20037508.342789244

@dataclass(frozen=True)
class SpatialReferenceOption:
    label: str
    short_name: str
    preset: CoordinateSystemPreset
    extent: Extent
    coordinate_decimals: int

SPATIAL_REFERENCE_OPTIONS = (
    SpatialReferenceOption(
        "EPSG:4326 - WGS 84",
        "EPSG:4326",
        CoordinateSystemPreset.WGS84,
        Extent(-180.0, -85.0, 180.0, 85.0),
        6,
    ),
    SpatialReferenceOption(
        "EPSG:3857 - WGS 84 / Web Mercator",
        "EPSG:3857",
        CoordinateSystemPreset.WEB_MERCATOR,
        Extent(
            -WEB_MERCATOR_LIMIT,
            -WEB_MERCATOR_LIMIT,
            WEB_MERCATOR_LIMIT,
            WEB_MERCATOR_LIMIT,
        ),
        2,
    ),
    SpatialReferenceOption(
        "EPSG:3395 - WGS 84 / World Mercator",
        "EPSG:3395",
        CoordinateSystemPreset.WORLD_MERCATOR,
        Extent(-WEB_MERCATOR_LIMIT, -20000000.0, WEB_MERCATOR_LIMIT, 20000000.0),
        2,
    ),
    SpatialReferenceOption(
        "World Miller Cylindrical",
        "Miller",
        CoordinateSystemPreset.MILLER,
        Extent(-WEB_MERCATOR_LIMIT, -15500000.0, WEB_MERCATOR_LIMIT, 15500000.0),
        2,
    ),
    SpatialReferenceOption(
        "World Mollweide",
        "Mollweide",
        CoordinateSystemPreset.MOLLWEIDE,
        Extent(-18500000.0, -9500000.0, 18500000.0, 9500000.0),
        2,
    ),
    SpatialReferenceOption(
        "World Sinusoidal",
        "Sinusoidal",
        CoordinateSystemPreset.SINUSOIDAL,
        Extent(-WEB_MERCATOR_LIMIT, -10500000.0, WEB_MERCATOR_LIMIT, 10500000.0),
        2,
    ),
    SpatialReferenceOption(
        "World Eckert IV",
        "Eckert IV",
        CoordinateSystemPreset.ECKERT_IV,
        Extent(-18500000.0, -9500000.0, 18500000.0, 9500000.0),
        2,
    ),
    SpatialReferenceOption(
        "World Eckert VI",
        "Eckert VI",
        CoordinateSystemPreset.ECKERT_VI,
        Extent(-18500000.0, -9500000.0, 18500000.0, 9500000.0),
        2,
    ),
)

class OnTheFlyReprojectWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.world_layer_loaded = False
        self.initialized = False

        self.setWindowTitle("OnTheFlyReproject")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Projection", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        full_extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.svg")), "Full Extent", self
        )
        full_extent_action.triggered.connect(self.show_selected_extent)
        toolbar.addAction(full_extent_action)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Spatial reference:", toolbar))

        self.spatial_reference_combo = QComboBox(toolbar)
        self.spatial_reference_combo.setMinimumWidth(330)
        for option in SPATIAL_REFERENCE_OPTIONS:
            self.spatial_reference_combo.addItem(option.label)
        self.spatial_reference_combo.currentIndexChanged.connect(
            self.apply_selected_spatial_reference
        )
        toolbar.addWidget(self.spatial_reference_combo)

        hint = QLabel(
            "  world_4326.shp is reprojected on the fly into the selected viewer CRS.",
            toolbar,
        )
        hint.setStyleSheet("color: #4E5F5B;")
        toolbar.addWidget(hint)

        self.coordinate_status = QLabel("Preparing world sample data...", self)
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
            path = ensure_sample_file(
                app=self.app,
                zip_url=(
                    "https://github.com/geokernel-io/GeoKernel.SampleData/"
                    "releases/download/v1/world_4326.zip"
                ),
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="OnTheFlyReproject",
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
            self.world_layer_loaded = True
            self.spatial_reference_combo.setCurrentIndex(1)
            self.apply_selected_spatial_reference()
        except Exception as error:
            self.coordinate_status.setText("World sample data could not be loaded.")
            QMessageBox.critical(self, "OnTheFlyReproject", str(error))

    def selected_option(self):
        index = self.spatial_reference_combo.currentIndex()
        if 0 <= index < len(SPATIAL_REFERENCE_OPTIONS):
            return SPATIAL_REFERENCE_OPTIONS[index]
        return None

    def apply_selected_spatial_reference(self, _index: int = -1) -> None:
        if not self.world_layer_loaded:
            return

        option = self.selected_option()
        if option is None:
            return

        try:
            if not self.viewer.set_coordinate_system_preset(option.preset):
                raise RuntimeError(f"{option.short_name} could not be applied.")
            self.viewer.set_view_extent(option.extent)
            self.coordinate_status.setText(
                f"{option.short_name}: world_4326.shp reprojected on the fly."
            )
        except Exception as error:
            self.coordinate_status.setText(f"{option.short_name} could not be applied.")
            QMessageBox.critical(self, "OnTheFlyReproject", str(error))

    def show_selected_extent(self) -> None:
        option = self.selected_option()
        if option is not None and self.world_layer_loaded:
            self.viewer.set_view_extent(option.extent)

    def on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.MOUSE_COORDINATES_CHANGED:
            return

        option = self.selected_option()
        if option is None:
            return

        screen_x = event.screen_rectangle.left
        screen_y = event.screen_rectangle.top
        world_x = event.extent.x_min
        world_y = event.extent.y_min
        decimals = option.coordinate_decimals
        self.coordinate_status.setText(
            f"Screen: {screen_x:.0f}, {screen_y:.0f}    |    "
            f"{option.short_name}: {world_x:.{decimals}f}, {world_y:.{decimals}f}"
        )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("OnTheFlyReproject")
    app.setWindowIcon(application_icon())

    window = OnTheFlyReprojectWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
