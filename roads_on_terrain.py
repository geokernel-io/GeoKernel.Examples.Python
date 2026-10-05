"""Load the Sagrada Familia DEM, orthophoto and roads automatically."""

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


class RoadsOnTerrainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.downloading = False
        self.loading = False
        self.roads_ready = False
        self.road_color = QColor(255, 207, 51)
        self.setWindowTitle("RoadsOnTerrain — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.viewer = TerrainViewer(self)
        self.viewer.enable_imagery_api()
        self.viewer.enable_roads_api()
        self.setCentralWidget(self.viewer)

        panel = QWidget()
        form = QFormLayout(panel)
        form.addRow(QLabel("Sagrada Família — terrain, orthophoto and roads"))
        self.quality = QComboBox()
        self.quality.addItems(["256 — Fast", "512 — Balanced", "1024 — Detailed"])
        self.quality.setCurrentIndex(1)
        form.addRow("Terrain mesh", self.quality)
        self.reload = QPushButton("Reload terrain")
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
        self.roads = QCheckBox("Show roads")
        self.roads.setChecked(True)
        self.roads.setEnabled(False)
        self.roads.toggled.connect(self.apply_road_style)
        form.addRow(self.roads)
        self.color_button = QPushButton("Road color")
        self.color_button.setEnabled(False)
        self.color_button.clicked.connect(self.choose_road_color)
        form.addRow(self.color_button)
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setValue(100)
        self.opacity.setSuffix(" %")
        self.opacity.setEnabled(False)
        self.opacity.valueChanged.connect(self.apply_road_style)
        form.addRow("Road opacity", self.opacity)
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
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)

    def apply_style(self, *_):
        self.viewer.set_imagery_visible(self.imagery.isChecked())
        self.viewer.set_height_scale(self.height.value())

    def apply_road_style(self, *_):
        if self.roads_ready:
            self.viewer.set_road_style(
                self.roads.isChecked(), self.opacity.value() / 100, self.road_color)
            self.color_button.setText(f"Road color: {self.road_color.name()}")

    def choose_road_color(self):
        color = QColorDialog.getColor(self.road_color, self, "Road color")
        if color.isValid():
            self.road_color = color
            self.apply_road_style()

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
                "sagrada_familia_terrain.tif", "RoadsOnTerrain",
            )
            imagery_path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_ortophoto.zip",
                "sagrada_familia_ortophoto.zip", "sagrada_familia_ortophoto",
                "sagrada_familia_ortophoto.tif", "RoadsOnTerrain",
            )
            for extension in ("shp", "shx", "dbf", "prj"):
                road_file = ensure_sample_file(
                    self.app,
                    "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_roads.zip",
                    "sagrada_familia_roads.zip", "sagrada_familia_roads",
                    f"roads.{extension}", "RoadsOnTerrain",
                )
                if extension == "shp":
                    roads_path = road_file
                elif road_file.parent != roads_path.parent:
                    raise RuntimeError("Road shapefile components must share a directory.")
        except Exception:
            # The shared downloader already displays the error.
            self.statusBar().showMessage("Sample unavailable. Reload to retry.")
            self.set_busy(False)
            return
        finally:
            self.downloading = False
        try:
            self.viewer.load_roads_on_terrain(
                path, imagery_path, roads_path, 256 << self.quality.currentIndex())
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
                self.roads_ready = True
                for control in (self.roads, self.color_button, self.opacity):
                    control.setEnabled(True)
                self.apply_road_style()
                count = self.viewer.get_road_vertex_count()
                self.statusBar().showMessage(
                    f"Terrain, orthophoto and roads loaded — {count:,} road vertices")
            else:
                raise RuntimeError("Terrain loading ended without a scene.")
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        self.set_busy(False)
        self.statusBar().showMessage("Terrain could not be loaded.")
        QMessageBox.critical(self, "RoadsOnTerrain", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RoadsOnTerrain")
    app.setWindowIcon(application_icon())
    try:
        window = RoadsOnTerrainWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "RoadsOnTerrain", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
