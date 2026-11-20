"""DSM + orthophoto to DTM: three independent methods.

Compare three newly computed terrain estimates on the same full DSM: the native classical
filter (DSM only), the experimental pix_grad model (DSM only) and the experimental rgb_grad_fm
model (DSM plus an aligned RGB orthophoto). Four linked native GeoKernel 2D maps keep the input
context on the left. The reference is evaluation-only; the methods do not feed each other.
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
import dsm_ortho as do
import dsm_support as ds
import dsm_terrain as dt
from common import ROOT_DIR, application_icon
from dsm_maps import NativeMap
from geokernel import ViewerEventType, ViewerTool

TITLE = "DSM + Orthophoto to DTM | Three independent methods — GeoKernel"
STYLE = (
    "QMainWindow,QWidget#page{background:#f2f6f8;color:#233e50;}"
    "QLabel#title{font-size:22px;font-weight:600;color:#145e72;}"
    "QLabel#heading{background:#e4eef2;color:#125a70;padding:9px;font-weight:600;} QPushButton{padding:7px;}"
    "QToolBar{background:white;border-bottom:1px solid #d5e2e9;spacing:8px;padding:7px;}")
SUFFIX = ("DTM · relief", "REMOVED HEIGHT", "ERROR · DTM − reference")
LEGENDS = (
    "Same relief light/contrast for all methods; source orthophoto or DSM remains on the left.",
    "Shared removed-height scale: white 0 m → red ≥20 m. Display saturation only; numeric heights are unchanged.",
    "Shared signed-error scale: blue ≤−2 m · white 0 · red ≥+2 m. Scores use identical valid reference cells in the selected scope.")
NAMES = ("Classical · DSM", "pix_grad · DSM", "rgb_grad_fm · DSM + RGB")
COLORS = ("#087e8b", "#8857bd", "#ba7020")
PENDING = ("CLASSICAL · Run to generate", "PIX_GRAD · Run to generate", "RGB_GRAD_FM · Run to generate")


@dataclass
class Outcome:
    scene: do.Scene | None = None
    comparison: do.Comparison | None = None
    message: str = ""
    models: list | None = None


class Bridge(QObject):
    # Native viewer callbacks may run while the viewer renders; handle them afterwards.
    event = Signal(int, object)


class OrthoWindow(QMainWindow):
    def __init__(self, arguments: argparse.Namespace):
        super().__init__()
        self.arguments = arguments
        self.assets = ds.read_json(do.SAMPLE_ASSETS)
        self.archive_sha256 = [ds.read_json(p)["sha256"] for p in do.MODEL_ASSETS]
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.temporary = tempfile.TemporaryDirectory(prefix="geokernel-dsm-ortho-")
        self.cancel = threading.Event()
        self.pending: Future | None = None
        self.scene: do.Scene | None = None
        self.comparison: do.Comparison | None = None
        self.models: list | None = None
        self.setup_models = False
        self.probe_point = None
        self.presses: list = [None] * 4
        self.applied: list = [None] * 4
        self.busy = self.close_queued = self.closed = False
        self.generation = 0
        self._phase = (0, "")
        self.viewers = [NativeMap() for _ in range(4)]
        self.bridge = Bridge(self)
        self.bridge.event.connect(self.viewer_event, Qt.ConnectionType.QueuedConnection)
        self.setWindowTitle(TITLE)
        self.setWindowIcon(application_icon())
        self.resize(1920, 980)
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
        controls.addWidget(label("DSM + RGB → DTM\nCompare three methods", "title"))
        controls.addWidget(label("Classical · DSM-only AI · DSM+RGB AI.\nEach starts from the same full DSM."))
        self.sample_button = button("Load Zurich DSM + orthophoto", self.load_sample, "loadSample")
        self.open_button = button("Open aligned DSM + RGB...", self.open_inputs, "openInputs")
        self.reference_button = button("Open reference (optional)...", self.open_reference, "openReference")
        self.source = label("Preparing sample...", "sourceInfo")
        controls.addWidget(self.source)
        self.models_button = button("Download / verify both models", lambda: self.prepare_models(), "prepareModels")
        self.pix_button = button("Use pix_grad model ZIP...", lambda: self.choose_model(0), "localPixModel")
        self.rgb_button = button("Use RGB model ZIP...", lambda: self.choose_model(1), "localRgbModel")
        self.model_info = label("Models not prepared.", "modelInfo")
        controls.addWidget(self.model_info)
        form = QFormLayout()
        self.overlap = QSpinBox(objectName="aiOverlap", minimum=0, maximum=128, singleStep=32, value=64)
        form.addRow("AI overlap (px)", self.overlap)
        self.threads = QSpinBox(objectName="cpuThreads", minimum=1, maximum=8, value=4)
        form.addRow("CPU threads", self.threads)
        self.preset = QComboBox(objectName="classicalPreset")
        self.preset.addItems(["Balanced", "Remove more objects", "Preserve more relief"])
        form.addRow("Classical preset", self.preset)
        controls.addLayout(form)
        self.run_button = button("Run all three methods", self.process, "runComparison")
        self.cancel_button = button("Cancel", self.request_cancel, "cancelProcessing")
        self.state = label("Load data and models, then Run.", "runState")
        controls.addWidget(self.state)
        controls.addWidget(label("Input context"))
        self.input = QComboBox(objectName="inputDisplay")
        self.input.addItems(["Original DSM relief", "RGB orthophoto"])
        self.input.setCurrentIndex(1)
        self.input.currentIndexChanged.connect(self.show_input)
        controls.addWidget(self.input)
        controls.addWidget(label("Compare estimates"))
        self.mode = QComboBox(objectName="displayMode")
        self.mode.addItems(["Terrain relief", "Removed height: DSM − DTM", "Signed reference errors"])
        self.mode.currentIndexChanged.connect(self.display)
        controls.addWidget(self.mode)
        self.scope = QComboBox(objectName="evaluationScope")
        self.scope.addItems(["Full input", "Shared comparison crop"])
        self.scope.setCurrentIndex(1)
        self.scope.currentIndexChanged.connect(self.scope_changed)
        controls.addWidget(self.scope)
        self.save_button = button("Save comparison folder...", self.export_results, "saveResults")
        self.probe = label("Click a source pixel to inspect RGB and all terrain estimates.", "pixelProbe")
        self.probe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.probe)
        controls.addStretch()
        controls.addWidget(label("Data: Federal Office of Topography swisstopo.\nAI weights: David Perez · CC BY 4.0.\n"
                                 "Reference is evaluation-only; no datum conversion."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(320)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(sidebar)
        layout.addWidget(scroll)

        workspace = QVBoxLayout()
        maps = QHBoxLayout()
        maps.setSpacing(7)
        self.headings = []
        titles = ("RGB ORTHOPHOTO · input context", "CLASSICAL · DSM only", "PIX_GRAD · DSM only", "RGB_GRAD_FM · DSM + RGB")
        for pane, viewer in enumerate(self.viewers):
            column = QVBoxLayout()
            column.setSpacing(0)
            heading = label(titles[pane], "heading")
            column.addWidget(heading)
            widget = viewer.qt_widget(auto_close=False)
            widget.setMinimumSize(230, 260)
            column.addWidget(widget, 1)
            maps.addLayout(column, 1)
            self.headings.append(heading)
            viewer.set_tool(ViewerTool.PAN)
            viewer.set_event_callback(lambda event, side=pane: self.bridge.event.emit(side, event))
        workspace.addLayout(maps, 1)
        self.legend = label("Inputs ready first; Run generates all three terrain estimates.")
        workspace.addWidget(self.legend)
        self.scores = QTableWidget(3, 5, objectName="metricTable")
        self.scores.setHorizontalHeaderLabels(["Method", "Valid pixels", "RMSE (m)", "MAE (m)", "Bias (m)"])
        self.scores.verticalHeader().hide()
        self.scores.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.scores.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.scores.setFixedHeight(130)
        workspace.addWidget(self.scores)
        self.summary = label("No prepared prediction is loaded.", "comparisonSummary")
        workspace.addWidget(self.summary)
        workspace.addWidget(label("Different pretrained checkpoints and objectives: differences do not isolate the causal "
                                  "benefit of RGB. Process full input, then evaluate the same crop. Experimental development scene."))
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
        self.controls = [self.sample_button, self.open_button, self.models_button, self.pix_button, self.rgb_button,
                         self.overlap, self.threads, self.preset, self.input, self.scope]
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
        self.run_button.setEnabled(not busy and self.scene is not None and self.models is not None)
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
            self.state.setText("Controls changed. Run to update; maps and scores retain the last completed settings.")

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
    def choose_model(self, index: int):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, f"Choose the pinned {do.METHODS[index + 1]} model ZIP", "", "ZIP (*.zip)")
        if path:
            self.prepare_models(index, path)

    def prepare_models(self, selected: int = -1, local: str | None = None):
        if self.busy:
            return
        a = self.arguments
        archives = [local if selected == 0 else a.pix_model_archive, local if selected == 1 else a.rgb_model_archive]
        urls = [a.pix_model_url, a.rgb_model_url]
        has_scene = self.scene is not None

        def job():
            try:
                folders = [do.prepare_model(i, self.data_root(), archives[i], urls[i], self.cancel, self.set_phase)
                           for i in range(2)]
            except ds.Cancelled:
                raise
            except Exception as error:
                raise RuntimeError(f"{error}\nUse the pinned model ZIPs or retry the published URLs.") from error
            ds.check_cancel(self.cancel)
            return Outcome(message="Inputs and both models ready. Press Run." if has_scene
                           else "Models ready; load aligned DSM and RGB.", models=folders)

        self.begin(job)

    def load_sample(self):
        if self.busy:
            return
        url = self.arguments.sample_url or self.assets["url"]
        folder = self.directory()
        self.setup_models = self.models is None

        def job():
            sample = ds.prepare_sample(self.assets, self.data_root(), self.arguments.sample_archive, url, self.cancel,
                                       self.set_phase, do.AGENT)
            ds.check_cancel(self.cancel)
            ds.configure_runtime(sample)
            return self.load_job(sample / "dsm.tif", sample / "ortho_rgb.tif", sample / "reference.tif",
                                 ds.read_json(sample / "source-manifest.json"), folder)

        self.begin(job)

    def load_job(self, path: Path, rgb: Path, reference: Path | None, manifest: dict, folder: Path) -> Outcome:
        self.set_phase(5, "Reading source DSM...")
        dsm = dt.read_raster(path, self.cancel)
        self.set_phase(25, "Checking RGB channels, grid and coverage...")
        ortho = do.read_ortho(dsm, rgb, self.cancel)
        ref = None
        if reference is not None:
            self.set_phase(50, "Reading evaluation-only reference...")
            ref = dt.read_raster(reference, self.cancel)
            dt.validate_reference(dsm, ref)
        if manifest.get("standard_full_tile"):
            if not (ds.same_crs(dsm.projection, 2056) and dsm.width == 2000 and dsm.height == 2000 and dsm.pixel == 0.5
                    and dsm.extent() == (2677000, 1251000, 2678000, 1252000)):
                raise RuntimeError("Unexpected Zurich sample grid.")
        self.set_phase(70, "Preparing original DSM relief...")
        original = ds.write_rgb_bands(folder / "original.tif", dsm.width, dsm.height, dsm.transform, dsm.projection,
                                      dt.relief_bands(dsm, dsm.z, self.cancel))
        ds.check_cancel(self.cancel)
        return Outcome(do.Scene(dsm, ortho, ref, original, manifest), None,
                       "Aligned inputs ready. Prepare both models and Run.")

    def open_inputs(self):
        if self.busy:
            return
        dsm, _ = QFileDialog.getOpenFileName(self, "Open metre-height DSM", "", "GeoTIFF (*.tif *.tiff)")
        if not dsm:
            return
        rgb, _ = QFileDialog.getOpenFileName(self, "Open exactly aligned RGB Byte orthophoto", str(Path(dsm).parent),
                                             "GeoTIFF (*.tif *.tiff)")
        if rgb:
            folder = self.directory()
            self.begin(lambda: self.load_job(Path(dsm), Path(rgb), None, {}, folder))

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
            new = (do.attach_reference(new_scene, comparison, folder, self.archive_sha256, self.cancel, self.set_phase)
                   if comparison is not None else None)
            ds.check_cancel(self.cancel)
            return Outcome(new_scene, new, "Reference updated; all generated height arrays are unchanged.")

        self.begin(job)

    def process(self):
        if self.scene is None or self.models is None or self.busy:
            return
        scene, models, folder = self.scene, list(self.models), self.directory()
        parameters = da.effective_parameters(scene.dsm, dt.PRESETS[self.preset.currentIndex()])
        overlap, threads = self.overlap.value(), self.threads.value()

        def job():
            result = do.compare(scene, models, parameters, overlap, threads, folder, self.archive_sha256, self.cancel,
                                self.set_phase)
            return Outcome(scene, result, "All three methods completed from the same full source grid.")

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
            self.failure("Cancelled; last completed comparison retained." if cancelled else str(error))
            return
        if self.cancel.is_set() and (out.scene is not None or out.models is not None):
            self.failure("Cancelled; last completed comparison retained.")
            return
        try:
            if out.models is not None:
                self.models = out.models
                self.model_info.setText("pix_grad + rgb_grad_fm ready\nVerified 256 × 256 tiles · CPU")
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
        elif self.setup_models and out.scene is not None:
            self.setup_models = False
            QTimer.singleShot(0, self.prepare_models)

    def apply_scene(self, out: Outcome):
        changed = self.scene is None or out.scene.dsm is not self.scene.dsm
        self.scene, self.comparison = out.scene, out.comparison
        if changed:
            self.show_input()
            for pane in (1, 2, 3):
                self.viewers[pane].clear_layers()
                self.viewers[pane].refresh_layers()
            self.probe_point = None
            self.draw_probe()
            self.probe.setText("Click a source pixel to inspect RGB and all terrain estimates.")
            self.applied = [None] * 4
            QTimer.singleShot(0, self.fit)
        d = self.scene.dsm
        self.source.setText(f"{Path(d.path).name} + {Path(self.scene.rgb.path).name}\n{d.width} × {d.height} · "
                            f"{d.pixel:g} m cells\n" + ("Aligned reference attached" if self.scene.reference else "No reference"))
        if self.comparison is not None:
            self.display()
            self.update_scores()
        else:
            self.scores.clearContents()
            self.summary.setText("Aligned inputs loaded. Run to create all three terrain estimates.")
            for pane in (1, 2, 3):
                self.headings[pane].setText(PENDING[pane - 1])

    # ----- maps ---------------------------------------------------------------------------
    def replace(self, pane: int, path):
        """Swap the map's raster while keeping its view (the empty map adopts the raster's CRS)."""
        viewer = self.viewers[pane]
        if viewer.layer_count():
            extent = viewer.get_view_extent()
        else:  # a map receiving its first layer joins the linked view instead of its own default
            extent = self.viewers[0].get_view_extent() if pane and self.viewers[0].layer_count() else None
        viewer.clear_layers()
        viewer.add_layer(Path(path))
        if extent is not None:
            viewer.set_view_extent(extent)
            self.applied[pane] = viewer.get_view_extent()
        viewer.refresh_layers()

    def show_input(self):
        if self.scene is None:
            return
        rgb = self.input.currentIndex() == 1
        self.replace(0, self.scene.rgb.path if rgb else self.scene.original)
        self.headings[0].setText("RGB ORTHOPHOTO · source input" if rgb else "ORIGINAL DSM · source input")

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
            if other != side and viewer.layer_count():
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
            self.statusBar().showMessage("Attach an aligned reference to show errors.")
        for method in range(3):
            self.replace(method + 1, self.comparison.maps[method][mode])
            self.headings[method + 1].setText(f"{do.METHODS[method].upper()} {SUFFIX[mode]}")
        self.legend.setText(LEGENDS[mode])

    def update_scores(self):
        if self.comparison is None:
            return
        r = self.comparison
        values = r.crop if self.scope.currentIndex() else r.full
        for method, score in enumerate(values):
            has = score.count > 0
            cells = (NAMES[method], str(score.count), f"{score.rmse:.3f}" if has else "—",
                     f"{score.mae:.3f}" if has else "—", f"{score.bias:.3f}" if has else "—")
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(COLORS[method]))
                self.scores.setItem(method, column, item)
        p = r.classical.parameters
        _, _, w, h = da.comparison_window(self.scene)
        pixel = self.scene.dsm.pixel
        self.summary.setText(
            f"Last run · pix_grad {r.ai[0].tiles} tiles · rgb_grad_fm {r.ai[1].tiles} tiles · overlap {r.overlap} px · "
            f"CPU threads {r.threads} · classical working {r.classical.working:g} m / window {p.window:g} m\nEvaluation: "
            f"{'shared crop' if self.scope.currentIndex() else 'full input'} · common crop {w} × {h} cells "
            f"({w * pixel:g} × {h * pixel:g} m). All methods processed the full input; outside-crop map areas are dimmed.")

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
        r, g, b = (band[i] for band in self.scene.rgb.bands)
        text = f"Source pixel {col} / {row}\nRGB {r} / {g} / {b}\n"
        if not d.valid[i]:
            text += "DSM NoData"
        else:
            text += f"DSM {d.z[i]:.2f} m"
            if self.comparison is not None:
                for method in range(3):
                    text += f"\n{do.METHODS[method]} {self.comparison.heights(method)[i]:.2f} m"
            reference = self.scene.reference
            if reference is not None and reference.valid[i]:
                text += f"\nReference {reference.z[i]:.2f} m"
        self.probe.setText(text)
        self.probe_point = (d.transform[0] + (col + 0.5) * d.pixel, d.transform[3] - (row + 0.5) * d.pixel)
        self.draw_probe()

    def export_results(self):
        if self.comparison is None or self.busy:
            return
        base = QFileDialog.getExistingDirectory(self, "Choose parent folder for a new complete result bundle")
        if not base:
            return
        result = self.comparison

        def job():
            target = do.export_bundle(result, Path(base), self.cancel, self.set_phase)
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
    parser = argparse.ArgumentParser(description="Compare independent classical, DSM-only AI and DSM+RGB AI terrain estimates.")
    parser.add_argument("--data-dir", metavar="directory", help="Data/model cache root.")
    parser.add_argument("--sample-archive", metavar="zip", help="Exact pinned DSM+ortho sample ZIP.")
    parser.add_argument("--sample-url", metavar="url", help="HTTPS sample mirror; pinned hashes still apply.")
    for model in ("pix", "rgb"):
        parser.add_argument(f"--{model}-model-archive", metavar="zip", help=f"Pinned {model} model ZIP.")
        parser.add_argument(f"--{model}-model-url", metavar="url", help=f"HTTPS {model} model mirror; pinned hashes still apply.")
    arguments, qt_arguments = parser.parse_known_args()
    app = QApplication([sys.argv[0], *qt_arguments])
    app.setApplicationName("DsmOrthoToDtm")
    palette = app.palette()
    for role, color in ((QPalette.ColorRole.Window, "#f2f6f8"), (QPalette.ColorRole.Base, "white"),
                        (QPalette.ColorRole.WindowText, "#233e50"), (QPalette.ColorRole.Text, "#233e50")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    try:
        ds.configure_runtime()
        window = OrthoWindow(arguments)
    except Exception as error:
        QMessageBox.critical(None, "DsmOrthoToDtm", str(error))
        return 1
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    window.show_viewers()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
