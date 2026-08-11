import sys
from importlib.resources import files
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 52.0)
LAYER_NAME = "Drawn Polygons"

class AddPolygonInteractiveWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = files("geokernel").joinpath("assets/images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.polygon_layer_index = -1

        self.setWindowTitle("AddPolygonInteractive")
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

        self.full_extent_action = self.create_action("FullExtent.svg", "Full Extent", self.viewer.full_extent)
        toolbar.addAction(self.full_extent_action)
        toolbar.addSeparator()

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.add_polygon_action = self.create_action("Polygon.svg", "Add Polygon", self.activate_add_polygon, True)
        self.pan_action = self.create_action("Pan.svg", "Pan", self.activate_pan, True)
        self.tool_group.addAction(self.add_polygon_action)
        self.tool_group.addAction(self.pan_action)
        toolbar.addAction(self.add_polygon_action)
        toolbar.addAction(self.pan_action)
        toolbar.addSeparator()

        self.clear_action = self.create_action("Delete.svg", "Clear Polygons", self.clear_polygons)
        toolbar.addAction(self.clear_action)
        self.count_label = QLabel("Polygon count: 0", toolbar)
        self.count_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(self.count_label)

        self.full_extent_action.setEnabled(False)
        self.add_polygon_action.setEnabled(False)
        self.clear_action.setEnabled(False)
        self.pan_action.setChecked(True)

    def create_action(self, icon_name, text, callback, checkable=False) -> QAction:
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
                title="AddPolygonInteractive",
            )
            self.viewer.add_layer(str(world_path), {"buildFeatureSource": True})
            self.viewer.set_layer_name(0, "World")
            self.viewer.set_layer_style(0, self.world_style())
            self.polygon_layer_index = self.viewer.add_empty_vector_layer(
                LAYER_NAME, ShapeType.POLYGON, self.polygon_style()
            )
            if not self.activate_edit_layer():
                raise RuntimeError("The editable polygon layer could not be initialized.")

            self.full_extent_action.setEnabled(True)
            self.add_polygon_action.setEnabled(True)
            self.clear_action.setEnabled(True)
            self.add_polygon_action.setChecked(True)
            self.viewer.set_tool(ViewerTool.ADD_POLYGON)
            self.viewer.set_view_extent(SAMPLE_EXTENT)
            self.update_count()
            self.statusBar().showMessage(
                "Add Polygon active. Click vertices, then press Enter or double-click to finish."
            )
        except Exception as error:
            self.statusBar().showMessage("Editable polygon layer could not be initialized.")
            QMessageBox.critical(self, "AddPolygonInteractive", str(error))

    def activate_edit_layer(self) -> bool:
        if self.polygon_layer_index < 0:
            return False
        if not self.viewer.is_layer_editing(self.polygon_layer_index):
            if not self.viewer.begin_edit_layer(self.polygon_layer_index):
                return False
        return self.viewer.set_active_edit_layer_index(self.polygon_layer_index)

    def activate_add_polygon(self) -> None:
        if not self.activate_edit_layer():
            self.statusBar().showMessage("Drawn Polygons layer could not enter edit mode.")
            return
        self.viewer.set_tool(ViewerTool.ADD_POLYGON)
        self.statusBar().showMessage(
            "Add Polygon active. Click vertices, then press Enter or double-click to finish."
        )

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan tool active.")

    def clear_polygons(self) -> None:
        if self.polygon_layer_index < 0:
            return
        if not self.viewer.rollback_edit_layer(self.polygon_layer_index):
            QMessageBox.warning(self, "AddPolygonInteractive", "The polygons could not be cleared.")
            return
        if not self.activate_edit_layer():
            QMessageBox.warning(self, "AddPolygonInteractive", "Polygon editing could not be restarted.")
            return
        self.refresh_viewer()
        self.update_count()
        self.statusBar().showMessage("Drawn polygons cleared.")

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            self.refresh_viewer()
            self.update_count()
        elif (
            event.event_type == ViewerEventType.MOUSE_COORDINATES_CHANGED
            and self.add_polygon_action.isChecked()
        ):
            self.statusBar().showMessage(
                f"Add Polygon active. x={event.extent.x_min:.4f}, y={event.extent.y_min:.4f}"
            )

    def refresh_viewer(self) -> None:
        self.viewer.invalidate_render_cache(False, True)
        self.viewer.refresh_layers()

    def update_count(self) -> None:
        count = 0 if self.polygon_layer_index < 0 else self.viewer.layer_feature_count(self.polygon_layer_index)
        self.count_label.setText(f"Polygon count: {count}")

    def world_style(self) -> dict:
        return {"fillColor": "#D8E5E1", "fillOpacity": 210, "lineColor": "#6F8883", "lineWidth": 0.7}

    def polygon_style(self) -> dict:
        return {"fillColor": "#F2D27A", "fillOpacity": 160, "lineColor": "#D95D39", "lineWidth": 2.0}

    def closeEvent(self, event) -> None:
        try:
            if self.polygon_layer_index >= 0 and self.viewer.is_layer_editing(self.polygon_layer_index):
                self.viewer.rollback_edit_layer(self.polygon_layer_index)
        except Exception:
            pass
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AddPolygonInteractive")
    app.setWindowIcon(application_icon())
    window = AddPolygonInteractiveWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
