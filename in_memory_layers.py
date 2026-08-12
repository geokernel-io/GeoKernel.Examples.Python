import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerTool
from common import ensure_sample_file

POINT_STYLE = {"pointColor": "#D95F35", "pointSize": 7.0}
LINE_STYLE = {"lineColor": "#266D8F", "lineWidth": 2.2}
POLYGON_STYLE = {"fillColor": "#F1D58A", "fillOpacity": 150, "lineColor": "#9A7A1F", "lineWidth": 1.5}

def route(offset: float) -> list[tuple[float, float]]:
    return [(-122.4194 + offset, 37.7749), (-118.2437 + offset, 34.0522), (-112.0740 + offset, 33.4484), (-104.9903 + offset, 39.7392)]

def region(offset: float) -> list[tuple[float, float]]:
    return [(-101.0 + offset, 30.0), (-91.0 + offset, 30.0), (-89.0 + offset, 37.0), (-96.0 + offset, 42.0), (-103.0 + offset, 38.0), (-101.0 + offset, 30.0)]

def generated_point(index: int) -> tuple[float, float]:
    column, row = index % 12, index // 12
    return (-124.0 + column * 4.8 + (row % 3) * 0.35, 25.0 + row * 3.2 + (column % 4) * 0.25)

class InMemoryLayersWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_indices: dict[str, int] = {}
        self.point_counter, self.line_counter, self.polygon_counter = 0, 1, 1
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("InMemoryLayers")
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Memory Layers", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.add_point_action = toolbar.addAction("Add Point")
        self.add_line_action = toolbar.addAction("Add Line")
        self.add_polygon_action = toolbar.addAction("Add Polygon")
        toolbar.addSeparator()
        self.clear_action = toolbar.addAction("Clear Memory Layers")
        self.full_extent_action = toolbar.addAction("Full Extent")
        self.actions = (self.add_point_action, self.add_line_action, self.add_polygon_action, self.clear_action, self.full_extent_action)
        for action in self.actions:
            action.setEnabled(False)
        self.add_point_action.triggered.connect(self.add_point)
        self.add_line_action.triggered.connect(self.add_line)
        self.add_polygon_action.triggered.connect(self.add_polygon)
        self.clear_action.triggered.connect(self.reset_memory_layers)
        self.full_extent_action.triggered.connect(self.viewer.full_extent)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            path = ensure_sample_file(app=self.app, zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip", zip_name="world_4326.zip", target_folder="world_4326", required_file="world_4326.shp", title="InMemoryLayers")
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_name(0, "World")
            self.viewer.set_layer_style(0, {"fillColor": "#D8E5E1", "fillOpacity": 210, "lineColor": "#6F8883", "lineWidth": 0.7})
            self.create_memory_layers()
            for action in self.actions:
                action.setEnabled(True)
            self.update_status()
            self.viewer.set_view_extent(Extent(-130.0, 20.0, -65.0, 52.0))
        except Exception as error:
            QMessageBox.critical(self, "InMemoryLayers", f"Layers could not be created:\n\n{error}")

    def create_memory_layers(self) -> None:
        self.viewer.add_empty_vector_layer("Memory Regions", ShapeType.POLYGON, POLYGON_STYLE)
        self.viewer.add_empty_vector_layer("Memory Routes", ShapeType.POLYLINE, LINE_STYLE)
        self.viewer.add_empty_vector_layer("Memory Cities", ShapeType.POINT, POINT_STYLE)
        self.layer_indices = {"point": 0, "line": 1, "polygon": 2}
        for index in self.layer_indices.values():
            self.viewer.begin_edit_layer(index)
        self.viewer.add_polygon_to_edit_layer(2, region(0.0))
        self.viewer.add_polyline_to_edit_layer(1, route(0.0))
        self.viewer.add_point_to_edit_layer(0, -122.4194, 37.7749)
        self.viewer.add_point_to_edit_layer(0, -118.2437, 34.0522)
        self.viewer.refresh_layers()

    def add_point(self) -> None:
        point = generated_point(self.point_counter)
        self.point_counter += 1
        self.viewer.add_point_to_edit_layer(self.layer_indices["point"], *point)
        self.finish_edit_action()

    def add_line(self) -> None:
        self.viewer.add_polyline_to_edit_layer(self.layer_indices["line"], route(self.line_counter * 2.0))
        self.line_counter += 1
        self.finish_edit_action()

    def add_polygon(self) -> None:
        self.viewer.add_polygon_to_edit_layer(self.layer_indices["polygon"], region(self.polygon_counter * 5.0))
        self.polygon_counter += 1
        self.finish_edit_action()

    def finish_edit_action(self) -> None:
        self.viewer.refresh_layers()
        self.update_status()

    def reset_memory_layers(self) -> None:
        for name in ("Memory Cities", "Memory Routes", "Memory Regions"):
            self.viewer.remove_layer_by_name(name)
        self.point_counter, self.line_counter, self.polygon_counter = 0, 1, 1
        self.create_memory_layers()
        self.update_status()

    def update_status(self) -> None:
        self.statusBar().showMessage("Memory features - points: {} | lines: {} | polygons: {}".format(self.viewer.layer_feature_count(self.layer_indices["point"]), self.viewer.layer_feature_count(self.layer_indices["line"]), self.viewer.layer_feature_count(self.layer_indices["polygon"])))

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("InMemoryLayers")
    app.setWindowIcon(icon)
    window = InMemoryLayersWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
