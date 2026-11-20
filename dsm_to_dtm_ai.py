"""DSM to DTM: live AI versus classical.

Run the experimental pix_grad model through GeoKernel.AI, run the native classical filter
independently on the same DSM, and compare the newly generated heights. Three linked native
GeoKernel 2D maps keep the original DSM on the left. Neither method receives the reference
or the other method's terrain estimate.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

import dsm_ai as da
import dsm_support as ds
import dsm_terrain as dt
from common import ROOT_DIR, application_icon
from dsm_maps import NativeMap
from geokernel import ViewerEventType, ViewerTool

TITLE = "DSM to DTM | Live AI versus classical — GeoKernel"
STYLE = (
    "QMainWindow,QWidget#page{background:#f2f6f8;color:#233e50;}"
    "QLabel#title{font-size:22px;font-weight:600;color:#145e72;}"
    "QLabel#heading{background:#e4eef2;color:#125a70;padding:9px;font-weight:600;} QPushButton{padding:7px;}"
    "QToolBar{background:white;border-bottom:1px solid #d5e2e9;spacing:8px;padding:7px;}")
SUFFIX = ("DTM · terrain relief", "REMOVED HEIGHT · DSM − DTM", "ERROR · DTM − reference")
LEGENDS = (
    "Identical relief light and contrast. Left: original DSM. Both estimates are independently computed from this full input.",
    "One shared removed-height scale: white 0 m → red ≥20 m. Display saturation only; numeric heights are not clipped.",
    "One shared signed-error scale: blue ≤−2 m · white 0 · red ≥+2 m. Scores use all common valid pixels in the selected scope.")


@dataclass
class Outcome:
    scene: da.Scene | None = None
    comparison: da.Comparison | None = None
    message: str = ""
    model: Path | None = None


class Bridge(QObject):
    # Native viewer callbacks may run while the viewer renders; handle them afterwards.
    event = Signal(int, object)


class AiWindow(QMainWindow):
    def __init__(self, arguments: argparse.Namespace):
        super().__init__()
        self.arguments = arguments
        self.sample_assets = ds.read_json(ds.ZURICH_V2)
        self.model_assets = ds.read_json(da.MODEL_ASSETS)
        self.terrain_assets = ds.read_json(da.TERRAIN_ASSETS)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.temporary = tempfile.TemporaryDirectory(prefix="geokernel-dsm-ai-")
        self.cancel = threading.Event()
        self.pending: Future | None = None
        self.scene: da.Scene | None = None
        self.comparison: da.Comparison | None = None
        self.model: Path | None = None
        self.setup_model = False
        self.probe_point = None
        self.presses: list = [None, None, None]
        self.applied: list = [None, None, None]
        self.busy = self.close_queued = self.closed = False
        self.generation = 0
        self._phase = (0, "")
        self.viewers = [NativeMap(), NativeMap(), NativeMap()]
        self.bridge = Bridge(self)
        self.bridge.event.connect(self.viewer_event, Qt.ConnectionType.QueuedConnection)
        self.setWindowTitle(TITLE)
        self.setWindowIcon(application_icon())
        self.resize(1760, 980)
        self.setStyleSheet(STYLE)
        self._build()
        self.poll = QTimer(self, interval=50, timeout=self.finish)
        self.set_busy(False)
        QTimer.singleShot(0, self.load_sample)

    # ----- layout -------------------------------------------------------------------------
    def _build(self):
        def label(text, name=None):
            item = QLabel(text)
            item.setWordWrap(True)
            if name:
                item.setObjectName(name)
            return item

        def button(text, slot, name):
            item = QPushButton(text, objectName=name)
            item.clicked.connect(slot)
            controls.addWidget(item)
            return item

        page = QWidget(objectName="page")
        layout = QHBoxLayout(page)
        sidebar = QWidget()
        controls = QVBoxLayout(sidebar)
        controls.setContentsMargins(0, 0, 8, 0)
        controls.setSpacing(8)
        controls.addWidget(label("AI / Classical\nRun both methods", "title"))
        controls.addWidget(label("One DSM · two independent estimates.\npix_grad · experimental DSM-only model."))
        self.sample_button = button("Load full Zurich 1 km tile", self.load_sample, "loadSample")
        self.open_button = button("Open DSM GeoTIFF...", self.open_dsm, "openDsm")
        self.reference_button = button("Open reference (optional)...", self.open_reference, "openReference")
        self.source = label("Preparing source data...", "sourceInfo")
        controls.addWidget(self.source)
        self.model_button = button("Download / verify model", lambda: self.prepare_model(), "prepareModel")
        self.zip_button = button("Use model ZIP...", self.local_model, "localModel")
        self.model_info = label("Model not prepared.", "modelInfo")
        controls.addWidget(self.model_info)
        form = QFormLayout()
        self.overlap = QSpinBox(objectName="aiOverlap", minimum=0, maximum=128, singleStep=32, value=64)
        form.addRow("Tile overlap (px)", self.overlap)
        self.threads = QSpinBox(objectName="cpuThreads", minimum=1, maximum=8, value=4)
        form.addRow("CPU threads", self.threads)
        self.preset = QComboBox(objectName="classicalPreset")
        self.preset.addItems(["Balanced", "Remove more objects", "Preserve more relief"])
        form.addRow("Classical preset", self.preset)
        controls.addLayout(form)
        self.run_button = button("Run AI + classical", self.process, "runComparison")
        self.cancel_button = button("Cancel", self.request_cancel, "cancelProcessing")
        self.state = label("Load source and model, then Run.", "runState")
        controls.addWidget(self.state)
        controls.addWidget(label("Compare maps"))
        self.mode = QComboBox(objectName="displayMode")
        self.mode.addItems(["Terrain relief", "Removed height: DSM − DTM", "Signed reference errors"])
        self.mode.currentIndexChanged.connect(self.display)
        controls.addWidget(self.mode)
        self.scope = QComboBox(objectName="evaluationScope")
        self.scope.addItems(["Full input", "Shared comparison crop"])
        self.scope.currentIndexChanged.connect(self.scope_changed)
        controls.addWidget(self.scope)
        controls.addWidget(label("Source DSM remains on the left. Display and evaluation scope never change the full "
                                 "input used for processing."))
        self.save_button = button("Save comparison folder...", self.export_results, "saveResults")
        self.probe = label("Click a source pixel to inspect both estimates.", "pixelProbe")
        self.probe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.probe)
        controls.addStretch()
        controls.addWidget(label("Terrain: Federal Office of Topography swisstopo.\nWeights: David Perez · CC BY 4.0 · "
                                 "Zenodo 7973800.\nReference is evaluation-only. No vertical datum conversion."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(320)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(sidebar)
        layout.addWidget(scroll)

        workspace = QVBoxLayout()
        maps = QHBoxLayout()
        maps.setSpacing(8)
        self.headings = []
        titles = ("ORIGINAL DSM · shared input", "CLASSICAL DTM · Run to generate", "AI DTM · Run to generate")
        for pane, viewer in enumerate(self.viewers):
            column = QVBoxLayout()
            column.setSpacing(0)
            heading = label(titles[pane], "heading")
            column.addWidget(heading)
            widget = viewer.qt_widget(auto_close=False)
            widget.setMinimumSize(250, 270)
            column.addWidget(widget, 1)
            maps.addLayout(column, 1)
            self.headings.append(heading)
            viewer.set_tool(ViewerTool.PAN)
            viewer.set_event_callback(lambda event, side=pane: self.bridge.event.emit(side, event))
        workspace.addLayout(maps, 1)
        self.legend = label("Same light and contrast for both methods. No conversion has run yet.")
        workspace.addWidget(self.legend)
        self.scores = QTableWidget(2, 5, objectName="metricTable")
        self.scores.setHorizontalHeaderLabels(["Method", "Valid pixels", "RMSE (m)", "MAE (m)", "Bias (m)"])
        self.scores.verticalHeader().hide()
        self.scores.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.scores.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.scores.setFixedHeight(101)
        workspace.addWidget(self.scores)
        self.summary = label("No prepared terrain result is loaded.", "comparisonSummary")
        workspace.addWidget(self.summary)
        workspace.addWidget(label("Both methods process the complete supplied DSM. The shared crop changes only the "
                                  "view and scores. Experimental model; this development scene is not a held-out benchmark."))
        layout.addLayout(workspace, 1)
        self.setCentralWidget(page)

        toolbar = self.addToolBar("Navigation")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        images = ROOT_DIR / "images"
        self.navigation = (
            toolbar.addAction("Pan", lambda: self.use_tool(ViewerTool.PAN)),
            toolbar.addAction("Zoom box", lambda: self.use_tool(ViewerTool.ZOOM_BOX)),
            toolbar.addAction(QIcon(str(images / "ZoomIn.png")), "Zoom in", lambda: self.viewers[0].zoom_in(1.5)),
            toolbar.addAction(QIcon(str(images / "ZoomOut.png")), "Zoom out", lambda: self.viewers[0].zoom_out(1.5)),
            toolbar.addAction(QIcon(str(images / "FullExtent.png")), "Fit comparison", self.fit),
        )
        self.progress = QProgressBar()
        self.progress.setFixedWidth(230)
        self.statusBar().addPermanentWidget(self.progress)
        self.controls = [self.sample_button, self.open_button, self.model_button, self.zip_button, self.overlap,
                         self.threads, self.preset, self.scope]
        for signal in (self.overlap.valueChanged, self.threads.valueChanged, self.preset.currentIndexChanged):
            signal.connect(self.settings_changed)

    def show_viewers(self):
        # Embedded native maps start painting once shown, after the host window is visible.
        for viewer in self.viewers:
            viewer.show()

    # ----- state --------------------------------------------------------------------------
    def data_root(self) -> Path:
        return Path(self.arguments.data_dir).resolve() if self.arguments.data_dir else ROOT_DIR / "data"

    def set_busy(self, busy: bool):
        self.busy = busy
        for widget in self.controls:
            widget.setEnabled(not busy)
        for action in self.navigation:
            action.setEnabled(not busy and self.scene is not None)
        self.run_button.setEnabled(not busy and self.scene is not None and self.model is not None)
        self.reference_button.setEnabled(not busy and self.scene is not None)
        self.save_button.setEnabled(not busy and self.comparison is not None)
        self.mode.setEnabled(not busy and self.comparison is not None)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)

    def set_phase(self, value: int, text: str):
        # Worker (or SDK inference) thread: only primitive state crosses to the GUI timer.
        self._phase = (value, text)

    def request_cancel(self):
        self.cancel.set()
        self.cancel_button.setEnabled(False)
        self.set_phase(self._phase[0], "Cancelling; completed comparison retained...")

    def settings_changed(self):
        if self.comparison is not None:
            self.state.setText("Controls changed. Run to update; displayed maps and scores use the last completed settings.")

    def directory(self) -> Path:
        self.generation += 1
        path = Path(self.temporary.name) / str(self.generation)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def begin(self, job):
        self.cancel.clear()
        self._phase = (0, "Working...")
        self.set_busy(True)
        self.pending = self.executor.submit(job)
        self.poll.start()

    def failure(self, message: str):
        self.set_busy(False)
        self.state.setText(message)
        self.statusBar().showMessage(message)
        if self.close_queued:
            QTimer.singleShot(0, self.close)
        elif not self.cancel.is_set():
            QMessageBox.warning(self, "Unable to complete operation", message)

    # ----- jobs ---------------------------------------------------------------------------
    def prepare_model(self, archive: str | None = None):
        if self.busy:
            return
        archive = archive or self.arguments.model_archive
        url = self.arguments.model_url or self.model_assets["url"]

        def job():
            folder = da.prepare_model(self.model_assets, self.data_root(), archive, url, self.cancel,
                                      lambda value, text: self.set_phase(value, "Model: " + text))
            ds.check_cancel(self.cancel)
            message = ("Source and model ready. Press Run AI + classical." if self.scene is not None
                       else "Model ready; load a DSM.")
            return Outcome(message=message, model=folder)

        self.begin(job)

    def local_model(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose the pinned pix_grad model ZIP", "", "ZIP (*.zip)")
        if path:
            self.prepare_model(path)

    def load_sample(self):
        if self.busy:
            return
        url = self.arguments.sample_url or self.sample_assets["url"]
        folder = self.directory()
        self.setup_model = self.model is None

        def job():
            support = ds.prepare_sample(self.sample_assets, self.data_root(), self.arguments.sample_archive, url,
                                        self.cancel, lambda v, t: self.set_phase(v, "Projection/sample support: " + t))
            ds.check_cancel(self.cancel)
            ds.configure_runtime(support)
            terrain = da.prepare_terrain(self.terrain_assets, self.data_root(), self.cancel, self.set_phase)
            manifest = dict(self.terrain_assets, standard_full_tile=True)
            return self.load_job(terrain / "dsm.tif", terrain / "reference.tif", manifest, folder)

        self.begin(job)

    def load_job(self, path: Path, reference: Path | None, manifest: dict, folder: Path) -> Outcome:
        self.set_phase(5, "Reading source DSM...")
        dsm = dt.read_raster(path, self.cancel)
        ref = None
        if reference is not None:
            ref = dt.read_raster(reference, self.cancel)
            dt.validate_reference(dsm, ref)
        if manifest.get("standard_full_tile"):
            x0, y0, x1, y1 = dsm.extent()
            if not (dsm.width == 2000 and dsm.height == 2000 and dsm.pixel == 0.5 and (x0, y0, x1, y1)
                    == (2677000, 1251000, 2678000, 1252000)):
                raise RuntimeError("Unexpected full Zurich grid.")
        self.set_phase(60, "Preparing original DSM display...")
        original = ds.write_rgb_bands(folder / "original.tif", dsm.width, dsm.height, dsm.transform, dsm.projection,
                                      dt.relief_bands(dsm, dsm.z, self.cancel))
        ds.check_cancel(self.cancel)
        return Outcome(da.Scene(dsm, ref, original, manifest), None, "Source ready. Prepare model and Run.")

    def open_dsm(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open metre-height DSM", "", "GeoTIFF (*.tif *.tiff)")
        if path:
            folder = self.directory()
            self.begin(lambda: self.load_job(Path(path), None, {}, folder))

    def open_reference(self):
        if self.scene is None or self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open aligned evaluation-only reference", "", "GeoTIFF (*.tif *.tiff)")
        if not path:
            return
        scene, comparison, folder = self.scene, self.comparison, self.directory()

        def job():
            self.set_phase(5, "Reading evaluation-only reference...")
            reference = dt.read_raster(Path(path), self.cancel)
            dt.validate_reference(scene.dsm, reference)
            new_scene = replace(scene, reference=reference)
            new = (da.attach_reference(new_scene, comparison, folder, self.model_assets, self.cancel, self.set_phase)
                   if comparison is not None else None)
            ds.check_cancel(self.cancel)
            return Outcome(new_scene, new, "Reference updated. Both generated height arrays are unchanged.")

        self.begin(job)

    def process(self):
        if self.scene is None or self.model is None or self.busy:
            return
        scene, model, folder = self.scene, self.model, self.directory()
        parameters = da.effective_parameters(scene.dsm, dt.PRESETS[self.preset.currentIndex()])
        overlap, threads = self.overlap.value(), self.threads.value()

        def job():
            result = da.compare(scene, model, parameters, overlap, threads, folder, self.model_assets, self.cancel,
                                self.set_phase)
            return Outcome(scene, result, "Both methods completed from the same full DSM.")

        self.begin(job)

    def finish(self):
        value, text = self._phase
        self.progress.setValue(value)
        self.statusBar().showMessage(text)
        if self.pending is None or not self.pending.done():
            return
        self.poll.stop()
        future, self.pending = self.pending, None
        try:
            out = future.result()
        except Exception as error:
            cancelled = isinstance(error, ds.Cancelled) or self.cancel.is_set()
            message = "Cancelled; completed comparison retained." if cancelled else str(error)
            self.failure(message)
            return
        if self.cancel.is_set() and (out.scene is not None or out.model is not None):
            self.failure("Cancelled; completed comparison retained.")
            return
        try:
            if out.model is not None:
                self.model = out.model
                self.model_info.setText("pix_grad ready · 256 × 256 tiles\nVerified ONNX · CPU · experimental")
            if out.scene is not None:
                self.apply_scene(out)
        except Exception as error:
            self.failure(str(error))
            return
        self.set_busy(False)
        self.state.setText(out.message)
        self.statusBar().showMessage(out.message)
        if self.close_queued:
            QTimer.singleShot(0, self.close)
        elif self.setup_model and out.scene is not None:
            self.setup_model = False
            QTimer.singleShot(0, self.prepare_model)

    def apply_scene(self, out: Outcome):
        changed = self.scene is None or out.scene.dsm is not self.scene.dsm
        self.scene, self.comparison = out.scene, out.comparison
        if changed:
            self.replace(0, self.scene.original)
            for pane in (1, 2):
                self.viewers[pane].clear_layers()
                self.viewers[pane].refresh_layers()
            self.probe_point = None
            self.draw_probe()
            self.probe.setText("Click a source pixel to inspect both estimates.")
            self.applied = [None, None, None]
            QTimer.singleShot(0, self.fit)
        d = self.scene.dsm
        self.source.setText(f"{Path(d.path).name} · {d.width} × {d.height}\n{d.pixel:g} m cells · "
                            + ("aligned reference" if self.scene.reference else "no reference"))
        if self.comparison is not None:
            self.display()
            self.update_scores()
        else:
            self.scores.clearContents()
            self.summary.setText("No terrain conversion has run for this input.")
            self.headings[1].setText("CLASSICAL DTM · Run to generate")
            self.headings[2].setText("AI DTM · Run to generate")

    # ----- maps ---------------------------------------------------------------------------
    def replace(self, pane: int, path: Path):
        """Swap the map's raster while keeping its view (the empty map adopts the raster's CRS)."""
        viewer = self.viewers[pane]
        if viewer.layer_count():
            extent = viewer.get_view_extent()
        else:  # a map receiving its first layer joins the linked view instead of its own default
            extent = self.viewers[0].get_view_extent() if pane and self.viewers[0].layer_count() else None
        viewer.clear_layers()
        viewer.add_layer(path)
        if extent is not None:
            viewer.set_view_extent(extent)
            self.applied[pane] = viewer.get_view_extent()
        viewer.refresh_layers()

    def scope_changed(self):
        self.update_scores()
        self.fit()

    def fit(self):
        if self.scene is None:
            return
        crop = self.scope.currentIndex() == 1
        x0, y0, x1, y1 = da.crop_extent(self.scene) if crop else self.scene.dsm.extent()
        dx, dy = (x1 - x0) * 0.025, (y1 - y0) * 0.025
        self.draw_area(crop)
        self.viewers[0].set_view_extent((x0 - dx, y0 - dy, x1 + dx, y1 + dy))
        self.sync_from(0)

    def draw_area(self, crop: bool):
        """Dim everything outside the evaluated cells (four translucent bands) and outline them."""
        x0, y0, x1, y1 = da.crop_extent(self.scene)
        ox0, oy0, ox1, oy1 = self.scene.dsm.extent()
        margin = max(ox1 - ox0, oy1 - oy0)
        ox0, oy0, ox1, oy1 = ox0 - margin, oy0 - margin, ox1 + margin, oy1 + margin
        bands = ((ox0, y1, ox1, oy1), (ox0, oy0, ox1, y0), (ox0, y0, x0, y1), (x1, y0, ox1, y1))
        dim = {"fillColor": "#ffffff", "fillOpacity": 155, "lineWidth": 0, "lineColor": "#ffffff"}
        outline = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        for viewer in self.viewers:
            viewer.clear_shapes()
            if crop:
                for a, b, c, d in bands:
                    viewer.add_polygon_shape([(a, b), (c, b), (c, d), (a, d), (a, b)], dim)
                viewer.add_polyline_shape(outline, {"lineColor": "#098b97", "lineWidth": 2})
            viewer.refresh_layers()  # owned shapes are drawn on the next full map render

    def sync_from(self, side: int):
        value = self.viewers[side].get_view_extent()
        if value is None:
            return
        self.applied[side] = value
        for other, viewer in enumerate(self.viewers):
            if other != side:
                viewer.set_view_extent(value)
                self.applied[other] = viewer.get_view_extent()

    def use_tool(self, tool):
        for viewer in self.viewers:
            viewer.set_tool(tool)

    def viewer_event(self, side: int, event):
        if self.closed or self.scene is None:
            return
        kind = event.event_type
        if kind == ViewerEventType.VISIBLE_EXTENT_CHANGED:
            value = self.viewers[side].get_view_extent()
            if value is not None and value != self.applied[side] and self.viewers[side].layer_count():
                self.sync_from(side)
        elif kind == ViewerEventType.MAP_MOUSE_DOWN and event.int_value2 == 1:  # Qt::LeftButton
            self.presses[side] = (event.screen_rectangle.left, event.screen_rectangle.top)
        elif kind == ViewerEventType.MAP_MOUSE_UP and event.int_value2 == 1:
            press, self.presses[side] = self.presses[side], None
            screen = (event.screen_rectangle.left, event.screen_rectangle.top)
            if (event.int_value == ViewerTool.PAN and press
                    and abs(press[0] - screen[0]) + abs(press[1] - screen[1]) <= 3):
                self.inspect(event.extent.x_min, event.extent.y_min)

    def display(self):
        if self.comparison is None:
            return
        mode = self.mode.currentIndex()
        if mode == 2 and self.scene.reference is None:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(0)
            self.mode.blockSignals(False)
            mode = 0
            self.statusBar().showMessage("Attach an aligned reference to compare errors.")
        for method in range(2):
            self.replace(method + 1, self.comparison.maps[method][mode])
        self.headings[1].setText("CLASSICAL " + SUFFIX[mode])
        self.headings[2].setText("AI " + SUFFIX[mode])
        self.legend.setText(LEGENDS[mode])

    def update_scores(self):
        if self.comparison is None:
            return
        r = self.comparison
        values = r.crop if self.scope.currentIndex() else r.full
        for method, score in enumerate(values):
            has = score.count > 0
            cells = ("AI · pix_grad" if method else "Classical", str(score.count),
                     f"{score.rmse:.3f}" if has else "—", f"{score.mae:.3f}" if has else "—",
                     f"{score.bias:.3f}" if has else "—")
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(QColor("#8857bd" if method else "#087e8b"))
                self.scores.setItem(method, column, item)
        p = r.classical.parameters
        _, _, w, h = da.comparison_window(self.scene)
        pixel = self.scene.dsm.pixel
        self.summary.setText(
            f"Last completed run · {r.ai.tiles} AI tiles · overlap {r.overlap} px · CPU threads {r.threads} · "
            f"classical working {r.classical.working:g} m / window {p.window:g} m\nScores: "
            f"{'shared crop' if self.scope.currentIndex() else 'full input'} · crop {w} × {h} cells "
            f"({w * pixel:g} × {h * pixel:g} m). Full input was used by both methods. Reference is evaluation-only.")

    def draw_probe(self):
        for viewer in self.viewers:
            if self.probe_point is None:
                viewer.remove_overlay_shape("probe")
            else:
                viewer.set_overlay_point("probe", *self.probe_point,
                                         {"pointColor": "#d73573", "pointSize": 11, "lineColor": "#ffffff", "lineWidth": 2})

    def inspect(self, x: float, y: float):
        if self.scene is None or self.busy:
            return
        d = self.scene.dsm
        cx, cy = (x - d.transform[0]) / d.pixel, (d.transform[3] - y) / d.pixel
        if not (0 <= cx < d.width and 0 <= cy < d.height):
            return
        col, row = int(cx), int(cy)
        i = row * d.width + col
        text = f"Source pixel {col} / {row}\n"
        if not d.valid[i]:
            text += "NoData"
        else:
            text += f"DSM {d.z[i]:.2f} m"
            if self.comparison is not None:
                text += f"\nClassical {self.comparison.classical.dtm[i]:.2f} m\nAI {self.comparison.ai.dtm[i]:.2f} m"
            reference = self.scene.reference
            if reference is not None and reference.valid[i]:
                text += f"\nReference {reference.z[i]:.2f} m"
        self.probe.setText(text)
        self.probe_point = (d.transform[0] + (col + 0.5) * d.pixel, d.transform[3] - (row + 0.5) * d.pixel)
        self.draw_probe()

    def export_results(self):
        if self.comparison is None or self.busy:
            return
        base = QFileDialog.getExistingDirectory(self, "Choose parent folder for a new result bundle")
        if not base:
            return
        result = self.comparison

        def job():
            target = da.export_bundle(result, Path(base), self.cancel, self.set_phase)
            return Outcome(message=f"Saved complete comparison bundle: {target}")

        self.begin(job)

    # ----- shutdown -----------------------------------------------------------------------
    def closeEvent(self, event):
        if self.busy:
            # The SDK inference call has no cancellation hook; the job stops after the current AI pass.
            self.close_queued = True
            self.request_cancel()
            event.ignore()
            return
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        self.cancel.set()
        self.poll.stop()
        self.executor.shutdown(wait=True)
        for viewer in self.viewers:
            viewer.set_event_callback(None)
            viewer.close()
        self.temporary.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description="Live pix_grad AI and classical DSM-to-DTM comparison on one full input.")
    parser.add_argument("--data-dir", metavar="directory", help="Data/model cache directory.")
    parser.add_argument("--sample-archive", metavar="zip", help="Pinned Zurich v2 support ZIP.")
    parser.add_argument("--sample-url", metavar="url", help="HTTPS support ZIP mirror; hashes still apply.")
    parser.add_argument("--model-archive", metavar="zip", help="Pinned pix_grad model ZIP.")
    parser.add_argument("--model-url", metavar="url", help="HTTPS model ZIP mirror; hashes still apply.")
    arguments, qt_arguments = parser.parse_known_args()
    app = QApplication([sys.argv[0], *qt_arguments])
    app.setApplicationName("DsmToDtmAI")
    palette = app.palette()
    for role, color in ((QPalette.ColorRole.Window, "#f2f6f8"), (QPalette.ColorRole.Base, "white"),
                        (QPalette.ColorRole.WindowText, "#233e50"), (QPalette.ColorRole.Text, "#233e50")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    try:
        ds.configure_runtime()
        window = AiWindow(arguments)
    except Exception as error:
        QMessageBox.critical(None, "DsmToDtmAI", str(error))
        return 1
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    window.show_viewers()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
