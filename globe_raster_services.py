"""Open real Sagrada Familia orthophoto and DEM with the published Globe SDK."""

from dataclasses import replace
from hashlib import file_digest
from math import degrees

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from geokernel.globe_qt import GlobeWidget
from geokernel.globe_types import GlobeCamera, GlobeDemRequest, GlobeOptions, GlobeRasterRequest

from common import DATA_DIR, application_icon, download_file, extract_zip


def prepare_rasters(app):
    paths = []
    for name, checksum in (
        ("sagrada_familia_ortophoto", "43a09656ca07490e91a48b413428e8c093d392d3a63549e997c9b4b20ffa9f40"),
        ("sagrada_familia_terrain", "69ed86c686b2500a70921920387afcb8993f3fe042e2a682932f86b7c6d5127c"),
    ):
        folder = DATA_DIR / name
        raster = folder / f"{name}.tif"
        marker = folder / ".complete"
        if not (raster.exists() and marker.exists()):
            archive = DATA_DIR / f"{name}.zip"
            try:
                download_file(
                    f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{name}.zip",
                    archive, app, "GlobeRasterServices",
                )
                with archive.open("rb") as file:
                    if file_digest(file, "sha256").hexdigest() != checksum:
                        raise RuntimeError(f"Archive checksum mismatch: {name}")
                extract_zip(archive, folder, app, "GlobeRasterServices")
                if not raster.exists():
                    raise FileNotFoundError(raster)
                marker.write_text("1", encoding="utf-8")
            finally:
                archive.unlink(missing_ok=True)
        paths.append(raster)
    return paths


class GlobeRasterServicesWindow(QMainWindow):
    def __init__(self, ortho, dem):
        super().__init__()
        self.ortho = ortho
        self.dem = dem
        self.job = None
        self.loading_dem = False
        self.loaded = False
        self.setWindowTitle("GeoKernel — Sagrada Ortho & DEM")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setMinimumSize(720, 480)
        self.view = GlobeWidget(
            self,
            camera=GlobeCamera(2.1744, 41.4036, 0, 2500, degrees(1.32), degrees(.6)),
            options=GlobeOptions(network_enabled=True, atmosphere_enabled=True),
        )
        self.setCentralWidget(self.view)
        self.statusBar().setFixedHeight(24)
        self.statusBar().setSizeGripEnabled(False)
        self.report("Preparing globe…")
        self.job_timer = QTimer(self)
        self.job_timer.setInterval(50)
        self.job_timer.timeout.connect(self.poll_job)
        self.error_timer = QTimer(self)
        self.error_timer.setInterval(500)
        self.error_timer.timeout.connect(self.check_errors)
        self.view.ready.connect(self.globe_ready)
        self.view.error.connect(self.report)

    def globe_ready(self):
        try:
            globe = self.view.globe
            esri = next((item.id for item in globe.get_basemaps() if item.name == "Esri Satellite"), -1)
            globe.set_basemap(esri)
            self.report("Loading Sagrada orthophoto…")
            self.job = globe.load_raster(GlobeRasterRequest("ortho", str(self.ortho)))
            self.job_timer.start()
        except Exception as error:
            self.report(error)

    def poll_job(self):
        try:
            globe = self.view.globe
            state = globe.get_job_state(self.job)
            if state.status in ("queued", "running"):
                return
            globe.forget_job(self.job)
            self.job = None
            if state.status != "completed":
                raise RuntimeError(state.error or "Operation cancelled.")
            if not self.loading_dem:
                self.report("Loading Sagrada DEM…")
                self.job = globe.load_dem(GlobeDemRequest("dem", str(self.dem)))
                self.loading_dem = True
                return
            self.job_timer.stop()
            stats = globe.get_layer_state("dem").statistics
            # Keep elevation active without coloring over the orthophoto.
            globe.set_dem_style(False, stats["minimum"], stats["maximum"])
            globe.options = replace(globe.options, terrain_enabled=True, terrain_exaggeration=1)
            globe.focus_layer("ortho")
            camera = replace(globe.camera, distance_metres=globe.camera.distance_metres * .6,
                             pitch_degrees=degrees(1.32), heading_degrees=degrees(.6))
            globe.camera = camera
            globe.set_home_camera(camera)
            self.loaded = True
            self.check_errors()
            self.error_timer.start()
        except Exception as error:
            self.job_timer.stop()
            self.report(error)

    def check_errors(self):
        if not self.loaded:
            return
        try:
            globe = self.view.globe
            error = next((value for value in globe.get_state().errors.values() if value), None)
            self.report(error or f"Sagrada Familia orthophoto + DEM | Elevation 1x | {globe.get_attribution()}")
        except Exception as error:
            self.report(error)

    def report(self, message):
        self.statusBar().showMessage(str(message))
        self.statusBar().setToolTip(str(message))

    def closeEvent(self, event):
        self.job_timer.stop()
        self.error_timer.stop()
        self.view.close_globe()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("GlobeRasterServices")
    app.setWindowIcon(application_icon())
    try:
        ortho, dem = prepare_rasters(app)
    except Exception as error:
        QMessageBox.critical(None, "GlobeRasterServices", str(error))
        raise SystemExit(1)
    window = GlobeRasterServicesWindow(ortho, dem)
    window.show()
    raise SystemExit(app.exec())
