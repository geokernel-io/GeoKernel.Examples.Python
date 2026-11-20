"""DSM to DTM: ground beneath buildings.

Two linked native GeoKernel 3D viewers show the original DSM beside a prepared
terrain estimate (classical morphological/TIN or experimental DSM-only pix_grad).
The surface slider linearly interpolates numeric heights between both endpoints.
No inference runs here; the reference DTM is used only for the profile and scores.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import threading
from array import array
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

import dsm_support as ds
from common import ROOT_DIR, application_icon
from terrain_viewer import TerrainViewer

TITLE = "DSM to DTM | Ground beneath buildings — GeoKernel"
READY = "Ready · Original DSM stays visible | Drag: pan · Wheel: zoom · Middle/Ctrl+drag: orbit"
COLORS = ("#66768a", "#087e8b", "#8857bd", "#d98419")
STYLE = (
    "QMainWindow,QWidget#page{background:#f2f6f8;color:#233e50;}"
    "QLabel#title{font-size:22px;font-weight:600;color:#145e72;}"
    "QLabel#paneTitle{background:#e4eef2;color:#125a70;padding:10px;font-weight:600;}"
    "QPushButton{padding:7px 10px;}"
    "QToolBar{background:white;border-bottom:1px solid #d5e2e9;spacing:8px;padding:7px;}"
    "QLabel#notice{background:#fff5db;color:#705528;padding:9px;}"
    "QLabel#metrics{background:white;border:1px solid #d5e2e9;padding:12px;}"
    "QProgressBar{max-height:16px;}")


def blended(grids: ds.Grids, method: int, percent: int) -> array:
    """0% is exactly the DSM, 100% exactly the selected DTM; between: (1-t)*DSM + t*DTM."""
    if method not in (1, 2) or not 0 <= percent <= 100:
        raise RuntimeError("Invalid surface selection.")
    if percent == 0:
        return grids.z[0]
    if percent == 100:
        return grids.z[method]
    t = percent / 100
    return array("f", ((1 - t) * a + t * b for a, b in zip(grids.z[0], grids.z[method])))


def surface_file(grids: ds.Grids, method: int, percent: int, temporary: Path) -> Path:
    if percent == 0:
        return grids.folder / "dsm.tif"
    if percent == 100:
        return grids.folder / ("dtm_classical.tif" if method == 1 else "dtm_ai.tif")
    return ds.write_float_geotiff(temporary, grids.width, grids.height, grids.transform,
                                  grids.projection, [blended(grids, method, percent)])


def same_camera(a, b) -> bool:
    return a is not None and b is not None and sum(abs(x - y) for x, y in zip(a, b)) < 1e-5


class ProfileChart(QWidget):
    def __init__(self):
        super().__init__()
        self.grids: ds.Grids | None = None
        self.selected = 1
        self.setMinimumHeight(190)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        g = self.grids
        if not g:
            return
        plot = QRectF(64, 30, self.width() - 88, self.height() - 64)
        start = g.profile_row * g.width
        rows = [values[start:start + g.width] for values in g.z]
        low = min(min(row) for row in rows) - 2
        high = max(max(row) for row in rows) + 2
        p.setPen(QColor("#476174"))
        p.drawText(QRectF(8, 3, self.width() - 16, 22), Qt.AlignmentFlag.AlignLeft,
                   "Fixed building transect · original pixel heights (LN02 metres)")
        for i in range(5):
            t = i / 4
            y = plot.bottom() - t * plot.height()
            p.setPen(QColor("#e2e9ee"))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor("#476174"))
            p.drawText(QRectF(0, y - 9, 56, 18), Qt.AlignmentFlag.AlignRight, f"{low + t * (high - low):.0f}")
            p.drawText(QRectF(plot.left() + t * plot.width() - 25, plot.bottom() + 5, 50, 18),
                       Qt.AlignmentFlag.AlignCenter, f"{t * 249.5:.0f} m")
        for index in (0, 3, 1, 2):
            path = QPainterPath()
            for x, value in enumerate(rows[index]):
                point = QPointF(plot.left() + x / (g.width - 1) * plot.width(),
                                plot.bottom() - (value - low) / (high - low) * plot.height())
                path.moveTo(point) if x == 0 else path.lineTo(point)
            pen = QPen(QColor(COLORS[index]), 2.5 if index == self.selected else 1.4)
            if index == 3:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawPath(path)


class DemoWindow(QMainWindow):
    def __init__(self, arguments: argparse.Namespace):
        super().__init__()
        self.arguments = arguments
        self.assets = ds.read_json(ds.ZURICH_V2)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.temporary = tempfile.TemporaryDirectory(prefix="geokernel-dsm-to-dtm-")
        self.cancel = threading.Event()
        self.pending: Future | None = None
        self.loading: list[int] = []
        self.work: dict | None = None
        self.grids: ds.Grids | None = None
        self.ready = self.busy = self.close_queued = self.closed = False
        self.committed_method, self.committed_percent, self.serial = 1, 100, 0
        self.height_scale = 1.0
        self.last_camera = [None, None]
        self._progress = (0, "")

        self.setWindowTitle(TITLE)
        self.setWindowIcon(application_icon())
        self.resize(1520, 960)
        self.setStyleSheet(STYLE)
        self._build()
        self.poll = QTimer(self, interval=50, timeout=self.poll_work)
        self.camera_poll = QTimer(self, interval=30, timeout=self.poll_cameras)
        self.debounce = QTimer(self, interval=200, singleShot=True,
                               timeout=lambda: None if self.slider.isSliderDown() else self.update_surface())
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
        outer = QHBoxLayout(page)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)
        sidebar = QWidget()
        sidebar.setFixedWidth(285)
        controls = QVBoxLayout(sidebar)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(12)
        controls.addWidget(label("Ground beneath\nbuildings", "title"))
        controls.addWidget(label("Zürich · 250 × 250 m\n0.5 m height pixels · EPSG:2056"))
        controls.addWidget(label("1  Inspect the original roofs and trees.\n2  Choose a prepared terrain estimate.\n"
                                 "3  Move the slider to reveal the ground."))
        self.method = QComboBox()
        self.method.addItems(["Classical · morphological / TIN", "AI · DSM-only pix_grad"])
        controls.addWidget(label("Terrain estimate"))
        controls.addWidget(self.method)
        self.percent_label = label("100% · prepared DTM endpoint")
        controls.addWidget(self.percent_label)
        self.slider = QSlider(Qt.Orientation.Horizontal, objectName="surfaceSlider")
        self.slider.setRange(0, 100)
        self.slider.setValue(100)
        self.slider.setToolTip("0% = original DSM; 100% = prepared DTM. Release to rebuild the surface.")
        controls.addWidget(self.slider)
        endpoints = QHBoxLayout()
        original, terrain = QPushButton("Original · 0%"), QPushButton("Terrain · 100%")
        endpoints.addWidget(original)
        endpoints.addWidget(terrain)
        controls.addLayout(endpoints)
        self.endpoint_buttons = (original, terrain)
        controls.addWidget(label("Intermediate positions interpolate heights for display. "
                                 "They are not new terrain estimates."))
        form = QFormLayout()
        self.exaggeration = QDoubleSpinBox()
        self.exaggeration.setRange(.25, 4)
        self.exaggeration.setSingleStep(.25)
        self.exaggeration.setValue(1)
        self.exaggeration.setSuffix(" ×")
        form.addRow("Vertical exaggeration", self.exaggeration)
        controls.addLayout(form)
        self.metrics = label("Preparing the sample...", "metrics")
        self.metrics.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls.addWidget(self.metrics)
        controls.addWidget(label("Prepared results · no inference runs here. Both methods start from the "
                                 "original DSM independently.", "notice"))
        controls.addStretch()
        self.retry = QPushButton("Retry / reload sample")
        self.cancel_button = QPushButton("Cancel loading")
        controls.addWidget(self.retry)
        controls.addWidget(self.cancel_button)
        controls.addWidget(label("Source: Federal Office of Topography swisstopo\nAI: David Perez · experimental pix_grad"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(300)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(sidebar)
        outer.addWidget(scroll)

        workspace = QVBoxLayout()
        workspace.setSpacing(8)
        workspace.addWidget(label("One observed surface. Two independent ways to estimate terrain."))
        views = QHBoxLayout()
        views.setSpacing(8)
        self.headings, self.viewers = [], []
        for i in range(2):
            column = QVBoxLayout()
            column.setSpacing(0)
            heading = label("ORIGINAL DSM · roofs + trees + ground" if i == 0 else
                            "CLASSICAL DTM · prepared terrain estimate", "paneTitle")
            column.addWidget(heading)
            viewer = TerrainViewer()
            viewer.enable_imagery_api()
            viewer.enable_camera_api()
            viewer.setMinimumSize(300, 320)
            viewer.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            column.addWidget(viewer, 1)
            views.addLayout(column, 1)
            self.headings.append(heading)
            self.viewers.append(viewer)
        workspace.addLayout(views, 1)
        self.chart = ProfileChart()
        workspace.addWidget(self.chart)
        workspace.addWidget(label("Profile: gray DSM · teal classical · purple AI · dashed orange reference. "
                                  "The line is fixed across the same buildings in both views."))
        workspace.addWidget(label("Local 3D preview of source LN02 heights; no geoid conversion. DSM/reference "
                                  "source years: 2018/2019. Fixed development crop; scores are not a held-out "
                                  "accuracy benchmark."))
        outer.addLayout(workspace, 1)
        self.setCentralWidget(page)

        toolbar = self.addToolBar("Navigation")
        toolbar.setMovable(False)
        images = ROOT_DIR / "images"
        toolbar.addAction(QIcon(str(images / "FullExtent.png")), "Reset view", self.reset_view)
        toolbar.addAction("Top view", self.top_view)
        toolbar.addAction(QIcon(str(images / "ZoomIn.png")), "Zoom in", lambda: self.zoom(.8))
        toolbar.addAction(QIcon(str(images / "ZoomOut.png")), "Zoom out", lambda: self.zoom(1.25))
        profile = QAction("Show profile", self, checkable=True, checked=True)
        profile.toggled.connect(self.chart.setVisible)
        toolbar.addAction(profile)
        toolbar.addAction("Data folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data_root()))))
        toolbar.addAction("Controls", lambda: QMessageBox.information(
            self, "Camera controls",
            "Left drag: pan\nWheel or right drag: zoom\nMiddle drag or Ctrl + left drag: orbit\n"
            "Both cameras stay linked.\n\nMove the surface slider and release to update geometry. "
            "The original view stays unchanged."))
        self.progress = QProgressBar()
        self.progress.setFixedWidth(200)
        self.progress.setRange(0, 100)
        self.statusBar().addPermanentWidget(self.progress)
        self.progress.hide()

        self.retry.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.request_cancel)
        self.slider.valueChanged.connect(lambda: (self.update_percent_label(), self.debounce.start()))
        self.slider.sliderReleased.connect(lambda: (self.debounce.stop(), self.update_surface()))
        original.clicked.connect(lambda: self.slider.setValue(0))
        terrain.clicked.connect(lambda: self.slider.setValue(100))
        self.method.currentIndexChanged.connect(lambda: (self.debounce.stop(), self.update_surface()))
        self.exaggeration.valueChanged.connect(self.set_exaggeration)

    # ----- state --------------------------------------------------------------------------
    def data_root(self) -> Path:
        return Path(self.arguments.data_dir).resolve() if self.arguments.data_dir else ROOT_DIR / "data"

    def set_busy(self, busy: bool):
        self.busy = busy
        self.retry.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        for widget in (self.method, self.slider, *self.endpoint_buttons):
            widget.setEnabled(not busy and self.ready)
        self.progress.setVisible(busy)

    def failure(self, message: str):
        self.set_busy(False)
        self.statusBar().showMessage(message)
        if self.close_queued:
            QTimer.singleShot(0, self.close)
            return
        if not self.cancel.is_set():
            QMessageBox.warning(self, "Sample unavailable", message)

    def request_cancel(self):
        self.cancel.set()
        for viewer in self.viewers:
            viewer.cancel_load()
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("Cancelling... Previous complete views are retained.")

    def report(self, percent: int, message: str):
        # Called on the worker thread; only primitive state crosses to the GUI timer.
        self._progress = (percent, message)

    def start(self):
        if self.busy:
            return
        self.cancel.clear()
        self._progress = (0, "Checking cached sample files...")
        self.set_busy(True)
        method, percent = self.method.currentIndex() + 1, self.slider.value()
        self.serial += 1
        temporary = Path(self.temporary.name) / f"surface-{self.serial}.tif"
        url = self.arguments.sample_url or self.assets["url"]

        def job():
            folder = ds.prepare_sample(self.assets, self.data_root(), self.arguments.sample_archive, url,
                                       self.cancel, self.report)
            ds.check_cancel(self.cancel)
            ds.configure_runtime(folder)
            self.report(0, "Reading numeric heights and preparing both native 3D scenes...")
            grids = ds.read_grids(folder, self.cancel)
            ds.check_cancel(self.cancel)
            return {"grids": grids, "method": method, "percent": percent, "original": folder / "dsm.tif",
                    "result": surface_file(grids, method, percent, temporary)}

        self.pending = self.executor.submit(job)
        self.poll.start()

    def update_surface(self):
        if not self.ready or self.busy:
            return
        method, percent = self.method.currentIndex() + 1, self.slider.value()
        if (method, percent) == (self.committed_method, self.committed_percent):
            return
        self.cancel.clear()
        self._progress = (0, "Preparing the interpolated display surface...")
        self.set_busy(True)
        grids = self.grids
        self.serial += 1
        temporary = Path(self.temporary.name) / f"surface-{self.serial}.tif"

        def job():
            ds.check_cancel(self.cancel)
            path = surface_file(grids, method, percent, temporary)
            ds.check_cancel(self.cancel)
            return {"grids": grids, "method": method, "percent": percent, "original": None, "result": path}

        self.pending = self.executor.submit(job)
        self.poll.start()

    def restore_selection(self):
        for widget in (self.method, self.slider):
            widget.blockSignals(True)
        self.method.setCurrentIndex(self.committed_method - 1)
        self.slider.setValue(self.committed_percent)
        for widget in (self.method, self.slider):
            widget.blockSignals(False)
        self.update_percent_label()

    def poll_work(self):
        percent, message = self._progress
        self.progress.setRange(0, 100 if percent or not self.loading else 0)
        self.progress.setValue(percent)
        self.statusBar().showMessage(message)
        if self.pending is not None:
            if not self.pending.done():
                return
            future, self.pending = self.pending, None
            try:
                self.work = future.result()
            except Exception as error:
                self.poll.stop()
                self.restore_selection()
                self.failure("Loading cancelled. Previous complete views retained."
                             if isinstance(error, ds.Cancelled) or self.cancel.is_set() else str(error))
                return
            # Native scene preparation runs asynchronously inside Viewer3D; the GUI keeps polling.
            try:
                self.loading = []
                if self.work["original"] is not None:
                    self.viewers[0].load_terrain_and_imagery(
                        self.work["original"], self.work["grids"].folder / "neutral_surface.tif", 500)
                    self.loading.append(0)
                self.viewers[1].load_terrain_and_imagery(
                    self.work["result"], self.work["grids"].folder / "neutral_surface.tif", 500)
                self.loading.append(1)
                self._progress = (0, "Preparing native 3D terrain...")
            except Exception as error:
                self.poll.stop()
                self.restore_selection()
                self.failure(str(error))
            return
        states = {}
        try:
            for index in self.loading:
                states[index] = self.viewers[index].poll_load()
        except Exception as error:
            self.loading = []
            self.poll.stop()
            self.restore_selection()
            self.failure(str(error))
            return
        if any(state == 0 for state in states.values()):
            return
        self.poll.stop()
        self.loading = []
        if self.cancel.is_set() or any(state == -2 for state in states.values()):
            self.restore_selection()
            self.failure("Loading cancelled. Previous complete views retained.")
            return
        self.commit()

    def commit(self):
        work = self.work
        first = not self.ready
        self.grids = work["grids"]
        self.ready = True
        self.committed_method, self.committed_percent = work["method"], work["percent"]
        for viewer in self.viewers:
            viewer.set_height_scale(self.height_scale)
        self.chart.grids, self.chart.selected = self.grids, self.committed_method
        self.chart.update()
        if first:
            self.reset_view()
            self.camera_poll.start()
        else:
            self.sync_from(0)
        self.update_presentation()
        self.set_busy(False)
        self.statusBar().showMessage(READY)
        if self.close_queued:
            QTimer.singleShot(0, self.close)

    # ----- cameras ------------------------------------------------------------------------
    def render_scale(self) -> float:
        # Viewer3D maps local ENU metres to render units by 2 / horizontal span of the
        # pixel-centre grid (499 pixels x 0.5 m); vertical render units include exaggeration.
        return 2 / ((self.grids.width - 1) * self.grids.transform[1])

    def reset_view(self):
        if not self.ready:
            return
        viewer = self.viewers[0]
        viewer.reset_camera()
        dsm = self.grids.z[0]
        mean = sum(dsm) / len(dsm)
        # Both scenes share the grid-centre origin at zero height, so the centre of the
        # crop at the mean DSM height is (0, mean * scale * exaggeration, 0).
        viewer.move_camera([20, 48, 3.25, 0, mean * self.render_scale() * self.height_scale, 0], 0)
        self.sync_from(0)

    def top_view(self):
        if self.ready:
            camera = self.viewers[0].get_camera()
            camera[0], camera[1] = 0, 85
            self.viewers[0].move_camera(camera, 0)
            self.sync_from(0)

    def zoom(self, factor: float):
        if self.ready:
            camera = self.viewers[0].get_camera()
            camera[2] = min(max(camera[2] * factor, .05), 20)
            self.viewers[0].move_camera(camera, 0)
            self.sync_from(0)

    def sync_from(self, source: int):
        # Same grid, same origin and (to within 1e-5) the same render scale: render-space
        # cameras transfer directly between the two native scenes.
        target = 1 - source
        self.viewers[target].move_camera(self.viewers[source].get_camera(), 0)
        self.last_camera = [viewer.get_camera() for viewer in self.viewers]

    def poll_cameras(self):
        # Pause while a scene is being replaced: its interim camera must not propagate.
        if not self.ready or self.busy or self.closed:
            return
        for index in range(2):
            if not same_camera(self.last_camera[index], self.viewers[index].get_camera()):
                self.sync_from(index)
                break

    def set_exaggeration(self, value: float):
        old, self.height_scale = self.height_scale, float(value)
        for viewer in self.viewers:
            if self.ready:
                camera = viewer.get_camera()
                camera[4] *= self.height_scale / old
            viewer.set_height_scale(self.height_scale)
            if self.ready:
                viewer.move_camera(camera, 0)
        if self.ready:
            self.sync_from(0)

    # ----- presentation -------------------------------------------------------------------
    def update_percent_label(self):
        value = self.slider.value()
        self.percent_label.setText("100% · prepared DTM endpoint" if value == 100 else
                                   "0% · original DSM endpoint" if value == 0 else
                                   f"{value}% · display interpolation")

    def update_presentation(self):
        method = "CLASSICAL" if self.committed_method == 1 else "AI · pix_grad"
        percent = self.committed_percent
        self.headings[1].setText(
            method + " DTM · prepared terrain estimate" if percent == 100 else
            "ORIGINAL DSM · slider at 0%" if percent == 0 else
            f"{method} · {percent}% removal transition (display only)")
        metrics = self.grids.manifest.get("metrics", {})
        classical, ai = metrics.get("classical", {}), metrics.get("ai", {})
        self.metrics.setText(
            "REFERENCE CHECK · this crop only\n\n"
            f"Classical: RMSE {classical.get('rmse_m', 0):.2f} m · MAE {classical.get('mae_m', 0):.2f} m\n"
            f"AI: RMSE {ai.get('rmse_m', 0):.2f} m · MAE {ai.get('mae_m', 0):.2f} m\n\n"
            "250,000 shared reference pixels\nLower error is better.\n\n"
            "Scores describe the final DTM endpoints, not the transition slider.")
        self.update_percent_label()

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
        for timer in (self.poll, self.camera_poll, self.debounce):
            timer.stop()
        self.executor.shutdown(wait=True)
        for viewer in self.viewers:
            viewer.cancel_load()
            viewer.close_viewer()
        self.temporary.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ground beneath buildings — native GeoKernel 3D prepared DSM/DTM comparison.")
    parser.add_argument("--sample-archive", metavar="zip", help="Use the exact pinned local sample ZIP.")
    parser.add_argument("--sample-url", metavar="url", help="Override the HTTPS download mirror; SHA-256 pins still apply.")
    parser.add_argument("--data-dir", metavar="directory", help="Override the sample cache directory.")
    arguments, qt_arguments = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_arguments])
    app.setApplicationName("DsmToDtm")
    palette = app.palette()
    for role, color in ((QPalette.ColorRole.Window, "#f2f6f8"), (QPalette.ColorRole.Base, "white"),
                        (QPalette.ColorRole.WindowText, "#233e50"), (QPalette.ColorRole.Text, "#233e50"),
                        (QPalette.ColorRole.Button, "white"), (QPalette.ColorRole.ButtonText, "#233e50"),
                        (QPalette.ColorRole.Highlight, "#16859b"), (QPalette.ColorRole.HighlightedText, "white")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    try:
        ds.configure_runtime()
        window = DemoWindow(arguments)
    except Exception as error:
        QMessageBox.critical(None, "DsmToDtm", str(error))
        return 1
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
