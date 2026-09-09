from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from geokernel import AI, Viewer, ViewerTool
from common import application_icon, ensure_sample_file


RASTER_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/bilbao_s2_rgbnir_2021.zip"
MODEL_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/landcover-bilbao-model.zip"

WORLD_COVER_COLORS = [
    {"code": 10, "red": 0, "green": 100, "blue": 0},
    {"code": 20, "red": 255, "green": 187, "blue": 34},
    {"code": 30, "red": 255, "green": 255, "blue": 76},
    {"code": 40, "red": 240, "green": 150, "blue": 255},
    {"code": 50, "red": 250, "green": 0, "blue": 0},
    {"code": 60, "red": 180, "green": 180, "blue": 180},
    {"code": 70, "red": 240, "green": 240, "blue": 240},
    {"code": 80, "red": 0, "green": 100, "blue": 200},
    {"code": 90, "red": 0, "green": 150, "blue": 160},
    {"code": 95, "red": 0, "green": 207, "blue": 117},
    {"code": 100, "red": 250, "green": 230, "blue": 160},
]


def output_for(raster: str) -> str:
    path = Path(raster)
    output = Path(__file__).resolve().parent / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(output / f"{path.stem}_landcover_mask_{stamp}.tif") if path.is_file() else ""


def preview_for(mask: str) -> str:
    path = Path(mask)
    return str(path.with_name(f"{path.stem}_preview.tif"))


def diagnostics(result: dict, mask: str, preview: str) -> str:
    return (
        "GeoKernel AI land-cover inference\n\n"
        f"Provider: {result.get('provider', '')}\n"
        f"Raster: {result.get('width', 0)} x {result.get('height', 0)}\n"
        f"Tiles: {result.get('processedTiles', 0)}\n"
        f"Elapsed: {result.get('elapsedMilliseconds', 0)} ms\n\n"
        f"Class mask:\n{mask}\n\n"
        f"Color preview:\n{preview}"
    )


class Bridge(QObject):
    inference_progress = Signal(int, str)


