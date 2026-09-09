import sys
from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDockWidget, QLabel, QMainWindow, QMessageBox, QTextEdit, QToolBar
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

@dataclass(frozen=True)
class XyzPreset:
    name: str
    url_template: str
    min_zoom: int = 0
    max_zoom: int = 19
    tile_size: int = 256
    attribution: str = ""

PRESETS = (
    XyzPreset("Bing Virtual Earth", "http://ecn.t3.tiles.virtualearth.net/tiles/a{q}.jpeg?g=1"),
    XyzPreset("CartoDb Dark Matter", "http://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"),
    XyzPreset("CartoDb Dark Matter (No Labels)", "http://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png"),
    XyzPreset("CartoDb Positron", "http://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"),
    XyzPreset("CartoDb Positron (No Labels)", "http://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"),
    XyzPreset("Esri Boundaries Places", "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Gray (dark)", "http://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Gray (light)", "http://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Hillshade", "http://services.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri National Geographic", "http://services.arcgisonline.com/ArcGIS/rest/services/NatGeo_World_Map/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Navigation Charts", "http://services.arcgisonline.com/ArcGIS/rest/services/Specialty/World_Navigation_Charts/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Ocean", "https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Physical Map", "https://services.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Satellite", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Shaded Relief", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Standard", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Topo World", "http://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Esri Transportation", "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}"),
    XyzPreset("Google Maps", "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}"),
    XyzPreset("Google Satellite", "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"),
    XyzPreset("Google Satellite Hybrid", "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"),
    XyzPreset("Google Terrain", "https://mt1.google.com/vt/lyrs=t&x={x}&y={y}&z={z}"),
    XyzPreset("Google Terrain Hybrid", "https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}"),
    XyzPreset("Mapzen Global Terrain", "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"),
    XyzPreset("Gempa", "https://demo.gempa.de/gaps/tiles/{z}/{y}/{x}"),
    XyzPreset("OpenStreetMap", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
    XyzPreset("OpenTopoMap", "https://tile.opentopomap.org/{z}/{x}/{y}.png"),
)

DEFAULT_EXTENT_3857 = Extent(-1400000.0, 4100000.0, 4200000.0, 7800000.0)

class XyzPresetsWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.icons = Path(__file__).resolve().parent / "images"
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("XyzPresets")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        self.details_view = QTextEdit(self)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(330)
        details_dock = QDockWidget("XYZ preset details", self)
        details_dock.setWidget(self.details_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        toolbar = QToolBar("XYZ presets", self)
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
            self.show_default_extent,
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

        toolbar.addSeparator()
        preset_label = QLabel("Preset:", toolbar)
        preset_label.setContentsMargins(4, 0, 4, 0)
        toolbar.addWidget(preset_label)

        self.preset_combo = QComboBox(toolbar)
        self.preset_combo.setMinimumWidth(260)
        for index, preset in enumerate(PRESETS):
            self.preset_combo.addItem(preset.name, index)
        self.preset_combo.setCurrentIndex(
            next(
                index
                for index, preset in enumerate(PRESETS)
                if preset.name == "OpenStreetMap"
            )
        )
        self.preset_combo.currentIndexChanged.connect(self.reload_preset)
        toolbar.addWidget(self.preset_combo)

        self.cache_check = QCheckBox("Local cache", toolbar)
        self.cache_check.setChecked(True)
        self.cache_check.toggled.connect(self.reload_preset)
        toolbar.addWidget(self.cache_check)

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
        self.reload_preset()

    def selected_preset(self):
        index = self.preset_combo.currentData()
        if isinstance(index, int) and 0 <= index < len(PRESETS):
            return PRESETS[index]
        return None

    def reload_preset(self, *_args) -> None:
        if not self.initialized:
            return

        preset = self.selected_preset()
        if preset is None:
            return

        try:
            self.viewer.clear_layers()
            layer_index = self.viewer.add_xyz_layer(
                preset.name,
                preset.url_template,
                preset.min_zoom,
                preset.max_zoom,
                preset.tile_size,
                preset.attribution,
                self.cache_check.isChecked(),
            )
            if layer_index < 0:
                raise RuntimeError("add_xyz_layer returned an invalid layer index.")

            self.show_default_extent()
            self.show_preset_details(preset)
            self.statusBar().showMessage(f"XYZ preset loaded: {preset.name}")
        except Exception as error:
            QMessageBox.critical(
                self,
                "XyzPresets",
                f"XYZ preset could not be loaded:\n{error}",
            )

    def show_preset_details(self, preset: XyzPreset) -> None:
        cache_state = "enabled" if self.cache_check.isChecked() else "disabled"
        lines = [
            "XYZ preset layer",
            "",
            f"Preset count: {len(PRESETS)}",
            f"Selected: {preset.name}",
            "",
            "URL template:",
            preset.url_template,
            "",
            f"Min zoom: {preset.min_zoom}",
            f"Max zoom: {preset.max_zoom}",
            f"Tile size: {preset.tile_size}",
            f"Local cache: {cache_state}",
        ]
        if preset.attribution:
            lines.extend(["", "Attribution:", preset.attribution])
        lines.extend(
            [
                "",
                "The sample creates the layer from:",
                "PRESETS",
                "viewer.add_xyz_layer(name, url_template, min_zoom, "
                "max_zoom, tile_size, attribution)",
            ]
        )
        self.details_view.setPlainText("\n".join(lines))

    def show_default_extent(self) -> None:
        if self.viewer.layer_count() > 0:
            self.viewer.set_view_extent(DEFAULT_EXTENT_3857)

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
    app.setApplicationName("XyzPresets")
    app.setWindowIcon(application_icon())
    window = XyzPresetsWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
