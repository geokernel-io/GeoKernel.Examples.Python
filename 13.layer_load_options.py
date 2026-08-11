import sys
import time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget
from geokernel import Extent, SpatialIndexType, Viewer, ViewerTool
from common import ensure_sample_file

VIEW_EXTENT = Extent(-16831516.0, 1856556.0, -4631023.0, 7472472.0)
DEFAULT_STYLE = {"fillColor": "#D8E5E1", "fillOpacity": 210, "lineColor": "#607D78", "lineWidth": 0.9}

class LayerLoadOptionsWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.sample_path = None
        self.mode = None
        self.load_linear_button = QPushButton("Load Without Index", self)
        self.load_rtree_button = QPushButton("Load With RTree", self)
        self.query_button = QPushButton("Run Query Test", self)
        self.clear_button = QPushButton("Clear Layers", self)
        self.no_index_result = QLabel("No Index: -", self)
        self.rtree_result = QLabel("RTree: -", self)
        self.status_label = QLabel("Prepare the USA states sample.", self)
        self.progress = QProgressBar(self)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("LayerLoadOptions")
        self.resize(1200, 800)
        self.create_layout()
        self.connect_signals()

    def create_layout(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        options_layout = QHBoxLayout()
        options_layout.setContentsMargins(6, 4, 6, 4)
        for button in (self.load_linear_button, self.load_rtree_button, self.query_button, self.clear_button):
            options_layout.addWidget(button)
        options_layout.addStretch(1)
        results_layout = QHBoxLayout()
        results_layout.setContentsMargins(6, 2, 6, 4)
        results_layout.addWidget(self.no_index_result)
        results_layout.addWidget(self.rtree_result)
        results_layout.addStretch(1)
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(6, 3, 6, 3)
        self.progress.setRange(0, 100)
        self.progress.setFixedWidth(220)
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.progress)
        layout.addLayout(options_layout)
        layout.addLayout(results_layout)
        layout.addWidget(self.viewer_widget, 1)
        layout.addLayout(status_layout)
        self.setCentralWidget(root)

    def connect_signals(self) -> None:
        self.load_linear_button.clicked.connect(self.load_without_index)
        self.load_rtree_button.clicked.connect(self.load_with_rtree)
        self.query_button.clicked.connect(self.run_query_test)
        self.clear_button.clicked.connect(self.clear_layers)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            self.sample_path = ensure_sample_file(app=self.app, zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/usa_states_3857.zip", zip_name="usa_states_3857.zip", target_folder="usa_states_3857", required_file="usa_states_3857.shp", title="LayerLoadOptions")
            self.status_label.setText("USA states sample is ready.")
        except Exception as error:
            QMessageBox.critical(self, "LayerLoadOptions", f"Sample could not be prepared:\n\n{error}")

    def load_without_index(self) -> None:
        self.load_layer(False)

    def load_with_rtree(self) -> None:
        self.load_layer(True)

    def load_layer(self, use_rtree: bool) -> None:
        if self.sample_path is None:
            self.status_label.setText("Sample data is not ready.")
            return
        self.progress.setValue(0)
        self.status_label.setText("Loading USA states with RTree..." if use_rtree else "Loading USA states without spatial index...")
        self.app.processEvents()
        started = time.perf_counter()
        self.viewer.clear_layers()
        self.viewer.set_spatial_index_type(SpatialIndexType.RTREE if use_rtree else SpatialIndexType.LINEAR)
        self.viewer.add_layer(self.sample_path, {"useSpatialIndex": use_rtree, "spatialIndexType": int(SpatialIndexType.RTREE), "buildFeatureSource": True, "applyDefaultStyle": True, "defaultStyle": DEFAULT_STYLE})
        self.viewer.set_layer_name(0, "USA States - RTree" if use_rtree else "USA States - No Index")
        self.viewer.set_layer_style(0, DEFAULT_STYLE)
        self.viewer.set_view_extent(VIEW_EXTENT)
        elapsed = int((time.perf_counter() - started) * 1000)
        self.progress.setValue(100)
        self.mode = "rtree" if use_rtree else "linear"
        self.status_label.setText(f"{'RTree' if use_rtree else 'No-index'} layer loaded. Load time: {elapsed} ms.")

    def run_query_test(self) -> None:
        if self.viewer.layer_count() == 0 or self.mode is None:
            self.status_label.setText("Load a vector layer first.")
            return
        extent = self.viewer.layer_projected_extent(0)
        if extent is None:
            self.status_label.setText("Layer extent is empty.")
            return
        rows, columns, passes = 5, 8, 6
        step_x = (extent.x_max - extent.x_min) / columns
        step_y = (extent.y_max - extent.y_min) / rows
        total_queries = rows * columns * passes
        total_hits = completed = 0
        started = time.perf_counter()
        for _pass in range(passes):
            for row in range(rows):
                for column in range(columns):
                    x_min = extent.x_min + column * step_x
                    y_min = extent.y_min + row * step_y
                    total_hits += len(self.viewer.hit_test_features_in_extent(x_min, y_min, x_min + step_x * 0.65, y_min + step_y * 0.65))
                    completed += 1
                    if completed % 16 == 0:
                        self.progress.setValue(completed * 100 // total_queries)
                        self.app.processEvents()
        elapsed = int((time.perf_counter() - started) * 1000)
        text = f"{'RTree' if self.mode == 'rtree' else 'No Index'}: query {elapsed} ms, {total_queries} queries, {total_hits} hits"
        (self.rtree_result if self.mode == "rtree" else self.no_index_result).setText(text)
        self.progress.setValue(100)
        self.status_label.setText(f"Query test finished: {total_queries} queries, {total_hits} hits, {elapsed} ms.")

    def clear_layers(self) -> None:
        self.viewer.clear_layers()
        self.mode = None
        self.progress.setValue(0)
        self.no_index_result.setText("No Index: -")
        self.rtree_result.setText("RTree: -")
        self.status_label.setText("Layers cleared.")

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("LayerLoadOptions")
    app.setWindowIcon(icon)
    window = LayerLoadOptionsWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
