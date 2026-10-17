"""Place the real Sagrada Familia model with the published Globe SDK."""

from dataclasses import asdict, replace
from hashlib import file_digest
from math import degrees

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLabel, QMainWindow, QMessageBox

from geokernel.globe_qt import GlobeWidget
from geokernel.globe_types import GlobeCamera, GlobeModelPlacement, GlobeModelRequest, GlobeOptions

from common import DATA_DIR, application_icon, download_file, extract_zip


def prepare_model(app):
    folder = DATA_DIR / "sagrada_familia_3d_model"
    model = folder / "model.gltf"
    marker = folder / ".complete"
    if marker.exists() and model.exists():
        return model
    archive = DATA_DIR / "sagrada_familia_3d_model.zip"
    try:
        download_file(
            "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_3d_model.zip",
            archive, app, "GlobeModelPlacement",
        )
        with archive.open("rb") as file:
            if file_digest(file, "sha256").hexdigest() != "d7f031059b2dc3fb22ce8d25dd3d7bd3d71b5f7675489c818309a78a068dd956":
                raise RuntimeError("The model archive checksum does not match.")
        extract_zip(archive, folder, app, "GlobeModelPlacement")
        if not model.exists():
            raise FileNotFoundError("model.gltf is missing from the archive.")
        marker.write_text("1", encoding="utf-8")
        return model
    finally:
        archive.unlink(missing_ok=True)


class GlobeModelPlacementWindow(QMainWindow):
    LAYER = "sagrada-familia"

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.placement = GlobeModelPlacement(self.LAYER, 2.1744, 41.4036, height=14.089, name="Sagrada Familia")
        self.pending_placement = None
        self.present = False
        self.esri_id = -1
        self.job = None
        self.waiting_for_gpu = False
        self.setWindowTitle("GeoKernel — Sagrada Familia Model")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setMinimumSize(1000, 480)
        self.view = GlobeWidget(
            self, camera=self.model_camera(),
            options=GlobeOptions(network_enabled=True, atmosphere_enabled=True),
        )
        self.setCentralWidget(self.view)
        self.toolbar = self.addToolBar("Model placement")
        self.toolbar.setMovable(False)
        self.toolbar.setEnabled(False)
        self.zoom = self.toolbar.addAction("Zoom to model", self.focus_model)
        self.rotate = self.toolbar.addAction("Rotate 30°", self.rotate_model)
        self.toolbar.addWidget(QLabel("Scale:"))
        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.01, 10)
        self.scale.setDecimals(2)
        self.scale.setSingleStep(0.1)
        self.scale.setValue(1)
        self.toolbar.addWidget(self.scale)
        self.toolbar.addWidget(QLabel("Anchor height (m):"))
        self.height = QDoubleSpinBox()
        self.height.setRange(-100, 10000)
        self.height.setDecimals(3)
        self.height.setValue(14.089)
        self.height.setToolTip("Ellipsoidal anchor height; placement is approximate.")
        self.toolbar.addWidget(self.height)
        self.apply = self.toolbar.addAction("Apply", self.apply_placement)
        self.remove = self.toolbar.addAction("Remove", self.remove_model)
        self.restore = self.toolbar.addAction("Restore", self.load_model)
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

    def model_camera(self):
        p = self.placement
        return GlobeCamera(p.longitude, p.latitude, p.height + 65 * p.scale,
                           550 * p.scale, degrees(1.15), degrees(0.6))

    def focus_model(self):
        self.view.globe.camera = self.model_camera()
        self.view.globe.set_home_camera(self.model_camera())

    def globe_ready(self):
        try:
            globe = self.view.globe
            self.esri_id = next(
                (item.id for item in globe.get_basemaps() if item.name == "Esri Satellite"), -1
            )
            globe.set_basemap(self.esri_id)
            self.load_model()
        except Exception as error:
            self.report(error)

    def start_job(self, job, placement):
        self.job = job
        self.pending_placement = placement
        self.toolbar.setEnabled(False)
        self.job_timer.start()

    def load_model(self):
        try:
            self.report("Loading Sagrada Familia model…")
            self.start_job(self.view.globe.load_model(GlobeModelRequest(
                **asdict(self.placement), path=str(self.model),
            )), self.placement)
        except Exception as error:
            self.finish_operation()
            self.report(error)

    def place_model(self, placement):
        if not self.present or not self.toolbar.isEnabled():
            return
        try:
            self.report("Updating model placement…")
            self.start_job(self.view.globe.set_model_placement(placement), placement)
        except Exception as error:
            self.finish_operation()
            self.report(error)

    def rotate_model(self):
        self.place_model(replace(self.placement, heading=(self.placement.heading + 30) % 360))

    def apply_placement(self):
        self.place_model(replace(self.placement, scale=self.scale.value(), height=self.height.value()))

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
                self.placement = self.pending_placement
                self.present = True
                self.focus_model()
                # Geometry completion precedes the incremental GPU upload.
                self.waiting_for_gpu = True
                self.report("Uploading model to the GPU…")
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
        self.pending_placement = None
        self.scale.setValue(self.placement.scale)
        self.height.setValue(self.placement.height)
        self.toolbar.setEnabled(True)
        for control in (self.rotate, self.scale, self.height, self.apply, self.remove):
            control.setEnabled(self.present)
        self.restore.setEnabled(not self.present)
        self.esri.setEnabled(self.esri_id >= 0)

    def remove_model(self):
        try:
            self.view.globe.remove_layer(self.LAYER)
            self.present = False
            self.finish_operation()
            self.show_summary()
        except Exception as error:
            self.report(error)

    def toggle_atmosphere(self):
        globe = self.view.globe
        globe.options = replace(globe.options, atmosphere_enabled=self.atmosphere.isChecked())

    def toggle_esri(self):
        self.view.globe.set_basemap(self.esri_id if self.esri.isChecked() else -1)
        self.show_summary()

    def show_summary(self):
        message = "Approximate placement" if self.present else "Model removed — click Restore"
        self.report(f"Sagrada Familia | {message} | Model: PeeJaa | {self.view.globe.get_attribution()}")

    def report(self, message):
        self.statusBar().showMessage(str(message))
        self.statusBar().setToolTip(str(message))

    def closeEvent(self, event):
        self.job_timer.stop()
        self.view.close_globe()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("GlobeModelPlacement")
    app.setWindowIcon(application_icon())
    try:
        model = prepare_model(app)
    except Exception as error:
        QMessageBox.critical(None, "GlobeModelPlacement", str(error))
        raise SystemExit(1)
    window = GlobeModelPlacementWindow(model)
    window.show()
    raise SystemExit(app.exec())
