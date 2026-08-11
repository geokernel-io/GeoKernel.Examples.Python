import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 55.0)

class AddWithAttributesWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_index = -1
        self.point_cursor = 0
        self.initialized = False
        self.setWindowTitle("AddWithAttributes")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Editing", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)
        self.add_action = self.create_action("Point.svg", "Add Point With Attributes", self.add_point)
        self.info_action = self.create_action("Identify.svg", "Info", self.toggle_info, True)
        self.clear_action = self.create_action("Delete.svg", "Clear Points", self.clear_points)
        self.extent_action = self.create_action("FullExtent.svg", "Full Extent", self.viewer.full_extent)
        for action in (self.add_action, self.info_action, self.clear_action, self.extent_action):
            toolbar.addAction(action)
            action.setEnabled(False)
        self.count_label = QLabel("Feature count: 0", toolbar)
        self.count_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(self.count_label)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["#", "Name", "Category", "Score", "Source"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setMaximumHeight(155)
        table_dock = QDockWidget("Added point attributes", self)
        table_dock.setWidget(self.table)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, table_dock)

        self.info_text = QPlainTextEdit(self)
        self.info_text.setReadOnly(True)
        self.reset_info_text()
        info_dock = QDockWidget("Info result", self)
        info_dock.setWidget(self.info_text)
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
            path = ensure_sample_file(app=self.app, zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip", zip_name="world_4326.zip", target_folder="world_4326", required_file="world_4326.shp", title="AddWithAttributes")
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.viewer.set_layer_name(0, "World")
            self.viewer.set_layer_style(0, self.world_style())
            self.layer_index = self.viewer.add_empty_vector_layer("Points With Attributes", ShapeType.POINT, self.point_style())
            if not self.activate_editing():
                raise RuntimeError("Points With Attributes layer could not enter edit mode.")
            for action in (self.add_action, self.info_action, self.clear_action, self.extent_action):
                action.setEnabled(True)
            self.viewer.set_view_extent(SAMPLE_EXTENT)
            self.update_count()
            self.statusBar().showMessage("Click Add Point to call addPointToEditLayer(index, worldPoint, attributes).")
        except Exception as error:
            QMessageBox.critical(self, "AddWithAttributes", str(error))

    def activate_editing(self) -> bool:
        if self.layer_index < 0:
            return False
        if not self.viewer.is_layer_editing(self.layer_index) and not self.viewer.begin_edit_layer(self.layer_index):
            return False
        return self.viewer.set_active_edit_layer_index(self.layer_index)

    def add_point(self) -> None:
        if not self.activate_editing():
            return
        feature_no = self.point_cursor + 1
        x, y = self.sample_point_at(self.point_cursor)
        attributes = {"Name": f"Site {feature_no}", "Category": "Even" if feature_no % 2 == 0 else "Odd", "Score": feature_no * 10, "Source": "Python Dictionary"}
        if not self.viewer.add_point_to_edit_layer(self.layer_index, x, y, attributes):
            self.statusBar().showMessage("Point could not be added.")
            return
        self.point_cursor += 1
        self.append_row(feature_no, attributes)
        self.info_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.PAN)
        self.refresh_viewer()
        self.update_count()
        self.statusBar().showMessage(f"addPointToEditLayer({self.layer_index}, [{x:.4f}, {y:.4f}], Dictionary attributes)")

    def sample_point_at(self, index: int) -> tuple[float, float]:
        return -123.0 + (index % 12) * 5.0, 29.0 + (index // 12) * 4.0

    def toggle_info(self, checked: bool) -> None:
        self.viewer.set_tool(ViewerTool.INFO if checked else ViewerTool.PAN)
        self.statusBar().showMessage("Info mode: click an added point to read its attributes." if checked else "Pan mode.")

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            self.update_count()
        elif event.event_type == ViewerEventType.ACTIVE_TOOL_CHANGED:
            self.info_action.setChecked(event.int_value == int(ViewerTool.INFO))
        elif event.event_type == ViewerEventType.MAP_MOUSE_UP and self.info_action.isChecked():
            self.inspect_at(event.screen_rectangle.left, event.screen_rectangle.top)

    def inspect_at(self, x: int, y: int) -> None:
        hit = self.viewer.hit_test_top_feature_at(x, y, 8)
        if not hit or hit.get("layerIndex", -1) != self.layer_index:
            self.info_text.setPlainText("No feature found.")
            self.table.clearSelection()
            return
        attributes = hit.get("attributes", {})
        feature_id = int(hit.get("featureId", -1))
        lines = [f"Layer: {hit.get('layerName', 'Points With Attributes')}", f"Feature ID: {feature_id}", ""]
        lines.extend(f"{key} = {attributes[key]}" for key in sorted(attributes, key=str.casefold))
        self.info_text.setPlainText("\n".join(lines))
        self.select_row(feature_id)
        self.viewer.select_top_feature_at(x, y, 8)

    def append_row(self, feature_no: int, attributes: dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value in enumerate((feature_no, attributes["Name"], attributes["Category"], attributes["Score"], attributes["Source"])):
            self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.scrollToBottom()

    def select_row(self, feature_id: int) -> None:
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if int(self.table.item(row, 0).text()) == feature_id:
                self.table.selectRow(row)
                return

    def clear_points(self) -> None:
        if self.layer_index < 0 or not self.viewer.rollback_edit_layer(self.layer_index):
            return
        self.activate_editing()
        self.point_cursor = 0
        self.table.setRowCount(0)
        self.reset_info_text()
        self.refresh_viewer()
        self.update_count()
        self.statusBar().showMessage("Points with attributes cleared.")

    def reset_info_text(self) -> None:
        self.info_text.setPlainText("Click Info, then click an added point to read its Python Dictionary attributes from the feature.")

    def refresh_viewer(self) -> None:
        self.viewer.invalidate_render_cache(False, True)
        self.viewer.refresh_layers()

    def update_count(self) -> None:
        count = 0 if self.layer_index < 0 else self.viewer.layer_feature_count(self.layer_index)
        self.count_label.setText(f"Feature count: {count}")

    def world_style(self) -> dict:
        return {"fillColor": "#D8E5E1", "fillOpacity": 210, "lineColor": "#6F8883", "lineWidth": 0.7}

    def point_style(self) -> dict:
        return {"pointColor": "#D95D39", "lineColor": "#8C321D", "pointSize": 9.5, "lineWidth": 1.2, "showLabels": True, "labelField": "Name", "labelFontSize": 10.0, "labelColor": "#263238", "labelHaloEnabled": True, "labelHaloColor": "#FFFFFF", "labelHaloWidth": 2.0, "labelOffsetY": -11.0, "labelAllowOverlap": True}

    def closeEvent(self, event) -> None:
        try:
            if self.layer_index >= 0 and self.viewer.is_layer_editing(self.layer_index):
                self.viewer.rollback_edit_layer(self.layer_index)
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AddWithAttributes")
    app.setWindowIcon(application_icon())
    window = AddWithAttributesWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
