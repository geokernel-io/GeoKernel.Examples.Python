import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 52.0)


class EditSessionWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_index = -1
        self.initialized = False
        self.setWindowTitle("EditSession")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Editing", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.full_extent_action = toolbar.addAction("Full Extent")
        self.add_point_action = toolbar.addAction("Add Point")
        self.pan_action = toolbar.addAction("Pan")
        self.commit_action = toolbar.addAction("Commit Edit")
        self.rollback_action = toolbar.addAction("Rollback Edit")
        toolbar.addSeparator()
        self.count_label = QLabel("Point count: 0", toolbar)
        toolbar.addWidget(self.count_label)
        self.full_extent_action.triggered.connect(self.show_sample_extent)
        self.add_point_action.triggered.connect(self.activate_add_point)
        self.pan_action.triggered.connect(self.activate_pan)
        self.commit_action.triggered.connect(self.commit_edit)
        self.rollback_action.triggered.connect(self.rollback_edit)

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
                "EditSession",
            )
            self.viewer.add_layer(str(world_path), {"buildFeatureSource": True})
            self.viewer.set_layer_style(0, self.world_style())
            self.layer_index = self.viewer.add_empty_vector_layer(
                "Editable Points", ShapeType.POINT, self.point_style()
            )
            if self.layer_index < 0 or not self.reopen_edit_session():
                raise RuntimeError("Editable point layer could not be created.")
            self.show_sample_extent()
            self.activate_pan()
            self.update_count()
        except Exception as error:
            QMessageBox.critical(self, "EditSession", str(error))

    def reopen_edit_session(self) -> bool:
        if not self.viewer.begin_edit_layer(self.layer_index):
            return False
        self.viewer.set_active_edit_layer_index(self.layer_index)
        return True

    def activate_add_point(self) -> None:
        if self.layer_index < 0:
            return
        if not self.viewer.is_layer_editing(self.layer_index):
            self.reopen_edit_session()
        self.viewer.set_active_edit_layer_index(self.layer_index)
        self.viewer.set_tool(ViewerTool.ADD_POINT)
        self.statusBar().showMessage("Add Point active. Click the map to add points.")

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan active.")

    def commit_edit(self) -> None:
        if self.layer_index >= 0 and self.viewer.commit_edit_layer(self.layer_index):
            self.reopen_edit_session()
            self.statusBar().showMessage("Edit session committed and reopened.")
        self.update_count()

    def rollback_edit(self) -> None:
        if self.layer_index >= 0 and self.viewer.rollback_edit_layer(self.layer_index):
            self.reopen_edit_session()
            self.viewer.refresh_layers()
            self.statusBar().showMessage("Edit session rolled back and reopened.")
        self.update_count()

    def show_sample_extent(self) -> None:
        self.viewer.set_view_extent(SAMPLE_EXTENT)

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            self.update_count()

    def update_count(self) -> None:
        count = (
            self.viewer.layer_feature_count(self.layer_index)
            if self.layer_index >= 0
            else 0
        )
        self.count_label.setText(f"Point count: {count}")

    @staticmethod
    def world_style() -> dict:
        return {"fillColor": "#D8E5E1", "lineColor": "#607D78", "lineWidth": 0.7}

    @staticmethod
    def point_style() -> dict:
        return {"pointColor": "#FF3B30", "pointSize": 9.0, "lineColor": "#FFFFFF"}

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = EditSessionWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
