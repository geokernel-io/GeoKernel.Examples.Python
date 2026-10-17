"""Interactive terrain analysis on the real Barcelona DEM."""
from dataclasses import replace
from hashlib import file_digest
from math import degrees

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget
from geokernel.globe_qt import GlobeWidget
from geokernel.globe_types import (
    GlobeAnalysisMode, GlobeAnalysisRequest, GlobeCamera, GlobeDemRequest,
    GlobeInteraction, GlobeMeasurementRequest, GlobeOptions, GlobePoint,
)
from common import DATA_DIR, application_icon, download_file, extract_zip


def prepare_terrain(app):
    name = "sagrada_familia_terrain"
    folder = DATA_DIR / name
    terrain = folder / f"{name}.tif"
    marker = folder / ".complete"
    if terrain.exists() and marker.exists():
        return terrain
    archive = DATA_DIR / f"{name}.zip"
    try:
        download_file(f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{name}.zip",
                      archive, app, "GlobeTerrainAnalysis")
        with archive.open("rb") as file:
            if file_digest(file, "sha256").hexdigest() != "69ed86c686b2500a70921920387afcb8993f3fe042e2a682932f86b7c6d5127c":
                raise RuntimeError("Terrain archive checksum mismatch.")
        extract_zip(archive, folder, app, "GlobeTerrainAnalysis")
        if not terrain.exists():
            raise FileNotFoundError(terrain)
        marker.write_text("1", encoding="utf-8")
        return terrain
    finally:
        archive.unlink(missing_ok=True)


