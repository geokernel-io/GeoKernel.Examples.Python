import sys
from importlib.resources import files
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 52.0)
LAYER_NAME = "Programmatic Polylines"

class AddPolylineProgrammaticWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = files("geokernel").joinpath("assets/images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.polyline_layer_index = -1
        self.polyline_cursor = 0

        self.setWindowTitle("AddPolylineProgrammatic")
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

        self.add_action = self.create_action("Polyline.svg", "Add Polyline", self.add_next_polyline)
        self.clear_action = self.create_action("Delete.svg", "Clear Lines", self.clear_polylines)
        self.full_extent_action = self.create_action("FullExtent.svg", "Full Extent", self.viewer.full_extent)
        toolbar.addAction(self.add_action)
        toolbar.addAction(self.clear_action)
        toolbar.addAction(self.full_extent_action)
        self.count_label = QLabel("Polyline count: 0", toolbar)
        self.count_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(self.count_label)

        self.add_action.setEnabled(False)
        self.clear_action.setEnabled(False)
        self.full_extent_action.setEnabled(False)

    def create_action(self, icon_name, text, callback) -> QAction:
        action = QAction(QIcon(str(self.icon_dir.joinpath(icon_name))), text, self)
        action.setToolTip(text)
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
                title="AddPolylineProgrammatic",
            )
            self.viewer.add_layer(str(world_path), {"buildFeatureSource": True})
            self.viewer.set_layer_name(0, "World")
            self.viewer.set_layer_style(0, self.world_style())
            self.polyline_layer_index = self.viewer.add_empty_vector_layer(
                LAYER_NAME, ShapeType.POLYLINE, self.polyline_style()
            )
            if not self.activate_edit_layer():
                raise RuntimeError("The programmatic polyline layer could not be initialized.")

            self.add_action.setEnabled(True)
            self.clear_action.setEnabled(True)
            self.full_extent_action.setEnabled(True)
            self.viewer.set_view_extent(SAMPLE_EXTENT)
            self.update_count()
            self.statusBar().showMessage(
                "Click Add Polyline to call addPolylineToEditLayer(index, worldPoints)."
            )
        except Exception as error:
            self.statusBar().showMessage("Programmatic polyline layer could not be initialized.")
            QMessageBox.critical(self, "AddPolylineProgrammatic", str(error))

    def activate_edit_layer(self) -> bool:
        if self.polyline_layer_index < 0:
            return False
        if not self.viewer.is_layer_editing(self.polyline_layer_index):
            if not self.viewer.begin_edit_layer(self.polyline_layer_index):
                return False
        return self.viewer.set_active_edit_layer_index(self.polyline_layer_index)

    def add_next_polyline(self) -> None:
        if not self.activate_edit_layer():
            self.statusBar().showMessage("Programmatic Polylines layer could not enter edit mode.")
            return
        points = self.sample_polyline_at(self.polyline_cursor)
        if not self.viewer.add_polyline_to_edit_layer(self.polyline_layer_index, points):
            self.statusBar().showMessage("Polyline could not be added.")
            return
        self.polyline_cursor += 1
        self.refresh_viewer()
        self.update_count()
        self.statusBar().showMessage(
            f"addPolylineToEditLayer({self.polyline_layer_index}, {len(points)} vertices)"
        )

    def sample_polyline_at(self, index: int) -> list[tuple[float, float]]:
        column = index % 7
        row = index // 7
        x = -124.0 + column * 7.0
        y = 29.0 + row * 3.0
        return [(x, y), (x + 2.2, y + 1.4), (x + 4.8, y + 0.4), (x + 6.4, y + 2.2)]

    def clear_polylines(self) -> None:
        if self.polyline_layer_index < 0:
            return
        if not self.viewer.rollback_edit_layer(self.polyline_layer_index):
            QMessageBox.warning(self, "AddPolylineProgrammatic", "The polylines could not be cleared.")
            return
        if not self.activate_edit_layer():
            QMessageBox.warning(self, "AddPolylineProgrammatic", "Polyline editing could not be restarted.")
            return
        self.polyline_cursor = 0
        self.refresh_viewer()
        self.update_count()
        self.statusBar().showMessage("Programmatic polylines cleared.")

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            self.update_count()

    def refresh_viewer(self) -> None:
        self.viewer.invalidate_render_cache(False, True)
        self.viewer.refresh_layers()

    def update_count(self) -> None:
        count = 0 if self.polyline_layer_index < 0 else self.viewer.layer_feature_count(self.polyline_layer_index)
        self.count_label.setText(f"Polyline count: {count}")

    def world_style(self) -> dict:
        return {"fillColor": "#D8E5E1", "fillOpacity": 210, "lineColor": "#6F8883", "lineWidth": 0.7}

    def polyline_style(self) -> dict:
        return {"lineColor": "#D95D39", "lineWidth": 2.6}

    def closeEvent(self, event) -> None:
        try:
            if self.polyline_layer_index >= 0 and self.viewer.is_layer_editing(self.polyline_layer_index):
                self.viewer.rollback_edit_layer(self.polyline_layer_index)
        except Exception:
            pass
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AddPolylineProgrammatic")
    app.setWindowIcon(application_icon())
    window = AddPolylineProgrammaticWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
