"""GlobeTerrainNavigation with the published SDK's PySide6 Globe widget."""

from dataclasses import replace
from math import degrees

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from geokernel.globe_qt import GlobeWidget
from geokernel.globe_types import GlobeCamera, GlobeNavigation, GlobeOptions

from common import application_icon


class GlobeTerrainNavigationWindow(QMainWindow):
    HOME = GlobeCamera(2.1744, 41.4036, 40, 2500, degrees(0.65), 0)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GeoKernel — Terrain & Navigation")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setMinimumSize(640, 480)
        self.esri_id = -1

        # Match the Qt, WinForms and WPF Barcelona view with real terrain.
        self.view = GlobeWidget(
            self,
            camera=self.HOME,
            options=GlobeOptions(
                network_enabled=True,
                terrain_enabled=True,
                atmosphere_enabled=True,
                sunlight_enabled=True,
                terrain_max_zoom=14,
                terrain_lerc=True,
            ),
        )
        self.setCentralWidget(self.view)
        self.toolbar = self.addToolBar("Globe controls")
        self.toolbar.setMovable(False)
        self.toolbar.setEnabled(False)
        self.atmosphere = self.toolbar.addAction("Atmosphere")
        self.esri = self.toolbar.addAction("Esri Satellite")
        self.dem = self.toolbar.addAction("DEM")
        self.sunlight = self.toolbar.addAction("Sunlight")
        for action in (self.atmosphere, self.esri, self.dem, self.sunlight):
            action.setCheckable(True)
            action.triggered.connect(self.apply_options)
        self.esri.setToolTip("Esri World Imagery; internet required")
        self.dem.setToolTip("Esri Terrain3D elevation, 1x; internet required")
        self.addToolBarBreak()
        self.navigation = self.addToolBar("Navigation")
        self.navigation.setMovable(False)
        self.navigation.setEnabled(False)
        for text, command in (
            ("Zoom in", GlobeNavigation.ZOOM_IN),
            ("Zoom out", GlobeNavigation.ZOOM_OUT),
            ("Rotate left", GlobeNavigation.ROTATE_LEFT),
            ("Rotate right", GlobeNavigation.ROTATE_RIGHT),
            ("Tilt up", GlobeNavigation.TILT_UP),
            ("Tilt down", GlobeNavigation.TILT_DOWN),
            ("Top view", GlobeNavigation.TOP),
            ("North", GlobeNavigation.NORTH),
            ("Overview", GlobeNavigation.HOME),
        ):
            action = self.navigation.addAction(text)
            action.triggered.connect(
                lambda checked=False, command=command: self.view.globe.navigate(command)
            )
        self.statusBar().setFixedHeight(24)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("Preparing globe…")

        self.status_timer = QTimer(self)
        self.status_timer.setInterval(250)
        self.status_timer.timeout.connect(self.update_status)
        self.view.ready.connect(self.globe_ready)
        self.view.error.connect(self.show_error)

    def globe_ready(self):
        self.esri_id = next(
            (item.id for item in self.view.globe.get_basemaps() if item.name == "Esri Satellite"),
            -1,
        )
        self.view.globe.options = replace(self.view.globe.options, basemap=self.esri_id)
        self.view.globe.set_home_camera(self.HOME)
        self.toolbar.setEnabled(True)
        self.navigation.setEnabled(True)
        self.esri.setEnabled(self.esri_id >= 0)
        self.update_status()
        self.status_timer.start()

    def apply_options(self):
        self.view.globe.options = replace(
            self.view.globe.options,
            atmosphere_enabled=self.atmosphere.isChecked(),
            basemap=self.esri_id if self.esri.isChecked() else -1,
            terrain_enabled=self.dem.isChecked(),
            sunlight_enabled=self.sunlight.isChecked(),
        )
        self.update_status()

    def update_status(self):
        globe = self.view.globe
        options = globe.options
        self.atmosphere.setChecked(options.atmosphere_enabled)
        self.esri.setChecked(self.esri_id >= 0 and options.basemap == self.esri_id)
        self.dem.setChecked(options.terrain_enabled)
        self.sunlight.setChecked(options.sunlight_enabled)
        messages = []
        if options.basemap >= 0:
            messages.append(globe.get_attribution())
        if options.terrain_enabled:
            messages.append("Terrain: Esri / source contributors")
        messages.extend(error for error in globe.get_state().errors.values() if error)
        text = " | ".join(messages) if messages else "Left: pan | Right / wheel: zoom | Middle / Ctrl: orbit"
        self.statusBar().showMessage(text)
        self.statusBar().setToolTip(text)

    def show_error(self, error):
        self.status_timer.stop()
        self.toolbar.setEnabled(False)
        self.navigation.setEnabled(False)
        self.statusBar().showMessage(str(error))
        QMessageBox.critical(self, "Terrain & Navigation", str(error))

    def closeEvent(self, event):
        self.status_timer.stop()
        self.view.close_globe()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("GlobeTerrainNavigation")
    app.setWindowIcon(application_icon())
    window = GlobeTerrainNavigationWindow()
    window.show()
    raise SystemExit(app.exec())