class GlobeTerrainAnalysisWindow(QMainWindow):
    def __init__(self, terrain):
        super().__init__()
        self.terrain = terrain
        self.loaded = False
        self.analyzing = False
        self.mode = -1
        self.points = []
        self.job = None
        self.home = GlobeCamera(2.1744, 41.4036, 40, 2500, degrees(.85), degrees(.6))
        self.setWindowTitle("GeoKernel — Barcelona Terrain Analysis")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setMinimumSize(850, 550)
        self.view = GlobeWidget(self, camera=self.home,
                                options=GlobeOptions(network_enabled=True, atmosphere_enabled=True))
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setFixedHeight(170)
        self.result.setPlainText("Choose an analysis tool, then click the terrain. Drag to navigate; Esc cancels.")
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.result)
        self.setCentralWidget(central)
        self.toolbar = self.addToolBar("Analysis")
        self.toolbar.setMovable(False)
        self.toolbar.setEnabled(False)
        self.tools = []
        for mode, name in enumerate(("Line of sight", "Viewshed", "Slope / aspect", "Measure")):
            action = self.toolbar.addAction(name)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, selected=mode: self.select_mode(selected))
            self.tools.append(action)
        self.toolbar.addAction("Clear", self.clear_selection)
        self.toolbar.addAction("Barcelona", self.go_home)
        self.statusBar().setFixedHeight(24)
        self.statusBar().setSizeGripEnabled(False)
        self.report("Loading Barcelona terrain…")
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.tick)
        self.view.ready.connect(self.globe_ready)
        self.view.event_received.connect(self.on_globe_event)
        self.view.error.connect(self.report)

    def globe_ready(self):
        try:
            globe = self.view.globe
            esri = next((item.id for item in globe.get_basemaps() if item.name == "Esri Satellite"), -1)
            globe.set_basemap(esri)
            self.job = globe.load_dem(GlobeDemRequest("dem", str(self.terrain)))
            self.timer.start()
        except Exception as error:
            self.report(error)

    def tick(self):
        try:
            globe = self.view.globe
            if self.job is not None:
                state = globe.get_job_state(self.job)
                if state.status in ("queued", "running"):
                    return
                globe.forget_job(self.job)
                self.job = None
                if state.status != "completed":
                    raise RuntimeError(state.error or "Terrain loading cancelled.")
                stats = globe.get_layer_state("dem").statistics
                globe.set_dem_style(False, stats["minimum"], stats["maximum"])
                globe.options = replace(globe.options, terrain_enabled=True, terrain_exaggeration=1)
                globe.camera = self.home
                globe.set_home_camera(self.home)
                self.loaded = True
                self.toolbar.setEnabled(True)
                self.report(f"Barcelona | Real DEM | Terrain only | {globe.get_attribution()}")
            if self.analyzing:
                self.show_analysis()
        except Exception as error:
            self.timer.stop()
            self.result.setPlainText(str(error))
            self.report(error)

    def clear_selection(self):
        self.analyzing = False
        self.points.clear()
        self.mode = -1
        globe = self.view.globe
        globe.cancel_terrain_analysis()
        globe.clear_terrain_analysis()
        globe.clear_measurement()
        # ClearInteraction emits selectionFinished; avoid feeding that event back into itself.
        globe.set_interaction_mode(GlobeInteraction.NAVIGATE)
        for action in self.tools:
            action.setChecked(False)
        self.result.setPlainText("Selection cleared. Choose an analysis tool to select new points.")

    def select_mode(self, mode):
        self.clear_selection()
        self.mode = mode
        self.tools[mode].setChecked(True)
        self.view.globe.set_interaction_mode(GlobeInteraction.GROUND_SELECTION)
        self.result.setPlainText((
            "Line of sight: click observer and target within 10 km. Heights: 1.7 m above ground. Terrain only; buildings excluded.",
            "Viewshed: click an observer. Radius: 350 m; sample spacing: 15 m. Terrain only; buildings excluded.",
            "Slope / aspect: click a terrain point. Slope and downhill direction will appear here.",
            "Measure: click a start point, then an end point.",
        )[mode])

    def on_globe_event(self, event):
        if not self.loaded:
            return
        try:
            if event.type == "selectionFinished":
                self.clear_selection()
            elif event.type == "groundClicked" and self.mode >= 0:
                if not event.data.get("heightAvailable"):
                    self.result.setPlainText("DEM not loaded here. Wait for terrain or return to Barcelona and try again.")
                    return
                self.add_point(GlobePoint(event.data["longitude"], event.data["latitude"]))
        except Exception as error:
            self.result.setPlainText(str(error))

    def add_point(self, point):
        globe = self.view.globe
        required = 2 if self.mode in (0, 3) else 1
        if len(self.points) == required:
            self.analyzing = False
            globe.cancel_terrain_analysis()
            globe.clear_terrain_analysis()
            globe.clear_measurement()
            self.points.clear()
        if self.points:
            globe.set_measurement_points(GlobeMeasurementRequest((self.points[0], point)))
            distance = globe.get_measurement().distance_metres
            if distance < 1 or (self.mode == 0 and distance > 10000):
                globe.set_measurement_points(GlobeMeasurementRequest(tuple(self.points)))
                self.result.setPlainText("Choose a point at least 1 metre away." if distance < 1 else "Choose a target within 10 km.")
                return
        self.points.append(point)
        globe.set_measurement_points(GlobeMeasurementRequest(tuple(self.points)))
        if len(self.points) < required:
            self.result.setPlainText(f"Start/observer: {point.latitude:.6f}, {point.longitude:.6f}. Now click the end/target. Esc cancels.")
        elif self.mode == 3:
            self.result.setPlainText(f"Ground distance: {globe.get_measurement().distance_metres:.2f} m.\nClick to start a new measurement.")
        else:
            mode = (GlobeAnalysisMode.LINE_OF_SIGHT, GlobeAnalysisMode.VIEWSHED, GlobeAnalysisMode.SLOPE)[self.mode]
            globe.start_terrain_analysis(GlobeAnalysisRequest(mode, tuple(self.points), spacing_metres=15, radius_metres=350))
            self.analyzing = True
            self.show_analysis()

    def show_analysis(self):
        analysis = self.view.globe.get_terrain_analysis()
        self.analyzing = analysis.status == "calculating"
        if analysis.stale:
            self.result.setPlainText("Terrain changed while calculating. Wait for terrain loading to settle, then click to start a new selection. Previous results are no longer current.")
            return
        text = f"Status: {analysis.status}"
        if analysis.slope and analysis.slope.available:
            slope = analysis.slope
            aspect = (f"{slope.aspect_degrees:.1f}° clockwise from north (downhill)"
                      if slope.aspect_degrees is not None else "Undefined: flat terrain")
            text += f"\nSlope: {slope.degrees:.2f}° ({slope.percent:.2f}%)\nAspect: {aspect}"
        elif analysis.line_of_sight:
            los = analysis.line_of_sight
            text += (f"\nLine of sight: {los.outcome} | Distance: {los.length_metres:.1f} m"
                     f"\nSamples: {los.processed}/{los.total}; missing: {los.missing_samples}"
                     "\nThe map line marks the ground path, not the elevated sight ray.")
        elif analysis.viewshed:
            view = analysis.viewshed
            text += (f"\nVisible: {view.clear}; blocked: {view.blocked}; unknown: {view.unknown}"
                     f"\nProcessed: {view.processed}/{view.total} | Radius: 350 m")
        else:
            text += "\nResult unavailable; neighbouring DEM samples may be missing."
        if analysis.error:
            text += f"\n{analysis.error}"
        self.result.setPlainText(text + "\nTerrain only. Click to start a new selection; Esc cancels.")

    def go_home(self):
        self.view.globe.camera = self.home

    def report(self, message):
        self.statusBar().showMessage(str(message))
        self.statusBar().setToolTip(str(message))

    def closeEvent(self, event):
        self.timer.stop()
        self.loaded = False
        self.view.close_globe()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("GlobeTerrainAnalysis")
    app.setWindowIcon(application_icon())
    try:
        terrain = prepare_terrain(app)
    except Exception as error:
        QMessageBox.critical(None, "GlobeTerrainAnalysis", str(error))
        raise SystemExit(1)
    window = GlobeTerrainAnalysisWindow(terrain)
    window.show()
    raise SystemExit(app.exec())
