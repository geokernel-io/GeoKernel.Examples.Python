"""Style real Sagrada Familia buildings using the published Globe SDK."""

from dataclasses import replace
from math import degrees

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QComboBox, QLabel, QMainWindow, QSlider,
)

from geokernel.globe_qt import GlobeWidget
from geokernel.globe_types import (
    GlobeCamera, GlobeInteraction, GlobeOptions, GlobeVectorRequest, GlobeVectorStyle,
)

from common import application_icon, ensure_sample_file


def prepare_buildings(app):
    paths = [
        ensure_sample_file(
            app,
            "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/sagrada_familia_buildings.zip",
            "sagrada_familia_buildings.zip", "sagrada_familia_buildings",
            f"buildings.{extension}", "GlobeVectorStyling",
        )
        for extension in ("shp", "shx", "dbf", "prj")
    ]
    if any(path.parent != paths[0].parent for path in paths):
        raise RuntimeError("Building shapefile components must be in the same folder.")
    return paths[0]


class GlobeVectorStylingWindow(QMainWindow):
    LAYER = "buildings"

    def __init__(self, buildings):
        super().__init__()
        self.buildings = buildings
        self.loaded = False
        self.home = None
        self.esri_id = -1
        self.base_color = QColor("#efb84c")
        self.job = None
        self.job_done = None
        self.setWindowTitle("GeoKernel — Sagrada Familia Building Styles")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setMinimumSize(900, 480)
        self.view = GlobeWidget(
            self,
            camera=GlobeCamera(2.1744, 41.4036, 0, 2500, degrees(1.32), degrees(0.60)),
            options=GlobeOptions(network_enabled=True, atmosphere_enabled=True),
        )
        self.setCentralWidget(self.view)
        self.toolbar = self.addToolBar("Building styles")
        self.toolbar.setMovable(False)
        self.toolbar.setEnabled(False)
        self.fill = self.toolbar.addAction("Fill")
        self.labels = self.toolbar.addAction("Labels")
        for action in (self.fill, self.labels):
            action.setCheckable(True)
            action.triggered.connect(self.apply_style)
        self.fill.setChecked(True)
        self.category = QComboBox()
        self.label_field = QComboBox()
        for text, combo in (("Color by:", self.category), ("Label:", self.label_field)):
            self.toolbar.addWidget(QLabel(text))
            combo.setMinimumWidth(100)
            self.toolbar.addWidget(combo)
            combo.currentIndexChanged.connect(self.apply_style)
        self.toolbar.addWidget(QLabel("Opacity:"))
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(15, 100)
        self.opacity.setValue(60)
        self.opacity.setFixedWidth(100)
        self.opacity.valueChanged.connect(self.apply_opacity)
        self.toolbar.addWidget(self.opacity)
        self.toolbar.addAction("Base color…", self.choose_color)
        self.zoom = self.toolbar.addAction("Zoom to buildings", self.zoom_to_buildings)
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
        self.view.event_received.connect(self.feature_picked)
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
                style=GlobeVectorStyle(category_field="type", label_field="name",
                                       base_color=self.base_color.name(), label_size=12),
            )), self.buildings_loaded)
        except Exception as error:
            self.report(error)

    def start_job(self, job, done):
        self.job = job
        self.job_done = done
        self.toolbar.setEnabled(False)
        self.job_timer.start()

    def poll_job(self):
        try:
            globe = self.view.globe
            state = globe.get_job_state(self.job)
            if state.status in ("queued", "running"):
                return
            self.job_timer.stop()
            globe.forget_job(self.job)
            self.job = None
            if state.status != "completed":
                raise RuntimeError(state.error or "Operation cancelled.")
            self.job_done()
            self.toolbar.setEnabled(self.loaded)
        except Exception as error:
            self.job_timer.stop()
            self.toolbar.setEnabled(self.loaded)
            self.report(error)

    def buildings_loaded(self):
        globe = self.view.globe
        fields = globe.get_layer_state(self.LAYER).statistics["fields"]
        if not {"type", "name"}.issubset(fields):
            raise RuntimeError("Expected building fields 'type' and 'name' are missing.")
        self.category.addItem("Uniform", "")
        for field in fields:
            self.category.addItem(field, field)
        self.label_field.addItems(fields)
        self.category.setCurrentIndex(self.category.findData("type"))
        self.label_field.setCurrentText("name")
        globe.set_layer_opacity(self.LAYER, self.opacity.value() / 100)
        globe.focus_layer(self.LAYER)
        self.home = replace(globe.camera, distance_metres=globe.camera.distance_metres * 0.28,
                            pitch_degrees=degrees(1.32), heading_degrees=degrees(0.60))
        globe.camera = self.home
        globe.set_home_camera(self.home)
        globe.set_interaction_mode(GlobeInteraction.IDENTIFY)
        self.loaded = True
        self.esri.setEnabled(self.esri_id >= 0)
        self.show_summary()

    def apply_style(self):
        if not self.loaded or self.job is not None:
            return
        try:
            style = GlobeVectorStyle(
                fill=self.fill.isChecked(), labels=self.labels.isChecked(),
                category_field=self.category.currentData(), label_field=self.label_field.currentText(),
                base_color=self.base_color.name(), label_size=12,
            )
            self.report("Applying building style…")
            self.start_job(self.view.globe.set_vector_style(self.LAYER, style), self.show_summary)
        except Exception as error:
            self.report(error)

    def apply_opacity(self, value):
        if self.loaded:
            self.view.globe.set_layer_opacity(self.LAYER, value / 100)

    def choose_color(self):
        color = QColorDialog.getColor(self.base_color, self, "Uniform / fallback building color")
        if color.isValid():
            self.base_color = color
            self.apply_style()

    def zoom_to_buildings(self):
        if self.home is not None:
            self.view.globe.camera = self.home

    def toggle_esri(self):
        self.view.globe.set_basemap(self.esri_id if self.esri.isChecked() else -1)
        self.show_summary()

    def feature_picked(self, event):
        if event.type != "featurePicked" or not event.data.get("hit"):
            return
        try:
            feature_id = str(event.data["featureId"])
            info = self.view.globe.get_feature_info(self.LAYER, feature_id)
            self.report(f"Building {feature_id}: " + " | ".join(
                f"{key}: {value}" for key, value in info.attributes.items()
            ))
        except Exception as error:
            self.report(error)

    def show_summary(self):
        stats = self.view.globe.get_layer_state(self.LAYER).statistics
        self.report(f"{stats['features']} buildings | {stats['outlineOnly']} outline-only | "
                    f"Click to identify | {self.view.globe.get_attribution()}")

    def report(self, message):
        self.statusBar().showMessage(str(message))
        self.statusBar().setToolTip(str(message))

    def closeEvent(self, event):
        self.job_timer.stop()
        self.view.close_globe()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("GlobeVectorStyling")
    app.setWindowIcon(application_icon())
    try:
        buildings = prepare_buildings(app)
    except Exception:
        raise SystemExit(1)
    window = GlobeVectorStylingWindow(buildings)
    window.show()
    raise SystemExit(app.exec())
