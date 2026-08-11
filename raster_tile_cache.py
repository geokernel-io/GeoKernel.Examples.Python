import sys
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTextEdit,
    QToolBar,
)
from geokernel import Viewer, ViewerTool
from common import application_icon, ensure_sample_file

MODES = {
    "Cache Disabled": (False, 0, 0),
    "Small Cache Budget": (True, 128 * 1024, 128 * 1024),
    "Large Cache Budget": (True, 4 * 1024 * 1024, 1024 * 1024),
}


class RasterTileCacheWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.raster_path = None
        self.initialized = False
        self.setWindowTitle("RasterTileCache")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Raster cache", self)
        toolbar.setMovable(False)
        toolbar.addWidget(QLabel("Mode:", toolbar))
        self.mode_combo = QComboBox(toolbar)
        self.mode_combo.addItems(MODES)
        self.mode_combo.currentTextChanged.connect(self.load_raster)
        toolbar.addWidget(self.mode_combo)
        self.addToolBar(toolbar)
        self.details = QTextEdit(self)
        self.details.setReadOnly(True)
        dock = QDockWidget("Cache configuration", self)
        dock.setWidget(self.details)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            self.raster_path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_8km_tif.zip",
                "world_8km_tif.zip",
                "world_8km_tif",
                "world_8km.tif",
                "RasterTileCache",
            )
            self.load_raster()
        except Exception as error:
            QMessageBox.critical(self, "RasterTileCache", str(error))

    def load_raster(self) -> None:
        if self.raster_path is None:
            return
        enabled, budget, item = MODES[self.mode_combo.currentText()]
        self.viewer.clear_layers()
        started = time.perf_counter()
        index = self.viewer.add_layer(
            str(self.raster_path),
            {
                "prepareRasterOverviews": True,
                "rasterOverviewMinimumPixels": 0,
                "rasterTileCacheEnabled": enabled,
                "rasterTileCachePixelBudget": budget,
                "rasterTileCacheMaximumItemPixels": item,
            },
        )
        elapsed = (time.perf_counter() - started) * 1000
        self.details.setPlainText(
            f"Mode: {self.mode_combo.currentText()}\n"
            f"Layer index: {index}\n"
            f"rasterTileCacheEnabled={enabled}\n"
            f"rasterTileCachePixelBudget={budget}\n"
            f"rasterTileCacheMaximumItemPixels={item}\n"
            f"Load elapsed={elapsed:.1f} ms"
        )
        if index >= 0:
            self.viewer.zoom_to_layer(index)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = RasterTileCacheWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
