from __future__ import annotations

import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path


def apply_cloud_options() -> None:
    os.environ.update({
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".parquet,.pmtiles",
        "GDAL_CACHEMAX": "256",
        "VSI_CACHE": "TRUE",
        "VSI_CACHE_SIZE": "67108864",
        "CPL_VSIL_CURL_CHUNK_SIZE": "1048576",
        "CPL_VSIL_CURL_CACHE_SIZE": "67108864",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "GDAL_HTTP_CONNECTTIMEOUT": "10",
        "GDAL_HTTP_TIMEOUT": "30",
    })


apply_cloud_options()

from PySide6.QtCore import QObject, QSize, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QTextEdit, QToolBar, QVBoxLayout, QWidget,
)
from geokernel import CloudClient, Viewer, ViewerEventType, ViewerTool
from common import application_icon


REMOTE_URL = "https://raw.githubusercontent.com/opengeospatial/geoparquet/main/examples/example.parquet"


def probe_remote(remote: str) -> tuple[str, dict]:
    with CloudClient({
        "memoryEnabled": True,
        "maximumMemoryBytes": 4 * 1024 * 1024,
        "diskEnabled": False,
        "maximumDiskBytes": 0,
    }) as cloud:
        cloud.set_timeout(30000)
        probe = cloud.probe_geo_parquet(remote)
        if not probe.get("cloudReadable"):
            raise RuntimeError(str(probe.get("diagnostic", "Remote GeoParquet is not range-readable.")))
        return cloud.geo_parquet_gdal_virtual_path(remote), probe


def report(probe: dict) -> str:
    return (
        "Cloud GeoParquet streaming\n\n"
        f"URL: {probe.get('url', '')}\n"
        f"Content length: {probe.get('contentLength', 0)} bytes\n"
        f"Content type: {probe.get('contentType', '')}\n"
        f"Accept-Ranges: {'yes' if probe.get('acceptsRanges') else 'no'}\n"
        f"PAR1 header: {'valid' if probe.get('headerValid') else 'invalid'}\n"
        f"PAR1 footer: {'valid' if probe.get('footerValid') else 'invalid'}\n"
        "GDAL source: /vsicurl/\n\n"
        f"{probe.get('diagnostic', '')}\n\n"
        "Only metadata and requested byte ranges are transferred; the complete GeoParquet file is not downloaded."
    )


class EventBridge(QObject):
    drawing_progress = Signal(int, str)
    viewer_busy = Signal(bool)


class Window(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cloud-geoparquet")
        self.future: Future | None = None
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.bridge = EventBridge()
        self.bridge.drawing_progress.connect(self.show_drawing_progress)
        self.bridge.viewer_busy.connect(self.show_render_busy)
        self.viewer.set_event_callback(self.on_viewer_event)

        self.setWindowTitle("CloudGeoParquetLoad")
        self.setWindowIcon(application_icon())
        self.resize(1280, 820)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.viewer.qt_widget(), 1)

        panel_widget = QWidget()
        panel_widget.setFixedWidth(390)
        panel = QVBoxLayout(panel_widget)
        title = QLabel("Cloud GeoParquet streaming")
        font = title.font(); font.setBold(True); title.setFont(font)
        panel.addWidget(title)
        panel.addWidget(QLabel("Remote GeoParquet URL"))
        self.url = QLineEdit(REMOTE_URL)
        panel.addWidget(self.url)
        self.load_button = QPushButton("Probe and stream GeoParquet")
        self.load_button.clicked.connect(self.run)
        panel.addWidget(self.load_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        panel.addWidget(self.progress)
        panel.addWidget(QLabel("Cloud diagnostics"))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText("Ready.")
        panel.addWidget(self.details, 1)
        root.addWidget(panel_widget)
        self.setCentralWidget(central)
        self.add_navigation()

        self.poll = QTimer(self)
        self.poll.timeout.connect(self.poll_worker)
        self.poll.start(50)
        QTimer.singleShot(0, self.run)

    def add_navigation(self) -> None:
        icons = Path(__file__).resolve().parent / "images"
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)
        for icon, text, callback in (
            ("ZoomIn.png", "Zoom In", self.viewer.zoom_in),
            ("ZoomOut.png", "Zoom Out", self.viewer.zoom_out),
            ("FullExtent.png", "Full Extent", self.viewer.full_extent),
        ):
            action = QAction(QIcon(str(icons / icon)), text, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)
        toolbar.addSeparator()
        group = QActionGroup(toolbar)
        group.setExclusive(True)
        for icon, text, tool in (
            ("RectangularZoom.png", "Zoom Box", ViewerTool.ZOOM_BOX),
            ("Pan.png", "Pan", ViewerTool.PAN),
        ):
            action = QAction(QIcon(str(icons / icon)), text, self)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=tool: self.viewer.set_tool(value))
            toolbar.addAction(action)
            group.addAction(action)
            if tool == ViewerTool.PAN:
                action.setChecked(True)

    def run(self) -> None:
        if self.future is not None:
            return
        remote = self.url.text().strip()
        if not remote.startswith(("http://", "https://")):
            QMessageBox.warning(self, self.windowTitle(), "Enter a valid HTTP or HTTPS URL.")
            return
        self.load_button.setEnabled(False)
        self.details.setPlainText("Reading the GeoParquet header and footer with HTTP ranges...")
        self.set_progress(10, "Probing remote object...")
        self.future = self.executor.submit(probe_remote, remote)

    def poll_worker(self) -> None:
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        try:
            path, probe = future.result()
            self.set_progress(60, "Opening GeoParquet layer...")
            self.viewer.clear_layers()
            self.viewer.add_layer_file(path)
            self.viewer.set_layer_name(0, "Remote GeoParquet")
            self.details.setPlainText(report(probe))
            self.viewer.full_extent()
            self.set_progress(100, "GeoParquet is streaming through HTTP byte ranges.")
            self.load_button.setEnabled(True)
        except Exception as error:
            self.fail(error)

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.DRAWING_PROGRESS_CHANGED:
            self.bridge.drawing_progress.emit(int(event.int_value), str(event.text or "Rendering map..."))
        elif event.event_type == ViewerEventType.BUSY_CHANGED:
            self.bridge.viewer_busy.emit(bool(event.int_value))

    def show_drawing_progress(self, value: int, text: str) -> None:
        if not self.load_button.isEnabled():
            return
        self.set_progress(value, text or "Rendering map...")

    def show_render_busy(self, busy: bool) -> None:
        if not self.load_button.isEnabled():
            return
        self.progress.show()
        if busy:
            self.progress.setRange(0, 0)
            self.statusBar().showMessage("Rendering map...")
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.progress.setFormat("100% — Map ready")
            self.statusBar().showMessage("Map ready.")

    def set_progress(self, value: int, text: str) -> None:
        value = max(0, min(100, value))
        self.progress.show()
        self.progress.setRange(0, 100)
        self.progress.setValue(value)
        self.progress.setFormat(f"{value}% — {text}")
        self.statusBar().showMessage(text)
        self.app.processEvents()

    def fail(self, error: Exception) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.details.setPlainText(f"Load failed:\n{error}")
        self.statusBar().showMessage("Cloud GeoParquet load failed.")
        self.load_button.setEnabled(True)
        QMessageBox.critical(self, self.windowTitle(), str(error))

    def closeEvent(self, event) -> None:
        self.closing = True
        self.poll.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.viewer.set_event_callback(None)
        except Exception:
            pass
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = Window(app)
    window.show()
    app.processEvents()
    window.viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
