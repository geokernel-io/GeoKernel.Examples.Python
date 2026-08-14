import sys
from pathlib import Path
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLabel, QMainWindow, QMessageBox, QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

class WorldToleranceWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer_widget = self.viewer.qt_widget()
        self.icons = Path(__file__).with_name("images")
        self.initialized = False
        self.label = QLabel("Click map with world-coordinate tolerance.", self)
        self.results = QTableWidget(0, 5, self)
        self.tolerance = QDoubleSpinBox(self)
        self.setWindowTitle("WorldTolerance")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self._build_ui()
        self.viewer.set_event_callback(self._on_event)
        self.viewer.set_tool(ViewerTool.INFO)

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QToolBar("Tools", self)
        bar.setMovable(False)
        bar.setIconSize(QSize(32, 32))
        layout.addWidget(bar)

        inspect_action = QAction(
            QIcon(str(self.icons / "Identify.png")),
            "World Tolerance Hit Test",
            self,
        )
        inspect_action.triggered.connect(self.activate_select)
        bar.addAction(inspect_action)

        pan_action = QAction(QIcon(str(self.icons / "Pan.png")), "Pan", self)
        pan_action.triggered.connect(self.activate_pan)
        bar.addAction(pan_action)

        extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.png")),
            "Full Extent",
            self,
        )
        extent_action.triggered.connect(self.viewer.full_extent)
        bar.addAction(extent_action)

        self.tolerance.setDecimals(2)
        self.tolerance.setRange(0.0, 10.0)
        self.tolerance.setSingleStep(0.25)
        self.tolerance.setValue(1.0)
        self.tolerance.setSuffix(" deg")
        bar.addWidget(QLabel("World tolerance:", self))
        bar.addWidget(self.tolerance)
        bar.addWidget(self.label)
        self.results.setHorizontalHeaderLabels(
            ["#", "Layer", "Shape", "Feature", "Type"]
        )
        layout.addWidget(self.viewer_widget, 4)
        layout.addWidget(self.results, 1)
        self.setCentralWidget(root)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.viewer.resize(
            self.viewer_widget.width(),
            self.viewer_widget.height(),
        )
        self.viewer.show()

        try:
            self._load_layers()
            self.viewer.set_view_extent(Extent(-130.0, 22.0, -65.0, 55.0))
            self.statusBar().showMessage(
                "Click the map to call hitTestFeatures with world tolerance."
            )
        except Exception as error:
            QMessageBox.critical(self, "WorldTolerance", str(error))

    def _sample(self, zip_name: str, folder: str, filename: str):
        return ensure_sample_file(
            app=self.app,
            zip_url=f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{zip_name}",
            zip_name=zip_name,
            target_folder=folder,
            required_file=filename,
            title="WorldTolerance",
        )

    def _load_layers(self) -> None:
        samples = [
            (
                "world_4326.zip",
                "world_4326",
                "world_4326.shp",
                "World",
                {"fillColor": "#D8E5E1", "lineColor": "#708984"},
            ),
            (
                "usa_states.zip",
                "usa_states",
                "usa_states.shp",
                "States",
                {"fillColor": "#C7DEE7", "fillOpacity": 160, "lineColor": "#2D6F8E"},
            ),
            (
                "world_cities_4326.zip",
                "world_cities_4326",
                "world_cities_4326.shp",
                "Cities",
                {"pointColor": "#D95D39", "pointSize": 8.0},
            ),
        ]
        for zip_name, folder, filename, name, style in samples:
            self.viewer.add_layer(str(self._sample(zip_name, folder, filename)))
            self.viewer.set_layer_name(0, name)
            self.viewer.set_layer_style(0, style)

    def activate_select(self) -> None:
        self.viewer.set_tool(ViewerTool.INFO)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def clear_selection(self) -> None:
        self.viewer.clear_selected_features()

    def zoom_selection(self) -> None:
        self.viewer.zoom_to_selected_features()

    def _on_event(self, event) -> None:
        if event.event_type != ViewerEventType.MAP_MOUSE_UP:
            return

        if self.viewer.get_tool() != ViewerTool.INFO:
            return

        hits = self.viewer.hit_test_features(
            event.extent.x_min,
            event.extent.y_min,
            self.tolerance.value(),
        )
        if hits:
            self.viewer.select_top_feature_at(
                event.screen_rectangle.left,
                event.screen_rectangle.top,
                8,
            )
        else:
            self.viewer.clear_selected_features()
        self._show_hits(hits)

    def _show_hits(self, hits) -> None:
        valid = [hit for hit in hits if hit]
        self.results.setRowCount(len(valid))
        for row, hit in enumerate(valid):
            values = [
                row + 1,
                hit.get("layerName", hit.get("layer", "")),
                hit.get("shapeId", ""),
                hit.get("featureId", ""),
                hit.get("shapeType", hit.get("type", "")),
            ]
            for column, value in enumerate(values):
                self.results.setItem(row, column, QTableWidgetItem(str(value)))
        self.statusBar().showMessage(
            f"{len(valid)} feature hit(s) with tolerance "
            f"{self.tolerance.value():.2f} degrees."
        )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass

        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WorldTolerance")
    app.setWindowIcon(application_icon())
    window = WorldToleranceWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
