import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 52.0)
POINT_LAYER_NAME = "Clicked Points"

class AddPointInteractiveWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = Path(__file__).resolve().parent / "images"
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.point_layer_index = -1

        self.setWindowTitle("AddPointInteractive")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Editing", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.full_extent_action = self.create_action(
            "FullExtent.png", "Full Extent", self.show_sample_extent
        )
        self.add_point_action = self.create_action(
            "Point.png", "Add Point", self.activate_add_point, True
        )
        self.pan_action = self.create_action(
            "Pan.png", "Pan", self.activate_pan, True
        )
        self.clear_action = self.create_action(
            "Delete.png", "Clear Points", self.clear_points
        )

        self.tool_group.addAction(self.add_point_action)
        self.tool_group.addAction(self.pan_action)
        self.pan_action.setChecked(True)
        toolbar.addAction(self.full_extent_action)
        toolbar.addAction(self.add_point_action)
        toolbar.addAction(self.pan_action)
        toolbar.addAction(self.clear_action)
        toolbar.addSeparator()

        self.point_count_label = QLabel("Point count: 0", toolbar)
        toolbar.addWidget(self.point_count_label)

        self.full_extent_action.setEnabled(False)
        self.add_point_action.setEnabled(False)
        self.clear_action.setEnabled(False)

    def create_action(
        self,
        icon_name: str,
        text: str,
        callback,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(QIcon(str(self.icon_dir.joinpath(icon_name))), text, self)
        action.setToolTip(text)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        return action

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.statusBar().showMessage("Preparing world sample data...")

        try:
            world_path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="AddPointInteractive",
            )
            self.viewer.add_layer(str(world_path), {"buildFeatureSource": True})
            self.viewer.set_layer_name(0, "World")
            self.viewer.set_layer_style(0, self.world_style())

            self.point_layer_index = self.viewer.add_empty_vector_layer(
                POINT_LAYER_NAME,
                ShapeType.POINT,
                self.point_style(),
            )
            if self.point_layer_index < 0:
                raise RuntimeError("The editable point layer could not be created.")
            if not self.viewer.begin_edit_layer(self.point_layer_index):
                raise RuntimeError("The editable point layer could not be initialized.")

            self.viewer.set_active_edit_layer_index(self.point_layer_index)
            self.viewer.set_tool(ViewerTool.PAN)
            self.show_sample_extent()
            self.update_point_count()

            self.full_extent_action.setEnabled(True)
            self.add_point_action.setEnabled(True)
            self.clear_action.setEnabled(True)
            self.statusBar().showMessage(
                "Pan active. Choose Add Point, then click the map to add points."
            )
        except Exception as error:
            self.statusBar().showMessage("Editable point layer could not be initialized.")
            QMessageBox.critical(self, "AddPointInteractive", str(error))

    def activate_add_point(self) -> None:
        if self.point_layer_index < 0:
            return
        if not self.viewer.is_layer_editing(self.point_layer_index):
            self.viewer.begin_edit_layer(self.point_layer_index)
        self.viewer.set_active_edit_layer_index(self.point_layer_index)
        self.viewer.set_tool(ViewerTool.ADD_POINT)
        self.statusBar().showMessage("Add Point active. Click the map to add points.")

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan active.")

    def clear_points(self) -> None:
        if self.point_layer_index < 0:
            return
        if not self.viewer.rollback_edit_layer(self.point_layer_index):
            QMessageBox.warning(
                self,
                "AddPointInteractive",
                "The temporary points could not be cleared.",
            )
            return
        if not self.viewer.begin_edit_layer(self.point_layer_index):
            QMessageBox.warning(
                self,
                "AddPointInteractive",
                "The point edit session could not be restarted.",
            )
            return
        self.viewer.set_active_edit_layer_index(self.point_layer_index)
        self.viewer.invalidate_render_cache(False, True)
        self.viewer.refresh_layers()
        self.update_point_count()
        self.statusBar().showMessage("Clicked points cleared.")

    def show_sample_extent(self) -> None:
        self.viewer.set_view_extent(SAMPLE_EXTENT)

    def on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            return
        self.update_point_count()
        if self.add_point_action.isChecked():
            self.statusBar().showMessage(
                "Point layer updated. Click the map to add points."
            )

    def update_point_count(self) -> None:
        count = 0
        if self.point_layer_index >= 0:
            count = self.viewer.layer_feature_count(self.point_layer_index)
        self.point_count_label.setText(f"Point count: {count}")

    def world_style(self) -> dict:
        return {
            "fillColor": "#D8E5E1",
            "fillOpacity": 210,
            "lineColor": "#6F8883",
            "lineWidth": 0.7,
        }

    def point_style(self) -> dict:
        return {
            "pointColor": "#FF3B30",
            "lineColor": "#FFFFFF",
            "pointSize": 9.0,
            "lineWidth": 1.5,
        }

    def closeEvent(self, event) -> None:
        try:
            if (
                self.point_layer_index >= 0
                and self.viewer.is_layer_editing(self.point_layer_index)
            ):
                self.viewer.rollback_edit_layer(self.point_layer_index)
        except Exception:
            pass
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AddPointInteractive")
    app.setWindowIcon(application_icon())
    window = AddPointInteractiveWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
