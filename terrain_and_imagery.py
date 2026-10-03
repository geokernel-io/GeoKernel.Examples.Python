"""Load the Sagrada Familia DEM and orthophoto automatically."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox, QFormLayout,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QWidget,
)

from common import application_icon, ensure_sample_file
from terrain_viewer import TerrainViewer


class TerrainAndImageryWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.downloading = False
        self.loading = False
        self.setWindowTitle("TerrainAndImagery — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        # Until the imagery API is published, use the explicitly selected DLL
        # or the sibling GeoKernel checkout's Release build. Other examples keep
        # using the installed package unchanged.
        local_library = Path(__file__).resolve().parent.parent / (
            "GeoKernel/outputs/build/Release/GeoKernel.Viewer3D.dll")
        library = os.environ.get("GEOKERNEL_VIEWER3D_LIBRARY")
        if not library and local_library.is_file():
            library = local_library
        self.viewer = TerrainViewer(self, library=library)
        self.viewer.enable_imagery_api()
        self.setCentralWidget(self.viewer)

        panel = QWidget()
        form = QFormLayout(panel)
        form.addRow(QLabel("Sagrada Familia - terrain and orthophoto"))
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
        dock.setWidget(panel)
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
                "sagrada_familia_terrain.tif", "TerrainAndImagery",
            )
            imagery_path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_ortophoto.zip",
                "sagrada_familia_ortophoto.zip", "sagrada_familia_ortophoto",
                "sagrada_familia_ortophoto.tif", "TerrainAndImagery",
            )
        except Exception:
            # The shared downloader already displays the error.
            self.statusBar().showMessage("Sample unavailable. Reload to retry.")
            self.set_busy(False)
            return
        finally:
            self.downloading = False
        try:
            self.viewer.load_terrain_and_imagery(
                path, imagery_path, 256 << self.quality.currentIndex())
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
                self.statusBar().showMessage("Terrain and orthophoto loaded")
            else:
                raise RuntimeError("Terrain loading ended without a scene.")
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        self.set_busy(False)
        self.statusBar().showMessage("Terrain could not be loaded.")
        QMessageBox.critical(self, "TerrainAndImagery", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TerrainAndImagery")
    app.setWindowIcon(application_icon())
    try:
        window = TerrainAndImageryWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "TerrainAndImagery", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
