"""Load the Sagrada Familia DEM, orthophoto and textured model automatically."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox, QFormLayout,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QWidget,
)

from common import application_icon, ensure_sample_file, DATA_DIR, download_file, extract_zip
from terrain_viewer import TerrainViewer


class ModelPlacementWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.downloading = False
        self.loading = False
        self.model_ready = False
        self.setWindowTitle("ModelPlacement — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.viewer = TerrainViewer(self)
        self.viewer.enable_imagery_api()
        self.viewer.enable_model_api()
        self.setCentralWidget(self.viewer)

        panel = QWidget()
        form = QFormLayout(panel)
        form.addRow(QLabel("Sagrada Família — textured model"))
        self.quality = QComboBox()
        self.quality.addItems(["256 — Fast", "512 — Balanced", "1024 — Detailed"])
        self.quality.setCurrentIndex(1)
        form.addRow("Terrain mesh", self.quality)
        self.placement = []
        for label, minimum, maximum, value, decimals in (
            ("Longitude", -180, 180, 2.174401283, 9),
            ("Latitude", -90, 90, 41.403605046, 9),
            ("Above terrain (m)", -500, 1000, 2.938, 3),
            ("Heading (degrees)", -180, 180, .2373346, 7),
            ("Pitch (degrees)", -180, 180, 0, 2),
            ("Roll (degrees)", -180, 180, 0, 2),
            ("Scale", .01, 100, .958139, 6),
        ):
            field = QDoubleSpinBox()
            field.setDecimals(decimals)
            field.setRange(minimum, maximum)
            field.setValue(value)
            self.placement.append(field)
            form.addRow(label, field)
        self.reload = QPushButton("Apply placement / Reload")
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
        self.visible = QCheckBox("Show model")
        self.visible.setChecked(True)
        self.visible.setEnabled(False)
        self.visible.toggled.connect(self.viewer.set_model_visible)
        form.addRow(self.visible)
        self.focus = QPushButton("Focus model")
        self.focus.setEnabled(False)
        self.focus.clicked.connect(self.viewer.focus_model)
        form.addRow(self.focus)
        self.height = QDoubleSpinBox()
        self.height.setRange(0.25, 10)
        self.height.setSingleStep(0.25)
        self.height.setValue(1)
        self.height.setSuffix(" ×")
        self.height.valueChanged.connect(self.apply_style)
        form.addRow("Vertical exaggeration", self.height)
        note = QLabel(
            "Approximate demo placement; not a surveyed fit. Height is an offset above "
            "terrain at the model anchor. DEM uses EGM08D595 geoid correction. "
            "Textures are retained.\n\nModel: PeeJaa — La Sagrada Familia. "
            "Source and license: downloaded model/license.txt.\n\n"
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
        for field in self.placement:
            field.setEnabled(not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)

    def apply_style(self, *_):
        self.viewer.set_imagery_visible(self.imagery.isChecked())
        self.viewer.set_height_scale(self.height.value())

    def ensure_archive(self, name, url, required):
        folder = DATA_DIR / name
        marker = folder / ".complete"
        matches = list(folder.rglob(required)) if folder.exists() else []
        if marker.is_file() and len(matches) == 1:
            return matches[0]
        archive = DATA_DIR / (name + ".zip")
        try:
            if not archive.is_file():
                download_file(url, archive, self.app, "ModelPlacement")
            extract_zip(archive, folder, self.app, "ModelPlacement")
            matches = list(folder.rglob(required))
            if len(matches) != 1:
                raise RuntimeError(f"Expected one {required} in {name}.")
            marker.write_text("complete", encoding="utf-8")
            archive.unlink(missing_ok=True)
            return matches[0]
        except Exception as error:
            QMessageBox.critical(self, "ModelPlacement", str(error))
            raise

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
                "sagrada_familia_terrain.tif", "ModelPlacement",
            )
            imagery_path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_ortophoto.zip",
                "sagrada_familia_ortophoto.zip", "sagrada_familia_ortophoto",
                "sagrada_familia_ortophoto.tif", "ModelPlacement",
            )
            model_path = self.ensure_archive(
                "sagrada_familia_3d_model",
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_3d_model.zip",
                "model.gltf")
            geoid_path = self.ensure_archive(
                "egm08d595",
                "https://icgc-web-pro.s3.eu-central-1.amazonaws.com/produccio/s3fs-public/EGM08D595_19839.zip",
                "cat80000.gr")
        except Exception:
            # The shared downloader already displays the error.
            self.statusBar().showMessage("Sample unavailable. Reload to retry.")
            self.set_busy(False)
            return
        finally:
            self.downloading = False
        try:
            self.viewer.load_model_on_terrain(
                path, imagery_path, model_path, geoid_path, [field.value() for field in self.placement],
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
                self.model_ready = True
                self.visible.setEnabled(True)
                self.focus.setEnabled(True)
                self.viewer.set_model_visible(self.visible.isChecked())
                self.viewer.focus_model()
                count = self.viewer.get_model_vertex_count()
                self.statusBar().showMessage(
                    f"Model loaded — {count // 3:,} triangles; EGM08D595 corrected terrain")
            else:
                raise RuntimeError("Terrain loading ended without a scene.")
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        self.set_busy(False)
        self.statusBar().showMessage("Terrain could not be loaded.")
        QMessageBox.critical(self, "ModelPlacement", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ModelPlacement")
    app.setWindowIcon(application_icon())
    try:
        window = ModelPlacementWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "ModelPlacement", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
