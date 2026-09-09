import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QSpinBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

EXTENT = Extent(-132.0, 15.0, -55.0, 55.0)
POLYGON = [
    (-119, 28),
    (-109, 45),
    (-91, 42),
    (-83, 30),
    (-99, 22),
    (-115, 23.5),
    (-119, 28),
]

class DeleteVertexWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.EDIT_VERTICES)
        self.viewer.set_event_callback(self.on_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_index = -1
        self.initialized = False

        self.setWindowTitle("DeleteVertex")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Editing", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.edit_action = self.create_action(
            "Edit.png",
            "Edit Vertices",
            self.activate_edit,
            checkable=True,
        )
        self.select_action = self.create_action(
            "Select.png",
            "Select",
            self.activate_select,
            checkable=True,
        )
        toolbar.addAction(self.edit_action)
        toolbar.addAction(self.select_action)
        self.edit_action.setChecked(True)

        self.delete_active_action = self.create_action(
            "Delete.png",
            "Delete Selected Vertex",
            self.delete_selected_vertex,
        )
        self.delete_active_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        toolbar.addAction(self.delete_active_action)

        toolbar.addWidget(QLabel("Vertex index:", toolbar))
        self.vertex_spin = QSpinBox(toolbar)
        self.vertex_spin.setRange(0, 5)
        self.vertex_spin.setValue(2)
        toolbar.addWidget(self.vertex_spin)

        self.delete_index_action = self.create_action(
            "Delete.png",
            "Delete By Index",
            self.delete_by_index,
        )
        self.reset_action = self.create_action(
            "Refresh.png",
            "Reset Shape",
            self.reset_shape,
        )
        self.full_extent_action = self.create_action(
            "FullExtent.png",
            "Full Extent",
            self.viewer.full_extent,
        )

        toolbar.addAction(self.delete_index_action)
        toolbar.addAction(self.reset_action)
        toolbar.addAction(self.full_extent_action)

        self.data_actions = (
            self.delete_active_action,
            self.delete_index_action,
            self.reset_action,
            self.full_extent_action,
        )
        for action in self.data_actions:
            action.setEnabled(False)

    def create_action(
        self,
        icon_name: str,
        text: str,
        callback,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(QIcon(str(self.icons / icon_name)), text, self)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        return action

    def initialize_viewer(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()

        try:
            world_path = ensure_sample_file(
                app=self.app,
                zip_url=(
                    "https://github.com/geokernel-io/GeoKernel.SampleData/"
                    "releases/download/v1/world_4326.zip"
                ),
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="DeleteVertex",
            )

            self.viewer.add_layer(str(world_path))
            self.viewer.set_layer_style(
                0,
                {
                    "fillColor": "#D8E5E1",
                    "fillOpacity": 150,
                    "lineColor": "#6F8883",
                },
            )
            self.layer_index = self.viewer.add_empty_vector_layer(
                "Delete Target",
                ShapeType.POLYGON,
                {
                    "fillColor": "#F2D27A",
                    "fillOpacity": 160,
                    "lineColor": "#D95D39",
                    "lineWidth": 2.0,
                },
            )
            self.reset_shape()

            for action in self.data_actions:
                action.setEnabled(True)

            self.viewer.set_view_extent(EXTENT)
            self.statusBar().showMessage(
                "Use Edit Vertices for active vertex delete, or Select + index "
                "for direct API delete."
            )
        except Exception as error:
            QMessageBox.critical(self, "DeleteVertex", str(error))

    def begin_edit(self) -> bool:
        if self.layer_index < 0:
            return False

        if not self.viewer.is_layer_editing(self.layer_index):
            if not self.viewer.begin_edit_layer(self.layer_index):
                return False

        return self.viewer.set_active_edit_layer_index(self.layer_index)

    def reset_shape(self) -> None:
        if self.layer_index < 0:
            return

        if self.viewer.is_layer_editing(self.layer_index):
            self.viewer.rollback_edit_layer(self.layer_index)

        if not self.begin_edit():
            return

        self.viewer.add_polygon_to_edit_layer(
            self.layer_index,
            POLYGON,
            {"Name": "Delete target"},
        )
        self.viewer.clear_selected_features()
        self.viewer.set_tool(ViewerTool.EDIT_VERTICES)
        self.edit_action.setChecked(True)
        self.select_action.setChecked(False)
        self.vertex_spin.setRange(0, 5)
        self.vertex_spin.setValue(2)
        self.refresh_viewer()
        self.statusBar().showMessage(
            "Shape reset. Click a vertex or select the polygon."
        )

    def activate_edit(self) -> None:
        self.edit_action.setChecked(True)
        self.select_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.EDIT_VERTICES)

    def activate_select(self) -> None:
        self.edit_action.setChecked(False)
        self.select_action.setChecked(True)
        self.viewer.set_tool(ViewerTool.INFO)

    def on_event(self, event) -> None:
        if event.event_type != ViewerEventType.MAP_MOUSE_UP:
            return

        if not self.select_action.isChecked():
            return

        x = event.screen_rectangle.left
        y = event.screen_rectangle.top
        hit = self.viewer.hit_test_top_feature_at(x, y, 8)

        if not hit or hit.get("layerIndex") != self.layer_index:
            self.viewer.clear_selected_features()
            self.statusBar().showMessage("No editable polygon selected.")
            return

        if self.viewer.select_top_feature_at(x, y, 8):
            self.statusBar().showMessage(
                f"Selected feature {hit.get('featureId')}."
            )

    def delete_selected_vertex(self) -> None:
        if self.viewer.delete_selected_vertex_from_edit_layer():
            self.refresh_viewer()
            self.statusBar().showMessage(
                "deleteSelectedVertexFromEditLayer() succeeded."
            )
            return

        self.statusBar().showMessage(
            "No active vertex. Use Edit Vertices and click a vertex first."
        )

    def delete_by_index(self) -> None:
        if self.viewer.selected_feature_count() <= 0:
            self.statusBar().showMessage("Select the polygon first.")
            return

        index = self.vertex_spin.value()
        deleted = self.viewer.delete_selected_feature_vertex_in_edit_layer(0, index)
        if not deleted:
            self.statusBar().showMessage("deleteFeatureVertexInEditLayer failed.")
            return

        self.vertex_spin.setMaximum(max(0, self.vertex_spin.maximum() - 1))
        self.refresh_viewer()
        self.statusBar().showMessage(
            "deleteFeatureVertexInEditLayer"
            f"(feature, 0, {index}) succeeded."
        )

    def refresh_viewer(self) -> None:
        self.viewer.invalidate_render_cache(False, True)
        self.viewer.refresh_layers()

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass

        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("DeleteVertex")
    app.setWindowIcon(application_icon())

    window = DeleteVertexWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
