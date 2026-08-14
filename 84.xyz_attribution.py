import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTextEdit, QToolBar, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_ATTRIBUTION = "© OpenStreetMap contributors"
CUSTOM_ATTRIBUTION = "Tiles © Custom Provider | Data © GeoKernel Sample"
DEFAULT_EXTENT_3857 = Extent(-1400000.0, 4100000.0, 4200000.0, 7800000.0)

class XyzAttributionWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.icons = Path(__file__).resolve().parent / "images"
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("XyzAttribution")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_ui()

    def create_ui(self) -> None:
        map_host = QWidget(self)
        map_layout = QVBoxLayout(map_host)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)
        map_layout.addWidget(self.viewer_widget, 1)

        self.attribution_label = QLabel(map_host)
        self.attribution_label.setMinimumHeight(28)
        self.attribution_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.attribution_label.setContentsMargins(8, 2, 10, 2)
        self.attribution_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.attribution_label.setStyleSheet(
            "QLabel {"
            " background: rgba(255, 255, 255, 215);"
            " color: #1f2d2d;"
            " border-top: 1px solid rgba(120, 130, 130, 140);"
            "}"
        )
        map_layout.addWidget(self.attribution_label)
        self.setCentralWidget(map_host)

        self.details_view = QTextEdit(self)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(350)
        details_dock = QDockWidget("Attribution details", self)
        details_dock.setWidget(self.details_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        toolbar = QToolBar("XYZ attribution", self)
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
        toolbar.addWidget(QLabel("Attribution:", toolbar))

        self.attribution_edit = QLineEdit(DEFAULT_ATTRIBUTION, toolbar)
        self.attribution_edit.setMinimumWidth(360)
        self.attribution_edit.returnPressed.connect(self.apply_attribution)
        toolbar.addWidget(self.attribution_edit)

        apply_action = QAction("Apply Attribution", self)
        apply_action.triggered.connect(self.apply_attribution)
        toolbar.addAction(apply_action)

        osm_button = QPushButton("OSM", toolbar)
        osm_button.clicked.connect(self.apply_osm_attribution)
        toolbar.addWidget(osm_button)

        custom_button = QPushButton("Custom", toolbar)
        custom_button.clicked.connect(self.apply_custom_attribution)
        toolbar.addWidget(custom_button)

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
        self.apply_attribution()

    def apply_attribution(self) -> None:
        if not self.initialized:
            return

        attribution = self.attribution_edit.text().strip() or "No attribution"
        previous_extent = DEFAULT_EXTENT_3857
        if self.viewer.layer_count() > 0:
            previous_extent = self.viewer.get_view_extent()

        try:
            self.viewer.clear_layers()
            layer_index = self.viewer.add_xyz_layer(
                "OSM Attribution",
                OSM_URL,
                0,
                19,
                256,
                attribution,
                True,
                str(self.cache_directory()),
            )
            if layer_index < 0:
                raise RuntimeError("add_xyz_layer returned an invalid layer index.")

            self.viewer.set_view_extent(previous_extent)
            self.attribution_label.setText(attribution)
            self.attribution_label.setVisible(bool(attribution.strip()))
            self.show_attribution_details(attribution)
            self.statusBar().showMessage("XYZ attribution applied.")
        except Exception as error:
            QMessageBox.critical(
                self,
                "XyzAttribution",
                f"XYZ layer could not be loaded:\n{error}",
            )

    def apply_osm_attribution(self) -> None:
        self.attribution_edit.setText(DEFAULT_ATTRIBUTION)
        self.apply_attribution()

    def apply_custom_attribution(self) -> None:
        self.attribution_edit.setText(CUSTOM_ATTRIBUTION)
        self.apply_attribution()

    def cache_directory(self) -> Path:
        return Path(__file__).resolve().parent / "XyzAttributionCache" / "osm"

    def show_attribution_details(self, attribution: str) -> None:
        lines = [
            "XYZ attribution sample",
            "",
            "URL template:",
            OSM_URL,
            "",
            "Applied attribution:",
            attribution,
            "",
            "What this sample shows:",
            "- GisLayerXYZ stores attribution metadata on the layer.",
            "- The sample also renders the same text as a map overlay.",
            "- Project save/load preserves attribution for XYZ/WMS/WMTS layers.",
            "",
            "SDK flow:",
            "viewer.add_xyz_layer(name, url_template, min_zoom, max_zoom, "
            "tile_size, attribution, cache_enabled, cache_directory)",
        ]
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
    app.setApplicationName("XyzAttribution")
    app.setWindowIcon(application_icon())
    window = XyzAttributionWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
