"""Draw a terrain route and its native elevation profile."""

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDockWidget, QDoubleSpinBox,
    QFormLayout, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSplitter, QSpinBox, QWidget,
)

from common import application_icon, ensure_sample_file
from elevation_profile_chart import ProfileChart
from elevation_profile_viewer import ElevationProfileViewer


class ElevationProfileWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ready = self.loading = self.downloading = False
        self.snapshot = None
        self.setWindowTitle("ElevationProfile — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1300, 850)
        self.viewer = ElevationProfileViewer(
            self)
        self.chart = ProfileChart()
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.viewer)
        split.addWidget(self.chart)
        split.setSizes([560, 240])
        self.setCentralWidget(split)
        panel = QWidget()
        form = QFormLayout(panel)

        def caption(text):
            label = QLabel(text)
            label.setWordWrap(True)
            form.addRow(label)
            return label

        caption("Sagrada Família — terrain profiles")
        self.reload = QPushButton("Reload sample")
        self.reload.clicked.connect(self.load_sample)
        self.cancel = QPushButton("Cancel loading")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.viewer.cancel_load)
        form.addRow(self.reload)
        form.addRow(self.cancel)
        self.imagery = QCheckBox("Show orthophoto")
        self.imagery.setChecked(True)
        self.imagery.toggled.connect(self.apply_imagery)
        form.addRow(self.imagery)
        caption("Enable Add points, then click terrain. Dragging still navigates. "
                "Click at least two points to draw a profile.")
        self.spacing = QSpinBox()
        self.spacing.setRange(1, 100)
        self.spacing.setValue(10)
        self.spacing.valueChanged.connect(self.apply_mode)
        form.addRow("Sample spacing (m)", self.spacing)
        self.capture = QCheckBox("Add points on click")
        self.capture.setChecked(True)
        self.capture.toggled.connect(self.apply_mode)
        form.addRow(self.capture)
        self.finish = QPushButton("Finish profile")
        self.finish.clicked.connect(lambda: self.capture.setChecked(False))
        self.undo = QPushButton("Undo last point (Backspace)")
        self.undo.clicked.connect(lambda: self.edit_points(True))
        self.clear = QPushButton("Clear profile (Esc)")
        self.clear.clicked.connect(lambda: self.edit_points(False))
        for button in (self.finish, self.undo, self.clear):
            form.addRow(button)
        self.shortcuts = []
        for key, undo in (("Backspace", True), ("Esc", False)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda undo=undo: self.edit_points(undo))
            self.shortcuts.append(shortcut)
        self.result = caption("Load terrain to draw a profile.")
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.height = QDoubleSpinBox()
        self.height.setRange(.25, 10)
        self.height.setSingleStep(.25)
        self.height.setValue(1)
        self.height.valueChanged.connect(self.viewer.set_height_scale)
        form.addRow("Vertical exaggeration", self.height)
        reset = QPushButton("Reset view")
        reset.clicked.connect(self.viewer.reset_camera)
        form.addRow(reset)
        caption("Approximate terrain mesh profile; maximum 64 route points and 4096 samples. "
                "NoData gaps are not joined. Finer spacing cannot add DEM detail. "
                "Exaggeration does not change results. DEM datum is unverified.")
        caption("Left drag: pan\nWheel/right drag: zoom\nMiddle/Ctrl+left drag: orbit")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        dock = QDockWidget("Elevation profile", self)
        dock.setMinimumWidth(340)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(160)
        self.statusBar().addPermanentWidget(self.progress)
        self.poll = QTimer(self)
        self.poll.setInterval(50)
        self.poll.timeout.connect(self.poll_load)
        self.profile_timer = QTimer(self)
        self.profile_timer.setInterval(150)
        self.profile_timer.timeout.connect(self.poll_profile)
        self.set_busy(False)

    def set_busy(self, busy):
        self.loading = busy
        self.reload.setEnabled(not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)
        for control in (self.spacing, self.capture, self.imagery):
            control.setEnabled(self.ready and not busy)
        for control in (self.finish, self.undo, self.clear):
            control.setEnabled(False)
        self.snapshot = None
        if self.ready and not busy:
            self.profile_timer.start()
        else:
            self.profile_timer.stop()

    def apply_imagery(self, *_):
        if self.ready:
            self.viewer.set_imagery_visible(self.imagery.isChecked())

    def apply_mode(self, *_):
        if self.ready and not self.loading:
            self.viewer.profile_mode(self.capture.isChecked(), self.spacing.value())
            self.refresh_profile()

    def edit_points(self, undo):
        if self.ready and not self.loading:
            self.viewer.edit_profile(undo)
            self.refresh_profile()

    def poll_profile(self):
        try:
            self.refresh_profile()
        except Exception as error:
            self.profile_timer.stop()
            self.statusBar().showMessage(str(error))

    def refresh_profile(self):
        if not self.ready:
            return
        value = self.viewer.profile()
        if value == self.snapshot:
            return
        self.snapshot = value
        self.chart.set_profile(value)
        count = value["pointCount"]
        lines = [f"{count} route points",
                 f'Samples: {value["processed"]}/{len(value["samples"])}',
                 f'Horizontal: {value["horizontal"]:.1f} m',
                 f'Ascent: {value["ascent"]:.1f} m',
                 f'Descent: {value["descent"]:.1f} m',
                 f'Maximum interval: {value["maxInterval"]:.1f} m',
                 f'NoData: {value["missing"]}']
        if value["message"]:
            lines.append(value["message"])
        self.result.setText("\n".join(lines))
        self.undo.setEnabled(count > 0 and not self.loading)
        self.clear.setEnabled(count > 0 and not self.loading)
        self.finish.setEnabled(not self.loading and value["capture"] and count >= 2)

    def sample_file(self, dataset):
        sample = "sagrada_familia_" + dataset
        return ensure_sample_file(
            self.app, f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{sample}.zip",
            sample + ".zip", sample, sample + ".tif", "ElevationProfile")

    def load_sample(self):
        if self.loading:
            return
        self.downloading = True
        self.set_busy(True)
        try:
            if self.ready:
                self.viewer.profile_mode(False, self.spacing.value())
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

    def restore_controls(self):
        self.set_busy(False)
        if self.ready:
            self.apply_mode()

    def poll_load(self):
        try:
            state = self.viewer.poll_load()
            if state == 0:
                return
            self.poll.stop()
            if state == 1:
                self.ready = True
                self.viewer.set_height_scale(self.height.value())
                self.apply_imagery()
                self.statusBar().showMessage("Ready — click terrain to draw a profile.")
            elif state == -2:
                self.statusBar().showMessage("Loading cancelled.")
            else:
                raise RuntimeError("Loading ended without a scene.")
            self.restore_controls()
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        # A failed replacement load retains the previous scene and profile.
        try:
            self.restore_controls()
        except Exception:
            self.profile_timer.stop()
        self.statusBar().showMessage(str(error))
        QMessageBox.critical(self, "ElevationProfile", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.profile_timer.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ElevationProfile")
    app.setWindowIcon(application_icon())
    try:
        window = ElevationProfileWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "ElevationProfile", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
