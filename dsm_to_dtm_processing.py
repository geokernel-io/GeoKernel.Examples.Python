"""DSM to DTM: live classical processing.

Run the classical conversion (native-multiscale-morphological-tin-v1) on the input DSM,
change parameters, inspect the newly generated terrain and export numeric GeoTIFFs. Three
linked native GeoKernel 2D maps show the original DSM, the generated DTM and a selectable
diagnostic map. The reference is evaluation-only; it is never an input to processing.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

import dsm_support as ds
import dsm_terrain as dt
from common import ROOT_DIR, application_icon
from dsm_maps import NativeMap
from geokernel import ViewerEventType, ViewerTool

TITLE = "DSM to DTM | Live classical processing — GeoKernel"
STYLE = (
    "QMainWindow,QWidget#page{background:#f2f6f8;color:#233e50;}"
    "QLabel#title{font-size:22px;font-weight:600;color:#145e72;}"
    "QLabel#heading{background:#e4eef2;color:#125a70;padding:9px;font-weight:600;} QPushButton{padding:7px;}"
    "QToolBar{background:white;border-bottom:1px solid #d5e2e9;spacing:8px;padding:7px;}")
DIAGNOSTIC_TITLES = ("REMOVED HEIGHT · DSM − DTM", "PROCESSING QUALITY · supports / edges", "REFERENCE ERROR · DTM − reference")
LEGENDS = ("Removed height: white 0 m → dark red ≥20 m. Display saturation only. NoData gray.",
           "Quality: teal retained source · pale interpolated · orange edge-sensitive · purple hull fallback · gray NoData. "
           "Full flag combinations are saved in QA GeoTIFF.",
           "Signed error: blue ≤−2 m · white 0 · red ≥+2 m. Shared fixed scale; numeric scores are not clipped.")


@dataclass
class Scene:
    dsm: dt.Raster
    reference: dt.Raster | None
    original: Path
    manifest: dict = field(default_factory=dict)


@dataclass
class Run:
    terrain: dt.Terrain
    dtm: Path
    removed: Path
    quality: Path
    display: Path
    diagnostics: list
    all: dt.Score = field(default_factory=dt.Score)
    interior: dt.Score = field(default_factory=dt.Score)
    report: dict = field(default_factory=dict)


@dataclass
class Outcome:
    scene: Scene | None = None
    run: Run | None = None
    message: str = ""


def evaluate(scene: Scene, run: Run) -> None:
    """Score after processing, over all shared valid cells and outside the edge band."""
    import math

    run.all = dt.score(scene.dsm, run.terrain.dtm, scene.reference)
    border = int(math.ceil(run.terrain.parameters.window * 0.5 / scene.dsm.pixel))
    run.interior = dt.score(scene.dsm, run.terrain.dtm, scene.reference, border)
    run.report = dt.report_for(scene.dsm, scene.reference, scene.manifest, run.terrain, run.all, run.interior)


class Bridge(QObject):
    # Native viewer callbacks may run while the viewer renders; handle them afterwards.
    event = Signal(int, object)


class ProcessingWindow(QMainWindow):
    def __init__(self, arguments: argparse.Namespace):
        super().__init__()
        self.arguments = arguments
        self.assets = ds.read_json(ds.ZURICH_V2)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.temporary = tempfile.TemporaryDirectory(prefix="geokernel-dsm-processing-")
        self.cancel = threading.Event()
        self.pending: Future | None = None
        self.scene: Scene | None = None
        self.run: Run | None = None
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
        self.resize(1720, 960)
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

        def button(text, slot):
            item = QPushButton(text)
            item.clicked.connect(slot)
            controls.addWidget(item)
            return item

        page = QWidget(objectName="page")
        layout = QHBoxLayout(page)
        sidebar = QWidget()
        controls = QVBoxLayout(sidebar)
        controls.setContentsMargins(0, 0, 8, 0)
        controls.setSpacing(9)
        controls.addWidget(label("DSM → DTM\nRun the conversion", "title"))
        controls.addWidget(label("Live multiscale filtering + TIN.\nChange parameters, then Run."))
        self.sample_button = button("Load Zurich sample", self.load_sample)
        self.open_button = button("Open DSM GeoTIFF...", self.open_dsm)
        self.reference_button = button("Open reference (optional)...", self.open_reference)
        self.source = label("No source loaded.")
        self.source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.source)
        self.presets = QComboBox(objectName="processingPreset")
        self.presets.addItems(["Balanced", "Remove more objects", "Preserve more relief"])
        controls.addWidget(self.presets)
        form = QFormLayout()
        self.parameters = []

        def parameter(title, minimum, maximum, value, step, decimals):
            spin = QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setDecimals(decimals)
            spin.setSingleStep(step)
            spin.setValue(value)
            form.addRow(title, spin)
            self.parameters.append(spin)
            spin.valueChanged.connect(self.parameters_changed)
            return spin

        self.working = parameter("Working grid (m)", 0.25, 20, 2, 0.5, 2)
        self.window = parameter("Max. window (m)", 4, 200, 64, 4, 1)
        self.threshold = parameter("Base threshold (m)", 0.05, 3, 0.4, 0.05, 2)
        self.slope = parameter("Slope allowance", 0, 0.5, 0.12, 0.02, 2)
        self.terrain = parameter("Relief allowance", 0, 2, 0.5, 0.1, 2)
        self.retain = parameter("Keep tolerance (m)", 0, 1, 0.35, 0.05, 2)
        controls.addLayout(form)
        self.presets.activated.connect(self.apply_preset)
        self.run_button = button("Run DSM → DTM", self.process)
        self.cancel_button = button("Cancel", self.request_cancel)
        self.state = label("Load a DSM to begin.")
        controls.addWidget(self.state)
        controls.addWidget(label("Right map"))
        self.mode = QComboBox(objectName="diagnosticMode")
        self.mode.addItems(["Removed height: DSM − DTM", "Support / edge quality", "Signed reference error"])
        self.mode.currentIndexChanged.connect(self.show_diagnostic)
        controls.addWidget(self.mode)
        self.metrics = label("Reference errors appear after a completed run.")
        controls.addWidget(self.metrics)
        self.save_button = button("Save result GeoTIFFs...", self.save_result)
        self.probe = label("Click any map to inspect source heights.")
        self.probe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.probe)
        controls.addStretch()
        controls.addWidget(label("Sample: Federal Office of Topography swisstopo.\nReference is evaluation-only. "
                                 "Heights are metres; no vertical datum conversion."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(310)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(sidebar)
        layout.addWidget(scroll)

        workspace = QVBoxLayout()
        maps = QHBoxLayout()
        maps.setSpacing(8)
        self.headings = []
        titles = ("ORIGINAL DSM · input", "PROCESSED DTM · Run to generate", "REMOVED HEIGHT · Run to generate")
        for pane, viewer in enumerate(self.viewers):
            column = QVBoxLayout()
            column.setSpacing(0)
            heading = label(titles[pane], "heading")
            column.addWidget(heading)
            widget = viewer.qt_widget(auto_close=False)
            widget.setMinimumSize(240, 260)
            column.addWidget(widget, 1)
            maps.addLayout(column, 1)
            self.headings.append(heading)
            viewer.set_tool(ViewerTool.PAN)
            viewer.set_event_callback(lambda event, side=pane: self.bridge.event.emit(side, event))
        workspace.addLayout(maps, 1)
        self.legend = label("Original DSM remains visible. Both relief maps use identical lighting and contrast.")
        workspace.addWidget(self.legend)
        self.summary = label("No processing has run yet.")
        workspace.addWidget(self.summary)
        workspace.addWidget(label("Edge-sensitive band = half the maximum filter window. Use a larger DSM and crop "
                                  "afterward for better context. This prototype is independent of ArcGIS Terrain Filter."))
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
            toolbar.addAction(QIcon(str(images / "FullExtent.png")), "Fit scene", self.fit),
        )
        self.progress = QProgressBar()
        self.progress.setFixedWidth(230)
        self.statusBar().addPermanentWidget(self.progress)
        self.controls = [self.sample_button, self.open_button, self.presets, *self.parameters]

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
        self.run_button.setEnabled(not busy and self.scene is not None)
        self.reference_button.setEnabled(not busy and self.scene is not None)
        self.save_button.setEnabled(not busy and self.run is not None)
        self.mode.setEnabled(not busy and self.run is not None)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)

    def set_phase(self, value: int, text: str):
        # Worker thread: only primitive state crosses to the GUI timer.
        self._phase = (value, text)

    def request_cancel(self):
        self.cancel.set()
        self.cancel_button.setEnabled(False)
        self.set_phase(self._phase[0], "Cancelling; completed result will be retained...")

    def parameters_changed(self):
        if self.run is not None:
            self.state.setText("Controls changed. Run to update; displayed result and scores still use the last completed run.")

    def apply_preset(self, index: int):
        preset = dt.PRESETS[index]
        for spin, value in zip(self.parameters, (preset.working, preset.window, preset.threshold, preset.slope,
                                                 preset.terrain, preset.retain)):
            spin.setValue(value)

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
        self.statusBar().showMessage(message)
        if self.close_queued:
            QTimer.singleShot(0, self.close)
        elif not self.cancel.is_set():
            QMessageBox.warning(self, "Operation failed", message)

    # ----- jobs ---------------------------------------------------------------------------
    def load_sample(self):
        if self.busy:
            return
        url = self.arguments.sample_url or self.assets["url"]
        folder = self.directory()

        def job():
            self.set_phase(0, "Checking cached sample files...")
            sample = ds.prepare_sample(self.assets, self.data_root(), self.arguments.sample_archive, url,
                                       self.cancel, self.set_phase)
            ds.check_cancel(self.cancel)
            ds.configure_runtime(sample)
            return self.load_job(sample / "dsm.tif", sample / "dtm_reference.tif",
                                 ds.read_json(sample / "source-manifest.json"), folder)

        self.begin(job)

    def load_job(self, path: Path, reference: Path | None, manifest: dict, folder: Path) -> Outcome:
        self.set_phase(5, "Reading source DSM...")
        dsm = dt.read_raster(path, self.cancel)
        ref = None
        if reference is not None:
            self.set_phase(30, "Reading evaluation-only reference...")
            ref = dt.read_raster(reference, self.cancel)
            dt.validate_reference(dsm, ref)
        self.set_phase(60, "Preparing original DSM relief...")
        original = ds.write_rgb_bands(folder / "original.tif", dsm.width, dsm.height, dsm.transform, dsm.projection,
                                      dt.relief_bands(dsm, dsm.z, self.cancel))
        ds.check_cancel(self.cancel)
        return Outcome(Scene(dsm, ref, original, manifest), None, "Source ready. Choose parameters and Run.")

    def open_dsm(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open DSM: metre heights in projected metre CRS", "",
                                              "GeoTIFF (*.tif *.tiff)")
        if path:
            folder = self.directory()
            self.begin(lambda: self.load_job(Path(path), None, {}, folder))

    def open_reference(self):
        if self.scene is None or self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open aligned reference (evaluation only)", "", "GeoTIFF (*.tif *.tiff)")
        if not path:
            return
        scene, run, folder = self.scene, self.run, self.directory()

        def job():
            self.set_phase(10, "Reading evaluation-only reference...")
            reference = dt.read_raster(Path(path), self.cancel)
            dt.validate_reference(scene.dsm, reference)
            new_scene = replace(scene, reference=reference)
            new_run = None
            if run is not None:
                new_run = replace(run, diagnostics=list(run.diagnostics))
                evaluate(new_scene, new_run)
                bands = dt.diagnostic_bands(scene.dsm, run.terrain, 2, reference, self.cancel)
                new_run.diagnostics[2] = ds.write_rgb_bands(folder / "reference-error.tif", scene.dsm.width,
                                                            scene.dsm.height, scene.dsm.transform, scene.dsm.projection, bands)
            return Outcome(new_scene, new_run, "Reference attached; processing heights unchanged.")

        self.begin(job)

    def process(self):
        if self.scene is None or self.busy:
            return
        parameters = dt.Parameters(*(spin.value() for spin in self.parameters))
        scene, folder = self.scene, self.directory()

        def job():
            terrain = dt.estimate(scene.dsm, parameters, self.cancel, self.set_phase)
            d = scene.dsm

            def rgb(name, bands):
                return ds.write_rgb_bands(folder / name, d.width, d.height, d.transform, d.projection, bands)

            dtm = dt.write_raster(d, folder / "dtm.tif", terrain.dtm, 6)
            ds.check_cancel(self.cancel)
            removed = dt.write_raster(d, folder / "removed.tif", terrain.removed, 6)
            ds.check_cancel(self.cancel)
            quality = dt.write_raster(d, folder / "quality.tif", terrain.quality, 1)
            display = rgb("terrain-relief.tif", dt.relief_bands(d, terrain.dtm, self.cancel))
            diagnostics = [rgb(f"diagnostic-{mode}.tif", dt.diagnostic_bands(d, terrain, mode, scene.reference, self.cancel))
                           for mode in range(3)]
            run = Run(terrain, dtm, removed, quality, display, diagnostics)
            self.set_phase(96, "Scoring reference after processing...")
            evaluate(scene, run)
            ds.check_cancel(self.cancel)
            return Outcome(scene, run, "Processing complete. Change parameters to run again, or save the result.")

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
            self.failure("Cancelled. Last completed source/result retained." if cancelled else str(error))
            return
        if self.cancel.is_set():
            self.failure("Cancelled. Last completed source/result retained.")
            return
        try:
            if out.scene is not None:
                changed = self.scene is None or out.scene.dsm is not self.scene.dsm
                self.scene, self.run = out.scene, out.run
                if changed:
                    self.replace(0, self.scene.original)
                    for pane in (1, 2):
                        self.viewers[pane].clear_layers()
                        self.viewers[pane].refresh_layers()
                    self.probe_point = None
                    self.draw_probe()
                    self.probe.setText("Click a map to inspect source heights.")
                    self.applied = [None, None, None]
                    QTimer.singleShot(0, self.fit)
                if self.run is not None:
                    self.replace(1, self.run.display)
                    self.show_diagnostic()
                    self.update_summary()
                else:
                    self.headings[1].setText("PROCESSED DTM · Run to generate")
                    self.headings[2].setText("REMOVED HEIGHT · Run to generate")
                    self.metrics.setText("No processing has run yet.")
                    self.summary.setText("Source loaded. Run to generate a new terrain estimate.")
                d = self.scene.dsm
                self.source.setText(f"{Path(d.path).name}\n{d.width} × {d.height} · {d.pixel:g} m cells\n"
                                    + ("Aligned reference attached" if self.scene.reference
                                       else "No reference: heights can still be processed"))
        except Exception as error:
            self.failure(str(error))
            return
        self.set_busy(False)
        self.state.setText(out.message)
        self.statusBar().showMessage(out.message)
        if self.close_queued:
            QTimer.singleShot(0, self.close)

    # ----- maps ---------------------------------------------------------------------------
    def replace(self, pane: int, path: Path):
        """Swap the map's raster while keeping its view (the empty map adopts the raster's CRS)."""
        viewer = self.viewers[pane]
        extent = viewer.get_view_extent() if viewer.layer_count() else None
        viewer.clear_layers()
        viewer.add_layer(path)
        if extent is not None:
            viewer.set_view_extent(extent)
        viewer.refresh_layers()

    def fit(self):
        if self.scene is None:
            return
        x0, y0, x1, y1 = self.scene.dsm.extent()
        pad = self.scene.dsm.pixel * 10
        self.viewers[0].set_view_extent((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
        self.sync_from(0)

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
            if value is not None and value != self.applied[side]:
                self.sync_from(side)
        elif kind == ViewerEventType.MAP_MOUSE_DOWN and event.int_value2 == 1:  # Qt::LeftButton
            self.presses[side] = (event.screen_rectangle.left, event.screen_rectangle.top)
        elif kind == ViewerEventType.MAP_MOUSE_UP and event.int_value2 == 1:
            press, self.presses[side] = self.presses[side], None
            screen = (event.screen_rectangle.left, event.screen_rectangle.top)
            if (event.int_value == ViewerTool.PAN and press
                    and abs(press[0] - screen[0]) + abs(press[1] - screen[1]) <= 3):
                self.inspect(event.extent.x_min, event.extent.y_min)

    def show_diagnostic(self):
        if self.run is None:
            return
        mode = self.mode.currentIndex()
        if mode == 2 and self.scene.reference is None:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(0)
            self.mode.blockSignals(False)
            mode = 0
            self.statusBar().showMessage("Attach an aligned reference to show errors.")
        self.replace(2, self.run.diagnostics[mode])
        self.headings[1].setText("PROCESSED DTM · live native result")
        self.headings[2].setText(DIAGNOSTIC_TITLES[mode])
        self.legend.setText(LEGENDS[mode])

    def update_summary(self):
        run, p = self.run, self.run.terrain.parameters
        self.summary.setText(
            f"Last completed run · {run.terrain.supports} supports · {run.terrain.seconds:.2f} s · working "
            f"{run.terrain.working:g} m · max window {p.window:g} m · base {p.threshold:g} m · slope {p.slope:g} · "
            f"relief {p.terrain:g} · keep {p.retain:g} m\nEdge band {p.window * 0.5:g} m · hull fallback "
            f"{run.terrain.summary['outside_hull_fallback_pixels']} pixels · reference is evaluation-only.")

        def line(name, s):
            return (f"{name} ({s.count} px)\nRMSE {s.rmse:.3f} m · MAE {s.mae:.3f} m · bias {s.bias:.3f} m" if s.count
                    else f"{name}: no common valid reference pixels")

        self.metrics.setText(line("All valid reference cells", run.all) + "\n\n" + line("Interior outside edge band", run.interior)
                             if self.scene.reference else
                             "No reference attached. Scores are unavailable; processing does not require a reference.")

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
        text = f"Source pixel · {col} / {row}\n"
        if not d.valid[i]:
            text += "NoData"
        else:
            text += f"DSM {d.z[i]:.2f} m"
            if self.run is not None:
                t = self.run.terrain
                text += f"\nDTM {t.dtm[i]:.2f} m · removed {t.removed[i]:.2f} m\nQA bits: {t.quality[i]}"
            reference = self.scene.reference
            if reference is not None and reference.valid[i]:
                text += f"\nReference {reference.z[i]:.2f} m"
                if self.run is not None:
                    text += f" · error {self.run.terrain.dtm[i] - reference.z[i]:.3f} m"
        self.probe.setText(text)
        self.probe_point = (d.transform[0] + (col + 0.5) * d.pixel, d.transform[3] - (row + 0.5) * d.pixel)
        self.draw_probe()

    def save_result(self):
        if self.run is None or self.busy:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save DTM, removed heights, QA and JSON",
                                              str(Path.home() / "terrain-result.tif"), "GeoTIFF (*.tif)")
        if not path:
            return
        if not path.lower().endswith(".tif"):
            path += ".tif"
        target = Path(path)
        stem = target.with_suffix("")
        destinations = [target, Path(f"{stem}.removed.tif"), Path(f"{stem}.qa.tif"), Path(f"{stem}.json")]
        scene, run = self.scene, self.run
        sources = [scene.dsm.path] + ([scene.reference.path] if scene.reference else [])
        if any(dt.same_file(d, s) for d in destinations for s in sources):
            QMessageBox.warning(self, "Cannot export", "Choose output names different from the source and reference.")
            return
        if any(d.exists() for d in destinations[1:]) and QMessageBox.question(
                self, "Replace existing result companions?",
                "Removed-height, QA or JSON companion files already exist. Replace the result set?") != QMessageBox.StandardButton.Yes:
            return

        def job():
            saved = []
            try:
                for i, source in enumerate((run.dtm, run.removed, run.quality)):
                    self.set_phase(i * 30, f"Saving {destinations[i].name}")
                    dt.atomic_copy(source, destinations[i], self.cancel)
                    saved.append(str(destinations[i]))
                ds.check_cancel(self.cancel)
                dt.write_json(destinations[3], run.report)
            except Exception as error:
                committed = ("\nFiles already committed:\n" + "\n".join(saved)) if saved else ""
                raise RuntimeError(f"{error}{committed}") from error
            return Outcome(None, None, "Saved DTM, removed heights, QA flags and provenance JSON.")

        self.begin(job)

    # ----- shutdown -----------------------------------------------------------------------
    def closeEvent(self, event):
        if self.busy:
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
    parser = argparse.ArgumentParser(description="Live classical DSM-to-DTM filtering, TIN reconstruction and reference evaluation.")
    parser.add_argument("--sample-archive", metavar="zip", help="Use the pinned local sample ZIP.")
    parser.add_argument("--sample-url", metavar="url", help="HTTPS mirror; pinned hashes still apply.")
    parser.add_argument("--data-dir", metavar="directory", help="Sample cache directory.")
    arguments, qt_arguments = parser.parse_known_args()
    app = QApplication([sys.argv[0], *qt_arguments])
    app.setApplicationName("DsmToDtmProcessing")
    palette = app.palette()
    for role, color in ((QPalette.ColorRole.Window, "#f2f6f8"), (QPalette.ColorRole.Base, "white"),
                        (QPalette.ColorRole.WindowText, "#233e50"), (QPalette.ColorRole.Text, "#233e50")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    try:
        ds.configure_runtime()
        window = ProcessingWindow(arguments)
    except Exception as error:
        QMessageBox.critical(None, "DsmToDtmProcessing", str(error))
        return 1
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    window.show_viewers()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
