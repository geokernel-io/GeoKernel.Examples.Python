import sys
import time

from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from geokernel import Viewer, ViewerEventType, ViewerTool

from common import application_icon, ensure_sample_file


SAMPLE_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/output_1m_points.zip"
LOAD_OPTIONS = {
    "useSpatialIndex": True,
    "spatialIndexType": 1,
    "buildFeatureSource": True,
    "applyDefaultStyle": True,
    "defaultStyle": {
        "pointColor": "#2D82B7",
        "pointSize": 2.8,
        "lineColor": "#1C5D87",
        "lineWidth": 0.8,
    },
}


class BusyCallbackWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.loading = False

        self.load_button = QPushButton("Load Large Layer", self)
        self.clear_button = QPushButton("Clear Layers", self)
        self.busy_label = QLabel("Busy: OFF", self)
        self.event_log = QTextEdit(self)
        self.event_log.setReadOnly(True)
        self.event_log.setMinimumWidth(360)
        self.status_label = QLabel(
            "Ready. Click Load Large Layer to see busy/progress callbacks.", self
        )
        self.progress_bar = QProgressBar(self)

        self.setWindowTitle("BusyCallback")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_layout()
        self.connect_signals()
        self.append_log("Sample ready. API: BUSY_CHANGED + layer-load callbacks.")

    def create_layout(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addWidget(self.load_button)
        toolbar_layout.addWidget(self.clear_button)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.busy_label)
        toolbar_layout.addStretch(1)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.viewer_widget, 1)
        content_layout.addWidget(self.event_log)

        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(6, 3, 6, 3)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(220)
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.progress_bar)

        root_layout.addLayout(toolbar_layout)
        root_layout.addLayout(content_layout, 1)
        root_layout.addLayout(status_layout)
        self.setCentralWidget(root)

    def connect_signals(self) -> None:
        self.load_button.clicked.connect(self.load_large_layer)
        self.clear_button.clicked.connect(self.clear_layers)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()

    def load_large_layer(self) -> None:
        if self.loading:
            return

        self.set_loading(True)
        try:
            path = ensure_sample_file(
                self.app,
                SAMPLE_URL,
                "output_1m_points.zip",
                "output_1m_points",
                "output_1m_points.shp",
                "BusyCallback",
            )

            self.set_progress(0)
            self.set_status("Loading output_1m_points.shp...")
            self.append_log("Action: add_layer_file_with_callbacks(output_1m_points.shp)")
            started = time.perf_counter()
            self.viewer.clear_layers()
            loaded = self.viewer.add_layer_file_with_callbacks(
                path,
                LOAD_OPTIONS,
                progress=self.on_load_progress,
                spatial_index_state_changed=self.on_spatial_index_state_changed,
            )
            if not loaded:
                raise RuntimeError("Layer load was cancelled.")

            self.viewer.set_layer_name(0, "One Million Points")
            self.viewer.full_extent()
            elapsed = int((time.perf_counter() - started) * 1000)
            self.set_progress(100)
            self.set_status(f"Layer loaded in {elapsed} ms.")
            self.append_log(f"Result: loaded in {elapsed} ms")
        except Exception as error:
            self.set_progress(0)
            self.set_status("Layer load failed.")
            self.append_log("Result: load failed")
            QMessageBox.critical(self, "BusyCallback", f"Layer could not be loaded:\n{error}")
        finally:
            self.set_loading(False)

    def on_load_progress(self, percent: int, message: str) -> None:
        self.set_progress(percent)
        if message:
            self.set_status(message)

    def on_spatial_index_state_changed(self, state: int) -> None:
        states = {
            0: "Spatial index idle.",
            1: "Spatial index loading...",
            2: "Spatial locator preparing...",
            3: "Spatial index building...",
            4: "Spatial index ready.",
            5: "Spatial index cancelled.",
            6: "Spatial index failed.",
        }
        self.set_status(states.get(state, f"Spatial index state: {state}"))
        self.append_log(f"Callback: spatialIndexState={state}")

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.BUSY_CHANGED:
            busy = bool(event.int_value)
            self.busy_label.setText("Busy: ON" if busy else "Busy: OFF")
            self.append_log(f"Event: busyChanged({str(busy).lower()})")
        elif event.event_type == ViewerEventType.LAYER_ADDED:
            self.append_log(f"Event: layerAdded(index={event.int_value})")
        elif event.event_type == ViewerEventType.LAYERS_CHANGED:
            self.append_log(f"Event: layersChanged(count={self.viewer.layer_count()})")

    def clear_layers(self) -> None:
        if self.loading:
            return
        self.viewer.clear_layers()
        self.set_progress(0)
        self.set_status("Layers cleared.")
        self.append_log("Action: clear_layers()")

    def set_loading(self, loading: bool) -> None:
        self.loading = loading
        self.load_button.setEnabled(not loading)
        self.clear_button.setEnabled(not loading)
        if loading:
            self.setCursor(Qt.CursorShape.WaitCursor)
        else:
            self.unsetCursor()
        if not loading:
            self.busy_label.setText("Busy: OFF")

    def set_progress(self, value: int) -> None:
        self.progress_bar.setValue(max(0, min(100, value)))
        self.app.processEvents()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.app.processEvents()

    def append_log(self, text: str) -> None:
        timestamp = QTime.currentTime().toString("HH:mm:ss.zzz")
        self.event_log.append(f"{timestamp}  {text}")

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BusyCallback")
    app.setWindowIcon(application_icon())
    window = BusyCallbackWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
