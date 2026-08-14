import shutil
import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QCheckBox, QDockWidget, QFileDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTextEdit, QToolBar
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_EXTENT_3857 = Extent(-1400000.0, 4100000.0, 4200000.0, 7800000.0)

class XyzLocalCacheWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.icons = Path(__file__).resolve().parent / "images"
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("XyzLocalCache")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        self.details_view = QTextEdit(self)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(360)
        details_dock = QDockWidget("Local cache details", self)
        details_dock.setWidget(self.details_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        toolbar = QToolBar("XYZ local cache", self)
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
        self.cache_check = QCheckBox("Local cache", toolbar)
        self.cache_check.setChecked(True)
        self.cache_check.toggled.connect(self.apply_cache)
        toolbar.addWidget(self.cache_check)

        cache_label = QLabel("Cache:", toolbar)
        cache_label.setContentsMargins(4, 0, 4, 0)
        toolbar.addWidget(cache_label)

        self.cache_edit = QLineEdit(str(self.default_cache_directory()), toolbar)
        self.cache_edit.setMinimumWidth(360)
        self.cache_edit.returnPressed.connect(self.apply_cache)
        toolbar.addWidget(self.cache_edit)

        browse_button = QPushButton("Browse", toolbar)
        browse_button.clicked.connect(self.browse_cache_directory)
        toolbar.addWidget(browse_button)

        apply_action = QAction("Apply Cache", self)
        apply_action.triggered.connect(self.apply_cache)
        toolbar.addAction(apply_action)

        refresh_action = QAction("Refresh Stats", self)
        refresh_action.triggered.connect(self.update_details)
        toolbar.addAction(refresh_action)

        clear_action = QAction("Clear Cache", self)
        clear_action.triggered.connect(self.clear_cache)
        toolbar.addAction(clear_action)

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
        self.apply_cache()

    def default_cache_directory(self) -> Path:
        return Path(__file__).resolve().parent / "XyzLocalCacheData" / "osm"

    def cache_directory(self) -> Path:
        text = self.cache_edit.text().strip()
        if not text:
            return self.default_cache_directory()
        return Path(text).expanduser().resolve()

    def apply_cache(self, *_args) -> None:
        if not self.initialized:
            return

        cache_directory = self.cache_directory()
        self.cache_edit.setText(str(cache_directory))

        try:
            self.viewer.clear_layers()
            layer_index = self.viewer.add_xyz_layer(
                "OSM with Local Cache",
                OSM_URL,
                0,
                19,
                256,
                "OpenStreetMap contributors",
                self.cache_check.isChecked(),
                str(cache_directory),
            )
            if layer_index < 0:
                raise RuntimeError("add_xyz_layer returned an invalid layer index.")

            self.show_default_extent()
            self.update_details()
            state = (
                "with local disk cache"
                if self.cache_check.isChecked()
                else "with local cache disabled"
            )
            self.statusBar().showMessage(f"XYZ layer loaded {state}.")
        except Exception as error:
            QMessageBox.critical(
                self,
                "XyzLocalCache",
                f"XYZ layer could not be loaded:\n{error}",
            )

    def browse_cache_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select XYZ cache directory",
            str(self.cache_directory()),
        )
        if selected:
            self.cache_edit.setText(selected)

    def cache_statistics(self) -> tuple[int, int]:
        directory = self.cache_directory()
        if not directory.exists():
            return 0, 0

        tile_files = list(directory.rglob("*.tile"))
        byte_count = sum(path.stat().st_size for path in tile_files if path.is_file())
        return len(tile_files), byte_count

    def update_details(self) -> None:
        tile_count, byte_count = self.cache_statistics()
        cache_state = "enabled" if self.cache_check.isChecked() else "disabled"
        lines = [
            "XYZ local cache sample",
            "",
            "URL template:",
            OSM_URL,
            "",
            f"Local cache: {cache_state}",
            "Configured cache directory:",
            str(self.cache_directory()),
            "",
            "Cache contents:",
            f"Tile files: {tile_count}",
            f"Size: {self.format_bytes(byte_count)}",
            "",
            "SDK flow:",
            "viewer.add_xyz_layer(name, url_template, min_zoom, max_zoom, "
            "tile_size, attribution, cache_enabled, cache_directory)",
            "",
            "Pan or zoom the map to request tiles. When local cache is enabled, "
            "downloaded tiles are stored under the configured directory and "
            "reused on later runs.",
        ]
        self.details_view.setPlainText("\n".join(lines))

    def clear_cache(self) -> None:
        cache_directory = self.cache_directory()
        answer = QMessageBox.question(
            self,
            "XyzLocalCache",
            f"Clear all cached tiles under:\n{cache_directory}",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if cache_directory.exists():
            shutil.rmtree(cache_directory)

        self.update_details()
        self.statusBar().showMessage("Cache directory cleared.")
        self.viewer.invalidate_render_cache(True, True)
        self.viewer_widget.update()

    def format_bytes(self, byte_count: int) -> str:
        kilobytes = byte_count / 1024.0
        megabytes = kilobytes / 1024.0
        if megabytes >= 1.0:
            return f"{megabytes:.2f} MB"
        if kilobytes >= 1.0:
            return f"{kilobytes:.1f} KB"
        return f"{byte_count} bytes"

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
    app.setApplicationName("XyzLocalCache")
    app.setWindowIcon(application_icon())
    window = XyzLocalCacheWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
