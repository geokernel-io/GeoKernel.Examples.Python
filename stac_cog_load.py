from __future__ import annotations

import math
import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTextEdit, QToolBar, QVBoxLayout, QWidget,
)
from geokernel import CloudClient, CoordinateSystemPreset, Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon


CATALOG = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
RASTER_OPTIONS = {
    "prepareRasterOverviews": False,
    "rasterTileCacheEnabled": False,
    "rasterTileCachePixelBudget": 0,
    "rasterTileCacheMaximumItemPixels": 0,
}


@dataclass
class Asset:
    tile: str
    item_id: str
    datetime: str
    cloud_cover: str
    path: str
    content_length: int


class EventBridge(QObject):
    viewer_busy = Signal(bool)


def apply_gdal_options() -> None:
    os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
    os.environ["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif,.tiff"
    os.environ["GDAL_CACHEMAX"] = "256"
    os.environ["VSI_CACHE"] = "TRUE"
    os.environ["VSI_CACHE_SIZE"] = "67108864"


def search_assets(box: list[float]) -> list[Asset]:
    with CloudClient({"maximumMemoryBytes": 64 * 1024 * 1024, "maximumDiskBytes": 1024 * 1024 * 1024}) as cloud:
        cloud.set_timeout(15000)
        root = cloud.stac_search(CATALOG, {
            "collections": [COLLECTION], "bbox": box,
            "datetime": "2024-01-01T00:00:00Z/..", "limit": 100,
            "query": {"eo:cloud_cover": {"lt": 20}},
        })
        candidates: list[tuple[str, dict]] = []
        seen: set[str] = set()
        for item in root.get("items", []):
            properties = item.get("properties", {})
            tile = f"{properties.get('mgrs:utm_zone', '')}{properties.get('mgrs:latitude_band', '')}{properties.get('mgrs:grid_square', '')}"
            if tile in seen or "visual" not in item.get("assets", {}):
                continue
            seen.add(tile); candidates.append((tile, item))
            if len(candidates) >= 16:
                break

        output: list[Asset] = []
        for tile, item in candidates:
            properties = item["properties"]
            url = item["assets"]["visual"]["href"]
            probe = cloud.cog_probe(url)
            if not probe.get("cloudReadable"):
                continue
            output.append(Asset(
                tile, item["id"], properties.get("datetime", ""),
                f"{float(properties.get('eo:cloud_cover', 0)):.1f}%",
                cloud.cog_gdal_virtual_path(url), int(probe.get("contentLength", 0)),
            ))
        if not output:
            raise RuntimeError("STAC search returned no visual COG assets.")
        return output


def web_mercator_extent(box: list[float]) -> Extent:
    def x(lon: float) -> float: return lon * 20037508.342789244 / 180.0
    def y(lat: float) -> float:
        lat = max(-85.05112878, min(85.05112878, lat))
        return math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * 20037508.342789244 / math.pi
    x1, x2, y1, y2 = x(box[0]), x(box[2]), y(box[1]), y(box[3])
    px, py = (x2 - x1) * 0.04, (y2 - y1) * 0.04
    return Extent(x1 - px, y1 - py, x2 + px, y2 + py)


class Window(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__(); self.app = app; self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stac-cog")
        self.future: Future | None = None; self.pending_assets: list[Asset] = []; self.open_index = 0; self.current_box: list[float] = []
        self.viewer = Viewer(); self.viewer.set_tool(ViewerTool.PAN)
        self.bridge = EventBridge(); self.bridge.viewer_busy.connect(self.show_render_progress)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.setWindowTitle("StacCogLoad"); self.setWindowIcon(application_icon()); self.resize(1280, 820)

        central = QWidget(); root = QHBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self.viewer.qt_widget(), 1)
        panel_widget = QWidget(); panel_widget.setFixedWidth(390); panel = QVBoxLayout(panel_widget)
        title = QLabel("STAC COG streaming"); font = title.font(); font.setBold(True); title.setFont(font); panel.addWidget(title)
        form = QFormLayout(); self.catalog = QLineEdit(CATALOG); self.catalog.setReadOnly(True)
        self.collection = QComboBox(); self.collection.addItem("Sentinel-2 L2A", COLLECTION)
        self.bbox = QLineEdit("18.00, 59.25, 18.20, 59.40"); self.bbox.setPlaceholderText("xmin, ymin, xmax, ymax")
        form.addRow("Catalog", self.catalog); form.addRow("Collection", self.collection); form.addRow("BBOX", self.bbox); panel.addLayout(form)
        self.load_button = QPushButton("Search STAC and stream visual COG"); self.load_button.clicked.connect(self.run); panel.addWidget(self.load_button)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.hide(); panel.addWidget(self.progress)
        panel.addWidget(QLabel("Selected STAC item")); self.items = QListWidget(); self.items.setMaximumHeight(90); panel.addWidget(self.items)
        panel.addWidget(QLabel("Cloud diagnostics")); self.details = QTextEdit(); self.details.setReadOnly(True); panel.addWidget(self.details, 1)
        root.addWidget(panel_widget); self.setCentralWidget(central); self.add_navigation()
        self.poll = QTimer(self); self.poll.timeout.connect(self.poll_worker); self.poll.start(50)
        self.details.setPlainText("Ready. Search the STAC catalog to select COG assets.")
        QTimer.singleShot(0, self.run)

    def add_navigation(self) -> None:
        icons = Path(__file__).resolve().parent / "images"; toolbar = QToolBar("Navigation", self); toolbar.setMovable(False); toolbar.setIconSize(QSize(32, 32)); self.addToolBar(toolbar)
        for icon, text, callback in [("ZoomIn.png", "Zoom In", self.viewer.zoom_in), ("ZoomOut.png", "Zoom Out", self.viewer.zoom_out), ("FullExtent.png", "Full Extent", self.viewer.full_extent)]:
            action = QAction(QIcon(str(icons / icon)), text, self); action.triggered.connect(callback); toolbar.addAction(action)
        toolbar.addSeparator(); group = QActionGroup(toolbar); group.setExclusive(True)
        for icon, text, tool in [("RectangularZoom.png", "Zoom Box", ViewerTool.ZOOM_BOX), ("Pan.png", "Pan", ViewerTool.PAN)]:
            action = QAction(QIcon(str(icons / icon)), text, self); action.setCheckable(True); action.triggered.connect(lambda _checked=False, value=tool: self.viewer.set_tool(value)); toolbar.addAction(action); group.addAction(action)
            if tool == ViewerTool.PAN: action.setChecked(True)

    def parse_bbox(self) -> list[float] | None:
        try: values = [float(part.strip()) for part in self.bbox.text().split(",")]
        except ValueError: return None
        return values if len(values) == 4 and values[0] < values[2] and values[1] < values[3] and -180 <= values[0] <= values[2] <= 180 and -90 <= values[1] <= values[3] <= 90 else None

    def run(self) -> None:
        if self.future is not None or self.pending_assets: return
        box = self.parse_bbox()
        if box is None: QMessageBox.warning(self, "StacCogLoad", "Enter a valid WGS84 BBOX as:\nxmin, ymin, xmax, ymax"); return
        self.current_box = box; self.items.clear(); self.load_button.setEnabled(False); self.set_progress(10, "Searching the Earth Search STAC catalog...")
        self.future = self.executor.submit(search_assets, box)

    def poll_worker(self) -> None:
        if self.future is None or not self.future.done(): return
        future, self.future = self.future, None
        try:
            self.pending_assets = future.result(); self.open_index = 0; self.viewer.clear_layers(); self.set_progress(68, f"{len(self.pending_assets)} COG tiles verified. Preparing Viewer layers...")
            QTimer.singleShot(0, self.open_next_layer)
        except Exception as error: self.fail(error)

    def open_next_layer(self) -> None:
        if self.closing: return
        if self.open_index >= len(self.pending_assets): self.finish_load(); return
        asset = self.pending_assets[self.open_index]; value = 70 + (self.open_index + 1) * 25 // len(self.pending_assets)
        self.set_progress(value, f"Opening COG tile {self.open_index + 1} of {len(self.pending_assets)}...")
        try:
            self.viewer.add_layer_file(asset.path, RASTER_OPTIONS); self.items.addItem(f"{asset.tile} | {asset.datetime} | cloud {asset.cloud_cover}"); self.open_index += 1
            QTimer.singleShot(0, self.open_next_layer)
        except Exception as error: self.fail(error)

    def finish_load(self) -> None:
        assets = self.pending_assets; self.pending_assets = []
        if not self.viewer.set_coordinate_system_preset(CoordinateSystemPreset.WEB_MERCATOR): self.fail(RuntimeError("Viewer Web Mercator CRS could not be applied.")); return
        self.viewer.refresh_layers(); self.viewer.set_view_extent(web_mercator_extent(self.current_box))
        lines = ["STAC + COG streaming mosaic", "", "Catalog: Earth Search v1", f"Collection: {COLLECTION}", f"Unique MGRS tiles: {len(assets)}", ""]
        for asset in assets: lines += [f"{asset.tile} | {asset.item_id}", f"Date/time: {asset.datetime} | Cloud cover: {asset.cloud_cover}", f"Content: {asset.content_length} bytes | Range: yes", ""]
        lines.append("Only metadata and visible ranges are transferred; complete COG files are not downloaded.")
        self.details.setPlainText("\n".join(lines)); self.set_progress(100, f"{len(assets)} visual COG tiles are streaming through HTTP byte ranges."); self.load_button.setEnabled(True)

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.BUSY_CHANGED: self.bridge.viewer_busy.emit(bool(event.int_value))

    def show_render_progress(self, busy: bool) -> None:
        if not self.load_button.isEnabled(): return
        self.progress.show()
        if busy: self.progress.setRange(0, 0); self.statusBar().showMessage("Rendering map...")
        else: self.progress.setRange(0, 100); self.progress.setValue(100); self.progress.setFormat("100% — Map ready"); self.statusBar().showMessage("Map ready.")

    def set_progress(self, value: int, text: str) -> None:
        self.progress.show(); self.progress.setRange(0, 100); self.progress.setValue(max(0, min(100, value))); self.progress.setFormat(f"{value}% — {text}"); self.statusBar().showMessage(text); self.details.setPlainText(text); self.app.processEvents()

    def fail(self, error: Exception) -> None:
        self.pending_assets = []; self.progress.setRange(0, 100); self.progress.setValue(0); self.details.setPlainText(f"Load failed:\n{error}"); self.statusBar().showMessage("STAC COG load failed."); self.load_button.setEnabled(True); QMessageBox.critical(self, "StacCogLoad", str(error))

    def closeEvent(self, event) -> None:
        self.closing = True; self.poll.stop(); self.executor.shutdown(wait=False, cancel_futures=True)
        try: self.viewer.close()
        except Exception: pass
        super().closeEvent(event)


def main() -> None:
    apply_gdal_options(); app = QApplication(sys.argv); window = Window(app); window.show(); app.processEvents(); window.viewer.show(); sys.exit(app.exec())


if __name__ == "__main__": main()
