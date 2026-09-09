import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 55.0)

class DeleteFeatureWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_index = -1
        self.initialized = False
        self.setWindowTitle("DeleteFeature")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Editing", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)
        self.select_action = self.create_action("Select.png", "Select", self.toggle_select, True)
        self.delete_action = self.create_action("Delete.png", "Delete Selected", self.delete_selected)
        self.reset_action = self.create_action("Refresh.png", "Reset Points", self.populate_points)
        self.extent_action = self.create_action("FullExtent.png", "Full Extent", self.viewer.full_extent)
        for action in (self.select_action, self.delete_action, self.reset_action, self.extent_action):
            toolbar.addAction(action)
            action.setEnabled(False)
        self.count_label = QLabel("Feature count: 0 | Selected: 0", toolbar)
        self.count_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(self.count_label)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Feature ID", "Name", "Group", "Value"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        dock = QDockWidget("Editable point features", self)
        dock.setWidget(self.table)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.selection_info = QPlainTextEdit(self)
        self.selection_info.setReadOnly(True)
        self.selection_info.setPlainText("Select mode: click a point, then choose Delete Selected.")
        info_dock = QDockWidget("Selection", self)
        info_dock.setWidget(self.selection_info)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, info_dock)

    def create_action(self, icon_name, text, callback, checkable=False) -> QAction:
        action = QAction(QIcon(str(self.icon_dir.joinpath(icon_name))), text, self)
        action.setCheckable(checkable)
        action.setToolTip(text)
        action.triggered.connect(callback)
        return action

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            path = ensure_sample_file(app=self.app, zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip", zip_name="world_4326.zip", target_folder="world_4326", required_file="world_4326.shp", title="DeleteFeature")
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.viewer.set_layer_name(0, "World")
            self.viewer.set_layer_style(0, self.world_style())
            self.layer_index = self.viewer.add_empty_vector_layer("Editable Points", ShapeType.POINT, self.point_style())
            if not self.activate_editing():
                raise RuntimeError("Editable Points layer could not enter edit mode.")
            self.populate_points()
            for action in (self.select_action, self.delete_action, self.reset_action, self.extent_action):
                action.setEnabled(True)
            self.select_action.setChecked(True)
            self.viewer.set_tool(ViewerTool.INFO)
            self.viewer.set_view_extent(SAMPLE_EXTENT)
            self.statusBar().showMessage("Select mode: click a point, then choose Delete Selected.")
        except Exception as error:
            QMessageBox.critical(self, "DeleteFeature", str(error))

    def activate_editing(self) -> bool:
        if self.layer_index < 0:
            return False
        if not self.viewer.is_layer_editing(self.layer_index) and not self.viewer.begin_edit_layer(self.layer_index):
            return False
        return self.viewer.set_active_edit_layer_index(self.layer_index)

    def populate_points(self) -> None:
        if self.layer_index < 0:
            return
        if self.viewer.is_layer_editing(self.layer_index):
            self.viewer.rollback_edit_layer(self.layer_index)
        if not self.activate_editing():
            return
        for index in range(14):
            x, y = self.sample_point_at(index)
            self.viewer.add_point_to_edit_layer(self.layer_index, x, y, {"Name": f"Point {index + 1}", "Group": "North" if index % 2 == 0 else "South", "Value": (index + 1) * 10})
        self.viewer.clear_selected_features()
        self.rebuild_table()
        self.refresh_viewer()
        self.update_count()
        self.selection_info.setPlainText("Select mode: click a point, then choose Delete Selected.")

    def sample_point_at(self, index: int) -> tuple[float, float]:
        return -122.0 + (index % 8) * 7.0, 30.0 + (index // 8) * 5.0

    def toggle_select(self, checked: bool) -> None:
        self.viewer.set_tool(ViewerTool.INFO if checked else ViewerTool.PAN)
        self.statusBar().showMessage("Select mode: click a point." if checked else "Pan mode.")

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.MAP_MOUSE_UP and self.select_action.isChecked():
            self.select_at(event.screen_rectangle.left, event.screen_rectangle.top)
        elif event.event_type in (ViewerEventType.SELECTION_CHANGED, ViewerEventType.LAYER_EDIT_STATE_CHANGED):
            self.update_count()

    def select_at(self, x: int, y: int) -> None:
        hit = self.viewer.hit_test_top_feature_at(x, y, 8)
        if not hit or hit.get("layerIndex", -1) != self.layer_index:
            self.viewer.clear_selected_features()
            self.table.clearSelection()
            self.selection_info.setPlainText("No editable point feature found.")
            return
        self.viewer.select_top_feature_at(x, y, 8)
        feature_id = int(hit.get("featureId", -1))
        self.select_table_row(feature_id)
        attributes = hit.get("attributes", {})
        self.selection_info.setPlainText(f"Feature {feature_id}: {attributes.get('Name', '-')}")
        self.update_count()

    def delete_selected(self) -> None:
        if self.viewer.selected_feature_count() <= 0:
            self.statusBar().showMessage("Select one or more points first.")
            return
        if not self.viewer.delete_selected_features_from_edit_layer():
            self.statusBar().showMessage("Selected feature(s) could not be deleted.")
            return
        self.viewer.clear_selected_features()
        self.rebuild_table()
        self.refresh_viewer()
        self.update_count()
        self.selection_info.setPlainText("Selected feature(s) deleted.")
        self.statusBar().showMessage("Selected feature(s) deleted.")

    def rebuild_table(self) -> None:
        self.table.setRowCount(0)
        count = self.viewer.layer_feature_count(self.layer_index)
        for row in range(count):
            attributes = self.viewer.layer_feature_attributes(self.layer_index, row)
            self.table.insertRow(row)
            for column, value in enumerate((row + 1, attributes.get("Name", ""), attributes.get("Group", ""), attributes.get("Value", ""))):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def select_table_row(self, feature_id: int) -> None:
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if int(self.table.item(row, 0).text()) == feature_id:
                self.table.selectRow(row)
                return

    def refresh_viewer(self) -> None:
        self.viewer.invalidate_render_cache(False, True)
        self.viewer.refresh_layers()

    def update_count(self) -> None:
        count = 0 if self.layer_index < 0 else self.viewer.layer_feature_count(self.layer_index)
        self.count_label.setText(f"Feature count: {count} | Selected: {self.viewer.selected_feature_count()}")

    def world_style(self) -> dict:
        return {"fillColor": "#D8E5E1", "fillOpacity": 210, "lineColor": "#6F8883", "lineWidth": 0.7}

    def point_style(self) -> dict:
        return {"pointColor": "#D95D39", "lineColor": "#8C321D", "pointSize": 11.0, "lineWidth": 1.3, "selectedLineColor": "#F59E0B", "selectedLineWidth": 4.0, "showLabels": True, "labelField": "Name", "labelFontSize": 10.0, "labelHaloEnabled": True, "labelHaloColor": "#FFFFFF", "labelHaloWidth": 2.0, "labelOffsetY": -12.0, "labelAllowOverlap": True}

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("DeleteFeature")
    app.setWindowIcon(application_icon())
    window = DeleteFeatureWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
