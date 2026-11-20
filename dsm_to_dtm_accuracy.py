"""DSM to DTM: reference accuracy by area.

Three linked native GeoKernel 2D maps keep the original DSM beside classical and AI error
maps on one shared colour scale. Select an area to compare numeric errors, their
distribution and individual source pixels. Scores use the numeric Float32 rasters; the
maps are display-only Byte RGB images. No inference runs here; the reference is
evaluation-only.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QLinearGradient, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import dsm_support as ds
from common import ROOT_DIR, application_icon
from dsm_maps import NativeMap
from geokernel import ViewerEventType, ViewerTool

TITLE = "DSM to DTM | Where is each method more accurate? — GeoKernel"
READY = "Ready · select an evaluation area or click any source pixel."
FULL_EXTENT = (2677090, 1251340, 2677360, 1251610)
PRESETS = ("Full sample", "Central urban block", "Northern block", "Southern block", "Custom selection")
METHOD_COLORS = ("#087e8b", "#8857bd")
STYLE = (
    "QMainWindow,QWidget#page{background:#f2f6f8;color:#233e50;}"
    "QLabel#title{font-size:21px;font-weight:600;color:#145e72;}"
    "QLabel#heading{background:#e4eef2;color:#125a70;padding:9px;font-weight:600;}"
    "QLabel#card{background:white;border:1px solid #d5e2e9;padding:10px;} QPushButton{padding:7px;}"
    "QToolBar{background:white;border-bottom:1px solid #d5e2e9;spacing:8px;padding:7px;}")
HEADINGS = (("CLASSICAL DTM · signed error", "AI DTM · signed error"),
            ("CLASSICAL DTM · absolute error", "AI DTM · absolute error"),
            ("CLASSICAL DTM · terrain estimate", "AI DTM · experimental pix_grad"))


def prepare_displays(grids: ds.Grids, folder: Path, cancel: threading.Event, report) -> dict:
    """Nineteen shared-scale Byte RGB maps: DSM relief; per method 4 signed, 4 absolute, 1 relief."""
    done = 0

    def save(bands, name):
        nonlocal done
        ds.check_cancel(cancel)
        path = ds.write_rgb_bands(folder / name, grids.width, grids.height, grids.transform, grids.projection, bands)
        done += 1
        report(done * 100 // 19, "Reading heights and preparing shared-scale Byte RGB maps...")
        return path

    def relief(band):
        gray = ds.relief(grids, band, cancel)
        return gray, gray, gray

    files = {"original": save(relief(0), "original.tif"), "methods": []}
    for method in (1, 2):
        paths = [None] * 9
        for limit_index, limit in enumerate(ds.DISPLAY_LIMITS):
            paths[limit_index] = save(ds.error_bands(grids, method, False, limit, cancel), f"signed-{method}-{limit_index}.tif")
            paths[4 + limit_index] = save(ds.error_bands(grids, method, True, limit, cancel), f"absolute-{method}-{limit_index}.tif")
        paths[8] = save(relief(method), f"terrain-{method}.tif")
        files["methods"].append(paths)
    return files


class ColorLegend(QWidget):
    def __init__(self):
        super().__init__()
        self.mode, self.limit = 0, 2.0
        self.setMinimumHeight(62)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        p.setPen(QColor("#476174"))
        w = self.width()
        if self.mode == 2:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Neutral relief: same light and contrast for both terrain estimates. "
                       "Switch to an error view to compare reference differences.")
            return
        p.drawText(QRectF(8, 1, w - 16, 20), Qt.AlignmentFlag.AlignCenter,
                   "Estimated DTM − reference: blue below · white zero · red above (metres)" if self.mode == 0
                   else "Absolute reference error: white zero · orange/red larger errors (metres)")
        gradient = QLinearGradient(70, 0, w - 70, 0)
        for i in range(21):
            t = i / 20
            value = (t * 2 - 1) * self.limit if self.mode == 0 else t * self.limit
            gradient.setColorAt(t, QColor(*ds.error_color(value, self.mode == 1, self.limit)))
        p.fillRect(QRectF(70, 25, w - 140, 13), gradient)
        p.drawText(QRectF(8, 42, 180, 18), Qt.AlignmentFlag.AlignLeft, f"≤ −{self.limit:g} m" if self.mode == 0 else "0 m")
        p.drawText(QRectF(w - 188, 42, 180, 18), Qt.AlignmentFlag.AlignRight, f"≥ {self.limit:g} m")
        p.drawText(QRectF(200, 42, w - 400, 18), Qt.AlignmentFlag.AlignCenter,
                   "One shared scale · display saturation only; numeric errors are unchanged")


class ErrorHistogram(QWidget):
    LABELS = ("≤0.25", "0.25–0.5", "0.5–1", "1–2", "2–5", ">5 m")

    def __init__(self):
        super().__init__(objectName="errorHistogram")
        self.metrics: tuple[ds.Metric, ds.Metric] | None = None
        self.setMinimumHeight(150)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        if not self.metrics:
            return
        p.setPen(QColor("#476174"))
        p.drawText(QRectF(8, 1, self.width() - 16, 22), Qt.AlignmentFlag.AlignCenter,
                   "Absolute error distribution · evaluated area · teal classical / purple AI")
        plot = QRectF(50, 30, self.width() - 70, self.height() - 60)
        group = plot.width() / 6
        maximum = max([10.0] + [100.0 * c / m.count for m in self.metrics for c in m.bins])
        maximum = -(-maximum // 10) * 10
        for tick in range(3):
            y = plot.bottom() - tick * 0.5 * plot.height()
            p.setPen(QColor("#e2e9ee"))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor("#476174"))
            p.drawText(QRectF(0, y - 9, 43, 18), Qt.AlignmentFlag.AlignRight, f"{tick * 0.5 * maximum:.0f}%")
        for b in range(6):
            for method, metric in enumerate(self.metrics):
                height = 100.0 * metric.bins[b] / metric.count / maximum * plot.height()
                p.fillRect(QRectF(plot.left() + b * group + group * (0.18 + method * 0.32), plot.bottom() - height,
                                  group * 0.28, height), QColor(METHOD_COLORS[method]))
            p.setPen(QColor("#476174"))
            p.drawText(QRectF(plot.left() + b * group, plot.bottom() + 3, group, 20), Qt.AlignmentFlag.AlignCenter,
                       self.LABELS[b])


class Bridge(QObject):
    # Native viewer callbacks may run while the viewer renders; handle them afterwards.
    event = Signal(int, object)


class AccuracyWindow(QMainWindow):
    def __init__(self, arguments: argparse.Namespace):
        super().__init__()
        self.arguments = arguments
        self.assets = ds.read_json(ds.ZURICH_V2)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.temporary = tempfile.TemporaryDirectory(prefix="geokernel-dsm-accuracy-")
        self.cancel = threading.Event()
        self.pending: Future | None = None
        self.grids: ds.Grids | None = None
        self.area: tuple[int, int, int, int] | None = None
        self.area_name = ""
        self.metrics: tuple[ds.Metric, ds.Metric] | None = None
        self.probe_point: tuple[float, float] | None = None
        self.presses: list = [None, None, None]
        self.applied: list = [None, None, None]
        self.busy = self.close_queued = self.closed = False
        self.generation = 0
        self._progress = (0, "")
        self.viewers = [NativeMap(), NativeMap(), NativeMap()]
        self.bridge = Bridge(self)
        self.bridge.event.connect(self.viewer_event, Qt.ConnectionType.QueuedConnection)

        self.setWindowTitle(TITLE)
        self.setWindowIcon(application_icon())
        self.resize(1720, 970)
        self.setStyleSheet(STYLE)
        self._build()
        self.poll = QTimer(self, interval=50, timeout=self.poll_work)
        self.set_busy(False)
        QTimer.singleShot(0, self.start)

    # ----- layout -------------------------------------------------------------------------
    def _build(self):
        def label(text, name=None):
            item = QLabel(text)
            item.setWordWrap(True)
            if name:
                item.setObjectName(name)
            return item

        page = QWidget(objectName="page")
        layout = QHBoxLayout(page)
        layout.setSpacing(12)
        sidebar = QWidget()
        controls = QVBoxLayout(sidebar)
        controls.setContentsMargins(0, 0, 10, 0)
        controls.setSpacing(11)
        controls.addWidget(label("Where does each\nmethod work better?", "title"))
        controls.addWidget(label("Zürich · same DSM and reference\n250 × 250 m · 0.5 m source cells"))
        self.instructions = label("Preparing sample data...", "card")
        controls.addWidget(self.instructions)
        self.mode = QComboBox(objectName="displayMode")
        self.mode.addItems(["Signed reference errors", "Absolute reference errors", "Terrain estimates"])
        controls.addWidget(label("Map comparison"))
        controls.addWidget(self.mode)
        self.range = QComboBox(objectName="displayRange")
        self.range.addItems(["1 m", "2 m", "5 m", "10 m"])
        self.range.setCurrentIndex(1)
        self.threshold = QDoubleSpinBox(objectName="errorThreshold")
        self.threshold.setRange(0.1, 20)
        self.threshold.setDecimals(1)
        self.threshold.setSingleStep(0.5)
        self.threshold.setValue(2)
        self.threshold.setSuffix(" m")
        form = QFormLayout()
        form.addRow("Display limit", self.range)
        form.addRow("Large error >", self.threshold)
        controls.addLayout(form)
        self.presets = QComboBox(objectName="studyPreset")
        self.presets.addItems(PRESETS)
        controls.addWidget(label("Study-area preset"))
        controls.addWidget(self.presets)
        self.winners = label("Compare lower errors for each metric.", "card")
        controls.addWidget(self.winners)
        self.probe = label("Click a map pixel to inspect its heights and signed errors.", "card")
        self.probe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.probe)
        controls.addWidget(label("One shared reference and source grid. Geographic presets are not land-cover "
                                 "classes. Dimmed map pixels are outside the evaluated area."))
        controls.addStretch()
        self.export = QPushButton("Export area report", objectName="exportReport")
        self.reload = QPushButton("Retry / reload sample")
        self.cancel_button = QPushButton("Cancel loading")
        for button in (self.export, self.reload, self.cancel_button):
            controls.addWidget(button)
        controls.addWidget(label("Source: Federal Office of Topography swisstopo\nAI: David Perez · experimental pix_grad"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(290)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(sidebar)
        layout.addWidget(scroll)

        workspace = QVBoxLayout()
        maps = QHBoxLayout()
        maps.setSpacing(8)
        self.headings = []
        titles = ("ORIGINAL DSM · context", "CLASSICAL DTM · reference error", "AI DTM · reference error")
        for pane, viewer in enumerate(self.viewers):
            column = QVBoxLayout()
            column.setSpacing(0)
            heading = label(titles[pane], "heading")
            column.addWidget(heading)
            widget = viewer.qt_widget(auto_close=False)
            widget.setMinimumSize(270, 290)
            column.addWidget(widget, 1)
            maps.addLayout(column, 1)
            self.headings.append(heading)
            viewer.set_tool(ViewerTool.PAN)
            viewer.set_event_callback(lambda event, side=pane: self.bridge.event.emit(side, event))
        workspace.addLayout(maps, 1)
        self.legend = ColorLegend()
        workspace.addWidget(self.legend)
        self.scope = label("No evaluation area loaded.")
        workspace.addWidget(self.scope)
        self.table = QTableWidget(2, 6, objectName="metricTable")
        self.table.setHorizontalHeaderLabels(["Method", "RMSE (m)", "MAE (m)", "Bias (m)", "P95 |error| (m)",
                                              "|error| > 2 m (%)"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setFixedHeight(101)
        workspace.addWidget(self.table)
        self.histogram = ErrorHistogram()
        workspace.addWidget(self.histogram)
        workspace.addWidget(label(
            "Prepared independent results; reference is evaluation-only. Source heights: LN02 metres, no vertical "
            "datum conversion. Source filename years: DSM 2018 / reference 2019. Fixed development crop; these are "
            "not held-out benchmark results."))
        layout.addLayout(workspace, 1)
        self.setCentralWidget(page)

        toolbar = self.addToolBar("Area and navigation")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.area_action = QAction("Select evaluation area", self, checkable=True, objectName="selectArea")
        toolbar.addAction(self.area_action)
        current = toolbar.addAction("Evaluate current view",
                                    lambda: self.choose_area(self.extent_tuple(self.viewers[0].get_view_extent()),
                                                             "Current map view"))
        whole = toolbar.addAction("Full sample", lambda: self.apply_preset(0))
        toolbar.addSeparator()
        images = ROOT_DIR / "images"
        pan = toolbar.addAction("Pan", lambda: self.use_tool(ViewerTool.PAN))
        box = toolbar.addAction("Zoom box", lambda: self.use_tool(ViewerTool.ZOOM_BOX))
        zoom_in = toolbar.addAction(QIcon(str(images / "ZoomIn.png")), "Zoom in", lambda: self.viewers[0].zoom_in(1.5))
        zoom_out = toolbar.addAction(QIcon(str(images / "ZoomOut.png")), "Zoom out",
                                     lambda: self.viewers[0].zoom_out(1.5))
        fit = toolbar.addAction(QIcon(str(images / "FullExtent.png")), "Full extent", self.full_extent)
        self.navigation = (current, whole, pan, box, zoom_in, zoom_out, fit)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(210)
        self.statusBar().addPermanentWidget(self.progress)

        self.area_action.toggled.connect(self.toggle_area)
        self.mode.currentIndexChanged.connect(self.select_display)
        self.range.currentIndexChanged.connect(self.select_display)
        self.threshold.valueChanged.connect(lambda: self.update_metrics() if self.grids else None)
        self.presets.activated.connect(self.apply_preset)
        self.export.clicked.connect(self.export_report)
        self.reload.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.request_cancel)

    def show_viewers(self):
        # Embedded native maps start painting once shown, after the host window is visible.
        for viewer in self.viewers:
            viewer.show()

    # ----- loading ------------------------------------------------------------------------
    def data_root(self) -> Path:
        return Path(self.arguments.data_dir).resolve() if self.arguments.data_dir else ROOT_DIR / "data"

    def set_busy(self, busy: bool):
        self.busy = busy
        ready = not busy and self.grids is not None
        self.reload.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)
        for widget in (self.mode, self.threshold, self.presets, self.export, self.area_action, *self.navigation):
            widget.setEnabled(ready)
        self.range.setEnabled(ready and self.mode.currentIndex() != 2)

    def failure(self, message: str):
        self.set_busy(False)
        self.statusBar().showMessage(message)
        if self.close_queued:
            QTimer.singleShot(0, self.close)
        elif not self.cancel.is_set():
            QMessageBox.warning(self, "Unable to load comparison", message)

    def request_cancel(self):
        self.cancel.set()
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("Cancelling preparation...")

    def report(self, percent: int, message: str):
        # Worker thread: only primitive state crosses to the GUI timer.
        self._progress = (percent, message)

    def start(self):
        if self.busy:
            return
        self.cancel.clear()
        self.area_action.setChecked(False)
        self._progress = (0, "Checking cached sample files...")
        self.set_busy(True)
        self.generation += 1
        folder = Path(self.temporary.name) / str(self.generation)
        url = self.arguments.sample_url or self.assets["url"]

        def job():
            sample = ds.prepare_sample(self.assets, self.data_root(), self.arguments.sample_archive, url,
                                       self.cancel, self.report)
            ds.check_cancel(self.cancel)
            ds.configure_runtime(sample)
            folder.mkdir(parents=True, exist_ok=True)
            self.report(0, "Reading heights and preparing shared-scale Byte RGB maps...")
            grids = ds.read_grids(sample, self.cancel)
            return grids, prepare_displays(grids, folder, self.cancel, self.report)

        self.pending = self.executor.submit(job)
        self.poll.start()

    def poll_work(self):
        percent, message = self._progress
        self.progress.setValue(percent)
        self.statusBar().showMessage(message)
        if self.pending is None or not self.pending.done():
            return
        self.poll.stop()
        future, self.pending = self.pending, None
        try:
            grids, files = future.result()
        except Exception as error:
            cancelled = isinstance(error, ds.Cancelled) or self.cancel.is_set()
            self.failure("Preparation cancelled; completed comparison retained." if cancelled else str(error))
            return
        if self.cancel.is_set():
            self.failure("Preparation cancelled; completed comparison retained.")
            return
        try:
            self.publish(grids, files)
        except Exception as error:
            self.failure(str(error))
            return
        self.set_busy(False)
        if self.area is None:
            self.apply_preset(0)
        else:
            self.update_metrics()
            self.draw_area()
        self.instructions.setText("Select an area, choose a preset, or click a pixel to inspect errors.")
        self.statusBar().showMessage(READY)
        if self.close_queued:
            QTimer.singleShot(0, self.close)

    def publish(self, grids: ds.Grids, files: dict):
        self.grids = grids
        for pane, viewer in enumerate(self.viewers):
            viewer.clear_shapes()
            viewer.clear_layers()
            # The empty map adopts the first layer's CRS (EPSG:2056); new layers go to index 0.
            if pane == 0:
                viewer.add_layer(files["original"])
                viewer.set_layer_name(0, "Original DSM")
            else:
                for index, path in enumerate(files["methods"][pane - 1]):
                    viewer.add_layer(path)
                    viewer.set_layer_name(0, f"{'Classical' if pane == 1 else 'AI'} display {index}")
            if viewer.layer_count() != (1 if pane == 0 else 9):
                raise RuntimeError("The display layers were not added.")
        self.applied = [None, None, None]
        self.full_extent()
        self.select_display()

    # ----- maps ---------------------------------------------------------------------------
    @staticmethod
    def extent_tuple(extent):
        return (extent.x_min, extent.y_min, extent.x_max, extent.y_max)

    def full_extent(self):
        self.viewers[0].set_view_extent(FULL_EXTENT)
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
        self.area_action.setChecked(False)
        for viewer in self.viewers:
            viewer.set_tool(tool)

    def toggle_area(self, active: bool):
        for viewer in self.viewers:
            viewer.set_tool(ViewerTool.SELECT if active else ViewerTool.PAN)
        self.instructions.setText("Drag a box on any map. The same source pixels will be evaluated for both methods."
                                  if active else "Select an area, choose a preset, or click a pixel to inspect errors.")

    def select_display(self):
        mode, limit_index = self.mode.currentIndex(), self.range.currentIndex()
        self.legend.mode, self.legend.limit = mode, ds.DISPLAY_LIMITS[limit_index]
        self.legend.update()
        self.range.setEnabled(not self.busy and self.grids is not None and mode != 2)
        if self.grids is None:
            return
        selected = 8 if mode == 2 else (4 if mode == 1 else 0) + limit_index
        for method in (1, 2):
            viewer = self.viewers[method]
            for file in range(9):
                viewer.set_layer_visible(8 - file, file == selected)  # files 0..8 were prepended in order
            viewer.refresh_layers()
            self.headings[method].setText(HEADINGS[mode][method - 1])

    def viewer_event(self, side: int, event):
        if self.closed or self.grids is None:
            return
        kind = event.event_type
        if kind == ViewerEventType.VISIBLE_EXTENT_CHANGED:
            value = self.viewers[side].get_view_extent()
            if value is not None and value != self.applied[side]:
                self.sync_from(side)
        elif kind == ViewerEventType.MAP_SELECTION_BOX_FINISHED and self.area_action.isChecked():
            self.choose_area(self.extent_tuple(event.extent), "User-selected area")
            self.area_action.setChecked(False)
        elif kind == ViewerEventType.MAP_MOUSE_DOWN and event.int_value2 == 1:  # Qt::LeftButton
            self.presses[side] = (event.screen_rectangle.left, event.screen_rectangle.top)
        elif kind == ViewerEventType.MAP_MOUSE_UP and event.int_value2 == 1:
            press, self.presses[side] = self.presses[side], None
            screen = (event.screen_rectangle.left, event.screen_rectangle.top)
            if (press and not self.area_action.isChecked()
                    and abs(press[0] - screen[0]) + abs(press[1] - screen[1]) <= 3):
                self.inspect(event.extent.x_min, event.extent.y_min)

    def draw_area(self):
        """Dim everything outside the evaluated cells (four translucent bands) and outline them."""
        if self.grids is None or self.area is None:
            return
        x0, y0, x1, y1 = ds.window_extent(self.grids, self.area)
        g = self.grids
        margin = 2000.0
        ox0, oy0 = g.transform[0] - margin, g.transform[3] + g.height * g.transform[5] - margin
        ox1, oy1 = g.transform[0] + g.width * g.transform[1] + margin, g.transform[3] + margin
        bands = ((ox0, y1, ox1, oy1), (ox0, oy0, ox1, y0), (ox0, y0, x0, y1), (x1, y0, ox1, y1))
        dim = {"fillColor": "#ffffff", "fillOpacity": 100, "lineWidth": 0, "lineColor": "#ffffff"}
        outline = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        for viewer in self.viewers:
            viewer.clear_shapes()
            for a, b, c, d in bands:
                if c > a and d > b:
                    viewer.add_polygon_shape([(a, b), (c, b), (c, d), (a, d), (a, b)], dim)
            viewer.add_polyline_shape(outline, {"lineColor": "#167d8d", "lineWidth": 2})
            viewer.refresh_layers()  # owned shapes are drawn on the next full map render

    def draw_probe(self):
        for viewer in self.viewers:
            if self.probe_point is None:
                viewer.remove_overlay_shape("probe")
            else:
                viewer.set_overlay_point("probe", *self.probe_point,
                                         {"pointColor": "#dc3672", "pointSize": 11, "lineColor": "#ffffff", "lineWidth": 2})

    # ----- evaluation ---------------------------------------------------------------------
    def choose_area(self, extent, name: str, preset: int = -1):
        if self.grids is None:
            return
        try:
            window = ds.pixel_window(self.grids, extent)
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.area, self.area_name = window, name
        self.presets.blockSignals(True)
        self.presets.setCurrentIndex(4 if preset < 0 else preset)
        self.presets.blockSignals(False)
        self.update_metrics()
        self.draw_area()
        self.statusBar().showMessage("Updated both methods on exactly the same source cells.")

    def apply_preset(self, index: int):
        if self.grids is None:
            return
        if index == 4:
            self.area_action.setChecked(True)
            return
        self.area_action.setChecked(False)
        self.choose_area(ds.preset_area(self.grids, index), PRESETS[index], index)

    def update_metrics(self):
        if self.grids is None or self.area is None:
            return
        threshold = self.threshold.value()
        self.metrics = ds.measure(self.grids, self.area, threshold)
        self.histogram.metrics = self.metrics
        self.histogram.update()
        self.table.setHorizontalHeaderItem(5, QTableWidgetItem(f"|error| > {threshold:g} m (%)"))
        for method, metric in enumerate(self.metrics):
            values = ("AI · pix_grad" if method else "Classical", f"{metric.rmse:.3f}", f"{metric.mae:.3f}",
                      f"{metric.bias:.3f}", f"{metric.p95:.3f}", f"{100.0 * metric.above / metric.count:.2f}")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setForeground(QColor(METHOD_COLORS[method]))
                self.table.setItem(method, column, item)

        def rank(classical, ai):
            return "Tie" if abs(classical - ai) <= 1e-9 else ("Classical" if classical < ai else "AI · pix_grad")

        c, a = self.metrics
        self.winners.setText(f"THIS AREA ONLY\n\nLower RMSE: {rank(c.rmse, a.rmse)}\nLower MAE: {rank(c.mae, a.mae)}\n\n"
                             "Different metrics can rank methods differently. No overall winner is implied.")
        self.scope.setText(f"{self.area_name} · {c.count} common valid reference pixels · evaluated cell footprint "
                           f"{c.count * 0.25:.2f} m² · reference coverage 100% · bias is estimate − reference")

    def inspect(self, x: float, y: float):
        g = self.grids
        if g is None or self.busy:
            return
        col, row = (x - g.transform[0]) / 0.5, (g.transform[3] - y) / 0.5
        if not (0 <= col < g.width and 0 <= row < g.height):
            self.statusBar().showMessage("Click inside the source raster.")
            return
        cx, cy = int(col), int(row)
        i = cy * g.width + cx
        self.probe_point = (g.transform[0] + (cx + 0.5) * 0.5, g.transform[3] - (cy + 0.5) * 0.5)
        left, top, width, height = self.area or (0, 0, 0, 0)
        outside = "" if left <= cx < left + width and top <= cy < top + height else "\nOutside evaluation area"
        z = g.z
        self.probe.setText(
            f"SOURCE PIXEL · column {cx} / row {cy}{outside}\n\nDSM: {z[0][i]:.2f} m\nReference: {z[3][i]:.2f} m\n\n"
            f"Classical: {z[1][i]:.2f} m · error {z[1][i] - z[3][i]:.3f} m\nAI: {z[2][i]:.2f} m · error {z[2][i] - z[3][i]:.3f} m")
        self.draw_probe()

    def export_report(self):
        if self.grids is None or self.area is None or self.metrics is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export evaluation report", "accuracy-report.json", "JSON (*.json)")
        if not path:
            return
        try:
            ds.export_accuracy_report(Path(path), self.grids, self.area, self.area_name, self.threshold.value(),
                                      self.metrics, self.assets["sha256"])
        except Exception as error:
            QMessageBox.warning(self, "Export report", str(error))
            return
        self.statusBar().showMessage("Saved selected-area metrics and source provenance.")

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
    parser = argparse.ArgumentParser(description="Shared-scale DSM-to-DTM reference error comparison and selected-area metrics.")
    parser.add_argument("--sample-archive", metavar="zip", help="Use the exact pinned local sample ZIP.")
    parser.add_argument("--sample-url", metavar="url", help="HTTPS sample mirror; pinned hashes still apply.")
    parser.add_argument("--data-dir", metavar="directory", help="Sample cache directory.")
    arguments, qt_arguments = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_arguments])
    app.setApplicationName("DsmToDtmAccuracy")
    palette = app.palette()
    for role, color in ((QPalette.ColorRole.Window, "#f2f6f8"), (QPalette.ColorRole.Base, "white"),
                        (QPalette.ColorRole.WindowText, "#233e50"), (QPalette.ColorRole.Text, "#233e50")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    try:
        ds.configure_runtime()
        window = AccuracyWindow(arguments)
    except Exception as error:
        QMessageBox.critical(None, "DsmToDtmAccuracy", str(error))
        return 1
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    window.show_viewers()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
