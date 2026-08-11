import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 52.0)

class CancelEditSketchWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_index = -1
        self.initialized = False
        self.setWindowTitle("CancelEditSketch")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Editing", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        full_extent = toolbar.addAction("Full Extent")
        add_polygon = toolbar.addAction("Add Polygon")
        pan = toolbar.addAction("Pan")
        cancel = toolbar.addAction("Cancel Sketch")
        toolbar.addSeparator()
        toolbar.addWidget(
            QLabel("Start a polygon, then cancel the unfinished sketch.", toolbar)
        )
        full_extent.triggered.connect(self.show_sample_extent)
        add_polygon.triggered.connect(self.activate_add_polygon)
        pan.triggered.connect(self.activate_pan)
        cancel.triggered.connect(self.cancel_sketch)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            world_path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                "world_4326.zip",
                "world_4326",
                "world_4326.shp",
                "CancelEditSketch",
            )
            self.viewer.add_layer(str(world_path), {"buildFeatureSource": True})
            self.viewer.set_layer_style(
                0, {"fillColor": "#D8E5E1", "lineColor": "#607D78"}
            )
            self.layer_index = self.viewer.add_empty_vector_layer(
                "Sketch Polygons",
                ShapeType.POLYGON,
                {
                    "fillColor": "#F4A261",
                    "fillOpacity": 140,
                    "lineColor": "#E4572E",
                    "lineWidth": 2.5,
                },
            )
            if self.layer_index < 0 or not self.viewer.begin_edit_layer(
                self.layer_index
            ):
                raise RuntimeError("Editable polygon layer could not be created.")
            self.viewer.set_active_edit_layer_index(self.layer_index)
            self.show_sample_extent()
            self.activate_pan()
        except Exception as error:
            QMessageBox.critical(self, "CancelEditSketch", str(error))

    def activate_add_polygon(self) -> None:
        if self.layer_index < 0:
            return
        self.viewer.set_active_edit_layer_index(self.layer_index)
        self.viewer.set_tool(ViewerTool.ADD_POLYGON)
        self.statusBar().showMessage(
            "Add Polygon active. Click vertices without finishing the sketch."
        )

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan active.")

    def cancel_sketch(self) -> None:
        self.viewer.cancel_edit_sketch()
        self.statusBar().showMessage("Active edit sketch cancelled.")

    def show_sample_extent(self) -> None:
        self.viewer.set_view_extent(SAMPLE_EXTENT)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = CancelEditSketchWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
