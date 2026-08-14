import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 52.0)
LAYER_NAME = "Programmatic Polygons"

class AddPolygonProgrammaticWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = Path(__file__).resolve().parent / "images"
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.polygon_layer_index = -1
        self.polygon_cursor = 0

        self.setWindowTitle("AddPolygonProgrammatic")
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

        self.add_action = self.create_action("Polygon.png", "Add Polygon", self.add_next_polygon)
        self.clear_action = self.create_action("Delete.png", "Clear Polygons", self.clear_polygons)
        self.full_extent_action = self.create_action("FullExtent.png", "Full Extent", self.viewer.full_extent)
        toolbar.addAction(self.add_action)
        toolbar.addAction(self.clear_action)
        toolbar.addAction(self.full_extent_action)
        self.count_label = QLabel("Polygon count: 0", toolbar)
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
                title="AddPolygonProgrammatic",
            )
            self.viewer.add_layer(str(world_path), {"buildFeatureSource": True})
            self.viewer.set_layer_name(0, "World")
            self.viewer.set_layer_style(0, self.world_style())
            self.polygon_layer_index = self.viewer.add_empty_vector_layer(
                LAYER_NAME, ShapeType.POLYGON, self.polygon_style()
            )
            if not self.activate_edit_layer():
                raise RuntimeError("The programmatic polygon layer could not be initialized.")

            self.add_action.setEnabled(True)
            self.clear_action.setEnabled(True)
            self.full_extent_action.setEnabled(True)
            self.viewer.set_view_extent(SAMPLE_EXTENT)
            self.update_count()
            self.statusBar().showMessage(
                "Click Add Polygon to call addPolygonToEditLayer(index, points)."
            )
        except Exception as error:
            self.statusBar().showMessage("Programmatic polygon layer could not be initialized.")
            QMessageBox.critical(self, "AddPolygonProgrammatic", str(error))

    def activate_edit_layer(self) -> bool:
        if self.polygon_layer_index < 0:
            return False
        if not self.viewer.is_layer_editing(self.polygon_layer_index):
            if not self.viewer.begin_edit_layer(self.polygon_layer_index):
                return False
        return self.viewer.set_active_edit_layer_index(self.polygon_layer_index)

    def add_next_polygon(self) -> None:
        if not self.activate_edit_layer():
            self.statusBar().showMessage("Programmatic Polygons layer could not enter edit mode.")
            return
        points = self.sample_polygon_at(self.polygon_cursor)
        if not self.viewer.add_polygon_to_edit_layer(self.polygon_layer_index, points):
            self.statusBar().showMessage("Polygon could not be added.")
            return
        self.polygon_cursor += 1
        self.refresh_viewer()
        self.update_count()
        self.statusBar().showMessage(
            f"addPolygonToEditLayer({self.polygon_layer_index}, {len(points)} vertices)"
        )

    def sample_polygon_at(self, index: int) -> list[tuple[float, float]]:
        column = index % 7
        row = index // 7
        x = -124.0 + column * 7.5
        y = 27.0 + row * 4.2
        return [
            (x, y),
            (x + 4.4, y + 0.2),
            (x + 5.6, y + 2.4),
            (x + 2.3, y + 3.4),
            (x - 0.4, y + 2.0),
            (x, y),
        ]

    def clear_polygons(self) -> None:
        if self.polygon_layer_index < 0:
            return
        if not self.viewer.rollback_edit_layer(self.polygon_layer_index):
            QMessageBox.warning(self, "AddPolygonProgrammatic", "The polygons could not be cleared.")
            return
        if not self.activate_edit_layer():
            QMessageBox.warning(self, "AddPolygonProgrammatic", "Polygon editing could not be restarted.")
            return
        self.polygon_cursor = 0
        self.refresh_viewer()
        self.update_count()
        self.statusBar().showMessage("Programmatic polygons cleared.")

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            self.update_count()

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
    app.setApplicationName("AddPolygonProgrammatic")
    app.setWindowIcon(application_icon())
    window = AddPolygonProgrammaticWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
