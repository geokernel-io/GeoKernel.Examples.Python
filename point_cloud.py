"""Download and preview the EuroSDR P4 point cloud using the native SDK."""

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDockWidget, QFormLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QWidget,
)

from common import DATA_DIR, application_icon, download_file, extract_zip
from point_cloud_viewer import PointCloudViewer


class PointCloudWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ready = self.loading = self.downloading = False
        self.setWindowTitle("PointCloudViewer — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.viewer = PointCloudViewer(self)
        self.setCentralWidget(self.viewer)
        panel = QWidget()
        form = QFormLayout(panel)

        def caption(text):
            label = QLabel(text)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label)
            return label

        caption("EuroSDR P4 — 40 × 40 m crop")
        self.colors = QComboBox()
        self.colors.addItems(["RGB", "Height"])
        self.colors.currentIndexChanged.connect(self.color_changed)
        form.addRow("Colour", self.colors)
        self.samples = QComboBox()
        for limit in (50000, 100000, 250000):
            self.samples.addItem(f"{limit:,}", limit)
        self.samples.setCurrentIndex(2)
        form.addRow("Sample limit", self.samples)
        self.reload = QPushButton("Load / apply sample limit")
        self.reload.clicked.connect(self.load_sample)
        self.cancel = QPushButton("Cancel loading")
        self.cancel.clicked.connect(self.cancel_load)
        form.addRow(self.reload)
        form.addRow(self.cancel)
        self.details = caption("No points loaded.")
        self.errors = caption("")
        reset = QPushButton("Reset view")
        reset.clicked.connect(lambda: self.perform(self.viewer.reset_camera))
        form.addRow(reset)
        caption("Local normalized preview. Source coordinates remain EPSG:32630; heights are "
                "provisional. Display is sampled up to 250,000 points. Source points are preserved. "
                "Point size: 1 pixel (SDK fixed).")
        caption("Left drag: pan\nWheel/right drag: zoom\nMiddle/Ctrl+left drag: orbit\nShift+left drag: look")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        dock = QDockWidget("Point cloud", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setMinimumWidth(310)
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
        self.state_timer.setInterval(1000)
        self.state_timer.timeout.connect(self.poll_state)
        self.set_busy(False)

    def perform(self, action):
        try:
            action()
        except Exception as error:
            self.errors.setText(str(error))

    def color_changed(self, index):
        if self.ready and not self.loading:
            self.perform(lambda: self.viewer.set_point_style(index == 1))

    def cancel_load(self):
        self.viewer.cancel_load()
        self.cancel.setEnabled(False)

    def set_busy(self, busy):
        self.loading = busy
        self.reload.setEnabled(not busy)
        self.samples.setEnabled(not busy)
        self.colors.setEnabled(self.ready and not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)
        if self.ready and not busy:
            self.state_timer.start()
        else:
            self.state_timer.stop()

    def sample_file(self):
        name = "eurosdr_p4_pointcloud"
        folder = DATA_DIR / name
        marker = folder / ".complete"
        required = name + ".laz"
        matches = list(folder.rglob(required)) if folder.exists() else []
        if marker.is_file() and len(matches) == 1 and matches[0].stat().st_size > 0:
            return matches[0]
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        archive = DATA_DIR / (name + ".zip")
        if not archive.is_file():
            download_file(
                f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{name}.zip",
                archive, self.app, "PointCloudViewer")
        extract_zip(archive, folder, self.app, "PointCloudViewer")
        matches = list(folder.rglob(required))
        if len(matches) != 1 or matches[0].stat().st_size == 0:
            raise RuntimeError(f"Expected one non-empty {required} in the sample archive.")
        marker.write_text("complete", encoding="utf-8")
        archive.unlink(missing_ok=True)
        return matches[0]

    def load_sample(self):
        if self.loading:
            return
        self.downloading = True
        self.set_busy(True)
        try:
            path = self.sample_file()
            self.viewer.load_cloud(path, self.samples.currentData())
            self.cancel.setEnabled(True)
            self.statusBar().showMessage("Reading and sampling LAZ…")
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
                self.ready = True
                self.viewer.set_point_style(self.colors.currentIndex() == 1)
                self.refresh_state()
                self.statusBar().showMessage("Point cloud loaded.")
            elif state == -2:
                self.statusBar().showMessage(
                    "Cancelled; previous cloud retained." if self.ready else "Loading cancelled.")
            else:
                raise RuntimeError("Load ended without a point cloud.")
            self.set_busy(False)
        except Exception as error:
            self.fail(error)

    def refresh_state(self):
        state = self.viewer.cloud_state()
        self.details.setText(
            f'Source: {int(state["total"]):,} points\n'
            f'Display sample: {int(state["sample"]):,} points\n'
            f'Source Z: {state["minimumZ"]:.2f} – {state["maximumZ"]:.2f} m\n'
            f'RGB available: {"Yes" if state["hasRgb"] else "No"}')
        self.errors.setText(state["error"].strip())

    def poll_state(self):
        try:
            self.refresh_state()
        except Exception as error:
            self.state_timer.stop()
            self.errors.setText(str(error))

    def fail(self, error):
        self.poll.stop()
        self.set_busy(False)
        self.errors.setText(str(error))
        self.statusBar().showMessage(str(error))
        QMessageBox.critical(self, "PointCloudViewer", str(error))

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
    app.setApplicationName("PointCloudViewer")
    app.setWindowIcon(application_icon())
    try:
        window = PointCloudWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "PointCloudViewer", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
