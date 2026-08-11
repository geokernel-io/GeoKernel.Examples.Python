import sys
from pathlib import Path
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QWidget,
)
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

class ClickHitTestWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer_widget = self.viewer.qt_widget()
        self.icons = Path(__file__).with_name("images")
        self.initialized = False
        self.results = QTableWidget(0, 5, self)
        self.results.setHorizontalHeaderLabels(
            ["#", "Layer", "Shape", "Feature", "Type"]
        )
        self.setWindowTitle("ClickHitTest")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self._build_ui()
        self.viewer.set_event_callback(self._on_viewer_event)
        self.viewer.set_tool(ViewerTool.INFO)

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.viewer_widget, 3)
        layout.addWidget(self.results, 1)
        self.setCentralWidget(root)
        toolbar = QToolBar("Selection", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(28, 28))
        self.addToolBar(toolbar)
        inspect_action = QAction(
            QIcon(str(self.icons / "Identify.svg")),
            "Inspect",
            self,
        )
        inspect_action.triggered.connect(self.activate_inspect)
        toolbar.addAction(inspect_action)
        pan_action = QAction(QIcon(str(self.icons / "Pan.svg")), "Pan", self)
        pan_action.triggered.connect(self.activate_pan)
        toolbar.addAction(pan_action)
        extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.svg")),
            "Full Extent",
            self,
        )
        extent_action.triggered.connect(self.viewer.full_extent)
        toolbar.addAction(extent_action)

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
                "Click the map to inspect the top-most feature."
            )
        except Exception as error:
            QMessageBox.critical(self, "ClickHitTest", str(error))

    def _sample(self, zip_name: str, folder: str, filename: str):
        return ensure_sample_file(
            app=self.app,
            zip_url=f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{zip_name}",
            zip_name=zip_name,
            target_folder=folder,
            required_file=filename,
            title="ClickHitTest",
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
            path = self._sample(zip_name, folder, filename)
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_name(0, name)
            self.viewer.set_layer_style(0, style)

    def activate_inspect(self) -> None:
        self.viewer.set_tool(ViewerTool.INFO)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def _on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.MAP_MOUSE_UP:
            return
        x = event.screen_rectangle.left
        y = event.screen_rectangle.top
        hits = self._query_hits(x, y)
        self._show_hits(hits)

    def _query_hits(self, x: int, y: int):
        hit = self.viewer.hit_test_top_feature_at(x, y, 8)
        if hit:
            self.viewer.select_top_feature_at(x, y, 8)
        else:
            self.viewer.clear_selected_features()
        return [hit] if hit else []

    def _show_hits(self, hits) -> None:
        valid_hits = [hit for hit in hits if hit]
        self.results.setRowCount(len(valid_hits))
        for row, hit in enumerate(valid_hits):
            values = [
                row + 1,
                hit.get("layerName", hit.get("layer", "")),
                hit.get("shapeId", ""),
                hit.get("featureId", ""),
                hit.get("shapeType", hit.get("type", "")),
            ]
            for column, value in enumerate(values):
                self.results.setItem(row, column, QTableWidgetItem(str(value)))
        self.statusBar().showMessage(f"{len(valid_hits)} feature hit(s).")

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass

        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ClickHitTest")
    app.setWindowIcon(application_icon())
    window = ClickHitTestWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
