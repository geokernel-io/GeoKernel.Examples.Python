"""Display and extrude real Sagrada Familia buildings with the published SDK."""

from dataclasses import replace
from math import degrees

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLabel, QMainWindow

from geokernel.globe_qt import GlobeWidget
from geokernel.globe_types import (
    GlobeBuildingBase, GlobeBuildingColors, GlobeBuildingsRequest, GlobeCamera,
    GlobeOptions, GlobeVectorRequest, GlobeVectorStyle,
)

from common import application_icon, ensure_sample_file


def prepare_buildings(app):
    paths = [
        ensure_sample_file(
            app,
            "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_buildings.zip",
            "sagrada_familia_buildings.zip", "sagrada_familia_buildings",
            f"buildings.{extension}", "GlobeBuildings",
        )
        for extension in ("shp", "shx", "dbf", "prj")
    ]
    if any(path.parent != paths[0].parent for path in paths):
        raise RuntimeError("Building shapefile components must be in the same folder.")
    return paths[0]


class GlobeBuildingsWindow(QMainWindow):
    LAYER = "buildings"
    COLOR = "#e8d6b4"

    def __init__(self, buildings):
        super().__init__()
        self.buildings = buildings
        self.loaded = False
        self.home = None
        self.esri_id = -1
        self.job = None
        self.waiting_for_gpu = False
        self.setWindowTitle("GeoKernel — Sagrada Familia Buildings")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setMinimumSize(900, 480)
        self.view = GlobeWidget(
            self,
            camera=GlobeCamera(2.1744, 41.4036, 0, 2500, degrees(1.32), degrees(0.60)),
            options=GlobeOptions(network_enabled=True, atmosphere_enabled=True),
        )
        self.setCentralWidget(self.view)
        self.toolbar = self.addToolBar("Buildings")
        self.toolbar.setMovable(False)
        self.toolbar.setEnabled(False)
        self.extrude = self.toolbar.addAction("Extrude")
        self.extrude.setCheckable(True)
        self.extrude.triggered.connect(self.toggle_extrusion)
        self.toolbar.addWidget(QLabel("Display height (m):"))
        self.height = QDoubleSpinBox()
        self.height.setRange(1, 300)
        self.height.setDecimals(0)
        self.height.setValue(18)
        self.height.setToolTip("Display height, not measured. Turn extrusion off to change it.")
        self.toolbar.addWidget(self.height)
        self.toolbar.addAction("Zoom to buildings", self.zoom_to_buildings)
        self.atmosphere = self.toolbar.addAction("Atmosphere")
        self.atmosphere.setCheckable(True)
        self.atmosphere.setChecked(True)
        self.atmosphere.triggered.connect(self.toggle_atmosphere)
        self.esri = self.toolbar.addAction("Esri")
        self.esri.setCheckable(True)
        self.esri.setChecked(True)
        self.esri.triggered.connect(self.toggle_esri)
        self.statusBar().setFixedHeight(24)
        self.statusBar().setSizeGripEnabled(False)
        self.report("Preparing globe…")
        self.job_timer = QTimer(self)
        self.job_timer.setInterval(50)
        self.job_timer.timeout.connect(self.poll_job)
        self.view.ready.connect(self.globe_ready)
        self.view.error.connect(self.report)

    def globe_ready(self):
        try:
            globe = self.view.globe
            self.esri_id = next(
                (item.id for item in globe.get_basemaps() if item.name == "Esri Satellite"), -1
            )
            globe.set_basemap(self.esri_id)
            self.report("Loading Sagrada Familia buildings…")
            self.start_job(globe.load_vector(GlobeVectorRequest(
                self.LAYER, str(self.buildings), source_crs="EPSG:25831",
                style=GlobeVectorStyle(base_color=self.COLOR),
            )))
        except Exception as error:
            self.report(error)

    def start_job(self, job):
        self.job = job
        self.toolbar.setEnabled(False)
        self.job_timer.start()

    def poll_job(self):
        try:
            globe = self.view.globe
            if self.job is not None:
                state = globe.get_job_state(self.job)
                if state.status in ("queued", "running"):
                    return
                globe.forget_job(self.job)
                self.job = None
                if state.status != "completed":
                    raise RuntimeError(state.error or "Operation cancelled.")
                if not self.loaded:
                    globe.set_layer_opacity(self.LAYER, 0.65)
                    globe.focus_layer(self.LAYER)
                    self.home = replace(
                        globe.camera, distance_metres=globe.camera.distance_metres * 0.28,
                        pitch_degrees=degrees(1.32), heading_degrees=degrees(0.60),
                    )
                    globe.camera = self.home
                    globe.set_home_camera(self.home)
                    self.loaded = True
                elif globe.get_layer_state(self.LAYER).extruded:
                    # Geometry completion precedes the incremental GPU upload.
                    self.waiting_for_gpu = True
                    self.report("Uploading 3D buildings to the GPU…")
                    return
            if self.waiting_for_gpu:
                render = globe.get_state()
                if render.errors.get("scene"):
                    raise RuntimeError(render.errors["scene"])
                if render.scene_upload_pending or render.scene_vertices_drawn == 0:
                    return
            self.finish_operation()
            self.show_summary()
        except Exception as error:
            self.finish_operation()
            self.report(error)

    def finish_operation(self):
        self.job_timer.stop()
        self.waiting_for_gpu = False
        if self.loaded:
            self.extrude.setChecked(self.view.globe.get_layer_state(self.LAYER).extruded)
            self.height.setEnabled(not self.extrude.isChecked())
        self.toolbar.setEnabled(self.loaded)
        self.esri.setEnabled(self.esri_id >= 0)

    def toggle_extrusion(self):
        if not self.loaded or self.job is not None or self.waiting_for_gpu:
            return
        try:
            self.report("Extruding buildings…" if self.extrude.isChecked() else "Restoring footprints…")
            self.start_job(self.view.globe.configure_buildings(GlobeBuildingsRequest(
                self.LAYER, GlobeBuildingBase.REFERENCE_SPHERE,
                enabled=self.extrude.isChecked(), default_height=self.height.value(),
                building_colors=GlobeBuildingColors(mode="uniform", fallback=self.COLOR),
            )))
        except Exception as error:
            self.finish_operation()
            self.report(error)

    def zoom_to_buildings(self):
        if self.home is not None:
            self.view.globe.camera = self.home

    def toggle_atmosphere(self):
        globe = self.view.globe
        globe.options = replace(globe.options, atmosphere_enabled=self.atmosphere.isChecked())

    def toggle_esri(self):
        self.view.globe.set_basemap(self.esri_id if self.esri.isChecked() else -1)
        self.show_summary()

    def show_summary(self):
        layer = self.view.globe.get_layer_state(self.LAYER)
        stats = layer.statistics
        if layer.extruded:
            message = (f"{stats['extrudedPolygons']} extruded polygons | "
                       f"Display height {self.height.value():g} m (not measured) | Click Extrude for footprints")
        else:
            message = (f"{stats['features']} buildings | {stats['outlineOnly']} outline-only | "
                       "Click Extrude for 3D")
        self.report(f"{message} | {self.view.globe.get_attribution()}")

    def report(self, message):
        self.statusBar().showMessage(str(message))
        self.statusBar().setToolTip(str(message))

    def closeEvent(self, event):
        self.job_timer.stop()
        self.view.close_globe()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("GlobeBuildings")
    app.setWindowIcon(application_icon())
    try:
        buildings = prepare_buildings(app)
    except Exception:
        raise SystemExit(1)
    window = GlobeBuildingsWindow(buildings)
    window.show()
    raise SystemExit(app.exec())
