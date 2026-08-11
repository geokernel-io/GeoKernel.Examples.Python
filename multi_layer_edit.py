import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

VIEW_EXTENT = Extent(-135.0, 18.0, -55.0, 62.0)


class MultiLayerEditWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.red_layer = -1
        self.blue_layer = -1
        self.initialized = False
        self.setWindowTitle("MultiLayerEdit")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Multi-layer editing", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        red = toolbar.addAction("Active: Red Points")
        blue = toolbar.addAction("Active: Blue Points")
        commit = toolbar.addAction("Commit Both")
        rollback = toolbar.addAction("Rollback Both")
        full_extent = toolbar.addAction("Full Extent")
        toolbar.addSeparator()
        self.active_label = QLabel("Active edit layer: -", toolbar)
        toolbar.addWidget(self.active_label)
        red.triggered.connect(self.activate_red)
        blue.triggered.connect(self.activate_blue)
        commit.triggered.connect(self.commit_both)
        rollback.triggered.connect(self.rollback_both)
        full_extent.triggered.connect(self.show_extent)

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
                "MultiLayerEdit",
            )
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.viewer.set_layer_style(
                0, {"fillColor": "#D8E5E1", "lineColor": "#607D78"}
            )
            self.red_layer = self.viewer.add_empty_vector_layer(
                "Red Points",
                ShapeType.POINT,
                {"pointColor": "#DC2626", "pointSize": 9.0},
            )
            self.blue_layer = self.viewer.add_empty_vector_layer(
                "Blue Points",
                ShapeType.POINT,
                {"pointColor": "#2563EB", "pointSize": 9.0},
            )
            self.red_layer += 1
            self.begin_both()
            for index in range(7):
                self.viewer.add_point_to_edit_layer(
                    self.red_layer, -120 + index * 8, 38
                )
                self.viewer.add_point_to_edit_layer(
                    self.blue_layer, -120 + index * 8, 30
                )
            self.activate_red()
            self.show_extent()
        except Exception as error:
            QMessageBox.critical(self, "MultiLayerEdit", str(error))

    def begin_both(self) -> None:
        self.viewer.begin_edit_layer(self.red_layer)
        self.viewer.begin_edit_layer(self.blue_layer)

    def activate_layer(self, index: int, name: str) -> None:
        self.viewer.set_active_edit_layer_index(index)
        self.viewer.set_tool(ViewerTool.ADD_POINT)
        self.active_label.setText(f"Active edit layer: {name}")
        self.statusBar().showMessage(f"Click the map to add to {name}.")

    def activate_red(self) -> None:
        self.activate_layer(self.red_layer, "Red Points")

    def activate_blue(self) -> None:
        self.activate_layer(self.blue_layer, "Blue Points")

    def commit_both(self) -> None:
        self.viewer.commit_edit_layer(self.red_layer)
        self.viewer.commit_edit_layer(self.blue_layer)
        self.begin_both()
        self.statusBar().showMessage("Both edit sessions committed and reopened.")

    def rollback_both(self) -> None:
        self.viewer.rollback_edit_layer(self.red_layer)
        self.viewer.rollback_edit_layer(self.blue_layer)
        self.begin_both()
        self.viewer.refresh_layers()
        self.statusBar().showMessage("Both edit sessions rolled back and reopened.")

    def show_extent(self) -> None:
        self.viewer.set_view_extent(VIEW_EXTENT)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = MultiLayerEditWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
