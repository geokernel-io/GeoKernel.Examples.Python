"""Sampled terrain visibility, displayed in a grid and on the 3D terrain."""
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox,
    QFormLayout, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QWidget,
)

from common import application_icon, ensure_sample_file
from viewshed_map import ViewshedMap
from viewshed_viewer import ViewshedViewer


class ViewshedWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ready = self.loading = self.downloading = False
        self.snapshot = None
        self.setWindowTitle("ViewshedAnalysis — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1400, 900)
        self.viewer = ViewshedViewer(self)
        self.setCentralWidget(self.viewer)
        panel = QWidget()
        form = QFormLayout(panel)

        def caption(text):
            label = QLabel(text)
            label.setWordWrap(True)
            form.addRow(label)
            return label

        def button(text, callback):
            control = QPushButton(text)
            control.clicked.connect(callback)
            form.addRow(control)
            return control

        def check(text, callback):
            control = QCheckBox(text)
            control.setChecked(True)
            control.toggled.connect(callback)
            form.addRow(control)
            return control

        def number(text, low, high, initial):
            control = QDoubleSpinBox()
            control.setRange(low, high)
            control.setValue(initial)
            control.setSuffix(" m")
            control.valueChanged.connect(lambda *_: self.safe(self.configure))
            form.addRow(text, control)
            return control

        caption("Sagrada Família — viewshed analysis")
        self.reload = button("Reload sample", self.load_sample)
        self.cancel = button("Cancel loading", self.viewer.cancel_load)
        self.imagery = check("Show orthophoto", lambda value: self.safe(
            lambda: self.viewer.set_imagery_visible(value)))
        caption("Select observer, then click terrain. The marker shows eye height.")
        self.pick = check("Select observer on terrain", lambda value: self.safe(lambda: self.viewer.capture(value)))
        self.location = caption("No observer selected.")
        self.eye = number("Observer above terrain", .1, 100, 1.7)
        self.target = number("Target above terrain", 0, 100, 1.7)
        self.radius = number("Radius", 10, 2000, 300)
        self.spacing = number("Ray sample spacing", 1, 50, 5)
        self.grid = QComboBox()
        self.grid.addItems(["17 × 17 — fast", "33 × 33 — balanced", "65 × 65 — detailed"])
        self.grid.setCurrentIndex(1)
        self.grid.currentIndexChanged.connect(lambda *_: self.safe(self.configure))
        form.addRow("Grid", self.grid)
        self.calculate = button("Calculate", lambda: self.safe(lambda: self.viewer.action(0)))
        self.pause = button("Pause calculation", lambda: self.safe(lambda: self.viewer.action(1)))
        self.clear = button("Clear observer and result", lambda: self.safe(lambda: self.viewer.action(2)))
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(0)
        form.addRow(self.analysis_progress)
        self.map = ViewshedMap()
        form.addRow(self.map)
        self.overlay = check("Show result on terrain", lambda value: self.safe(lambda: self.viewer.overlay(value)))
        caption('<span style="color:#239b56">■ Visible</span> '
                '<span style="color:#d35445">■ Blocked</span><br>'
                '<span style="color:#858585">■ Unknown / NoData</span> '
                '<span style="color:#8795a6">■ Pending</span>')
        self.result = caption("Load terrain to begin.")
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.height = QDoubleSpinBox()
        self.height.setRange(.25, 10)
        self.height.setSingleStep(.25)
        self.height.setValue(1)
        self.height.valueChanged.connect(self.viewer.set_height_scale)
        form.addRow("Vertical exaggeration", self.height)
        button("Reset view", self.viewer.reset_camera)
        caption("Terrain-only sampled visibility; buildings, vegetation and atmospheric refraction "
                "are excluded. The DEM mesh has 512 samples per side. Small obstacles between "
                "samples may be missed. Vertical datum is unverified. Exaggeration changes only the view.")
        caption("Left drag: pan\nWheel/right drag: zoom\nMiddle/Ctrl+left drag: orbit")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        dock = QDockWidget("Viewshed analysis", self)
        dock.setMinimumWidth(370)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(160)
        self.statusBar().addPermanentWidget(self.progress)
        self.poll = QTimer(self)
        self.poll.setInterval(50)
        self.poll.timeout.connect(self.poll_load)
        self.result_timer = QTimer(self)
        self.result_timer.setInterval(150)
        self.result_timer.timeout.connect(self.poll_result)
        self.set_busy(False)

    def configure(self):
        self.viewer.configure(self.eye.value(), self.target.value(), self.radius.value(),
                              self.spacing.value(), (17, 33, 65)[self.grid.currentIndex()])

    def safe(self, action):
        if not self.ready or self.loading:
            return
        try:
            action()
            self.refresh_result()
        except Exception as error:
            self.statusBar().showMessage(str(error))

    def poll_result(self):
        try:
            self.refresh_result()
        except Exception as error:
            self.result_timer.stop()
            self.statusBar().showMessage(str(error))

    def refresh_result(self):
        if not self.ready:
            return
        value = self.viewer.viewshed()
        if value == self.snapshot:
            return
        self.snapshot = value
        self.pick.blockSignals(True)
        self.pick.setChecked(value["capture"])
        self.pick.blockSignals(False)
        self.location.setText(f'Observer: {value["longitude"]:.6f}° E, {value["latitude"]:.6f}° N'
                              if value["hasObserver"] else "No observer selected.")
        self.map.set_result(value)
        cells = value["cells"]
        self.analysis_progress.setValue(int(100 * value["processed"] / len(cells)) if cells else 0)
        self.result.setText("\n".join([
            value["message"], f"Visible: {cells.count(2)} | Blocked: {cells.count(3)}",
            f"Unknown: {cells.count(4)} | Pending: {cells.count(1)}",
            f'Grid spacing: {value["cellSpacing"]:.1f} m',
            f'Maximum ray spacing: {value["maxRaySpacing"]:.1f} m', value["overlayMessage"]]))
        self.calculate.setText("Recalculate" if value["complete"] else "Resume calculation" if cells else "Calculate")
        self.calculate.setEnabled(not self.loading and value["hasObserver"] and not value["running"])
        self.pause.setEnabled(not self.loading and value["running"])
        self.clear.setEnabled(not self.loading and value["hasObserver"])

    def set_busy(self, busy):
        self.loading = busy
        self.reload.setEnabled(not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)
        for control in (self.pick, self.imagery, self.overlay, self.eye, self.target,
                        self.radius, self.spacing, self.grid):
            control.setEnabled(self.ready and not busy)
        for control in (self.calculate, self.pause, self.clear):
            control.setEnabled(False)
        self.snapshot = None
        if self.ready and not busy:
            self.refresh_result()
            self.result_timer.start()
        else:
            self.result_timer.stop()

    def sample_file(self, dataset):
        sample = "sagrada_familia_" + dataset
        return ensure_sample_file(
            self.app, f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{sample}.zip",
            sample + ".zip", sample, sample + ".tif", "ViewshedAnalysis")

    def load_sample(self):
        if self.loading:
            return
        self.downloading = True
        self.set_busy(True)
        try:
            if self.ready:
                self.viewer.capture(False)
                if self.viewer.viewshed()["running"]:
                    self.viewer.action(1)
            dem = self.sample_file("terrain")
            imagery = self.sample_file("ortophoto")
            self.viewer.load_terrain_and_imagery(dem, imagery, 512)
            self.cancel.setEnabled(True)
            self.statusBar().showMessage("Loading terrain…")
            self.poll.start()
        except Exception as error:
            self.fail(error)
        finally:
            self.downloading = False

    def poll_load(self):
        try:
            state = self.viewer.poll_load()
            if state == 0:
                return
            self.poll.stop()
            if state == 1:
                self.configure()
                self.viewer.set_height_scale(self.height.value())
                self.viewer.set_imagery_visible(self.imagery.isChecked())
                self.viewer.overlay(self.overlay.isChecked())
                self.viewer.capture(True)
                self.ready = True
                self.statusBar().showMessage("Ready — select an observer on terrain.")
            elif state == -2:
                self.statusBar().showMessage("Loading cancelled.")
            else:
                raise RuntimeError("Loading ended without a scene.")
            self.set_busy(False)
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        try:
            self.set_busy(False)
        except Exception:
            self.result_timer.stop()
        self.statusBar().showMessage(str(error))
        QMessageBox.critical(self, "ViewshedAnalysis", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.result_timer.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ViewshedAnalysis")
    app.setWindowIcon(application_icon())
    try:
        window = ViewshedWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "ViewshedAnalysis", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
