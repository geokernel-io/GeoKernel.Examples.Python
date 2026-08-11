import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file


class BusyCallbackWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("BusyCallback")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        toolbar = QToolBar("Busy state", self)
        toolbar.setMovable(False)
        self.busy_label = QLabel("Busy: false", toolbar)
        toolbar.addWidget(self.busy_label)
        self.addToolBar(toolbar)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                "world_4326.zip",
                "world_4326",
                "world_4326.shp",
                "BusyCallback",
            )
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.viewer.set_layer_style(
                0, {"fillColor": "#D8E5E1", "lineColor": "#607D78"}
            )
            self.viewer.full_extent()
            self.statusBar().showMessage("BUSY_CHANGED callback is active.")
        except Exception as error:
            QMessageBox.critical(self, "BusyCallback", str(error))

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.BUSY_CHANGED:
            self.busy_label.setText(f"Busy: {bool(event.int_value)}")

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = BusyCallbackWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
