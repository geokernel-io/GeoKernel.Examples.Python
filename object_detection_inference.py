from __future__ import annotations

import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

PROJECTS_ROOT = Path(__file__).resolve().parent.parent
LOCAL_BINDINGS = PROJECTS_ROOT / "GeoKernel.Python" / "src"
if LOCAL_BINDINGS.is_dir():
    sys.path.insert(0, str(LOCAL_BINDINGS))
os.environ["GEOKERNEL_BIN"] = str(PROJECTS_ROOT / "GeoKernel" / "outputs" / "build" / "Release")

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QTextEdit,
    QToolBar, QVBoxLayout, QWidget,
)

from geokernel import AnalysisExecutor, Viewer, ViewerTool
from common import application_icon, ensure_sample_file


IMAGES_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/object_detection_images.zip"
MODEL_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/object_detection_model.zip"
CLASSES = [
    (1, "airplane", "#E53935"), (2, "ship", "#1E88E5"),
    (3, "storage_tank", "#FB8C00"), (4, "baseball_diamond", "#43A047"),
    (5, "tennis_court", "#8E24AA"), (6, "basketball_court", "#D81B60"),
    (7, "ground_track_field", "#00ACC1"), (8, "harbor", "#FDD835"),
    (9, "bridge", "#3949AB"), (10, "vehicle", "#6D4C41"),
]


def detection_style(color: str = "#FF4020") -> dict:
    return {
        "fillColor": color, "fillOpacity": 90, "lineColor": color, "lineWidth": 1.5,
        "showLabels": True, "labelField": "label", "labelFontSize": 11,
        "labelColor": "#FFFFFF", "labelHaloEnabled": True,
        "labelHaloColor": "#202020", "labelHaloWidth": 2, "labelAllowOverlap": True,
    }


class Bridge(QObject):
    progress = Signal(int, str)


