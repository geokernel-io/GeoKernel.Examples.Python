from __future__ import annotations

import os
import sys
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path


def apply_cloud_options() -> None:
    options = {
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
    }
    os.environ.update(options)


# GDAL reads several cloud options while the native SDK is being loaded.
# Apply them before importing geokernel, not after constructing the Viewer.
apply_cloud_options()

from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QTextEdit, QToolBar, QVBoxLayout, QWidget,
)
from geokernel import CloudClient, Viewer, ViewerTool, pmtiles_source_layers
from common import application_icon


REMOTE_URL = "https://pmtiles.io/protomaps(vector)ODbL_firenze.pmtiles"


def basemap_style(source_name: str) -> dict[str, object]:
    name = source_name.casefold()
    styles: dict[str, dict[str, object]] = {
        "earth": {"fillColor": "#f1eee8", "fillOpacity": 255, "lineWidth": 0.0},
        "landcover": {"fillColor": "#dce8d5", "fillOpacity": 255, "lineWidth": 0.0},
        "landuse": {"fillColor": "#e7e1d5", "fillOpacity": 255, "lineWidth": 0.0},
        "water": {"fillColor": "#b9d9eb", "fillOpacity": 255, "lineColor": "#9bc6df", "lineWidth": 0.35},
        "buildings": {"fillColor": "#d4ccc2", "fillOpacity": 255, "lineColor": "#b8aea3", "lineWidth": 0.25},
        "roads": {"lineColor": "#ffffff", "lineWidth": 1.15, "fillOpacity": 0},
        "transit": {"lineColor": "#d28a54", "lineWidth": 1.0, "fillOpacity": 0},
        "boundaries": {"lineColor": "#9a8f84", "lineWidth": 0.55, "fillOpacity": 0},
        "physical_line": {"lineColor": "#91a69a", "lineWidth": 0.5, "fillOpacity": 0},
        "natural": {"fillColor": "#cfe3c4", "fillOpacity": 255, "lineColor": "#9fbea0", "lineWidth": 0.25},
    }
    return styles.get(name, {"pointColor": "#557f9b", "pointSize": 2.5, "lineWidth": 0.3})


def probe_remote(remote: str) -> tuple[str, dict, list[dict]]:
    with CloudClient({"maximumMemoryBytes": 64 * 1024 * 1024, "maximumDiskBytes": 1024 * 1024 * 1024}) as cloud:
        cloud.set_timeout(30000)
        probe = cloud.probe_pmtiles(remote)
        if not probe.get("cloudReadable"):
            raise RuntimeError(str(probe.get("diagnostic", "Remote PMTiles is not range-readable.")))
        path = cloud.pmtiles_gdal_virtual_path(remote)
        layers = pmtiles_source_layers(path)
        if not layers:
            raise RuntimeError("PMTiles contains no drawable source layers.")
        return path, probe, layers


def report(probe: dict) -> str:
    yes_no = lambda value: "yes" if value else "no"
    return (
        "Cloud PMTiles streaming\n\n"
        f"URL: {probe.get('url', '')}\n"
        f"Content length: {probe.get('contentLength', 0)} bytes\n"
        f"Content type: {probe.get('contentType', '')}\n"
        f"Accept-Ranges: {yes_no(probe.get('acceptsRanges'))}\n"
        f"PMTiles header: {'valid' if probe.get('headerValid') else 'invalid'}\n"
        f"Specification: v{probe.get('specificationVersion', 0)}\n"
        f"Zoom range: {probe.get('minimumZoom', 0)}-{probe.get('maximumZoom', 0)}\n"
        f"Root directory: {probe.get('rootDirectoryLength', 0)} bytes\n"
        "GDAL source: /vsicurl/\n\n"
        f"{probe.get('diagnostic', '')}\n\n"
        "Only metadata and requested byte ranges are transferred; the complete PMTiles archive is not downloaded."
    )


