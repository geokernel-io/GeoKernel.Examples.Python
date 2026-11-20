"""DSM to DTM: interactive elevation profile.

Draw your own A -> B transect on two linked native GeoKernel 2D maps and compare the
original DSM, classical DTM, AI DTM and provider reference heights on one chart.
Profiles sample the numeric Float32 rasters; the maps show matching display reliefs.
No inference runs here; the reference DTM is evaluation-only.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

import dsm_support as ds
from common import ROOT_DIR, application_icon
from dsm_maps import NativeMap
from geokernel import ViewerEventType, ViewerTool

TITLE = "DSM to DTM | Interactive elevation profile — GeoKernel"
READY = "Ready · draw A → B on either map; move over the chart to inspect heights."
COLORS = ("#66768a", "#087e8b", "#8857bd", "#d98419")
FULL_EXTENT = (2677090, 1251340, 2677360, 1251610)
HEADINGS = ("CLASSICAL DTM · prepared estimate", "AI DTM · experimental pix_grad", "REFERENCE DTM · evaluation only")
LEGENDS = ("Gray DSM · teal classical · purple AI · dashed orange reference",
           "Teal classical − reference · purple AI − reference · zero is closest")
STYLE = (
    "QMainWindow,QWidget#page{background:#f2f6f8;color:#233e50;}"
    "QLabel#title{font-size:21px;font-weight:600;color:#145e72;}"
    "QLabel#heading{background:#e4eef2;color:#125a70;padding:9px;font-weight:600;}"
    "QLabel#card{background:white;border:1px solid #d5e2e9;padding:10px;} QPushButton{padding:7px;}"
    "QToolBar{background:white;border-bottom:1px solid #d5e2e9;spacing:8px;padding:7px;}")


def point_style(color: str, size: float) -> dict:
    return {"pointColor": color, "pointSize": size, "lineColor": "#ffffff", "lineWidth": 2}


class ProfileChart(QWidget):
    def __init__(self, hover_changed):
        super().__init__(objectName="profileChart")
        self.profile: ds.Profile | None = None
        self.errors = False
        self.hovered = -1
        self.hover_changed = hover_changed
        self.setMinimumHeight(230)
        self.setMouseTracking(True)

    def plot_rect(self) -> QRectF:
        return QRectF(65, 30, self.width() - 90, self.height() - 72)

    def mouseMoveEvent(self, event):
        plot, profile = self.plot_rect(), self.profile
        position = event.position()
        index = -1
        if profile and plot.contains(position):
            count = len(profile.samples)
            index = min(max(round((position.x() - plot.left()) / plot.width() * (count - 1)), 0), count - 1)
        self.set_hovered(index)

    def leaveEvent(self, _event):
        self.set_hovered(-1)

    def set_hovered(self, index: int):
        if index != self.hovered:
            self.hovered = index
            self.hover_changed(index)
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        profile = self.profile
        if not profile:
            p.setPen(QColor("#476174"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Draw a transect: choose A, then B on either map.")
            return
        plot = self.plot_rect()
        bands = (1, 2) if self.errors else (0, 1, 2, 3)

        def value(sample, band):
            return sample.heights[band] - (sample.heights[3] if self.errors else 0.0)

        values = [value(s, band) for s in profile.samples for band in bands]
        low, high = min(values), max(values)
        if self.errors:
            low, high = min(low, 0.0), max(high, 0.0)
        pad = max(.25, (high - low) * .12)
        low, high = low - pad, high + pad
        p.setPen(QColor("#476174"))
        p.drawText(QRectF(8, 2, self.width() - 16, 24), Qt.AlignmentFlag.AlignLeft,
                   "Estimate minus reference (m) · zero is closest" if self.errors
                   else "Source elevation (LN02 metres) · all four rasters on one scale")
        for i in range(5):
            t = i / 4
            y = plot.bottom() - t * plot.height()
            p.setPen(QColor("#e2e9ee"))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor("#476174"))
            p.drawText(QRectF(0, y - 9, 58, 18), Qt.AlignmentFlag.AlignRight, f"{low + t * (high - low):.1f}")
            p.drawText(QRectF(plot.left() + t * plot.width() - 28, plot.bottom() + 5, 56, 18),
                       Qt.AlignmentFlag.AlignCenter, f"{t * profile.length:.1f}")
        p.drawText(QRectF(0, self.height() - 22, self.width(), 20), Qt.AlignmentFlag.AlignCenter,
                   "Distance along A → B (projected metres)")
        if self.errors:
            y = plot.bottom() - (0 - low) / (high - low) * plot.height()
            p.setPen(QPen(QColor("#b4bfca"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        for band in (0, 3, 1, 2):
            if band not in bands:
                continue
            path = QPainterPath()
            for i, sample in enumerate(profile.samples):
                point = QPointF(plot.left() + sample.distance / profile.length * plot.width(),
                                plot.bottom() - (value(sample, band) - low) / (high - low) * plot.height())
                path.moveTo(point) if i == 0 else path.lineTo(point)
            pen = QPen(QColor(COLORS[band]), 1.5 if band == 0 else 2)
            if band == 3:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawPath(path)
        if 0 <= self.hovered < len(profile.samples):
            x = plot.left() + profile.samples[self.hovered].distance / profile.length * plot.width()
            p.setPen(QPen(QColor("#dd3470"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))


class Bridge(QObject):
    # Native viewer callbacks may run while the viewer renders; handle them afterwards.
    event = Signal(int, object)


class ProfileWindow(QMainWindow):
    def __init__(self, arguments: argparse.Namespace):
        super().__init__()
        self.arguments = arguments
        self.assets = ds.read_json(ds.ZURICH_V2)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.temporary = tempfile.TemporaryDirectory(prefix="geokernel-dsm-profile-")
        self.cancel = threading.Event()
        self.pending: Future | None = None
        self.grids: ds.Grids | None = None
        self.draft: tuple[float, float] | None = None
        self.presses: list = [None, None]
        self.applied = [None, None]
        self.busy = self.close_queued = self.closed = False
        self.generation = 0
        self._progress = (0, "")
        self.viewers = [NativeMap(), NativeMap()]
        self.bridge = Bridge(self)
        self.bridge.event.connect(self.viewer_event, Qt.ConnectionType.QueuedConnection)

        self.setWindowTitle(TITLE)
        self.setWindowIcon(application_icon())
        self.resize(1460, 940)
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
        controls.setSpacing(12)
        controls.addWidget(label("Compare along\nyour own transect", "title"))
        controls.addWidget(label("Zürich · 250 × 250 m\n0.5 m height pixels · EPSG:2056"))
        self.instructions = label("Preparing sample data...", "card")
        controls.addWidget(self.instructions)
        controls.addWidget(label("Right-hand map"))
        self.surface = QComboBox(objectName="surfaceChoice")
        self.surface.addItems(["Classical DTM", "AI DTM · pix_grad", "Reference DTM · evaluation only"])
        controls.addWidget(self.surface)
        self.spacing = QDoubleSpinBox(objectName="profileSpacing")
        self.spacing.setRange(.5, 10)
        self.spacing.setValue(.5)
        self.spacing.setSingleStep(.5)
        self.spacing.setSuffix(" m")
        form = QFormLayout()
        form.addRow("Sample spacing", self.spacing)
        controls.addLayout(form)
        self.stats = label("Select a transect to compare errors.", "card")
        self.stats.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.stats)
        self.cursor = label("Move over the chart to locate a sample on both maps.", "card")
        self.cursor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.cursor)
        controls.addWidget(label("Profiles sample numeric Float32 heights with bilinear interpolation. Relief "
                                 "images are for display only. Finer sampling cannot add source detail."))
        controls.addStretch()
        self.export = QPushButton("Export profile CSV", objectName="exportCsv")
        self.reload = QPushButton("Retry / reload sample")
        self.cancel_button = QPushButton("Cancel loading")
        for button in (self.export, self.reload, self.cancel_button):
            controls.addWidget(button)
        controls.addWidget(label("Source: Federal Office of Topography swisstopo\nAI: David Perez · experimental pix_grad"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(285)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(sidebar)
        layout.addWidget(scroll)

        workspace = QVBoxLayout()
        split = QSplitter(Qt.Orientation.Vertical)
        map_row = QWidget()
        maps = QHBoxLayout(map_row)
        maps.setContentsMargins(0, 0, 0, 0)
        maps.setSpacing(8)
        self.headings = []
        for i, viewer in enumerate(self.viewers):
            pane = QWidget()
            column = QVBoxLayout(pane)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            heading = label("ORIGINAL DSM · roofs + trees + ground" if i == 0 else HEADINGS[0], "heading")
            column.addWidget(heading)
            widget = viewer.qt_widget(auto_close=False)
            widget.setMinimumSize(300, 280)
            column.addWidget(widget, 1)
            maps.addWidget(pane, 1)
            self.headings.append(heading)
            viewer.set_tool(ViewerTool.PAN)
            viewer.set_event_callback(lambda event, side=i: self.bridge.event.emit(side, event))
        split.addWidget(map_row)
        profile_pane = QWidget()
        chart_layout = QVBoxLayout(profile_pane)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox(objectName="chartMode")
        self.mode.addItems(["Compare elevations", "Compare errors against reference"])
        chart_layout.addWidget(self.mode)
        self.chart = ProfileChart(self.hover)
        chart_layout.addWidget(self.chart, 1)
        self.legend = label(LEGENDS[0])
        chart_layout.addWidget(self.legend)
        split.addWidget(profile_pane)
        split.setSizes([540, 270])
        workspace.addWidget(split, 1)
        workspace.addWidget(label(
            "Prepared independent results; no new inference. Reference is evaluation-only. Source LN02 heights, "
            "metres; no vertical datum conversion. DSM/reference source years: 2018/2019. This is a fixed "
            "development scene."))
        layout.addLayout(workspace, 1)
        self.setCentralWidget(page)

        toolbar = self.addToolBar("Profile and navigation")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.draw = QAction("Draw transect · A → B", self, checkable=True, objectName="drawTransect")
        toolbar.addAction(self.draw)
        images = ROOT_DIR / "images"
        example = toolbar.addAction("Example transect", self.example_profile)
        clear = toolbar.addAction("Clear transect", self.clear_profile)
        toolbar.addSeparator()
        pan = toolbar.addAction("Pan", lambda: self.use_tool(ViewerTool.PAN))
        box = toolbar.addAction("Zoom box", lambda: self.use_tool(ViewerTool.ZOOM_BOX))
        zoom_in = toolbar.addAction(QIcon(str(images / "ZoomIn.png")), "Zoom in", lambda: self.viewers[0].zoom_in(1.5))
        zoom_out = toolbar.addAction(QIcon(str(images / "ZoomOut.png")), "Zoom out",
                                     lambda: self.viewers[0].zoom_out(1.5))
        fit = toolbar.addAction(QIcon(str(images / "FullExtent.png")), "Full extent", self.full_extent)
        self.navigation = (example, clear, pan, box, zoom_in, zoom_out, fit)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(200)
        self.statusBar().addPermanentWidget(self.progress)

        self.draw.toggled.connect(self.toggle_draw)
        self.surface.currentIndexChanged.connect(self.select_surface)
        self.spacing.valueChanged.connect(self.resample)
        self.mode.currentIndexChanged.connect(self.set_mode)
        self.export.clicked.connect(self.export_csv)
        self.reload.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.request_cancel)

    def show_viewers(self):
        # Embedded native maps start painting once shown, after the host window is visible.
        for viewer in self.viewers:
            viewer.show()

    # ----- state --------------------------------------------------------------------------
    def data_root(self) -> Path:
        return Path(self.arguments.data_dir).resolve() if self.arguments.data_dir else ROOT_DIR / "data"

    def set_busy(self, busy: bool):
        self.busy = busy
        ready = not busy and self.grids is not None
        self.reload.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)
        for widget in (self.draw, self.surface, self.spacing, *self.navigation):
            widget.setEnabled(ready)
        self.export.setEnabled(not busy and self.chart.profile is not None)

    def failure(self, message: str):
        self.set_busy(False)
        self.statusBar().showMessage(message)
        if self.close_queued:
            QTimer.singleShot(0, self.close)
        elif not self.cancel.is_set():
            QMessageBox.warning(self, "Unable to load sample", message)

    def request_cancel(self):
        self.cancel.set()
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("Cancelling loading...")

    def report(self, percent: int, message: str):
        # Worker thread: only primitive state crosses to the GUI timer.
        self._progress = (percent, message)

    def start(self):
        if self.busy:
            return
        self.cancel.clear()
        self._progress = (0, "Checking cached sample files...")
        self.set_busy(True)
        self.generation += 1
        temporary = Path(self.temporary.name) / str(self.generation)
        url = self.arguments.sample_url or self.assets["url"]

        def job():
            folder = ds.prepare_sample(self.assets, self.data_root(), self.arguments.sample_archive, url,
                                       self.cancel, self.report)
            ds.check_cancel(self.cancel)
            ds.configure_runtime(folder)
            temporary.mkdir(parents=True, exist_ok=True)
            self.report(0, "Reading numeric heights and preparing matching relief maps...")
            grids = ds.read_grids(folder, self.cancel)
            reliefs = []
            for band in range(4):
                gray = ds.relief(grids, band, self.cancel)
                reliefs.append(ds.write_rgb_geotiff(temporary / f"relief-{band}.tif", grids.width, grids.height,
                                                    grids.transform, grids.projection, gray))
                self.report((band + 1) * 25, "Reading numeric heights and preparing matching relief maps...")
            return grids, reliefs

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
            grids, reliefs = future.result()
        except Exception as error:
            cancelled = isinstance(error, ds.Cancelled) or self.cancel.is_set()
            self.failure("Loading cancelled." if cancelled else str(error))
            return
        if self.cancel.is_set():
            self.failure("Loading cancelled.")
            return
        try:
            self.publish(grids, reliefs)
        except Exception as error:
            self.failure(str(error))
            return
        self.set_busy(False)
        self.example_profile()
        self.statusBar().showMessage(READY)
        if self.close_queued:
            QTimer.singleShot(0, self.close)

    def publish(self, grids: ds.Grids, reliefs: list[Path]):
        """Show the DSM relief left and all three estimate reliefs right (one visible)."""
        self.grids = grids
        for pane, viewer in enumerate(self.viewers):
            viewer.clear_shapes()
            viewer.clear_layers()
            # The empty map adopts the first layer's CRS (EPSG:2056); new layers go to index 0.
            for band in (0,) if pane == 0 else (1, 2, 3):
                viewer.add_layer(reliefs[band])
                viewer.set_layer_name(0, ds.SURFACE_NAMES[band])
            if viewer.layer_count() != (1 if pane == 0 else 3):
                raise RuntimeError("The relief layers were not added.")
        self.applied = [None, None]
        self.full_extent()
        self.select_surface()

    # ----- maps ---------------------------------------------------------------------------
    def layer_index(self, viewer, name: str) -> int:
        for index, info in enumerate(viewer.layers_info()):
            if info.get("name") == name:
                return index
        return -1

    def full_extent(self):
        self.viewers[0].set_view_extent(FULL_EXTENT)
        self.sync_from(0)

    def sync_from(self, side: int):
        value = self.viewers[side].get_view_extent()
        if value is None:
            return
        self.applied[side] = value
        other = 1 - side
        self.viewers[other].set_view_extent(value)
        self.applied[other] = self.viewers[other].get_view_extent()

    def use_tool(self, tool):
        self.draw.setChecked(False)
        for viewer in self.viewers:
            viewer.set_tool(tool)

    def select_surface(self):
        if self.grids is None:
            return
        viewer, choice = self.viewers[1], self.surface.currentIndex() + 1
        for band in (1, 2, 3):
            viewer.set_layer_visible(self.layer_index(viewer, ds.SURFACE_NAMES[band]), band == choice)
        viewer.refresh_layers()
        self.headings[1].setText(HEADINGS[choice - 1])

    def viewer_event(self, side: int, event):
        if self.closed or self.grids is None:
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
            # A click (not a pan drag) picks a point; dragging still pans.
            if press and abs(press[0] - screen[0]) + abs(press[1] - screen[1]) <= 3:
                self.pick(event.extent.x_min, event.extent.y_min)

    def draw_transect(self):
        """Native owned shapes on both maps: white halo + teal line, A teal and B orange markers."""
        profile = self.chart.profile
        label = {"textColor": "#ffffff", "bold": True, "fontSize": 8}
        for viewer in self.viewers:
            viewer.clear_shapes()
            if self.draft is not None:
                viewer.add_point_shape(*self.draft, point_style(COLORS[1], 18))
                viewer.add_text_shape(*self.draft, "A", label)
            elif profile is not None:
                line = [profile.start, profile.end]
                viewer.add_polyline_shape(line, {"lineColor": "#ffffff", "lineWidth": 5})
                viewer.add_polyline_shape(line, {"lineColor": COLORS[1], "lineWidth": 2.5})
                for point, color, text in ((profile.start, COLORS[1], "A"), (profile.end, COLORS[3], "B")):
                    viewer.add_point_shape(*point, point_style(color, 18))
                    viewer.add_text_shape(*point, text, label)
            viewer.refresh_layers()  # owned shapes are drawn on the next full map render
        self.draw_cursor()

    def draw_cursor(self):
        """The chart's hovered sample as a lightweight overlay point (no map re-render)."""
        profile, hovered = self.chart.profile, self.chart.hovered
        for viewer in self.viewers:
            if self.draft is None and profile is not None and 0 <= hovered < len(profile.samples):
                sample = profile.samples[hovered]
                viewer.set_overlay_point("cursor", sample.x, sample.y, point_style("#dd3470", 11))
            else:
                viewer.remove_overlay_shape("cursor")

    # ----- transect -----------------------------------------------------------------------
    def toggle_draw(self, on: bool):
        self.draft = None
        if on:
            for viewer in self.viewers:
                viewer.set_tool(ViewerTool.PAN)
            self.instructions.setText("Click A on either map. Dragging still pans; wheel zooms.")
        else:
            self.instructions.setText("Draw a new A → B transect, or inspect the current profile.")
        self.draw_transect()

    def pick(self, x: float, y: float):
        if self.grids is None or self.busy or not self.draw.isChecked():
            return
        if ds.sample_height(self.grids, 0, x, y) is None:
            self.statusBar().showMessage("Click inside the valid raster pixel centres.")
            return
        if self.draft is None:
            self.draft = (x, y)
            self.instructions.setText("A selected. Click B on either map. Toggle Draw off to cancel.")
            self.draw_transect()
            return
        try:
            self.commit_profile(self.draft, (x, y))
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.draft = None
        self.draw.setChecked(False)
        self.instructions.setText("Your transect is ready. Hover over the chart to locate matching heights on both maps.")

    def example_profile(self):
        if self.grids is None:
            return
        self.draw.setChecked(False)
        self.draft = None
        self.commit_profile(*ds.example_endpoints(self.grids))
        self.instructions.setText("Example transect loaded. Select Draw transect, then click A and B to compare your own line.")

    def clear_profile(self):
        self.draw.setChecked(False)
        self.draft = None
        self.chart.profile, self.chart.hovered = None, -1
        self.chart.update()
        self.refresh_stats()
        self.hover(-1)
        self.draw_transect()

    def resample(self):
        profile = self.chart.profile
        if profile is not None:
            try:
                self.commit_profile(profile.start, profile.end)
            except ValueError as error:
                self.statusBar().showMessage(str(error))

    def commit_profile(self, a, b):
        self.chart.profile = ds.make_profile(self.grids, a, b, self.spacing.value())
        self.chart.hovered = -1
        self.chart.update()
        self.refresh_stats()
        self.hover(-1)
        self.draw_transect()

    def set_mode(self, index: int):
        self.chart.errors = index == 1
        self.legend.setText(LEGENDS[index])
        self.chart.update()

    def refresh_stats(self):
        profile = self.chart.profile
        self.export.setEnabled(not self.busy and profile is not None)
        if profile is None:
            self.stats.setText("No transect selected.")
            return
        self.stats.setText(
            f"THIS TRANSECT ONLY\n\nLength: {profile.length:.1f} m · {len(profile.samples)} samples\n"
            f"Actual spacing: {profile.spacing:.3f} m\n\n"
            f"Classical RMSE: {profile.rmse[0]:.2f} m\nClassical MAE: {profile.mae[0]:.2f} m\n\n"
            f"AI RMSE: {profile.rmse[1]:.2f} m\nAI MAE: {profile.mae[1]:.2f} m\n\n"
            "Lower error is better. These are line-sample errors, not full-area accuracy.")

    def hover(self, index: int):
        profile = self.chart.profile
        if profile is None or not 0 <= index < len(profile.samples):
            self.cursor.setText("Move over the chart to locate a sample on both maps.")
        else:
            s = profile.samples[index]
            h = s.heights
            self.cursor.setText(
                f"Distance: {s.distance:.1f} m\nE {s.x:.2f} · N {s.y:.2f}\n\n"
                f"DSM: {h[0]:.2f} m\nClassical: {h[1]:.2f} m\nAI: {h[2]:.2f} m\nReference: {h[3]:.2f} m")
        self.draw_cursor()

    def export_csv(self):
        profile = self.chart.profile
        if profile is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export numeric profile", "profile.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            ds.export_profile(Path(path), profile, self.grids, self.assets["sha256"])
        except Exception as error:
            QMessageBox.warning(self, "Export profile", str(error))
            return
        self.statusBar().showMessage("Saved numeric profile CSV and metadata sidecar.")

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
    parser = argparse.ArgumentParser(description="Interactive DSM / classical / AI / reference elevation profiles.")
    parser.add_argument("--sample-archive", metavar="zip", help="Use the exact pinned local sample ZIP.")
    parser.add_argument("--sample-url", metavar="url", help="HTTPS sample mirror; all pinned hashes still apply.")
    parser.add_argument("--data-dir", metavar="directory", help="Sample cache location.")
    arguments, qt_arguments = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_arguments])
    app.setApplicationName("DsmToDtmProfile")
    palette = app.palette()
    for role, color in ((QPalette.ColorRole.Window, "#f2f6f8"), (QPalette.ColorRole.Base, "white"),
                        (QPalette.ColorRole.WindowText, "#233e50"), (QPalette.ColorRole.Text, "#233e50")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    try:
        ds.configure_runtime()
        window = ProfileWindow(arguments)
    except Exception as error:
        QMessageBox.critical(None, "DsmToDtmProfile", str(error))
        return 1
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    window.show_viewers()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
