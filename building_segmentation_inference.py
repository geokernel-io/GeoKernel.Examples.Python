from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QTextEdit,
    QToolBar, QVBoxLayout, QWidget,
)

from geokernel import AnalysisExecutor, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file


RASTER_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/buildings.zip"
MODEL_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/buildings-model.zip"


def labels_for(raster: str) -> str:
    path = Path(raster)
    return str(path.with_name(f"{path.stem}_building_instances.tif")) if path.is_file() else ""


class Bridge(QObject):
    inference_progress = Signal(int, str)
    drawing_progress = Signal(int, str)
    viewer_busy = Signal(bool)


class Window(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="building-segmentation")
        self.future: Future | None = None
        self.prediction_layer = None
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.bridge = Bridge()
        self.bridge.inference_progress.connect(self.set_progress)
        self.bridge.drawing_progress.connect(self.show_drawing_progress)
        self.bridge.viewer_busy.connect(self.show_viewer_busy)
        self.viewer.set_event_callback(self.on_viewer_event)

        self.setWindowTitle("BuildingSegmentationInference")
        self.setWindowIcon(application_icon())
        self.resize(1280, 850)

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
        widget = QWidget()
        widget.setFixedWidth(420)
        panel = QVBoxLayout(widget)

        title = QLabel("Building segmentation inference")
        font = title.font(); font.setBold(True); title.setFont(font)
        panel.addWidget(title)
        description = QLabel("Run a GeoKernel model package on a georeferenced RGB raster.")
        description.setWordWrap(True)
        panel.addWidget(description)

        form = QFormLayout()
        self.model_path, model_button, model_row = self.path_editor()
        self.raster_path, raster_button, raster_row = self.path_editor()
        self.label_path, label_button, label_row = self.path_editor()
        form.addRow("Model package", model_row)
        form.addRow("Input raster", raster_row)
        form.addRow("Instance labels", label_row)
        self.provider = QComboBox()
        self.provider.addItems(["Auto", "CPU", "CUDA", "DirectML"])
        form.addRow("Execution provider", self.provider)
        panel.addLayout(form)

        model_button.clicked.connect(self.browse_model)
        raster_button.clicked.connect(self.browse_raster)
        label_button.clicked.connect(self.browse_labels)

        self.run_button = QPushButton("Run building segmentation inference")
        self.run_button.clicked.connect(self.run)
        panel.addWidget(self.run_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        panel.addWidget(self.progress)
        panel.addWidget(QLabel("Inference diagnostics"))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText("Preparing the buildings sample...")
        panel.addWidget(self.details, 1)

        legend = QLabel(
            "<b>Building segmentation classes</b><br>"
            "Background &nbsp; <font color='#ff3b30'>●</font> Building"
        )
        legend.setTextFormat(Qt.TextFormat.RichText)
        panel.addWidget(legend)
        return widget

    def prepare_samples(self) -> None:
        self.run_button.setEnabled(False)
        try:
            raster = ensure_sample_file(
                self.app, RASTER_URL, "buildings.zip", "buildings", "buildings.tif",
                title=self.windowTitle(),
            )
            manifest = ensure_sample_file(
                self.app, MODEL_URL, "buildings-model.zip", "buildings-model",
                "geokernel-model.json", title=self.windowTitle(),
            )
            self.raster_path.setText(str(raster))
            self.model_path.setText(str(manifest.parent))
            self.label_path.setText(labels_for(str(raster)))
            self.open_base_raster(str(raster))
            self.details.setPlainText(
                "The buildings raster and ONNX model package are ready. "
                "Run inference to add building polygons."
            )
        except Exception as error:
            self.details.setPlainText(f"Sample preparation failed:\n{error}")
            QMessageBox.critical(self, self.windowTitle(), str(error))
        finally:
            self.run_button.setEnabled(True)

    def open_base_raster(self, raster: str) -> None:
        if self.prediction_layer is not None:
            self.prediction_layer.close()
            self.prediction_layer = None
        self.viewer.clear_layers()
        self.viewer.add_layer_file(raster)
        self.viewer.set_layer_name(0, "Buildings RGB source")
        self.viewer.refresh_layers()
        self.viewer.full_extent()

    @staticmethod
    def path_editor() -> tuple[QLineEdit, QPushButton, QWidget]:
        row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0)
        editor = QLineEdit(); button = QPushButton("Browse..."); button.setFixedWidth(78)
        layout.addWidget(editor, 1); layout.addWidget(button)
        return editor, button, row

    def add_navigation(self) -> None:
        icons = Path(__file__).resolve().parent / "images"
        toolbar = QToolBar("Navigation", self); toolbar.setMovable(False); toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)
        for icon, text, callback in (
            ("ZoomIn.png", "Zoom In", self.viewer.zoom_in),
            ("ZoomOut.png", "Zoom Out", self.viewer.zoom_out),
            ("FullExtent.png", "Full Extent", self.viewer.full_extent),
        ):
            action = QAction(QIcon(str(icons / icon)), text, self); action.triggered.connect(callback); toolbar.addAction(action)
        toolbar.addSeparator(); group = QActionGroup(toolbar); group.setExclusive(True)
        for icon, text, tool in (
            ("RectangularZoom.png", "Zoom Rect", ViewerTool.ZOOM_BOX),
            ("Pan.png", "Pan", ViewerTool.PAN),
        ):
            action = QAction(QIcon(str(icons / icon)), text, self); action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=tool: self.viewer.set_tool(value))
            group.addAction(action); toolbar.addAction(action)
            if tool == ViewerTool.PAN: action.setChecked(True)

    def browse_model(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select GeoKernel model package", self.model_path.text())
        if path: self.model_path.setText(path)

    def browse_raster(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select input raster", self.raster_path.text(), "GeoTIFF (*.tif *.tiff)")
        if path:
            self.raster_path.setText(path)
            self.label_path.setText(labels_for(path))
            self.open_base_raster(path)

    def browse_labels(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save instance labels", self.label_path.text(), "GeoTIFF (*.tif)")
        if path: self.label_path.setText(path)

    def run(self) -> None:
        if self.future is not None: return
        if not hasattr(AnalysisExecutor, "run_ai_instance_vectorization_to_memory"):
            QMessageBox.critical(
                self,
                self.windowTitle(),
                "This sample requires geokernel 1.5.7 or newer. "
                "The installed package does not expose in-memory AI instance vectorization.",
            )
            self.details.setPlainText(
                "Incompatible GeoKernel Python package.\n"
                "Install geokernel 1.5.7 or newer and restart the sample."
            )
            return
        model, raster, labels = self.model_path.text().strip(), self.raster_path.text().strip(), self.label_path.text().strip()
        if not Path(model).is_dir() or not Path(raster).is_file():
            QMessageBox.warning(self, self.windowTitle(), "Select an existing model package and input raster."); return
        if not labels:
            QMessageBox.warning(self, self.windowTitle(), "Select an instance-label output path."); return
        self.run_button.setEnabled(False)
        self.set_progress(0, "Preparing building segmentation...")
        self.details.setPlainText("Validating the model package and preparing instance vectorization...")
        request = {
            "modelPackagePath": model, "rasterPath": raster, "labelRasterPath": labels,
            "provider": self.provider.currentText(), "layerName": "building_predictions",
            "instanceIdField": "instance_id", "connectivity": 4,
        }
        self.future = self.executor.submit(self.vectorize, request)

    def vectorize(self, request: dict):
        analysis = AnalysisExecutor()
        layer = analysis.run_ai_instance_vectorization_to_memory(
            request, lambda percent, message: self.bridge.inference_progress.emit(percent, message)
        )
        return layer, layer.diagnostics, str(request["rasterPath"]), str(request["labelRasterPath"])

    def poll_worker(self) -> None:
        if self.future is None or not self.future.done(): return
        future, self.future = self.future, None
        try:
            layer, result, raster, labels = future.result()
            self.set_progress(95, "Opening source and prediction overlay...")
            if self.prediction_layer is not None: self.prediction_layer.close()
            self.prediction_layer = layer
            self.viewer.clear_layers()
            self.viewer.add_layer_file(raster)
            layer.add_to(self.viewer)
            self.viewer.set_layer_style(0, {
                "fillColor": "#FF3B30", "fillOpacity": 125,
                "lineColor": "#C5160A", "lineWidth": 1.8,
            })
            self.viewer.refresh_layers(); self.viewer.full_extent()
            count = int(result.get("materializedCount", 0))
            self.details.setPlainText(
                "GeoKernel AI building segmentation inference\n\n"
                f"Provider: {self.provider.currentText()}\nBuilding polygons: {count}\n\n"
                f"Instance labels:\n{labels}\n\nVector output: in-memory layer"
            )
            self.set_progress(100, "Inference complete")
            self.statusBar().showMessage(f"Building mask and {count} vector polygons created.")
        except Exception as error:
            self.progress.setRange(0, 100); self.progress.setValue(0); self.progress.setFormat("Inference failed")
            self.details.setPlainText(f"Inference failed:\n{error}")
            QMessageBox.critical(self, self.windowTitle(), str(error))
        finally:
            self.run_button.setEnabled(True)

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.DRAWING_PROGRESS_CHANGED:
            self.bridge.drawing_progress.emit(int(event.int_value), str(event.text or "Rendering map..."))
        elif event.event_type == ViewerEventType.BUSY_CHANGED:
            self.bridge.viewer_busy.emit(bool(event.int_value))

    def show_drawing_progress(self, value: int, text: str) -> None:
        if self.run_button.isEnabled(): self.set_progress(value, text or "Rendering map...")

    def show_viewer_busy(self, busy: bool) -> None:
        if not self.run_button.isEnabled(): return
        if busy: self.progress.setRange(0, 0); self.statusBar().showMessage("Rendering map...")
        else: self.set_progress(100, "Map ready")

    def set_progress(self, value: int, text: str) -> None:
        value = max(0, min(100, value)); self.progress.setRange(0, 100); self.progress.setValue(value)
        self.progress.setFormat(f"{value}% — {text}"); self.statusBar().showMessage(text)

    def closeEvent(self, event) -> None:
        self.poll.stop(); self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            if self.prediction_layer is not None: self.prediction_layer.close()
            self.viewer.set_event_callback(None); self.viewer.close()
        except Exception: pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv); window = Window(app); window.show(); app.processEvents(); window.viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
