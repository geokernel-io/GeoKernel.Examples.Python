import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QMessageBox, QTableWidget, QTableWidgetItem, QToolBar
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

class BoxSelectWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer_widget = self.viewer.qt_widget()
        self.icons = Path(__file__).with_name("images")
        self.initialized = False
        self.label = QLabel("Drag a box to inspect intersecting features.", self)
        self.results = QTableWidget(0, 5, self)
        self.setWindowTitle("BoxSelect")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self._build_ui()
        self.viewer.set_event_callback(self._on_event)
        self.viewer.set_tool(ViewerTool.SELECT)

    def _build_ui(self) -> None:
        self.setCentralWidget(self.viewer_widget)

        toolbar = QToolBar("Tools", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.select_action = QAction(
            QIcon(str(self.icons / "Select.png")),
            "Box Select",
            self,
        )
        self.select_action.setCheckable(True)
        self.select_action.setChecked(True)
        self.select_action.triggered.connect(self.activate_select)
        toolbar.addAction(self.select_action)

        self.pan_action = QAction(
            QIcon(str(self.icons / "Pan.png")),
            "Pan",
            self,
        )
        self.pan_action.setCheckable(True)
        self.pan_action.triggered.connect(self.activate_pan)
        toolbar.addAction(self.pan_action)

        clear_action = QAction(
            QIcon(str(self.icons / "Delete.png")),
            "Clear Selection",
            self,
        )
        clear_action.triggered.connect(self.clear_selection)
        toolbar.addAction(clear_action)

        full_extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.png")),
            "Full Extent",
            self,
        )
        full_extent_action.triggered.connect(self.viewer.full_extent)
        toolbar.addAction(full_extent_action)
        toolbar.addWidget(self.label)

        self.results.setHorizontalHeaderLabels(
            ["#", "Layer", "Shape", "Feature", "Type"]
        )
        results_dock = QDockWidget("Selected by box", self)
        results_dock.setWidget(self.results)
        results_dock.setMinimumWidth(340)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, results_dock)

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
                "Drag a box with Select to inspect intersecting features."
            )
        except Exception as error:
            QMessageBox.critical(self, "BoxSelect", str(error))

    def _sample(self, zip_name: str, folder: str, filename: str):
        return ensure_sample_file(
            app=self.app,
            zip_url=f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{zip_name}",
            zip_name=zip_name,
            target_folder=folder,
            required_file=filename,
            title="BoxSelect",
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
        self.select_action.setChecked(True)
        self.pan_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.SELECT)

    def activate_pan(self) -> None:
        self.select_action.setChecked(False)
        self.pan_action.setChecked(True)
        self.viewer.set_tool(ViewerTool.PAN)

    def clear_selection(self) -> None:
        self.viewer.clear_selected_features()
        self.results.setRowCount(0)
        self.statusBar().showMessage("Selection cleared.")

    def zoom_selection(self) -> None:
        self.viewer.zoom_to_selected_features()

    def _on_event(self, event) -> None:
        if event.event_type == ViewerEventType.MAP_SELECTION_BOX_FINISHED:
            rect = event.screen_rectangle
            self.viewer.select_features_in_screen_rect(
                rect.left,
                rect.top,
                rect.right,
                rect.bottom,
                0,
            )
            hits = self.viewer.selected_features()
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
        self.statusBar().showMessage(f"{len(valid)} feature(s) intersect the box.")

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass

        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BoxSelect")
    app.setWindowIcon(application_icon())
    window = BoxSelectWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
