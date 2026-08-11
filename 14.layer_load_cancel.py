import sys
import time
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file

INDEX_STATES = {0: "Spatial index idle.", 1: "Spatial index is loading...", 2: "Feature locators are preparing...", 3: "Spatial index is building...", 4: "Spatial index is ready.", 5: "Load cancelled while preparing spatial index.", 6: "Spatial index failed."}

class LayerLoadCancelWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.cancelled = False
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.load_button = QPushButton("Load Large Layer", self)
        self.cancel_button = QPushButton("Cancel", self)
        self.clear_button = QPushButton("Clear", self)
        self.status_label = QLabel("Press Load Large Layer, then Cancel while loading.", self)
        self.progress = QProgressBar(self)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("LayerLoadCancel")
        self.resize(1200, 800)
        self.create_layout()
        self.connect_signals()

    def create_layout(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        self.cancel_button.setEnabled(False)
        controls.addWidget(self.load_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.clear_button)
        controls.addStretch(1)
        status_row = QHBoxLayout()
        self.progress.setRange(0, 100)
        self.progress.setFixedWidth(220)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.progress)
        layout.addLayout(controls)
        layout.addWidget(self.viewer_widget, 1)
        layout.addLayout(status_row)
        self.setCentralWidget(root)

    def connect_signals(self) -> None:
        self.load_button.clicked.connect(self.load_large_layer)
        self.cancel_button.clicked.connect(self.request_cancel)
        self.clear_button.clicked.connect(self.clear_layers)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()

    def request_cancel(self) -> None:
        self.cancelled = True
        self.status_label.setText("Cancel requested...")

    def clear_layers(self) -> None:
        self.cancelled = False
        self.viewer.clear_layers()
        self.progress.setValue(0)
        self.load_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Layers cleared.")

    def report_progress(self, value: int, message: str) -> None:
        self.progress.setValue(max(0, min(100, value)))
        if message:
            self.status_label.setText(message)
        self.app.processEvents()

    def is_cancelled(self) -> bool:
        self.app.processEvents()
        return self.cancelled

    def spatial_index_state_changed(self, state: int) -> None:
        self.status_label.setText(INDEX_STATES.get(state, f"Spatial index state: {state}"))

    def load_large_layer(self) -> None:
        self.cancelled = False
        self.load_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        self.status_label.setText("Preparing sample data...")
        self.app.processEvents()
        try:
            path = ensure_sample_file(app=self.app, zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/output_1m_points.zip", zip_name="output_1m_points.zip", target_folder="output_1m_points", required_file="output_1m_points.shp", title="LayerLoadCancel")
            self.viewer.clear_layers()
            started = time.perf_counter()
            loaded = self.viewer.add_layer_file_with_callbacks(path, {"useSpatialIndex": True, "spatialIndexType": 1, "buildFeatureSource": True, "applyDefaultStyle": True, "defaultStyle": {"fillColor": "#D8E5E1", "fillOpacity": 210, "lineColor": "#607D78", "lineWidth": 0.9}}, progress=self.report_progress, is_cancelled=self.is_cancelled, spatial_index_state_changed=self.spatial_index_state_changed)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if not loaded:
                self.progress.setValue(0)
                self.status_label.setText(f"Layer load cancelled after {elapsed_ms} ms.")
            else:
                self.viewer.set_layer_name(0, "One Million Points")
                self.viewer.full_extent()
                self.progress.setValue(100)
                self.status_label.setText(f"Layer loaded in {elapsed_ms} ms.")
        except Exception as error:
            QMessageBox.critical(self, "LayerLoadCancel", f"Layer could not be loaded:\n\n{error}")
        finally:
            self.cancel_button.setEnabled(False)
            self.load_button.setEnabled(True)

    def closeEvent(self, event) -> None:
        self.cancelled = True
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("LayerLoadCancel")
    app.setWindowIcon(icon)
    window = LayerLoadCancelWindow(app)
    window.show()
    window.initialize_viewer()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
