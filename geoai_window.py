"""Shared GeoAI window. Predictions are created only after Run."""
from __future__ import annotations

import queue
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from geoai_support import Cancelled, GeoAiProfile, PreparedRaster, asset_cache, check_cancel, configure_sdk, prepare_asset

configure_sdk()

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider, QTextEdit,
    QToolBar, QVBoxLayout, QWidget,
)
from geokernel import AITasks, Viewer, ViewerEventType, ViewerTool

class Bridge(QObject):
    drawing = Signal(int, str)
    busy = Signal(bool)


class GeoAiWindow(QMainWindow):
    def __init__(self, app: QApplication, profile: GeoAiProfile) -> None:
        super().__init__()
        self.app = app
        self.profile = profile
        self.tasks = AITasks()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="geoai-input-export")
        self.future: Future | None = None
        self.stage = ""
        self.finish = None
        self.job = None
        self.result = None
        self.raster: Path | None = None
        self.overlay = False
        self.busy = False
        self.running = False
        self.closing = False
        self.close_allowed = False
        self.polling = False
        self.cancel_event = threading.Event()
        self.renderer_idle = threading.Event()
        self.renderer_idle.set()
        self.render_busy = False
        self.messages = queue.SimpleQueue()
        self.bridge = Bridge(self)
        self.bridge.drawing.connect(self._drawing)
        self.bridge.busy.connect(self._renderer_busy)
        self.viewer.set_event_callback(self._viewer_event)
        self.setWindowTitle(profile.title + " — Python")
        self.resize(1280, 850)
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "GeoKernelAppIcon.ico")))
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        # This window owns asynchronous AI cleanup; the SDK's default close filter would close too early.
        layout.addWidget(self.viewer.qt_widget(auto_close=False), 1)
        panel = QWidget()
        panel.setFixedWidth(380)
        controls = QVBoxLayout(panel)
        controls.addWidget(QLabel(f"<b>{profile.title}</b>"))
        self.provider = QComboBox()
        self.provider.addItems(["Auto", "CPU", "CUDA"])
        form = QFormLayout()
        form.addRow("Execution provider", self.provider)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.01, 0.99)
        self.threshold.setDecimals(2)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(0.50)
        if profile.buildings:
            form.addRow(profile.threshold_label, self.threshold)
        else:
            self.threshold.hide()
        controls.addLayout(form)
        self.opacity_label = QLabel("Output transparency: 40%")
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(60)
        self.opacity.valueChanged.connect(self.apply_opacity)
        controls.addWidget(self.opacity_label)
        controls.addWidget(self.opacity)
        self.run_button = QPushButton(profile.run_label)
        self.save_button = QPushButton("Save Shapefile")
        self.cancel_button = QPushButton("Cancel")
        self.run_button.clicked.connect(self.run)
        self.save_button.clicked.connect(self.save)
        self.cancel_button.clicked.connect(self.cancel)
        for button in (self.run_button, self.save_button, self.cancel_button):
            controls.addWidget(button)
        self.progress = QProgressBar()
        controls.addWidget(self.progress)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText(profile.description)
        controls.addWidget(self.details, 1)
        legend = QLabel("<b>Output</b><br>" + profile.legend)
        legend.setWordWrap(True)
        controls.addWidget(legend)
        credits = QLabel(profile.credits)
        credits.setWordWrap(True)
        controls.addWidget(credits)
        layout.addWidget(panel)
        self.setCentralWidget(central)
        tools = QToolBar("Navigation", self)
        self.addToolBar(tools)
        for name, callback in (("Zoom In", self.viewer.zoom_in), ("Zoom Out", self.viewer.zoom_out),
                               ("Full Extent", self.viewer.full_extent), ("Pan", lambda: self.viewer.set_tool(ViewerTool.PAN))):
            action = QAction(name, self)
            action.triggered.connect(callback)
            tools.addAction(action)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(50)
        self._controls()
        QTimer.singleShot(0, self.prepare)

    def _controls(self) -> None:
        self.run_button.setEnabled(not self.busy and not self.closing)
        self.provider.setEnabled(not self.busy and not self.closing)
        self.threshold.setEnabled(not self.busy and not self.closing)
        self.save_button.setEnabled(not self.busy and self.result is not None and not self.closing)
        self.cancel_button.setEnabled(self.busy and self.stage not in ("export", "cleanup", "close") and not self.closing)
        self.opacity.setEnabled(self.overlay and not self.closing)

    def _progress(self, percent: int, message: str) -> None:
        percent = max(0, min(100, percent))
        message = message.replace("%p%", f"{percent}%")
        self.progress.setValue(percent)
        self.progress.setFormat(f"{percent}% — {message}")
        self.statusBar().showMessage(message)

    def _submit(self, stage, work, finish) -> None:
        self.stage, self.finish, self.busy = stage, finish, True
        self.future = self.pool.submit(work)
        self._controls()

    def _input(self) -> PreparedRaster:
        raster = prepare_asset(self.profile.data_url, self.profile.data_sha, self.profile.raster_name, self.cancel_event,
                               lambda p, m: self.messages.put((p, m)), archive=self.profile.archived_data)
        if self.profile.task == "prithvi-flood":
            from geoai_raster import prepare_flood_rgb
            self.messages.put((0, "Preparing source RGB display…"))
            display = prepare_flood_rgb(raster, asset_cache(self.profile.data_sha), self.cancel_event)
        elif self.profile.task == "prue-fields":
            from geoai_raster import prepare_fields_rgb
            self.messages.put((0, "Preparing first-period RGB display…"))
            display = prepare_fields_rgb(raster, asset_cache(self.profile.data_sha), self.cancel_event)
        else:
            display = raster.with_name(self.profile.display_name)
        return PreparedRaster(raster, display)

    def prepare(self) -> None:
        self.cancel_event.clear()
        self._submit("prepare", self._input, self._show_source)

    def _show_source(self, prepared: PreparedRaster) -> None:
        self.raster = prepared.raster
        self.viewer.clear_layers()
        self.viewer.add_layer(prepared.display)
        self.viewer.set_layer_name(0, "RGB source")
        self.viewer.full_extent()
        self._progress(0, "Ready. Click Run to process the image.")

    def run(self) -> None:
        if self.busy:
            return
        self._detach_result()
        old, self.job = self.job, None
        self.result = None
        self.cancel_event.clear()
        provider = self.provider.currentText().lower()
        threshold = self.threshold.value()
        raster = self.raster

        def start():
            if old is not None:
                self._release(old)
            prepared = None if raster is not None else self._input()
            source = raster if raster is not None else prepared.raster
            manifest = prepare_asset(self.profile.model_url, self.profile.model_sha, "geokernel-model.json", self.cancel_event,
                                     lambda p, m: self.messages.put((p, m)))
            check_cancel(self.cancel_event)
            request = dict(task=self.profile.task, modelPackagePath=str(manifest.parent), rasterPath=str(source),
                           provider=provider, intraOpThreads=4, maximumMilliseconds=600000)
            if self.profile.buildings:
                request["threshold"] = threshold
            elif self.profile.task == "dynamic-world":
                request["validityMaskPath"] = str(source.with_name("dynamicworld_spain_valid_mask.tif"))
            return prepared, self.tasks.start(request)

        def started(value):
            prepared, self.job = value
            if prepared is not None:
                self._show_source(prepared)
            self.running = self.busy = True
            self._progress(0, "Running inference…")

        self._submit("start", start, started)

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.job is not None:
            self._cancel_job(self.job)

    @staticmethod
    def _cancel_job(job) -> None:
        terminal = ("completed", "failed", "cancelled")
        if job.status()["state"] in terminal:
            return
        try:
            job.cancel()
        except RuntimeError:
            # Completion can race the UI's cancellation request.
            if job.status()["state"] not in terminal:
                raise

    def _detach_result(self) -> None:
        if self.overlay:
            self.viewer.remove_layer(0)
            self.overlay = False

    def apply_opacity(self, value: int) -> None:
        self.opacity_label.setText(f"Output transparency: {100 - value}%")
        if self.overlay:
            if self.profile.buildings:
                from geoai_vector import apply_vector_opacity
                apply_vector_opacity(self.viewer, 0, value)
            else:
                self.viewer.set_layer_opacity(0, value / 100)
                self.viewer.refresh_layers()

    def save(self) -> None:
        if self.job is None or self.busy or self.result is None:
            return
        name = self.profile.export_name or ("building-footprints.shp" if self.profile.buildings else "dynamic-world.shp")
        path, _ = QFileDialog.getSaveFileName(self, "Save polygons", name, "Shapefile (*.shp)")
        if path:
            self._submit("export", lambda: self.job.export(Path(path).resolve()),
                         lambda _: self._progress(100, "Shapefile saved."))

    def _completed(self) -> None:
        result = self.job.result()
        self.running = False
        if self.profile.buildings:
            from geoai_vector import prepare_vector_preview
            self._progress(95, "Preparing polygon display…")
            def prepare():
                preview = prepare_vector_preview(Path(result["vectorPath"]), self.cancel_event)
                return result, preview
            self._submit("preview", prepare, lambda value: self._show_completed(*value))
        else:
            self._show_completed(result, result["previewPath"])

    def _show_completed(self, result, preview) -> None:
        check_cancel(self.cancel_event)
        self.viewer.add_layer(preview)
        self.overlay = True
        self.viewer.set_layer_name(0, "Building footprints" if self.profile.buildings else self.profile.title)
        self.apply_opacity(self.opacity.value())
        self.result = result
        self.running = self.busy = False
        instances = f"Instances: {result['instances']}\n" if "instances" in result else ""
        self.details.setPlainText(f"{self.profile.title}\nProvider: {result['provider']}\n{instances}Polygons: {result['polygons']}\n"
            f"Elapsed: {result['elapsedMilliseconds']} ms\n\nTemporary session result. Use Save Shapefile to retain polygons.\n"
            + ("Building footprints are predictions, not ground truth. Model errors can remain." if self.profile.buildings
             else "Class 0 is non-water; class 1 is water/flood. Shapefile contains only water/flood polygons.\nA single image does not distinguish permanent water from newly flooded land."
             if self.profile.task == "prithvi-flood"
             else "Class-1 field interiors are exported; background and boundaries stay in the preview.\nImage-derived field divisions are not legal/cadastral parcels."
             if self.profile.task == "prue-fields"
             else "Water (class 0) is valid; NoData is excluded. Predictions are not ground truth."))
        self._progress(100, "Inference complete.")

    def _failed(self, error: Exception) -> None:
        self.running = False
        self.details.setPlainText(str(error))
        self._progress(0, "Cancelled." if isinstance(error, Cancelled) else "Operation failed. See diagnostics.")
        if self.result is None and self.job is not None:
            self._detach_result()
            old, self.job = self.job, None
            self._submit("cleanup", lambda: self._release(old), lambda _: None)
        else:
            self.busy = False

    def _poll(self) -> None:
        if self.polling:
            return
        self.polling = True
        try:
            self.viewer.process_events()
            while not self.messages.empty():
                self._progress(*self.messages.get_nowait())
            if self.future is not None and self.future.done():
                future, stage, finish = self.future, self.stage, self.finish
                self.future = None
                self.busy = False
                try:
                    value = future.result()
                    if stage == "close":
                        self._closed()
                        return
                    if self.closing:
                        if stage == "start":
                            _, self.job = value
                    else:
                        finish(value)
                except Exception as error:
                    if stage == "close":
                        self._closed()
                        return
                    self._failed(error)
            if self.closing:
                if self.future is None:
                    self._close_next()
                return
            if self.running and self.future is None:
                status = self.job.status()
                self._progress(status["percent"], status["message"])
                if status["state"] == "completed":
                    if self.cancel_event.is_set():
                        raise Cancelled("Cancelled.")
                    self._completed()
                elif status["state"] in ("failed", "cancelled"):
                    if status["state"] == "cancelled":
                        raise Cancelled("Cancelled.")
                    raise RuntimeError(status["error"])
            self._controls()
        except Exception as error:
            self._failed(error)
            self._controls()
        finally:
            self.polling = False

    def _viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.DRAWING_PROGRESS_CHANGED:
            self.bridge.drawing.emit(int(event.int_value), str(event.text or "Drawing…"))
        elif event.event_type == ViewerEventType.BUSY_CHANGED:
            self.bridge.busy.emit(bool(event.int_value))

    def _renderer_busy(self, busy: bool) -> None:
        self.render_busy = busy
        if busy:
            self.renderer_idle.clear()
        else:
            # Let the native render-completion stack release retired layer objects first.
            QTimer.singleShot(0, lambda: self.renderer_idle.set() if not self.render_busy else None)

    def _release(self, job) -> None:
        deadline = time.monotonic() + 60
        while not self.renderer_idle.wait(.05):
            if time.monotonic() >= deadline:
                raise RuntimeError("Renderer is still using the result; cleanup could not finish.")
        job.close()

    def _drawing(self, value: int, text: str) -> None:
        if not self.busy and not self.closing:
            self.statusBar().showMessage(text.replace("%p%", f"{value}%"))

    def closeEvent(self, event) -> None:
        if self.close_allowed:
            event.accept()
            return
        event.ignore()
        self.closing = True
        self.cancel()
        self._controls()
        self.statusBar().showMessage("Closing; waiting for background cleanup…")

    def _close_next(self) -> None:
        self.running = False
        self.viewer.clear_layers()
        self.overlay = False
        old, self.job = self.job, None
        self.result = None
        if old is not None:
            self._cancel_job(old)
        self._submit("close", lambda: self._release(old) if old is not None else None, None)

    def _closed(self) -> None:
        self.timer.stop()
        self.viewer.set_event_callback(None)
        self.viewer.close()
        self.pool.shutdown(wait=False)
        self.close_allowed = True
        self.close()


def run_example(profile: GeoAiProfile) -> None:
    app = QApplication(sys.argv)
    try:
        window = GeoAiWindow(app, profile)
        window.show()
        app.processEvents()
        window.viewer.show()
    except Exception as error:
        QMessageBox.critical(None, profile.title, str(error))
        return
    sys.exit(app.exec())