class Window(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="land-cover-inference")
        self.future: Future | None = None
        self.prediction_layer_index = -1
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.bridge = Bridge()
        self.bridge.inference_progress.connect(self.set_progress)

        self.setWindowTitle("LandCoverInference")
        self.setWindowIcon(application_icon())
        self.resize(1280, 820)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("Map ready.")

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.viewer.qt_widget(), 1)
        root.addWidget(self.create_panel())
        self.setCentralWidget(central)
        self.add_navigation()

        self.poll = QTimer(self)
        self.poll.timeout.connect(self.poll_worker)
        self.poll.start(50)
        QTimer.singleShot(0, self.prepare_samples)

    def create_panel(self) -> QWidget:
        panel_widget = QWidget()
        panel_widget.setFixedWidth(420)
        panel = QVBoxLayout(panel_widget)

        title = QLabel("Land-cover inference")
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        panel.addWidget(title)
        description = QLabel("Run a GeoKernel model package on a georeferenced RGBNIR raster.")
        description.setWordWrap(True)
        panel.addWidget(description)

        form = QFormLayout()
        self.model_path, model_browse, model_row = self.path_editor("Browse...")
        self.raster_path, raster_browse, raster_row = self.path_editor("Browse...")
        self.output_path, output_browse, output_row = self.path_editor("Browse...")
        form.addRow("Model package", model_row)
        form.addRow("Input raster", raster_row)
        form.addRow("Class mask", output_row)
        self.provider = QComboBox()
        self.provider.addItems(["Auto", "CPU", "CUDA", "DirectML"])
        form.addRow("Execution provider", self.provider)
        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        self.prediction_opacity = QSlider(Qt.Orientation.Horizontal)
        self.prediction_opacity.setRange(0, 100)
        self.prediction_opacity.setSingleStep(5)
        self.prediction_opacity.setValue(50)
        self.prediction_opacity_label = QLabel("50%")
        self.prediction_opacity_label.setFixedWidth(38)
        opacity_layout.addWidget(self.prediction_opacity, 1)
        opacity_layout.addWidget(self.prediction_opacity_label)
        form.addRow("Prediction opacity", opacity_row)
        panel.addLayout(form)

        model_browse.clicked.connect(self.browse_model)
        raster_browse.clicked.connect(self.browse_raster)
        output_browse.clicked.connect(self.browse_output)
        self.prediction_opacity.valueChanged.connect(self.apply_prediction_opacity)

        self.run_button = QPushButton("Run land-cover inference")
        self.run_button.clicked.connect(self.run)
        panel.addWidget(self.run_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        panel.addWidget(self.progress)
        panel.addWidget(QLabel("Inference diagnostics"))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText("Select a model package and an input raster.")
        panel.addWidget(self.details, 1)

        legend = QLabel()
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setWordWrap(True)
        legend.setText(
            "<b>ESA WorldCover classes</b><br>"
            "<font color='#006400'>●</font> Tree cover &nbsp; "
            "<font color='#ffbb22'>●</font> Shrubland &nbsp; "
            "<font color='#ffff4c'>●</font> Grassland<br>"
            "<font color='#f096ff'>●</font> Cropland &nbsp; "
            "<font color='#fa0000'>●</font> Built-up &nbsp; "
            "<font color='#b4b4b4'>●</font> Bare / sparse<br>"
            "<font color='#0064c8'>●</font> Permanent water"
        )
        panel.addWidget(legend)
        return panel_widget

    def prepare_samples(self) -> None:
        try:
            raster = ensure_sample_file(
                self.app, RASTER_URL, "bilbao_s2_rgbnir_2021.zip",
                "bilbao_s2_rgbnir_2021", "bilbao_s2_rgbnir_2021.tif",
                title=self.windowTitle(),
            )
            manifest = ensure_sample_file(
                self.app, MODEL_URL, "landcover-bilbao-model.zip",
                "landcover-bilbao-model", "geokernel-model.json",
                title=self.windowTitle(),
            )
            self.raster_path.setText(str(raster))
            self.model_path.setText(str(manifest.parent))
            self.output_path.setText(output_for(str(raster)))
            self.open_base_raster(str(raster))
            self.details.setPlainText("Bilbao input raster is open. Run land-cover inference to add the prediction layer.")
        except Exception as error:
            self.details.setPlainText(f"Sample preparation failed:\n{error}")
            QMessageBox.critical(self, self.windowTitle(), str(error))

    def open_base_raster(self, path: str) -> None:
        self.prediction_layer_index = -1
        self.viewer.clear_layers()
        self.viewer.add_layer_file(path)
        self.viewer.set_layer_name(0, "Bilbao RGBNIR raster")
        self.viewer.full_extent()

    def apply_prediction_opacity(self, value: int) -> None:
        self.prediction_opacity_label.setText(f"{value}%")
        if self.prediction_layer_index < 0:
            return
        self.viewer.set_layer_opacity(self.prediction_layer_index, value / 100.0)
        self.viewer.refresh_layers()

    @staticmethod
    def path_editor(text: str) -> tuple[QLineEdit, QPushButton, QWidget]:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        editor = QLineEdit()
        button = QPushButton(text)
        button.setFixedWidth(78)
        layout.addWidget(editor, 1)
        layout.addWidget(button)
        return editor, button, row

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
            ("RectangularZoom.png", "Zoom Rect", ViewerTool.ZOOM_BOX),
            ("Pan.png", "Pan", ViewerTool.PAN),
        ):
            action = QAction(QIcon(str(icons / icon)), text, self)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=tool: self.viewer.set_tool(value))
            group.addAction(action)
            toolbar.addAction(action)
            if tool == ViewerTool.PAN:
                action.setChecked(True)

    def browse_model(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select GeoKernel model package", self.model_path.text())
        if path:
            self.model_path.setText(path)

    def browse_raster(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select input raster", self.raster_path.text(), "GeoTIFF (*.tif *.tiff)")
        if path:
            self.raster_path.setText(path)
            self.output_path.setText(output_for(path))
            self.open_base_raster(path)

    def browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save class mask", self.output_path.text(), "GeoTIFF (*.tif)")
        if path:
            self.output_path.setText(path)

    def run(self) -> None:
        if self.future is not None:
            return
        model = self.model_path.text().strip()
        raster = self.raster_path.text().strip()
        mask = self.output_path.text().strip()
        if not Path(model).is_dir() or not Path(raster).is_file():
            QMessageBox.warning(self, self.windowTitle(), "Select an existing model package and input raster.")
            return
        if not mask:
            QMessageBox.warning(self, self.windowTitle(), "Select a class-mask output path.")
            return

        self.run_button.setEnabled(False)
        self.set_progress(0, "Opening model package...")
        self.details.setPlainText("Validating the model package and preparing tiled inference...")
        request = {
            "modelPackagePath": model,
            "rasterPath": raster,
            "outputPath": mask,
            "previewOutputPath": preview_for(mask),
            "applyManifestClassCodes": True,
            "classPalette": WORLD_COVER_COLORS,
            "bands": [1, 2, 3, 4],
            "provider": self.provider.currentText().lower(),
            "outputMode": "classMask",
        }
        self.future = self.executor.submit(self.infer, request)

    def infer(self, request: dict) -> tuple[dict, str, str]:
        ai = AI()
        result = ai.run_raster_inference(
            request,
            lambda state: self.bridge.inference_progress.emit(
                int(state.get("percent", 0)), str(state.get("message", ""))
            ),
        )
        return result, str(request["outputPath"]), str(request["previewOutputPath"])

    def poll_worker(self) -> None:
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        try:
            result, mask, preview = future.result()
            self.set_progress(95, "Opening color preview...")
            self.viewer.remove_layer_by_name("Land-cover prediction")
            self.viewer.add_layer_file(preview)
            self.prediction_layer_index = 0
            self.viewer.set_layer_name(self.prediction_layer_index, "Land-cover prediction")
            self.viewer.set_layer_opacity(
                self.prediction_layer_index, self.prediction_opacity.value() / 100.0
            )
            self.viewer.refresh_layers()
            self.details.setPlainText(diagnostics(result, mask, preview))
            self.set_progress(100, "Inference complete")
            self.statusBar().showMessage(
                f"Land-cover mask created in {result.get('elapsedMilliseconds', 0)} ms."
            )
        except Exception as error:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("Inference failed")
            self.details.setPlainText(f"Inference failed:\n{error}")
            QMessageBox.critical(self, self.windowTitle(), str(error))
        finally:
            self.run_button.setEnabled(True)

    def set_progress(self, value: int, text: str) -> None:
        value = max(0, min(100, value))
        self.progress.setRange(0, 100)
        self.progress.setValue(value)
        self.progress.setFormat(f"{value}% — {text}")
        self.statusBar().showMessage(text)

    def closeEvent(self, event) -> None:
        self.closing = True
        self.poll.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
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
