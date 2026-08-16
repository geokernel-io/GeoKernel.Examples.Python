import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)
from geokernel import Viewer, ViewerTool
from common import application_icon, ensure_sample_file


MODES = {
    "Cache Disabled": (False, 0, 0),
    "Small Cache Budget": (True, 128 * 1024, 128 * 1024),
    "Large Cache Budget": (True, 4 * 1024 * 1024, 512 * 512),
}


class RasterTileCacheWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.raster_path: Path | None = None
        self.current_mode = "No Raster Loaded"
        self.last_benchmark: dict | None = None
        self.initialized = False
        self.setWindowTitle("RasterTileCache")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_ui()

    def create_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        toolbar = QWidget(root)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(8)
        actions = (
            ("Load Cache Disabled", lambda: self.load_raster("Cache Disabled")),
            ("Load Small Budget", lambda: self.load_raster("Small Cache Budget")),
            ("Load Large Budget", lambda: self.load_raster("Large Cache Budget")),
            ("Run Tile Benchmark", self.run_benchmark),
            ("Clear Tile Cache", self.clear_cache),
            ("Full Extent", self.viewer.full_extent),
        )
        for text, callback in actions:
            button = QPushButton(text, toolbar)
            button.clicked.connect(callback)
            toolbar_layout.addWidget(button)
        toolbar_layout.addStretch()

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.details = QTextEdit(content)
        self.details.setReadOnly(True)
        self.details.setMinimumWidth(430)
        content_layout.addWidget(self.viewer_widget, 1)
        content_layout.addWidget(self.details)

        status = QWidget(root)
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(6, 3, 6, 3)
        self.status_label = QLabel("Ready.", status)
        self.progress_bar = QProgressBar(status)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedWidth(240)
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.progress_bar)

        root_layout.addWidget(toolbar)
        root_layout.addWidget(content, 1)
        root_layout.addWidget(status)
        self.setCentralWidget(root)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.update_details()
        try:
            self.status_label.setText("Preparing sample data...")
            self.raster_path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_8km_tif.zip",
                "world_8km_tif.zip", "world_8km_tif", "world_8km.tif",
                "RasterTileCache",
            )
            self.load_raster("Large Cache Budget")
        except Exception as error:
            self.status_label.setText("Load failed.")
            QMessageBox.critical(self, "RasterTileCache", str(error))

    def load_raster(self, mode: str) -> None:
        if self.raster_path is None:
            return
        enabled, pixel_budget, maximum_item_pixels = MODES[mode]
        self.current_mode = mode
        self.last_benchmark = None
        self.viewer.clear_layers()
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Loading {mode}...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.viewer.add_layer(
                str(self.raster_path),
                {
                    "prepareRasterOverviews": True,
                    "rasterOverviewMinimumPixels": 0,
                    "rasterTileCacheEnabled": enabled,
                    "rasterTileCachePixelBudget": pixel_budget,
                    "rasterTileCacheMaximumItemPixels": maximum_item_pixels,
                },
            )
            layer_index = self.viewer.layer_count() - 1
            if layer_index < 0:
                raise RuntimeError("Raster layer was not added.")
            self.viewer.set_layer_name(layer_index, mode)
            self.viewer.full_extent()
            self.progress_bar.setValue(100)
            self.status_label.setText(f"{mode} loaded.")
            self.update_details()
        except Exception as error:
            self.status_label.setText("Load failed.")
            self.update_details()
            QMessageBox.critical(self, "RasterTileCache", f"Raster could not be loaded:\n{error}")
        finally:
            QApplication.restoreOverrideCursor()

    def diagnostics(self, run_benchmark: bool = False, clear_cache: bool = False) -> dict:
        if self.viewer.layer_count() == 0:
            raise RuntimeError("Load a raster first.")
        return self.viewer.raster_tile_cache_diagnostics(0, run_benchmark, clear_cache)

    def run_benchmark(self) -> None:
        try:
            self.status_label.setText("Running tile cache benchmark...")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            result = self.diagnostics(run_benchmark=True)
            self.last_benchmark = result.get("benchmark")
            self.update_details(result)
            benchmark = self.last_benchmark or {}
            self.status_label.setText(
                f"Second pass: {benchmark.get('secondPassMs', '-')} ms, "
                f"cache hits={benchmark.get('secondPassHits', '-')}."
            )
        except Exception as error:
            self.status_label.setText("Benchmark failed.")
            QMessageBox.critical(self, "RasterTileCache", str(error))
        finally:
            QApplication.restoreOverrideCursor()

    def clear_cache(self) -> None:
        try:
            result = self.diagnostics(clear_cache=True)
            self.last_benchmark = None
            self.status_label.setText("Memory tile cache cleared.")
            self.update_details(result)
        except Exception as error:
            QMessageBox.critical(self, "RasterTileCache", str(error))

    def update_details(self, diagnostics: dict | None = None) -> None:
        if diagnostics is None and self.viewer.layer_count() > 0:
            try:
                diagnostics = self.diagnostics()
            except Exception:
                diagnostics = None
        source = str(self.raster_path) if self.raster_path else "-"
        lines = [
            "RasterTileCache sample", "", f"Load mode: {self.current_mode}",
            f"Source: {source}", "",
        ]
        if diagnostics is None:
            lines.append("No raster layer loaded.")
        else:
            lines.extend([
                "Raster metadata",
                f"Driver: {diagnostics.get('driverName', '-')}",
                f"Size: {diagnostics.get('width', '-')} x {diagnostics.get('height', '-')} px",
                f"Bands: {diagnostics.get('bandCount', '-')}",
                f"Overview count: {diagnostics.get('overviewCount', '-')}", "",
                "Cache stats",
                f"Enabled: {diagnostics.get('enabled', '-')}",
                f"Items: {diagnostics.get('itemCount', '-')}",
                f"Used pixel cost: {diagnostics.get('usedPixelCost', '-')}",
                f"Max pixel cost: {diagnostics.get('maxPixelCost', '-')}",
                f"Max item pixel cost: {diagnostics.get('maxItemPixelCost', '-')}", "",
                "LayerLoadOptions knobs", "rasterTileCacheEnabled",
                "rasterTileCachePixelBudget", "rasterTileCacheMaximumItemPixels", "",
            ])
            lines.extend(self.benchmark_lines())
        self.details.setPlainText("\n".join(lines))

    def benchmark_lines(self) -> list[str]:
        benchmark = self.last_benchmark
        if not benchmark:
            return ["Benchmark has not run."]
        return [
            "Benchmark", f"Tiles read per pass: {benchmark.get('tileCount', '-')}",
            f"First pass: {benchmark.get('firstPassMs', '-')} ms, "
            f"cache hits={benchmark.get('firstPassHits', '-')}, "
            f"overview={benchmark.get('firstPassOverviewLevel', '-')}",
            f"Second pass: {benchmark.get('secondPassMs', '-')} ms, "
            f"cache hits={benchmark.get('secondPassHits', '-')}, "
            f"overview={benchmark.get('secondPassOverviewLevel', '-')}", "",
            "How to read this", "- First pass fills the memory tile cache.",
            "- Second pass requests the same tiles again.",
            "- With a large budget, second-pass cache hits should equal tile count.",
            "- With cache disabled, second-pass hits stay at 0.",
            "- With a tiny budget, only the last few tiles survive in cache.",
        ]

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = RasterTileCacheWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
