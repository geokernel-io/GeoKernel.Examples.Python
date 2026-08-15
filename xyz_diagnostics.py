import sys
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMessageBox, QTextEdit, QToolBar
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_EXTENT_3857 = Extent(-1400000.0, 4100000.0, 4200000.0, 7800000.0)

class XyzDiagnosticsWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.icons = Path(__file__).resolve().parent / "images"
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_index = -1
        self.initialized = False

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(750)
        self.refresh_timer.timeout.connect(self.refresh_diagnostics)

        self.setWindowTitle("XyzDiagnostics")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        self.details_view = QTextEdit(self)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(390)
        details_dock = QDockWidget("XYZ diagnostics", self)
        details_dock.setWidget(self.details_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        toolbar = QToolBar("XYZ diagnostics", self)
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
        refresh_action = QAction("Refresh Stats", self)
        refresh_action.triggered.connect(self.refresh_diagnostics)
        toolbar.addAction(refresh_action)

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
            self.layer_index = self.viewer.add_xyz_layer(
                "OSM Diagnostics",
                OSM_URL,
                0,
                19,
                256,
                "OpenStreetMap",
                True,
                str(self.cache_directory()),
            )
            if self.layer_index < 0:
                raise RuntimeError("add_xyz_layer returned an invalid layer index.")

            self.show_default_extent()
            self.refresh_diagnostics()
            self.refresh_timer.start()
        except Exception as error:
            QMessageBox.critical(
                self,
                "XyzDiagnostics",
                f"XYZ diagnostics layer could not be loaded:\n{error}",
            )

    def cache_directory(self) -> Path:
        return Path(__file__).resolve().parent / "XyzDiagnosticsCache" / "osm"

    def refresh_diagnostics(self) -> None:
        if self.layer_index < 0:
            self.details_view.setPlainText("XYZ layer is not available.")
            return

        try:
            snapshot = self.viewer.xyz_layer_diagnostics(self.layer_index)
            if not snapshot:
                self.details_view.setPlainText(
                    "XYZ layer diagnostics are not available."
                )
                return

            self.details_view.setPlainText(self.details_text(snapshot))
            self.statusBar().showMessage(
                "XYZ diagnostics: "
                f"{snapshot['downloadsStarted']} requests, "
                f"{snapshot['downloadsSucceeded']} downloads, "
                f"{snapshot['diskHits']} disk hits, "
                f"{snapshot['memoryHits']} memory hits"
            )
        except Exception as error:
            self.refresh_timer.stop()
            self.details_view.setPlainText(f"Diagnostics could not be read:\n{error}")

    def details_text(self, snapshot: dict) -> str:
        memory_total = snapshot["memoryHits"] + snapshot["memoryMisses"]
        disk_total = snapshot["diskHits"] + snapshot["diskMisses"]
        download_total = snapshot["downloadsSucceeded"] + snapshot["downloadsFailed"]
        updated = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        lines = [
            "XYZ diagnosticsSnapshot sample",
            f"Updated: {updated}",
            "",
            "Layer",
            f"Name: {snapshot['name']}",
            f"URL template: {snapshot['urlTemplate']}",
            f"Tile size: {snapshot['tileSize']}",
            f"Zoom range: {snapshot['minZoom']} - {snapshot['maxZoom']}",
            "Local cache: "
            + ("enabled" if snapshot["localCacheEnabled"] else "disabled"),
            f"Cache directory: {snapshot['cacheDirectory']}",
            "",
            "Memory cache",
            f"Hits: {snapshot['memoryHits']}",
            f"Misses: {snapshot['memoryMisses']}",
            f"Total lookups: {memory_total}",
            "",
            "Disk cache",
            f"Hits: {snapshot['diskHits']}",
            f"Misses: {snapshot['diskMisses']}",
            f"Total lookups: {disk_total}",
            f"Read time total: {snapshot['diskReadMs']} ms",
            f"Decode time total: {snapshot['decodeMs']} ms",
            "Average read: "
            + self.average_text(snapshot["diskReadMs"], snapshot["diskHits"]),
            "Average decode: "
            + self.average_text(snapshot["decodeMs"], snapshot["diskHits"]),
            "",
            "Network",
            f"Downloads started: {snapshot['downloadsStarted']}",
            f"Downloads succeeded: {snapshot['downloadsSucceeded']}",
            f"Downloads failed: {snapshot['downloadsFailed']}",
            f"Downloads completed: {download_total}",
            "Bytes downloaded: " + self.bytes_text(snapshot["bytesDownloaded"]),
            f"Download time total: {snapshot['downloadMs']} ms",
            "Average download: "
            + self.average_text(
                snapshot["downloadMs"],
                snapshot["downloadsSucceeded"],
            ),
            f"Queue depth: {snapshot['networkQueueDepth']}",
            f"Max queue depth: {snapshot['maxNetworkQueueDepth']}",
            "",
            "How to test",
            "- Pan or zoom the map to request new tiles.",
            "- First pass usually increases downloads and disk misses.",
            "- Revisit the same area to see memory/disk cache hits.",
        ]
        return "\n".join(lines)

    def average_text(self, total_milliseconds: int, count: int) -> str:
        if count == 0:
            return "0.00 ms"
        return f"{total_milliseconds / count:.2f} ms"

    def bytes_text(self, byte_count: int) -> str:
        mebibytes = byte_count / (1024.0 * 1024.0)
        return f"{byte_count} bytes ({mebibytes:.2f} MiB)"

    def show_default_extent(self) -> None:
        if self.viewer.layer_count() > 0:
            self.viewer.set_view_extent(DEFAULT_EXTENT_3857)

    def activate_zoom_box(self) -> None:
        self.viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def closeEvent(self, event) -> None:
        self.refresh_timer.stop()
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("XyzDiagnostics")
    app.setWindowIcon(application_icon())

    window = XyzDiagnosticsWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
