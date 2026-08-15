import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QMessageBox, QSplitter, QTextEdit, QToolBar, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_EXTENT_3857 = Extent(-1400000.0, 4100000.0, 4200000.0, 7800000.0)
LEFT_TILE_SIZE = 256
RIGHT_TILE_SIZE = 512

class XyzTileSizeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.icons = Path(__file__).resolve().parent / "images"
        self.left_viewer = Viewer()
        self.right_viewer = Viewer()
        self.left_viewer.set_tool(ViewerTool.PAN)
        self.right_viewer.set_tool(ViewerTool.PAN)
        self.left_widget = self.left_viewer.qt_widget()
        self.right_widget = self.right_viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("XyzTileSize")
        self.setWindowIcon(application_icon())
        self.resize(1280, 800)
        self.create_ui()

    def create_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(
            self.create_viewer_panel(
                "256 px tiles",
                LEFT_TILE_SIZE,
                self.left_widget,
            )
        )
        splitter.addWidget(
            self.create_viewer_panel(
                "512 px tiles",
                RIGHT_TILE_SIZE,
                self.right_widget,
            )
        )
        splitter.setSizes([640, 640])
        self.setCentralWidget(splitter)

        details_view = QTextEdit(self)
        details_view.setReadOnly(True)
        details_view.setMinimumWidth(340)
        details_view.setPlainText(self.details_text())
        details_dock = QDockWidget("Tile size details", self)
        details_dock.setWidget(details_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        toolbar = QToolBar("XYZ tile size", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)

        self.add_action(toolbar, "ZoomIn.png", "Zoom In", self.zoom_in_both)
        self.add_action(toolbar, "ZoomOut.png", "Zoom Out", self.zoom_out_both)
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

        self.statusBar().showMessage(
            "Compare GisLayerXYZ::setTileSize(256) and setTileSize(512)."
        )

    def create_viewer_panel(
        self,
        title: str,
        tile_size: int,
        viewer_widget: QWidget,
    ) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        label = QLabel(f"{title} | setTileSize({tile_size})", panel)
        label.setMinimumHeight(26)
        label.setStyleSheet(
            "QLabel { background: #eeeeee; padding-left: 6px; font-weight: 600; }"
        )
        layout.addWidget(label)
        layout.addWidget(viewer_widget, 1)
        return panel

    def add_action(self, toolbar, icon_name: str, text: str, callback) -> QAction:
        action = QAction(QIcon(str(self.icons.joinpath(icon_name))), text, self)
        action.setToolTip(text)
        action.triggered.connect(callback)
        toolbar.addAction(action)
        return action

    def initialize_viewers(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.initialize_viewer(
            self.left_viewer,
            self.left_widget,
            LEFT_TILE_SIZE,
        )
        self.initialize_viewer(
            self.right_viewer,
            self.right_widget,
            RIGHT_TILE_SIZE,
        )

    def initialize_viewer(
        self,
        viewer: Viewer,
        viewer_widget: QWidget,
        tile_size: int,
    ) -> None:
        viewer.resize(viewer_widget.width(), viewer_widget.height())
        viewer.show()
        self.add_tile_layer(viewer, tile_size)

    def add_tile_layer(self, viewer: Viewer, tile_size: int) -> None:
        cache_directory = self.cache_directory_for(tile_size)

        try:
            viewer.clear_layers()
            layer_index = viewer.add_xyz_layer(
                f"OSM tileSize {tile_size}",
                OSM_URL,
                0,
                19,
                tile_size,
                "OpenStreetMap contributors",
                True,
                str(cache_directory),
            )
            if layer_index < 0:
                raise RuntimeError("add_xyz_layer returned an invalid layer index.")
            viewer.set_view_extent(DEFAULT_EXTENT_3857)
        except Exception as error:
            QMessageBox.critical(
                self,
                "XyzTileSize",
                f"{tile_size} px XYZ layer could not be loaded:\n{error}",
            )

    def cache_directory_for(self, tile_size: int) -> Path:
        return Path(__file__).resolve().parent / "XyzTileSizeCache" / str(tile_size)

    def details_text(self) -> str:
        lines = [
            "XYZ tile size sample",
            "",
            "Left map:",
            "GisLayerXYZ + setTileSize(256)",
            "",
            "Right map:",
            "GisLayerXYZ + setTileSize(512)",
            "",
            "URL template:",
            OSM_URL,
            "",
            "Why this matters:",
            "- tileSize is the expected pixel size of one downloaded tile.",
            "- Standard OSM tiles are usually 256 px.",
            "- Some services expose 512 px retina/high-DPI tiles.",
            "- The cache key includes tileSize, so 256 and 512 variants stay separate.",
            "",
            "SDK flow:",
            "viewer.add_xyz_layer(name, url_template, min_zoom, max_zoom, "
            "tile_size, attribution, cache_enabled, cache_directory)",
        ]
        return "\n".join(lines)

    def zoom_in_both(self) -> None:
        self.left_viewer.zoom_in()
        self.right_viewer.zoom_in()

    def zoom_out_both(self) -> None:
        self.left_viewer.zoom_out()
        self.right_viewer.zoom_out()

    def show_default_extent(self) -> None:
        if self.left_viewer.layer_count() > 0:
            self.left_viewer.set_view_extent(DEFAULT_EXTENT_3857)
        if self.right_viewer.layer_count() > 0:
            self.right_viewer.set_view_extent(DEFAULT_EXTENT_3857)

    def activate_zoom_box(self) -> None:
        self.left_viewer.set_tool(ViewerTool.ZOOM_BOX)
        self.right_viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.left_viewer.set_tool(ViewerTool.PAN)
        self.right_viewer.set_tool(ViewerTool.PAN)

    def closeEvent(self, event) -> None:
        for viewer in (self.left_viewer, self.right_viewer):
            try:
                viewer.close()
            except Exception:
                pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("XyzTileSize")
    app.setWindowIcon(application_icon())

    window = XyzTileSizeWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewers)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
