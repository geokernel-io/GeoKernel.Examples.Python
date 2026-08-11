import sys
from pathlib import Path
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-132.0, 15.0, -55.0, 55.0)

class EditVerticesToolWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__(); self.app = app; self.icon_dir = Path(__file__).with_name("images")
        self.viewer = Viewer(); self.viewer.set_tool(ViewerTool.EDIT_VERTICES); self.viewer.set_event_callback(self.on_event)
        self.viewer_widget = self.viewer.qt_widget(); self.line_index = -1; self.polygon_index = -1; self.initialized = False
        self.setWindowTitle("EditVerticesTool"); self.setWindowIcon(application_icon()); self.resize(1200, 800); self.setCentralWidget(self.viewer_widget); self.create_toolbar()

    def create_toolbar(self) -> None:
        bar = QToolBar("Editing", self); bar.setMovable(False); bar.setIconSize(QSize(32, 32)); self.addToolBar(bar)
        self.edit_action = self.action("Edit.svg", "Edit Vertices", self.activate_edit, True)
        self.delete_action = self.action("Delete.svg", "Delete Vertex", self.delete_vertex)
        self.reset_action = self.action("Refresh.svg", "Reset Shapes", self.reset_shapes)
        self.extent_action = self.action("FullExtent.svg", "Full Extent", self.viewer.full_extent)
        for item in (self.edit_action, self.delete_action, self.reset_action, self.extent_action): bar.addAction(item); item.setEnabled(False)
        self.edit_action.setChecked(True); self.info_label = QLabel("Lines: 0 | Polygons: 0", bar); self.info_label.setContentsMargins(12, 0, 12, 0); bar.addWidget(self.info_label)

    def action(self, icon: str, text: str, callback, checkable=False) -> QAction:
        item = QAction(QIcon(str(self.icon_dir / icon)), text, self); item.setCheckable(checkable); item.triggered.connect(callback); return item

    def initialize_viewer(self) -> None:
        if self.initialized: return
        self.initialized = True; self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height()); self.viewer.show()
        try:
            path = ensure_sample_file(app=self.app, zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip", zip_name="world_4326.zip", target_folder="world_4326", required_file="world_4326.shp", title="EditVerticesTool")
            self.viewer.add_layer(str(path)); self.viewer.set_layer_name(0, "World"); self.viewer.set_layer_style(0, {"fillColor":"#D8E5E1","fillOpacity":150,"lineColor":"#6F8883","lineWidth":0.7})
            self.line_index = self.viewer.add_empty_vector_layer("Editable Lines", ShapeType.POLYLINE, {"lineColor":"#D95D39","lineWidth":2.6})
            self.polygon_index = self.viewer.add_empty_vector_layer("Editable Polygons", ShapeType.POLYGON, {"fillColor":"#F2D27A","fillOpacity":120,"lineColor":"#2878A0","lineWidth":2.0})
            self.line_index = int(self.viewer.layer_info_by_name("Editable Lines").get("index", 1))
            self.polygon_index = int(self.viewer.layer_info_by_name("Editable Polygons").get("index", 0))
            self.reset_shapes()
            for item in (self.edit_action, self.delete_action, self.reset_action, self.extent_action): item.setEnabled(True)
            self.viewer.set_view_extent(SAMPLE_EXTENT); self.statusBar().showMessage("Edit Vertices: drag vertices, double-click segments to add, Delete to remove.")
        except Exception as error: QMessageBox.critical(self, "EditVerticesTool", str(error))

    def begin_layers(self) -> bool:
        for index in (self.line_index, self.polygon_index):
            if index < 0: return False
            if not self.viewer.is_layer_editing(index) and not self.viewer.begin_edit_layer(index): return False
        return self.viewer.set_active_edit_layer_index(self.polygon_index)

    def reset_shapes(self) -> None:
        if self.line_index < 0: return
        for index in (self.line_index, self.polygon_index):
            if self.viewer.is_layer_editing(index): self.viewer.rollback_edit_layer(index)
        if not self.begin_layers(): return
        self.viewer.add_polyline_to_edit_layer(self.line_index,[(-127,31),(-118,40),(-107,34),(-96,43),(-86,37)],{"Name":"Pacific route"})
        self.viewer.add_polyline_to_edit_layer(self.line_index,[(-113,24),(-101,29),(-90,27),(-80,33)],{"Name":"Gulf route"})
        self.viewer.add_polygon_to_edit_layer(self.polygon_index,[(-118,30),(-109,45),(-91,42),(-94,27),(-111,24),(-118,30)],{"Name":"Edit polygon A"})
        self.viewer.add_polygon_to_edit_layer(self.polygon_index,[(-83,24),(-73,31),(-65,25),(-72,18),(-83,24)],{"Name":"Edit polygon B"})
        self.viewer.clear_selected_features(); self.viewer.set_tool(ViewerTool.EDIT_VERTICES); self.edit_action.setChecked(True); self.refresh(); self.update_info(); self.statusBar().showMessage("Shapes reset. Edit Vertices tool is active.")

    def activate_edit(self) -> None:
        self.begin_layers(); self.viewer.set_tool(ViewerTool.EDIT_VERTICES); self.statusBar().showMessage("Edit Vertices active.")

    def delete_vertex(self) -> None:
        if self.viewer.delete_selected_vertex_from_edit_layer(): self.refresh(); self.statusBar().showMessage("Selected vertex deleted.")
        else: self.statusBar().showMessage("No active vertex to delete. Click a vertex first.")

    def on_event(self, event) -> None:
        if event.event_type == ViewerEventType.LAYER_EDIT_STATE_CHANGED: self.update_info()

    def refresh(self) -> None: self.viewer.invalidate_render_cache(False, True); self.viewer.refresh_layers()
    def update_info(self) -> None:
        if self.line_index >= 0: self.info_label.setText(f"Lines: {self.viewer.layer_feature_count(self.line_index)} | Polygons: {self.viewer.layer_feature_count(self.polygon_index)}")
    def closeEvent(self, event) -> None:
        try: self.viewer.close()
        except Exception: pass
        super().closeEvent(event)

def main() -> None:
    app=QApplication(sys.argv);
    app.setApplicationName("EditVerticesTool");
    app.setWindowIcon(application_icon());
    window=EditVerticesToolWindow(app);
    window.show();
    QTimer.singleShot(0,window.initialize_viewer);
    sys.exit(app.exec())

if __name__=="__main__":
    main()
