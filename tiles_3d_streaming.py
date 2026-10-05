"""Stream the downloaded Sagrada Família 3D Tiles over corrected terrain."""

import os
import sys

from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDockWidget, QFormLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QWidget,
)

from common import application_icon, ensure_sample_file, DATA_DIR, download_file, extract_zip
from tiles_viewer import TilesViewer


class TilesWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ready = self.loading = self.downloading = self.resume = False
        self.source = self.pending_source = None
        self.setWindowTitle("Tiles3DStreaming — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1400, 850)
        self.viewer = TilesViewer(self)
        self.setCentralWidget(self.viewer)
        panel = QWidget()
        form = QFormLayout(panel)

        def caption(text):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label)
            return label

        caption("Sagrada Família — terrain and 3D Tiles")
        self.reload = QPushButton("Reload sample")
        self.reload.clicked.connect(self.load_sample)
        self.cancel = QPushButton("Cancel loading")
        self.cancel.clicked.connect(self.viewer.cancel_load)
        form.addRow(self.reload)
        form.addRow(self.cancel)
        self.imagery = QCheckBox("Show orthophoto")
        self.imagery.setChecked(True)
        self.imagery.toggled.connect(self.imagery_changed)
        form.addRow(self.imagery)
        caption("Camera movement selects tile detail automatically. Data streams from the downloaded local archive.")
        self.budget = QSpinBox()
        self.budget.setRange(64, 128)
        self.budget.setSingleStep(32)
        self.budget.setValue(96)
        form.addRow("CPU geometry batch budget (MiB)", self.budget)
        self.start = QPushButton("Start / apply budget")
        self.start.clicked.connect(lambda: self.perform(self.start_streaming))
        self.stop = QPushButton("Stop streaming (keep current tiles)")
        self.stop.clicked.connect(lambda: self.perform(self.viewer.stop_tiles))
        self.visible = QCheckBox("Show buildings")
        self.visible.setChecked(True)
        self.visible.toggled.connect(self.visibility_changed)
        self.focus = QPushButton("Focus loaded tiles")
        self.focus.clicked.connect(lambda: self.perform(self.viewer.focus_tiles))
        for widget in (self.start, self.stop, self.visible, self.focus):
            form.addRow(widget)
        self.details = caption("No terrain loaded.")
        self.errors = caption("")
        reset = QPushButton("Reset view")
        reset.clicked.connect(lambda: self.perform(self.viewer.reset_camera))
        form.addRow(reset)
        caption("Vertical exaggeration: 1×. DEM uses the regional EGM08D595 correction. "
                "Building/terrain alignment is approximate and not independently surveyed.")
        caption("Hiding clears the loaded model; showing restarts streaming. Stop may wait for "
                "in-flight work. Cache counters are not total RAM/VRAM usage.")
        caption("Left drag: pan\nWheel/right drag: zoom\nMiddle/Ctrl+left drag: orbit")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        dock = QDockWidget("3D Tiles streaming", self)
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
        self.state_timer = QTimer(self)
        self.state_timer.setInterval(500)
        self.state_timer.timeout.connect(self.poll_state)
        self.set_busy(False)

    def perform(self, action):
        try:
            action()
            self.errors.clear()
            self.refresh_state()
        except Exception as error:
            self.errors.setText(str(error))

    def imagery_changed(self, *_):
        if self.ready:
            self.perform(lambda: self.viewer.set_imagery_visible(self.imagery.isChecked()))

    def visibility_changed(self, visible):
        if self.ready and not self.loading:
            self.perform(self.start_streaming if visible else lambda: self.viewer.stop_tiles(clear=True))

    def start_streaming(self):
        if not self.ready or self.source is None:
            return
        self.viewer.start_tiles(self.source, self.budget.value())
        with QSignalBlocker(self.visible):
            self.visible.setChecked(True)

    def poll_state(self):
        try:
            self.refresh_state()
        except Exception as error:
            self.state_timer.stop()
            self.errors.setText(str(error))

    def refresh_state(self):
        if not self.ready or self.loading:
            return
        state = self.viewer.tiles_state()
        self.stop.setEnabled(state["active"])
        self.focus.setEnabled(state["attached"] and self.visible.isChecked())
        phase = "Updating (previous tiles visible)" if state["loading"] else "Active"
        if not state["active"]:
            phase = "Stopped"
        self.details.setText(
            f'State: {phase}\nLoaded tiles: {state["tiles"]}\nDeferred tiles: {state["deferredTiles"]}\n'
            f'Detail budget limited: {"Yes" if state["selectionLimited"] else "No"}\n'
            f'CPU cache: {int(state["cacheBytes"]) / (1024 * 1024):.1f} MiB\n'
            f'Cache hits: {state["cacheHits"]}\nDrawn vertices: {state["drawnVertices"]}\n'
            f'GPU upload pending: {"Yes" if state["uploadPending"] else "No"}')
        self.errors.setText(state["error"].strip())

    def set_busy(self, busy):
        self.loading = busy
        self.reload.setEnabled(not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)
        for control in (self.start, self.budget, self.visible, self.imagery):
            control.setEnabled(self.ready and not busy)
        self.stop.setEnabled(False)
        self.focus.setEnabled(False)
        if self.ready and not busy:
            self.state_timer.start()
        else:
            self.state_timer.stop()

    def raster(self, dataset):
        name = "sagrada_familia_" + dataset
        return ensure_sample_file(
            self.app, f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{name}.zip",
            name + ".zip", name, name + ".tif", "Tiles3DStreaming")

    def archive(self, name, url, required):
        folder = DATA_DIR / name
        marker = folder / ".complete"
        matches = list(folder.rglob(required)) if folder.exists() else []
        if marker.is_file() and len(matches) == 1:
            return matches[0]
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        archive = DATA_DIR / (name + ".zip")
        if not archive.is_file():
            download_file(url, archive, self.app, "Tiles3DStreaming")
        extract_zip(archive, folder, self.app, "Tiles3DStreaming")
        matches = list(folder.rglob(required))
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {required} in {name}.")
        marker.write_text("complete", encoding="utf-8")
        archive.unlink(missing_ok=True)
        return matches[0]

    def load_sample(self):
        if self.loading:
            return
        self.downloading = True
        self.set_busy(True)
        self.resume = False
        try:
            if self.ready:
                self.resume = self.viewer.tiles_state()["active"]
                self.viewer.stop_tiles()
            dem = self.raster("terrain")
            imagery = self.raster("ortophoto")
            tiles = self.archive("sagrada_familia_3d_tiles",
                                 "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_3d_tiles.zip",
                                 "tileset.json")
            geoid = self.archive("egm08d595",
                                 "https://icgc-web-pro.s3.eu-central-1.amazonaws.com/produccio/s3fs-public/EGM08D595_19839.zip",
                                 "cat80000.gr")
            self.pending_source = tiles
            self.viewer.load_tiles_terrain(dem, imagery, geoid, tiles)
            self.cancel.setEnabled(True)
            self.statusBar().showMessage("Loading corrected terrain…")
            self.poll.start()
        except Exception as error:
            self.fail(error)
        finally:
            self.downloading = False

    def complete_load(self):
        self.set_busy(False)
        if self.resume and self.ready:
            self.start_streaming()
        self.refresh_state()

    def poll_load(self):
        try:
            state = self.viewer.poll_load()
            if state == 0:
                return
            self.poll.stop()
            if state == 1:
                self.ready = True
                self.source = self.pending_source
                self.viewer.set_imagery_visible(self.imagery.isChecked())
                self.resume = self.visible.isChecked()
                self.statusBar().showMessage("Terrain loaded — camera movement controls tile detail.")
            elif state == -2:
                self.statusBar().showMessage("Loading cancelled.")
            else:
                raise RuntimeError("Loading ended without a scene.")
            self.complete_load()
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.poll.stop()
        try:
            self.complete_load()
        except Exception:
            self.state_timer.stop()
        self.errors.setText(str(error))
        self.statusBar().showMessage(str(error))
        QMessageBox.critical(self, "Tiles3DStreaming", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.poll.stop()
        self.state_timer.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Tiles3DStreaming")
    app.setWindowIcon(application_icon())
    try:
        window = TilesWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "Tiles3DStreaming", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
