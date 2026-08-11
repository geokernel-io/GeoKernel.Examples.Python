import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 52.0)


class EditAndSaveWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_index = -1
        self.initialized = False
        self.setWindowTitle("EditAndSave")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Editing", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        full_extent = toolbar.addAction("Full Extent")
        add_point = toolbar.addAction("Add Point")
        pan = toolbar.addAction("Pan")
        save = toolbar.addAction("Save As Shapefile")
        reset = toolbar.addAction("Reset Working Copy")
        toolbar.addSeparator()
        self.count_label = QLabel("Point count: 0", toolbar)
        toolbar.addWidget(self.count_label)
        full_extent.triggered.connect(self.show_sample_extent)
        add_point.triggered.connect(self.activate_add_point)
        pan.triggered.connect(self.activate_pan)
        save.triggered.connect(self.save_layer)
        reset.triggered.connect(self.reset_working_copy)

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
                "EditAndSave",
            )
            self.viewer.add_layer(str(world_path), {"buildFeatureSource": True})
            self.viewer.set_layer_style(
                0, {"fillColor": "#D8E5E1", "lineColor": "#607D78"}
            )
            self.layer_index = self.viewer.add_empty_vector_layer(
                "Clicked Points",
                ShapeType.POINT,
                {"pointColor": "#E4572E", "pointSize": 9.0},
            )
            if self.layer_index < 0 or not self.reopen_edit_session():
                raise RuntimeError("Clicked Points layer could not be created.")
            self.show_sample_extent()
            self.activate_pan()
            self.update_count()
        except Exception as error:
            QMessageBox.critical(self, "EditAndSave", str(error))

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

    def save_layer(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save clicked points",
            str(Path.cwd() / "clicked_points.shp"),
            "Shapefile (*.shp)",
        )
        if not path:
            return
        if not self.viewer.commit_edit_layer(self.layer_index):
            QMessageBox.warning(
                self, "EditAndSave", "The edit session could not be committed."
            )
            return
        saved = self.viewer.save_layer_as_shapefile(self.layer_index, path)
        self.reopen_edit_session()
        if saved:
            self.statusBar().showMessage(f"Saved: {path}")
        else:
            QMessageBox.warning(self, "EditAndSave", "Layer could not be saved.")

    def reset_working_copy(self) -> None:
        if self.layer_index < 0:
            return
        if self.viewer.rollback_edit_layer(self.layer_index):
            self.reopen_edit_session()
            self.viewer.refresh_layers()
            self.update_count()
            self.statusBar().showMessage("Working copy reset.")

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

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = EditAndSaveWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
