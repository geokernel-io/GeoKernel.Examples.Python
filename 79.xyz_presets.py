import sys
from dataclasses import dataclass
from importlib.resources import files
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDockWidget, QLabel, QMainWindow, QMessageBox, QTextEdit, QToolBar
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

@dataclass(frozen=True)
class XyzPreset:
    name: str
    url_template: str
    min_zoom: int
    max_zoom: int
    tile_size: int
    attribution: str

PRESETS = (
    XyzPreset(
        "OpenStreetMap",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        0,
        19,
        256,
        "© OpenStreetMap contributors",
    ),
    XyzPreset(
        "OpenTopoMap",
        "https://tile.opentopomap.org/{z}/{x}/{y}.png",
        0,
        17,
        256,
        "© OpenTopoMap contributors",
    ),
    XyzPreset(
        "Esri World Imagery",
        (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        0,
        19,
        256,
        "Tiles © Esri",
    ),
)

DEFAULT_EXTENT_3857 = Extent(-1400000.0, 4100000.0, 4200000.0, 7800000.0)

class XyzPresetsWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.icons = files("geokernel").joinpath("assets/images")
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

        self.add_action(toolbar, "ZoomIn.svg", "Zoom In", self.viewer.zoom_in)
        self.add_action(toolbar, "ZoomOut.svg", "Zoom Out", self.viewer.zoom_out)
        self.add_action(
            toolbar,
            "FullExtent.svg",
            "Full Extent",
            self.show_default_extent,
        )
        toolbar.addSeparator()

        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)
        self.zoom_box_action = self.add_action(
            toolbar,
            "RectangularZoom.svg",
            "Zoom Rect",
            self.activate_zoom_box,
        )
        self.zoom_box_action.setCheckable(True)
        tool_group.addAction(self.zoom_box_action)

        self.pan_action = self.add_action(
            toolbar,
            "Pan.svg",
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
