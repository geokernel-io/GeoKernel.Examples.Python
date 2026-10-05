"""Display terrain relief, slope and aspect using the native terrain mesh."""

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDockWidget, QDoubleSpinBox, QFormLayout,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QWidget,
)

from common import application_icon, ensure_sample_file
from terrain_analysis_viewer import TerrainAnalysisViewer


class TerrainAnalysisWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.downloading = self.loading = self.ready = False
        self.resolution = 512
        self.setWindowTitle("TerrainAnalysis — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.viewer = TerrainAnalysisViewer(
            self)
        self.setCentralWidget(self.viewer)
        panel = QWidget()
        form = QFormLayout(panel)

        def caption(text):
            label = QLabel(text)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            form.addRow(label)
            return label

        caption("Sagrada Família — sample terrain")
        caption("Slope and aspect describe the loaded terrain mesh, not an exported analysis "
                "raster. Mesh resolution affects results. Heights have an unverified vertical reference.")
        self.reload = QPushButton("Reload sample")
        self.reload.clicked.connect(self.load_sample)
        self.cancel = QPushButton("Cancel loading")
        self.cancel.clicked.connect(self.cancel_load)
        form.addRow(self.reload)
        form.addRow(self.cancel)
        self.quality = QComboBox()
        self.quality.addItems(["256 — Fast", "512 — Balanced", "1024 — Detailed"])
        self.quality.setCurrentIndex(1)
        form.addRow("Mesh samples per side", self.quality)
        self.mode = QComboBox()
        self.mode.addItems(["Terrain relief", "Slope (degrees)", "Aspect (downhill direction)"])
        self.mode.setCurrentIndex(1)
        form.addRow("Display", self.mode)
        self.legend = QLabel()
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        self.legend.setWordWrap(True)
        form.addRow(self.legend)
        caption("Analysis uses terrain mesh faces before vertical exaggeration. "
                "Aspect is clockwise from north in the local ENU frame.")
        self.height = QDoubleSpinBox()
        self.height.setRange(0.25, 10)
        self.height.setSingleStep(0.25)
        self.height.setValue(1)
        self.height.setSuffix(" ×")
        form.addRow("Vertical exaggeration", self.height)
        self.info = caption("No terrain loaded.")
        reset = QPushButton("Reset view")
        reset.clicked.connect(lambda: self.perform(self.viewer.reset_camera))
        form.addRow(reset)
        caption("Left drag: pan\nWheel/right drag: zoom\nMiddle/Ctrl+left drag: orbit\nShift+left drag: look")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        dock = QDockWidget("Terrain analysis", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setMinimumWidth(315)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(160)
        self.statusBar().addPermanentWidget(self.progress)
        self.poll = QTimer(self)
        self.poll.setInterval(50)
        self.poll.timeout.connect(self.poll_load)
        self.mode.currentIndexChanged.connect(lambda _: self.perform(self.apply_style))
        self.height.valueChanged.connect(lambda _: self.perform(self.apply_style))
        self.apply_style()
        self.set_busy(False)

    def perform(self, action):
        try:
            action()
        except Exception as error:
            self.statusBar().showMessage(str(error))

    def apply_style(self):
        mode = self.mode.currentIndex()
        if self.ready:
            self.viewer.set_color_ramp(1)
            self.viewer.set_display_mode(mode)
            self.viewer.set_height_scale(self.height.value())
        note = ""
        if mode == 1:
            rows = [("#2c7bb6", "0 to &lt;5°"), ("#abd9e9", "5 to &lt;15°"),
                    ("#ffffbf", "15 to &lt;30°"), ("#fdae61", "30 to &lt;45°"),
                    ("#d7191c", "45 to 90°")]
        elif mode == 2:
            rows = list(zip(
                ["#e6194b", "#f58230", "#ffe119", "#3cb44b", "#46f0f0", "#0082c8", "#911eb4", "#f032e6"],
                ["N — 0°", "NE — 45°", "E — 90°", "SE — 135°", "S — 180°", "SW — 225°", "W — 270°", "NW — 315°"]))
            rows.append(("#808080", "Flat (slope &lt;0.01°)"))
            note = "Each direction spans ±22.5°."
        else:
            rows = [("#185b3f", "Low"), ("#68984c", "↓"), ("#cfbe7e", "↓"),
                    ("#926b4c", "↓"), ("#fafafa", "High")]
            note = "Relative ENU relief, with lighting."
        swatches = "".join(f'<tr><td bgcolor="{color}" width="24">&nbsp;</td><td>{label}</td></tr>'
                           for color, label in rows)
        self.legend.setText(f'<table cellspacing="5">{swatches}</table>{note}')

    def set_busy(self, busy):
        self.loading = busy
        self.reload.setEnabled(not busy)
        self.quality.setEnabled(not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)

    def cancel_load(self):
        self.viewer.cancel_load()
        self.cancel.setEnabled(False)

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
                "sagrada_familia_terrain.tif", "TerrainAnalysis")
        except Exception:
            self.statusBar().showMessage("Sample unavailable. Reload to retry.")
            self.set_busy(False)
            return
        finally:
            self.downloading = False
        try:
            self.resolution = 256 << self.quality.currentIndex()
            self.viewer.load_terrain(path, self.resolution)
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
                self.statusBar().showMessage("Loading cancelled. Previous scene retained.")
            elif state == 1:
                self.ready = True
                self.apply_style()
                self.info.setText("DEM: sagrada_familia_terrain.tif\nHeights: Unknown — unverified preview\n"
                                  f"Mesh: up to {self.resolution} samples per side")
                self.statusBar().showMessage("Terrain loaded.")
            else:
                raise RuntimeError("Load ended without a terrain scene.")
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        self.set_busy(False)
        self.statusBar().showMessage(str(error))
        QMessageBox.critical(self, "TerrainAnalysis", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TerrainAnalysis")
    app.setWindowIcon(application_icon())
    try:
        window = TerrainAnalysisWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "TerrainAnalysis", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
