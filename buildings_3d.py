"""Load the Sagrada Familia DEM, orthophoto and buildings automatically."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDockWidget, QDoubleSpinBox, QFormLayout,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QWidget,
)

from common import application_icon, ensure_sample_file
from terrain_viewer import TerrainViewer


class Buildings3DWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.downloading = False
        self.loading = False
        self.buildings_ready = False
        self.building_color = QColor(217, 196, 165)
        self.setWindowTitle("Buildings3D — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.viewer = TerrainViewer(self)
        self.viewer.enable_imagery_api()
        self.viewer.enable_buildings_api()
        self.setCentralWidget(self.viewer)

        panel = QWidget()
        form = QFormLayout(panel)
        form.addRow(QLabel("Sagrada Família — terrain, orthophoto and buildings"))
        self.quality = QComboBox()
        self.quality.addItems(["256 — Fast", "512 — Balanced", "1024 — Detailed"])
        self.quality.setCurrentIndex(1)
        form.addRow("Terrain mesh", self.quality)
        self.building_height = QDoubleSpinBox()
        self.building_height.setRange(1, 300)
        self.building_height.setDecimals(1)
        self.building_height.setValue(9)
        self.building_height.setSuffix(" m")
        form.addRow("Default building height", self.building_height)
        height_note = QLabel(
            "Illustrative height: this dataset has no measured building heights. "
            "Apply height / Reload sample after changing it.")
        height_note.setWordWrap(True)
        form.addRow(height_note)
        self.reload = QPushButton("Apply height / Reload sample")
        self.reload.clicked.connect(self.load_sample)
        form.addRow(self.reload)
        self.cancel = QPushButton("Cancel loading")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.viewer.cancel_load)
        form.addRow(self.cancel)
        self.imagery = QCheckBox("Show orthophoto")
        self.imagery.setChecked(True)
        self.imagery.setEnabled(False)
        self.imagery.toggled.connect(self.apply_style)
        form.addRow(self.imagery)
        self.buildings = QCheckBox("Show buildings")
        self.buildings.setChecked(True)
        self.buildings.setEnabled(False)
        self.buildings.toggled.connect(self.apply_building_style)
        form.addRow(self.buildings)
        self.color_button = QPushButton("Building color")
        self.color_button.setEnabled(False)
        self.color_button.clicked.connect(self.choose_building_color)
        form.addRow(self.color_button)
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setValue(100)
        self.opacity.setSuffix(" %")
        self.opacity.setEnabled(False)
        self.opacity.valueChanged.connect(self.apply_building_style)
        form.addRow("Building opacity", self.opacity)
        self.height = QDoubleSpinBox()
        self.height.setRange(0.25, 10)
        self.height.setSingleStep(0.25)
        self.height.setValue(1)
        self.height.setSuffix(" ×")
        self.height.valueChanged.connect(self.apply_style)
        form.addRow("Vertical exaggeration", self.height)
        note = QLabel(
            "DEM heights are treated as metres; "
            "the vertical datum is unverified.\n\n"
            "Left drag: pan\nWheel / right drag: zoom\nMiddle / Ctrl + left drag: orbit"
        )
        note.setWordWrap(True)
        form.addRow(note)
        reset = QPushButton("Reset view")
        reset.clicked.connect(self.viewer.reset_camera)
        form.addRow(reset)
        dock = QDockWidget("Terrain", self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
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

    def set_busy(self, busy):
        self.loading = busy
        self.reload.setEnabled(not busy)
        self.quality.setEnabled(not busy)
        self.building_height.setEnabled(not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)

    def apply_style(self, *_):
        self.viewer.set_imagery_visible(self.imagery.isChecked())
        self.viewer.set_height_scale(self.height.value())

    def apply_building_style(self, *_):
        if self.buildings_ready:
            self.viewer.set_building_style(
                self.buildings.isChecked(), self.opacity.value() / 100, self.building_color)
            self.color_button.setText(f"Building color: {self.building_color.name()}")

    def choose_building_color(self):
        color = QColorDialog.getColor(self.building_color, self, "Building color")
        if color.isValid():
            self.building_color = color
            self.apply_building_style()

    def load_sample(self):
        if self.loading:
            return
        self.downloading = True
        self.set_busy(True)
        self.statusBar().showMessage("Preparing terrain…")
        try:
            path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_terrain.zip",
                "sagrada_familia_terrain.zip", "sagrada_familia_terrain",
                "sagrada_familia_terrain.tif", "Buildings3D",
            )
            imagery_path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_ortophoto.zip",
                "sagrada_familia_ortophoto.zip", "sagrada_familia_ortophoto",
                "sagrada_familia_ortophoto.tif", "Buildings3D",
            )
            for extension in ("shp", "shx", "dbf", "prj"):
                building_file = ensure_sample_file(
                    self.app,
                    "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_buildings.zip",
                    "sagrada_familia_buildings.zip", "sagrada_familia_buildings",
                    f"buildings.{extension}", "Buildings3D",
                )
                if extension == "shp":
                    buildings_path = building_file
                elif building_file.parent != buildings_path.parent:
                    raise RuntimeError("Building shapefile components must share a directory.")
        except Exception:
            # The shared downloader already displays the error.
            self.statusBar().showMessage("Sample unavailable. Reload to retry.")
            self.set_busy(False)
            return
        finally:
            self.downloading = False
        try:
            self.viewer.load_buildings_on_terrain(
                path, imagery_path, buildings_path, self.building_height.value(),
                256 << self.quality.currentIndex())
            self.apply_style()
            self.cancel.setEnabled(True)
            self.statusBar().showMessage("Loading terrain…")
            self.poll.start()
        except Exception as error:
            self.fail(error)

    def poll_load(self):
        try:
            state = self.viewer.poll_load()
            if state == 0:
                return
            self.poll.stop()
            self.set_busy(False)
            if state == -2:
                self.statusBar().showMessage("Loading cancelled.")
            elif state == 1:
                self.apply_style()
                self.imagery.setEnabled(True)
                self.buildings_ready = True
                for control in (self.buildings, self.color_button, self.opacity):
                    control.setEnabled(True)
                self.apply_building_style()
                count = self.viewer.get_building_vertex_count()
                self.statusBar().showMessage(
                    f"Terrain, orthophoto and buildings loaded — {count:,} building vertices")
            else:
                raise RuntimeError("Terrain loading ended without a scene.")
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        self.set_busy(False)
        self.statusBar().showMessage("Terrain could not be loaded.")
        QMessageBox.critical(self, "Buildings3D", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Buildings3D")
    app.setWindowIcon(application_icon())
    try:
        window = Buildings3DWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "Buildings3D", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