class Window(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cloud-pmtiles")
        self.future: Future | None = None
        self.pending: tuple[str, dict, list[dict]] | None = None
        self.open_index = 0
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.log_directory = Path(tempfile.gettempdir()) / "GeoKernelLogs"
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.metrics_log = self.log_directory / "cloud-pmtiles-python-metrics.log"
        self.steps_log = self.log_directory / "cloud-pmtiles-python-steps.log"
        for log_path in (self.metrics_log, self.steps_log):
            log_path.unlink(missing_ok=True)
        self.viewer.set_render_metrics_log_path(self.metrics_log)
        self.viewer.set_render_step_log_path(self.steps_log)
        self.viewer.set_render_step_log(True)
        self.viewer.set_verbose_mode(True)
        self.setWindowTitle("CloudPmTilesLoad")
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
        title = QLabel("Cloud PMTiles streaming")
        font = title.font(); font.setBold(True); title.setFont(font)
        panel.addWidget(title)
        panel.addWidget(QLabel("Remote PMTiles URL"))
        self.url = QLineEdit(REMOTE_URL)
        panel.addWidget(self.url)
        self.load_button = QPushButton("Probe and stream PMTiles")
        self.load_button.clicked.connect(self.run)
        panel.addWidget(self.load_button)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.hide()
        panel.addWidget(self.progress)
        panel.addWidget(QLabel("Cloud diagnostics"))
        self.details = QTextEdit(); self.details.setReadOnly(True); self.details.setPlainText("Ready.")
        panel.addWidget(self.details, 1)
        root.addWidget(panel_widget)
        self.setCentralWidget(central)
        self.add_navigation()
        self.poll = QTimer(self); self.poll.timeout.connect(self.poll_worker); self.poll.start(50)
        QTimer.singleShot(0, self.run)

    def add_navigation(self) -> None:
        icons = Path(__file__).resolve().parent / "images"
        toolbar = QToolBar("Navigation", self); toolbar.setMovable(False); toolbar.setIconSize(QSize(32, 32)); self.addToolBar(toolbar)
        for icon, text, callback in (("ZoomIn.png", "Zoom In", self.viewer.zoom_in), ("ZoomOut.png", "Zoom Out", self.viewer.zoom_out), ("FullExtent.png", "Full Extent", self.viewer.full_extent)):
            action = QAction(QIcon(str(icons / icon)), text, self); action.triggered.connect(callback); toolbar.addAction(action)
        toolbar.addSeparator()
        group = QActionGroup(toolbar); group.setExclusive(True)
        for icon, text, tool in (("RectangularZoom.png", "Zoom Box", ViewerTool.ZOOM_BOX), ("Pan.png", "Pan", ViewerTool.PAN)):
            action = QAction(QIcon(str(icons / icon)), text, self); action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=tool: self.viewer.set_tool(value))
            toolbar.addAction(action); group.addAction(action)
            if tool == ViewerTool.PAN: action.setChecked(True)

    def run(self) -> None:
        if self.future is not None or self.pending is not None: return
        remote = self.url.text().strip()
        if not remote.startswith(("http://", "https://")):
            QMessageBox.warning(self, self.windowTitle(), "Enter a valid HTTP or HTTPS URL."); return
        self.load_button.setEnabled(False)
        self.set_progress(10, "Probing the remote PMTiles v3 header...")
        self.future = self.executor.submit(probe_remote, remote)

    def poll_worker(self) -> None:
        if self.future is None or not self.future.done(): return
        future, self.future = self.future, None
        try:
            self.pending = future.result(); self.open_index = 0; self.viewer.clear_layers()
            self.details.setPlainText(report(self.pending[1]))
            self.set_progress(35, "Opening PMTiles source layers...")
            self.open_layers()
        except Exception as error:
            self.fail(error)

    def open_layers(self) -> None:
        if self.closing or self.pending is None: return
        path, probe, layers = self.pending
        try:
            # Add every source layer in one GUI event-loop turn, matching the
            # Qt sample. Yielding after each layer starts 13 obsolete remote
            # renders whose blocking HTTP/GDAL queries cannot cancel promptly.
            for self.open_index, source in enumerate(layers):
                name = str(source.get("name", f"Layer {self.open_index + 1}"))
                self.progress.setValue(35 + (self.open_index + 1) * 55 // len(layers))
                self.progress.setFormat(f"Opening {name}...")
                self.viewer.add_layer_file(path, {"sourceLayerIndex": int(source.get("index", self.open_index)), "useSpatialIndex": False})
                self.viewer.set_layer_name(0, name)
                self.viewer.set_layer_style(0, basemap_style(name))

            self.open_index = len(layers)
            self.pending = None
            self.viewer.full_extent()
            self.details.setPlainText(report(probe))
            self.set_progress(100, f"{len(layers)} PMTiles source layers are streaming through HTTP byte ranges.")
            self.load_button.setEnabled(True)
        except Exception as error:
            self.fail(error)

    def set_progress(self, value: int, text: str) -> None:
        value = max(0, min(100, value)); self.progress.show(); self.progress.setRange(0, 100); self.progress.setValue(value); self.progress.setFormat(f"{value}% — {text}"); self.statusBar().showMessage(text); self.app.processEvents()

    def fail(self, error: Exception) -> None:
        self.pending = None; self.progress.setRange(0, 100); self.progress.setValue(0); self.details.setPlainText(f"Load failed:\n{error}"); self.statusBar().showMessage("Cloud PMTiles load failed."); self.load_button.setEnabled(True); QMessageBox.critical(self, self.windowTitle(), str(error))

    def closeEvent(self, event) -> None:
        self.closing = True; self.poll.stop(); self.executor.shutdown(wait=False, cancel_futures=True)
        try: self.viewer.close()
        except Exception: pass
        super().closeEvent(event)


def main() -> None:
    apply_cloud_options(); app = QApplication(sys.argv); window = Window(app); window.show(); app.processEvents(); window.viewer.show(); sys.exit(app.exec())


if __name__ == "__main__":
    main()