class Window(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__(); self.app = app
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="object-detection")
        self.future: Future | None = None; self.detection_layer = None
        self.images: list[Path] = []; self.image_index = -1
        self.viewer = Viewer(); self.viewer.set_tool(ViewerTool.PAN)
        self.bridge = Bridge(); self.bridge.progress.connect(self.set_progress)
        self.setWindowTitle("ObjectDetectionInference"); self.setWindowIcon(application_icon()); self.resize(1280, 850)
        central = QWidget(); root = QHBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self.viewer.qt_widget(), 1); root.addWidget(self.create_panel()); self.setCentralWidget(central)
        self.add_navigation(); self.poll = QTimer(self); self.poll.timeout.connect(self.poll_worker); self.poll.start(50)
        QTimer.singleShot(0, self.prepare_samples)

    def create_panel(self) -> QWidget:
        widget = QWidget(); widget.setFixedWidth(430); panel = QVBoxLayout(widget)
        title = QLabel("NWPU-VHR-10 object detection"); font = title.font(); font.setBold(True); title.setFont(font); panel.addWidget(title)
        description = QLabel("Run the GeoKernel ONNX model and draw class-labelled bounding boxes as an on-the-fly layer.")
        description.setWordWrap(True); panel.addWidget(description)
        form = QFormLayout(); self.model_path, mb, mr = self.path_editor(); self.raster_path, rb, rr = self.path_editor()
        form.addRow("Model package", mr); form.addRow("Input image", rr); self.provider = QComboBox(); self.provider.addItems(["Auto", "CPU", "CUDA", "DirectML"]); form.addRow("Execution provider", self.provider); panel.addLayout(form)
        mb.clicked.connect(self.browse_model); rb.clicked.connect(self.browse_raster)
        nav = QHBoxLayout(); self.previous = QPushButton("Previous image"); self.position = QLabel("No sample images"); self.position.setAlignment(Qt.AlignmentFlag.AlignCenter); self.next = QPushButton("Next image")
        self.previous.clicked.connect(lambda: self.select_image(self.image_index - 1)); self.next.clicked.connect(lambda: self.select_image(self.image_index + 1)); nav.addWidget(self.previous); nav.addWidget(self.position, 1); nav.addWidget(self.next); panel.addLayout(nav)
        self.run_button = QPushButton("Run object detection inference"); self.run_button.clicked.connect(self.run); panel.addWidget(self.run_button)
        self.progress = QProgressBar(); panel.addWidget(self.progress); panel.addWidget(QLabel("Inference diagnostics")); self.details = QTextEdit(); self.details.setReadOnly(True); self.details.setPlainText("Preparing sample files..."); panel.addWidget(self.details, 1)
        legend = QLabel("<b>NWPU-VHR-10 classes</b><br>" + " &nbsp; ".join(f"<font color='{color}'>■</font> {name}" for _, name, color in CLASSES)); legend.setTextFormat(Qt.TextFormat.RichText); legend.setWordWrap(True); panel.addWidget(legend)
        return widget

    @staticmethod
    def path_editor():
        row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0); editor = QLineEdit(); button = QPushButton("Browse..."); button.setFixedWidth(78); layout.addWidget(editor, 1); layout.addWidget(button); return editor, button, row

    def add_navigation(self) -> None:
        icons = Path(__file__).resolve().parent / "images"; toolbar = QToolBar("Navigation", self); toolbar.setMovable(False); toolbar.setIconSize(QSize(32, 32)); self.addToolBar(toolbar)
        for icon, text, callback in (("ZoomIn.png", "Zoom In", self.viewer.zoom_in), ("ZoomOut.png", "Zoom Out", self.viewer.zoom_out), ("FullExtent.png", "Full Extent", self.viewer.full_extent)):
            action = QAction(QIcon(str(icons / icon)), text, self); action.triggered.connect(callback); toolbar.addAction(action)
        toolbar.addSeparator(); group = QActionGroup(toolbar); group.setExclusive(True)
        for icon, text, tool in (("RectangularZoom.png", "Zoom Rect", ViewerTool.ZOOM_BOX), ("Pan.png", "Pan", ViewerTool.PAN)):
            action = QAction(QIcon(str(icons / icon)), text, self); action.setCheckable(True); action.triggered.connect(lambda _=False, value=tool: self.viewer.set_tool(value)); group.addAction(action); toolbar.addAction(action); action.setChecked(tool == ViewerTool.PAN)

    def prepare_samples(self) -> None:
        self.run_button.setEnabled(False)
        try:
            first = ensure_sample_file(self.app, IMAGES_URL, "object_detection_images.zip", "object-detection-images", "1.jpg", title=self.windowTitle())
            manifest = ensure_sample_file(self.app, MODEL_URL, "object_detection_model.zip", "object-detection-model", "geokernel-model.json", title=self.windowTitle())
            self.images = sorted(first.parent.glob("*.jpg"), key=lambda item: int(item.stem))
            for image in self.images:
                sidecar = image.with_suffix(".jgw")
                if not sidecar.exists(): sidecar.write_text("1\n0\n0\n-1\n0.5\n-0.5\n", encoding="ascii")
            self.model_path.setText(str(manifest.parent)); self.select_image(0)
            self.details.setPlainText(f"{len(self.images)} images and the ONNX model are ready.")
        except Exception as error:
            self.details.setPlainText(f"Sample preparation failed:\n{error}"); QMessageBox.critical(self, self.windowTitle(), str(error))
        finally: self.run_button.setEnabled(True)

    def select_image(self, index: int) -> None:
        if not 0 <= index < len(self.images): return
        self.image_index = index; image = self.images[index]; self.raster_path.setText(str(image)); self.position.setText(f"{index + 1} / {len(self.images)} — {image.name}"); self.previous.setEnabled(index > 0); self.next.setEnabled(index + 1 < len(self.images)); self.open_source(str(image))

    def open_source(self, path: str) -> None:
        if self.detection_layer is not None: self.detection_layer.close(); self.detection_layer = None
        self.viewer.clear_layers(); self.viewer.add_layer_file(path); self.viewer.set_layer_name(0, "NWPU-VHR-10 source image"); self.viewer.refresh_layers(); self.viewer.full_extent()

    def browse_model(self) -> None:
        value = QFileDialog.getExistingDirectory(self, "Select GeoKernel object-detection package", self.model_path.text());
        if value: self.model_path.setText(value)

    def browse_raster(self) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "Select input image", self.raster_path.text(), "Raster images (*.jpg *.jpeg *.png *.tif *.tiff)")
        if value: self.raster_path.setText(value); self.open_source(value)

    def run(self) -> None:
        if self.future is not None: return
        model, raster = self.model_path.text().strip(), self.raster_path.text().strip()
        if not Path(model).is_dir() or not Path(raster).is_file(): QMessageBox.warning(self, self.windowTitle(), "Select an existing model package and input image."); return
        if not hasattr(AnalysisExecutor, "run_ai_object_detection_to_memory"): QMessageBox.critical(self, self.windowTitle(), "The installed geokernel package does not expose object detection."); return
        self.run_button.setEnabled(False); self.set_progress(0, "Running object detection...")
        request = {"modelPackagePath": model, "rasterPath": raster, "provider": self.provider.currentText(), "layerName": "object_detections", "buildSpatialIndex": True, "windowSize": 512, "overlap": 256, "nmsThreshold": 0.3}
        self.future = self.executor.submit(self.infer, request)

    def infer(self, request: dict):
        layer = AnalysisExecutor().run_ai_object_detection_to_memory(request, lambda p, m: self.bridge.progress.emit(p, m)); return layer, layer.diagnostics, request["rasterPath"]

    def poll_worker(self) -> None:
        if self.future is None or not self.future.done(): return
        future, self.future = self.future, None
        try:
            layer, result, raster = future.result()
            if self.detection_layer is not None: self.detection_layer.close()
            count = int(result.get("materializedCount", 0)); self.detection_layer = None; self.viewer.clear_layers(); self.viewer.add_layer_file(raster)
            if count > 0:
                self.detection_layer = layer; layer.add_to(self.viewer); base = detection_style(); self.viewer.set_layer_style(0, base)
                self.viewer.set_layer_symbol_renderer(0, {"type": "categorized", "field": "class_id", "defaultStyle": base, "categories": [{"value": class_id, "label": name, "enabled": True, "style": detection_style(color)} for class_id, name, color in CLASSES]})
            else: layer.close()
            output = "in-memory layer" if count > 0 else "no detections"; tiles = f"{result.get('tilesProcessed', 0)} ({result.get('tilesX', 0)} x {result.get('tilesY', 0)})"; self.viewer.refresh_layers(); self.viewer.full_extent(); self.details.setPlainText(f"GeoKernel AI tiled object detection\n\nProvider: {self.provider.currentText()}\nWindow: 512, overlap: 256, NMS: 0.3\nTiles processed: {tiles}\nDetections: {count}\nVector output: {output}"); self.set_progress(100, "Inference complete" if count > 0 else "Inference complete — no detections")
        except Exception as error:
            self.set_progress(0, "Inference failed"); self.details.setPlainText(f"Inference failed:\n{error}"); QMessageBox.critical(self, self.windowTitle(), str(error))
        finally: self.run_button.setEnabled(True)

    def set_progress(self, value: int, text: str) -> None:
        value = max(0, min(100, value)); self.progress.setValue(value); self.progress.setFormat(f"{value}% — {text}"); self.statusBar().showMessage(text)

    def closeEvent(self, event) -> None:
        self.poll.stop(); self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            if self.detection_layer is not None: self.detection_layer.close()
            self.viewer.close()
        except Exception: pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv); window = Window(app); window.show(); app.processEvents(); window.viewer.show(); sys.exit(app.exec())


if __name__ == "__main__": main()
