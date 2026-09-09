import shutil
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Viewer, ViewerTool
from common import application_icon, ensure_sample_file

class RasterOverviewWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.source_raster_path: Path | None = None
        self.current_mode = "Reset"
        self.current_elapsed_ms = 0
        self.last_benchmark: dict | None = None
        self.without_overview_benchmark: dict | None = None
        self.with_overview_benchmark: dict | None = None
        self.initialized = False

        self.setWindowTitle("RasterOverview")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_ui()

    def create_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        command_bar = QWidget(root)
        command_layout = QHBoxLayout(command_bar)
        command_layout.setContentsMargins(6, 4, 6, 4)
        command_layout.setSpacing(8)

        reset_button = QPushButton("Reset Working Copy", command_bar)
        reset_button.clicked.connect(self.reset_working_copy)
        command_layout.addWidget(reset_button)

        without_button = QPushButton("Load Without Overview", command_bar)
        without_button.clicked.connect(self.load_without_overview)
        command_layout.addWidget(without_button)

        with_button = QPushButton("Load With Overview", command_bar)
        with_button.clicked.connect(self.load_with_overview)
        command_layout.addWidget(with_button)

        benchmark_button = QPushButton("Run Downsample Benchmark", command_bar)
        benchmark_button.clicked.connect(self.run_benchmark)
        command_layout.addWidget(benchmark_button)

        full_extent_button = QPushButton("Full Extent", command_bar)
        full_extent_button.clicked.connect(self.viewer.full_extent)
        command_layout.addWidget(full_extent_button)
        command_layout.addStretch()

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(content)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(420)
        content_layout.addWidget(self.details_view)

        status_panel = QWidget(root)
        status_layout = QHBoxLayout(status_panel)
        status_layout.setContentsMargins(6, 3, 6, 3)
        self.status_label = QLabel("Ready.", status_panel)
        status_layout.addWidget(self.status_label, 1)

        self.progress_bar = QProgressBar(status_panel)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(240)
        status_layout.addWidget(self.progress_bar)

        root_layout.addWidget(command_bar)
        root_layout.addWidget(content, 1)
        root_layout.addWidget(status_panel)
        self.setCentralWidget(root)

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
            self.source_raster_path = ensure_sample_file(
                app=self.app,
                zip_url=(
                    "https://github.com/geokernel-io/GeoKernel.SampleData/"
                    "releases/download/v1/world_8km_tif.zip"
                ),
                zip_name="world_8km_tif.zip",
                target_folder="world_8km_tif",
                required_file="world_8km.tif",
                title="RasterOverview",
            )
            self.reset_working_copy()
        except Exception as error:
            QMessageBox.critical(
                self,
                "RasterOverview",
                f"Sample data could not be prepared:\n{error}",
            )

    def working_directory(self) -> Path:
        return Path(__file__).resolve().parent / "RasterOverviewData"

    def working_raster_path(self) -> Path:
        return self.working_directory() / "world_8km_overview_test.tif"

    def overview_path(self) -> Path:
        return Path(str(self.working_raster_path()) + ".ovr")

    def reset_working_copy(self) -> None:
        if self.source_raster_path is None:
            return

        try:
            self.viewer.clear_layers()
            self.progress_bar.setValue(0)
            self.working_directory().mkdir(parents=True, exist_ok=True)
            self.working_raster_path().unlink(missing_ok=True)
            self.overview_path().unlink(missing_ok=True)
            shutil.copy2(self.source_raster_path, self.working_raster_path())

            self.current_mode = "Reset"
            self.current_elapsed_ms = 0
            self.last_benchmark = None
            self.without_overview_benchmark = None
            self.with_overview_benchmark = None
            self.update_details()
            self.status_label.setText("Working copy reset. Overview file removed.")
        except Exception as error:
            QMessageBox.critical(self, "RasterOverview", str(error))
            self.status_label.setText("Reset failed.")

    def load_without_overview(self) -> None:
        self.load_raster(False)

    def load_with_overview(self) -> None:
        self.load_raster(True)

    def load_raster(self, prepare_overview: bool) -> None:
        if self.source_raster_path is None:
            return
        if not self.working_raster_path().exists():
            self.reset_working_copy()
        if not self.working_raster_path().exists():
            return

        mode = "Load With Overview" if prepare_overview else "Load Without Overview"
        options = {
            "prepareRasterOverviews": prepare_overview,
            "rasterOverviewMinimumPixels": 0 if prepare_overview else 2**63 - 1,
            "rasterOverviewResampling": "AVERAGE",
        }

        self.viewer.clear_layers()
        self.progress_bar.setValue(0)
        self.status_label.setText(mode)
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        started = time.perf_counter()

        try:
            self.viewer.add_layer_file_with_callbacks(
                self.working_raster_path(),
                options,
                progress=self.on_load_progress,
            )
            self.current_elapsed_ms = round((time.perf_counter() - started) * 1000)
            self.viewer.set_layer_name(
                0,
                "GeoTIFF - Overview" if prepare_overview else "GeoTIFF - No Overview",
            )
            self.viewer.full_extent()
            self.progress_bar.setValue(100)
            self.current_mode = mode
            self.last_benchmark = None
            self.status_label.setText(
                f"{mode} finished in {self.current_elapsed_ms} ms."
            )
            self.update_details()
        except Exception as error:
            self.current_elapsed_ms = round((time.perf_counter() - started) * 1000)
            self.current_mode = mode
            self.status_label.setText("Load failed.")
            QMessageBox.critical(
                self,
                "RasterOverview",
                f"Raster could not be loaded:\n{error}",
            )
            self.update_details()
        finally:
            QApplication.restoreOverrideCursor()

    def on_load_progress(self, value: int, message: str) -> None:
        self.progress_bar.setValue(max(0, min(100, value)))
        if message:
            self.status_label.setText(message)
        QApplication.processEvents()

    def run_benchmark(self) -> None:
        if self.viewer.layer_count() == 0:
            self.status_label.setText("Load a raster first.")
            return

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self.status_label.setText("Running downsample benchmark...")
        QApplication.processEvents()

        try:
            diagnostics = self.viewer.raster_overview_diagnostics(0, True)
            benchmark = diagnostics.get("benchmark", {})
            self.last_benchmark = benchmark
            if self.current_mode == "Load Without Overview":
                self.without_overview_benchmark = benchmark
            elif self.current_mode == "Load With Overview":
                self.with_overview_benchmark = benchmark

            comparison = self.comparison_text()
            self.status_label.setText(comparison or self.benchmark_text(benchmark))
            self.update_details(diagnostics)
        except Exception as error:
            self.status_label.setText(f"Benchmark failed: {error}")
        finally:
            QApplication.restoreOverrideCursor()

    def update_details(self, diagnostics: dict | None = None) -> None:
        if diagnostics is None and self.viewer.layer_count() > 0:
            diagnostics = self.viewer.raster_overview_diagnostics(0, False)
        diagnostics = diagnostics or {}

        raster_size = (
            self.working_raster_path().stat().st_size
            if self.working_raster_path().exists()
            else 0
        )
        overview_size = (
            self.overview_path().stat().st_size if self.overview_path().exists() else 0
        )
        overview_dimensions = self.overview_dimensions_text(diagnostics)
        factors = self.factor_text(diagnostics.get("overviewFactors", []))
        recommended = self.factor_text(
            diagnostics.get("recommendedOverviewFactors", [])
        )

        lines = [
            "RasterOverview sample",
            "",
            f"Load mode: {self.current_mode}",
            f"Load elapsed: {self.current_elapsed_ms} ms",
            f"Working raster: {self.working_raster_path()}",
            f"Raster file size: {raster_size} bytes",
            f"Overview file: {self.overview_path()}",
            f"Overview file exists: {'yes' if self.overview_path().exists() else 'no'}",
            f"Overview file size: {overview_size} bytes",
            "",
        ]

        if diagnostics:
            lines.extend(
                [
                    "Raster metadata",
                    f"Driver: {diagnostics.get('driverName', 'unknown')}",
                    f"Size: {diagnostics.get('width', 0)} x "
                    f"{diagnostics.get('height', 0)} px",
                    f"Pixels: {diagnostics.get('width', 0) * diagnostics.get('height', 0)}",
                    f"Bands: {diagnostics.get('bandCount', 0)}",
                    f"EPSG: {diagnostics.get('epsgCode') or 'unknown'}",
                    "",
                    "Provider overview state",
                    "Provider overview path: "
                    + str(diagnostics.get("overviewFilePath", "")),
                    "Recommended pyramid ready: "
                    + ("yes" if diagnostics.get("recommendedPyramidReady") else "no"),
                    f"Overview count: {len(diagnostics.get('overviews', []))}",
                    f"Overview dimensions: {overview_dimensions}",
                    f"Overview factors: {factors}",
                    f"Recommended factors: {recommended}",
                    "",
                ]
            )
        else:
            lines.extend(["No raster layer loaded.", ""])

        lines.extend(
            [
                "LayerLoadOptions knobs",
                "prepareRasterOverviews = true/false",
                "rasterOverviewMinimumPixels = threshold",
                "rasterOverviewResampling = AVERAGE",
                "",
                "Why overviews matter",
                "- Without overview, GDAL reads full-resolution raster data.",
                "- With overview, GDAL can read a smaller pyramid level.",
                "- selectedOverview=-1 means no pyramid level was used.",
                "- selectedOverview>=0 means a pyramid level was used.",
                "",
                "Benchmark",
                self.benchmark_text(self.last_benchmark),
            ]
        )
        comparison = self.comparison_text()
        if comparison:
            lines.append(comparison)
        self.details_view.setPlainText("\n".join(lines))

    def overview_dimensions_text(self, diagnostics: dict) -> str:
        overviews = diagnostics.get("overviews", [])
        if not overviews:
            return "-"
        return ", ".join(
            f"{overview.get('width', 0)}x{overview.get('height', 0)}"
            for overview in overviews
        )

    def factor_text(self, factors: list) -> str:
        return ", ".join(str(factor) for factor in factors) if factors else "-"

    def benchmark_text(self, benchmark: dict | None) -> str:
        if not benchmark:
            return "Run Downsample Benchmark after loading a raster."
        if not benchmark.get("valid"):
            return "Benchmark failed: " + str(benchmark.get("errorMessage", "unknown"))
        return (
            f"{self.current_mode} zoomed-out benchmark: "
            f"{benchmark['passes']} reads to "
            f"{benchmark['targetWidth']}x{benchmark['targetHeight']}, "
            f"selected overview={benchmark['selectedOverview']}, "
            f"elapsed={benchmark['elapsedMs']} ms"
        )

    def comparison_text(self) -> str:
        without = self.without_overview_benchmark
        with_overview = self.with_overview_benchmark
        if not without or not with_overview:
            return ""
        if not without.get("valid") or not with_overview.get("valid"):
            return ""
        without_ms = int(without.get("elapsedMs", 0))
        with_ms = int(with_overview.get("elapsedMs", 0))
        if without_ms <= 0:
            return ""

        saved_ms = without_ms - with_ms
        if saved_ms <= 0:
            return (
                "Comparison: overview did not win on this run "
                f"({without_ms} ms without, {with_ms} ms with)."
            )
        percent = saved_ms / without_ms * 100.0
        return (
            f"Comparison: overview saved {saved_ms} ms ({percent:.1f}% faster) "
            f"for this zoomed-out read ({without_ms} ms without, "
            f"{with_ms} ms with)."
        )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("RasterOverview")
    app.setWindowIcon(application_icon())
    window = RasterOverviewWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
