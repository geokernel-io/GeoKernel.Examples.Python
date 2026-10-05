"""Inspect buildings and roads using the SDK's existing vector picking logic."""

import os
import sys

from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox, QFormLayout,
    QHeaderView, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QWidget,
)

from common import application_icon, ensure_sample_file
from feature_picking_viewer import FeaturePickingViewer


class FeaturePickingWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.loading = self.downloading = self.ready = False
        self.snapshot = None
        self.setWindowTitle("FeaturePicking — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1200, 850)
        self.viewer = FeaturePickingViewer(
            self)
        self.setCentralWidget(self.viewer)
        panel = QWidget()
        form = QFormLayout(panel)
        for text in (
            "Sagrada Família — feature picking",
            "Click a building or road to inspect its attributes. Drag to navigate.",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            form.addRow(label)
        self.reload = QPushButton("Reload sample")
        self.reload.clicked.connect(self.load_sample)
        self.cancel = QPushButton("Cancel loading")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.viewer.cancel_load)
        form.addRow(self.reload)
        form.addRow(self.cancel)
        self.imagery = QCheckBox("Show orthophoto")
        self.buildings = QCheckBox("Show buildings")
        self.roads = QCheckBox("Show roads")
        for control in (self.imagery, self.buildings, self.roads):
            control.setChecked(True)
            control.setEnabled(False)
            control.toggled.connect(self.apply_style)
            form.addRow(control)
        self.multiple = QCheckBox("Multiple selection (click to add/remove)")
        self.multiple.setEnabled(False)
        self.multiple.toggled.connect(self.change_multiple)
        form.addRow(self.multiple)
        self.count = QLabel("No selection")
        form.addRow(self.count)
        self.selected = QComboBox()
        self.selected.setEnabled(False)
        self.selected.activated.connect(self.activate_selection)
        form.addRow(self.selected)
        self.attributes = QTableWidget(0, 2)
        self.attributes.setHorizontalHeaderLabels(["Property", "Value"])
        self.attributes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.attributes.verticalHeader().hide()
        self.attributes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.attributes.setMinimumHeight(220)
        form.addRow(self.attributes)
        self.focus = QPushButton("Zoom to selection")
        self.focus.clicked.connect(self.viewer.focus_selection)
        self.clear = QPushButton("Clear selection (Esc)")
        self.clear.clicked.connect(self.clear_selection)
        for control in (self.focus, self.clear):
            control.setEnabled(False)
            form.addRow(control)
        self.escape = QShortcut(QKeySequence("Esc"), self)
        self.escape.activated.connect(self.clear_selection)
        self.height = QDoubleSpinBox()
        self.height.setRange(.25, 10)
        self.height.setSingleStep(.25)
        self.height.setValue(1)
        self.height.valueChanged.connect(self.viewer.set_height_scale)
        form.addRow("Vertical exaggeration", self.height)
        reset = QPushButton("Reset view")
        reset.clicked.connect(self.viewer.reset_camera)
        form.addRow(reset)
        note = QLabel(
            "Building heights are illustrative (9 m), not measured. DEM heights are metres; "
            "the vertical datum is unverified.\n\n"
            "Left drag: pan\nWheel/right drag: zoom\nMiddle/Ctrl+left drag: orbit")
        note.setWordWrap(True)
        form.addRow(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        dock = QDockWidget("Feature picking", self)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(180)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.poll = QTimer(self)
        self.poll.setInterval(50)
        self.poll.timeout.connect(self.poll_load)
        self.selection_timer = QTimer(self)
        self.selection_timer.setInterval(150)
        self.selection_timer.timeout.connect(self.poll_selection)

    def set_busy(self, busy):
        self.loading = busy
        self.reload.setEnabled(not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)
        for control in (self.imagery, self.buildings, self.roads, self.multiple):
            control.setEnabled(self.ready and not busy)
        has_selection = self.ready and bool(self.snapshot and self.snapshot["entries"])
        for control in (self.selected, self.focus, self.clear):
            control.setEnabled(has_selection and not busy)
        if self.ready and not busy:
            self.selection_timer.start()
        else:
            self.selection_timer.stop()

    def apply_style(self, *_):
        if not self.ready:
            return
        self.viewer.set_imagery_visible(self.imagery.isChecked())
        self.viewer.set_building_style(self.buildings.isChecked(), 1, QColor(217, 196, 165))
        self.viewer.set_road_style(self.roads.isChecked(), 1, QColor(240, 224, 160))
        self.refresh_selection()

    def change_multiple(self, enabled):
        if self.ready:
            self.viewer.multiple_selection(enabled)

    def clear_selection(self):
        if self.ready and not self.loading:
            self.viewer.clear_selection()
            self.refresh_selection()

    def activate_selection(self, index):
        if self.snapshot and index >= 0:
            self.viewer.activate_selection(self.snapshot["revision"], self.selected.itemData(index))
            self.refresh_selection()

    def poll_selection(self):
        try:
            self.refresh_selection()
        except Exception as error:
            self.selection_timer.stop()
            self.statusBar().showMessage(str(error))

    def refresh_selection(self):
        if not self.ready:
            return
        snapshot = self.viewer.selection()
        if self.snapshot and self.snapshot["revision"] == snapshot["revision"]:
            return
        self.snapshot = snapshot
        entries = snapshot["entries"]
        with QSignalBlocker(self.selected):
            self.selected.clear()
            active = next((e for e in entries if e["index"] == snapshot.get("activeIndex")),
                          entries[0] if entries else None)
            for i, entry in enumerate(entries):
                name = entry["attributes"].get("name") or entry["sourceId"] or entry["featureId"]
                self.selected.addItem(f'{entry["layer"]} / {name}', entry["index"])
                if entry is active:
                    self.selected.setCurrentIndex(i)
        self.count.setText(f"{len(entries)} selected" if entries else "No selection")
        for control in (self.selected, self.focus, self.clear):
            control.setEnabled(bool(entries) and not self.loading)
        rows = []
        if active:
            rows = [("Layer", active["layer"]), ("Type", active["type"]),
                    ("Scene feature ID", active["featureId"])]
            if "sourceFid" in active:
                rows.append(("Source FID", active["sourceFid"]))
            if "displayHeight" in active:
                rows.append(("Display height (estimated)", f'{active["displayHeight"]:g} m'))
            rows.extend(sorted(active["attributes"].items(), key=lambda pair: pair[0].casefold()))
        self.attributes.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.attributes.setItem(row, 0, QTableWidgetItem(key))
            self.attributes.setItem(row, 1, QTableWidgetItem("(null)" if value is None else str(value)))

    def sample_file(self, dataset, filename):
        sample = "sagrada_familia_" + dataset
        return ensure_sample_file(
            self.app, f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{sample}.zip",
            sample + ".zip", sample, filename, "FeaturePicking")

    def shapefile(self, dataset):
        path = self.sample_file(dataset, dataset + ".shp")
        for extension in ("shx", "dbf", "prj"):
            part = self.sample_file(dataset, f"{dataset}.{extension}")
            if part.parent != path.parent:
                raise RuntimeError("Shapefile components must share a directory.")
        return path

    def load_sample(self):
        if self.loading:
            return
        self.downloading = True
        self.set_busy(True)
        try:
            dem = self.sample_file("terrain", "sagrada_familia_terrain.tif")
            imagery = self.sample_file("ortophoto", "sagrada_familia_ortophoto.tif")
            roads = self.shapefile("roads")
            buildings = self.shapefile("buildings")
        except Exception:
            self.statusBar().showMessage("Sample unavailable. Reload to retry.")
            self.set_busy(False)
            return
        finally:
            self.downloading = False
        try:
            self.viewer.load_features(dem, imagery, roads, buildings)
            self.cancel.setEnabled(True)
            self.statusBar().showMessage("Loading buildings and roads…")
            self.poll.start()
        except Exception as error:
            self.fail(error)

    def poll_load(self):
        try:
            state = self.viewer.poll_load()
            if state == 0:
                return
            self.poll.stop()
            if state == 1:
                self.ready = True
                self.snapshot = None
                self.viewer.set_height_scale(self.height.value())
                self.viewer.multiple_selection(self.multiple.isChecked())
                self.apply_style()
                self.statusBar().showMessage("Ready — click a building or road.")
            elif state == -2:
                self.statusBar().showMessage("Loading cancelled.")
            else:
                raise RuntimeError("Loading ended without a scene.")
            self.set_busy(False)
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        self.set_busy(False)
        self.statusBar().showMessage(str(error))
        QMessageBox.critical(self, "FeaturePicking", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.selection_timer.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FeaturePicking")
    app.setWindowIcon(application_icon())
    try:
        window = FeaturePickingWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "FeaturePicking", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
