"""Measure terrain distance and plan area with the native Viewer3D overlay."""

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox,
    QFormLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QWidget,
)

from common import application_icon, ensure_sample_file
from measurement_viewer import MeasurementViewer


class MeasurementWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ready = self.loading = self.downloading = False
        self.snapshot = None
        self.setWindowTitle("Measurement3D — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1300, 850)
        self.viewer = MeasurementViewer(
            self)
        self.setCentralWidget(self.viewer)
        panel = QWidget()
        form = QFormLayout(panel)

        def caption(text):
            label = QLabel(text)
            label.setWordWrap(True)
            form.addRow(label)
            return label

        caption("Sagrada Família — terrain measurements")
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
                "Area closes automatically after three points.")
        self.mode = QComboBox()
        self.mode.addItems(["Distance / polyline", "Area / polygon"])
        self.mode.currentIndexChanged.connect(self.apply_mode)
        form.addRow(self.mode)
        self.capture = QCheckBox("Add points on click")
        self.capture.setChecked(True)
        self.capture.toggled.connect(self.apply_mode)
        form.addRow(self.capture)
        self.finish = QPushButton("Finish measurement")
        self.finish.clicked.connect(lambda: self.capture.setChecked(False))
        self.undo = QPushButton("Undo last point (Backspace)")
        self.undo.clicked.connect(lambda: self.edit_points(True))
        self.clear = QPushButton("Clear measurement (Esc)")
        self.clear.clicked.connect(lambda: self.edit_points(False))
        for button in (self.finish, self.undo, self.clear):
            form.addRow(button)
        self.shortcuts = []
        for key, undo in (("Backspace", True), ("Esc", False)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda undo=undo: self.edit_points(undo))
            self.shortcuts.append(shortcut)
        self.result = caption("Load terrain to start measuring.")
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.points = QTableWidget(0, 3)
        self.points.setHorizontalHeaderLabels(["East (m)", "North (m)", "Up (m)"])
        self.points.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.points.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.points.setMinimumHeight(220)
        form.addRow(self.points)
        self.height = QDoubleSpinBox()
        self.height.setRange(.25, 10)
        self.height.setSingleStep(.25)
        self.height.setValue(1)
        self.height.valueChanged.connect(self.viewer.set_height_scale)
        form.addRow("Vertical exaggeration", self.height)
        reset = QPushButton("Reset view")
        reset.clicked.connect(self.viewer.reset_camera)
        form.addRow(reset)
        caption("Local ENU metres. 3D length joins points with straight segments, not along "
                "the terrain. Area is horizontal plan area, not terrain surface area. "
                "Exaggeration does not change results. DEM datum is unverified.")
        caption("Left drag: pan\nWheel/right drag: zoom\nMiddle/Ctrl+left drag: orbit")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        dock = QDockWidget("Measurement", self)
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
        self.measurement_timer = QTimer(self)
        self.measurement_timer.setInterval(150)
        self.measurement_timer.timeout.connect(self.poll_measurement)
        self.set_busy(False)

    def set_busy(self, busy):
        self.loading = busy
        self.reload.setEnabled(not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)
        for control in (self.mode, self.capture, self.imagery):
            control.setEnabled(self.ready and not busy)
        for control in (self.finish, self.undo, self.clear):
            control.setEnabled(False)
        self.snapshot = None
        if self.ready and not busy:
            self.measurement_timer.start()
        else:
            self.measurement_timer.stop()

    def apply_imagery(self, *_):
        if self.ready:
            self.viewer.set_imagery_visible(self.imagery.isChecked())

    def apply_mode(self, *_):
        if self.ready and not self.loading:
            self.viewer.measurement_mode(self.mode.currentIndex() == 1, self.capture.isChecked())
            self.refresh_measurement()

    def edit_points(self, undo):
        if self.ready and not self.loading:
            self.viewer.edit_measurement(undo)
            self.refresh_measurement()

    def poll_measurement(self):
        try:
            self.refresh_measurement()
        except Exception as error:
            self.measurement_timer.stop()
            self.statusBar().showMessage(str(error))

    def refresh_measurement(self):
        if not self.ready:
            return
        value = self.viewer.measurement()
        if value == self.snapshot:
            return
        self.snapshot = value
        points = value["points"]
        self.points.setRowCount(len(points))
        for row, point in enumerate(points):
            for column, key in enumerate(("east", "north", "up")):
                self.points.setItem(row, column, QTableWidgetItem(f"{point[key]:.2f}"))
        minimum = 3 if value["areaMode"] else 2
        lines = [f"{len(points)} points"]
        if len(points) < minimum:
            lines.append(f"Add at least {minimum} points.")
        if value["validArea"]:
            lines.append(f'Plan area: {value["planArea"]:.2f} m²')
        kind = "perimeter" if value["areaMode"] else "length"
        lines.extend([f'Horizontal {kind}: {value["horizontal"]:.2f} m',
                      f'3D segment total: {value["length3D"]:.2f} m'])
        if not value["areaMode"] and len(points) >= 2:
            lines.append(f'End-to-start ΔUp: {value["deltaUp"]:.2f} m')
        if value["message"]:
            lines.append(value["message"])
        self.result.setText("\n".join(lines))
        self.undo.setEnabled(bool(points) and not self.loading)
        self.clear.setEnabled(bool(points) and not self.loading)
        self.finish.setEnabled(not self.loading and value["capture"] and len(points) >= minimum
                               and (not value["areaMode"] or value["validArea"]))

    def sample_file(self, dataset):
        sample = "sagrada_familia_" + dataset
        return ensure_sample_file(
            self.app, f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{sample}.zip",
            sample + ".zip", sample, sample + ".tif", "Measurement3D")

    def load_sample(self):
        if self.loading:
            return
        self.downloading = True
        self.set_busy(True)
        try:
            if self.ready:
                self.viewer.measurement_mode(self.mode.currentIndex() == 1, False)
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
                self.statusBar().showMessage("Ready — click terrain to measure.")
            elif state == -2:
                self.statusBar().showMessage("Loading cancelled.")
            else:
                raise RuntimeError("Loading ended without a scene.")
            self.restore_controls()
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        # A failed replacement load retains the previous scene and measurement.
        try:
            self.restore_controls()
        except Exception:
            self.measurement_timer.stop()
        self.statusBar().showMessage(str(error))
        QMessageBox.critical(self, "Measurement3D", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.measurement_timer.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Measurement3D")
    app.setWindowIcon(application_icon())
    try:
        window = MeasurementWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "Measurement3D", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
