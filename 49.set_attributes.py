import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QComboBox, QDockWidget, QFormLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QSpinBox, QTableWidget, QTableWidgetItem, QToolBar, QWidget
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

EXTENT = Extent(-132.0, 18.0, -60.0, 55.0)
POINTS = [
    (-122, 36),
    (-111, 42),
    (-101, 34.5),
    (-91, 41),
    (-80, 33),
]

class SetAttributesWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.INFO)
        self.viewer.set_event_callback(self.on_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_index = -1
        self.selected_shape_id = -1
        self.initialized = False

        self.setWindowTitle("SetAttributes")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Editing", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.select_action = self.create_action(
            "Select.svg",
            "Select",
            self.toggle_select,
            checkable=True,
        )
        self.apply_action = self.create_action(
            "Edit.svg",
            "Apply Attributes",
            self.apply_attributes,
        )
        self.undo_action = self.create_action("Undo.svg", "Undo", self.undo)
        self.redo_action = self.create_action("Redo.svg", "Redo", self.redo)
        self.reset_action = self.create_action(
            "Refresh.svg",
            "Reset",
            self.reset,
        )
        self.full_extent_action = self.create_action(
            "FullExtent.svg",
            "Full Extent",
            self.viewer.full_extent,
        )
        self.actions = (
            self.select_action,
            self.apply_action,
            self.undo_action,
            self.redo_action,
            self.reset_action,
            self.full_extent_action,
        )

        self.select_action.setChecked(True)
        for action in self.actions:
            toolbar.addAction(action)
            action.setEnabled(False)

        self.create_attribute_editor()
        self.create_attribute_table()

    def create_attribute_editor(self) -> None:
        form_widget = QWidget(self)
        form = QFormLayout(form_widget)

        self.selected_label = QLabel("none", form_widget)
        self.name_edit = QLineEdit(form_widget)
        self.status_combo = QComboBox(form_widget)
        self.status_combo.addItems(["Planned", "Active", "Done"])
        self.priority_spin = QSpinBox(form_widget)
        self.priority_spin.setRange(1, 10)

        form.addRow("Selected shape", self.selected_label)
        form.addRow("Name", self.name_edit)
        form.addRow("Status", self.status_combo)
        form.addRow("Priority", self.priority_spin)

        dock = QDockWidget("Attribute editor", self)
        dock.setWidget(form_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def create_attribute_table(self) -> None:
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(
            ["Shape ID", "Name", "Status", "Priority"]
        )
        self.table.setMaximumHeight(170)

        dock = QDockWidget("Editable Attributes table", self)
        dock.setWidget(self.table)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

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
                title="SetAttributes",
            )

            self.viewer.add_layer(str(world_path))
            self.viewer.set_layer_style(
                0,
                {
                    "fillColor": "#D8E5E1",
                    "fillOpacity": 170,
                    "lineColor": "#6F8883",
                },
            )
            self.layer_index = self.viewer.add_empty_vector_layer(
                "Editable Attributes",
                ShapeType.POINT,
                {
                    "pointColor": "#D95D39",
                    "pointSize": 11.0,
                    "showLabels": True,
                    "labelField": "Name",
                    "labelOffsetY": -12.0,
                    "labelHaloEnabled": True,
                },
            )
            self.reset()

            for action in self.actions:
                action.setEnabled(True)

            self.update_action_state()
            self.viewer.set_view_extent(EXTENT)
            self.statusBar().showMessage(
                "Select a point, edit form values, then Apply Attributes."
            )
        except Exception as error:
            QMessageBox.critical(self, "SetAttributes", str(error))

    def begin_edit(self) -> bool:
        if self.layer_index < 0:
            return False

        if not self.viewer.is_layer_editing(self.layer_index):
            if not self.viewer.begin_edit_layer(self.layer_index):
                return False

        return self.viewer.set_active_edit_layer_index(self.layer_index)

    def reset(self) -> None:
        if self.layer_index < 0:
            return

        if self.viewer.is_layer_editing(self.layer_index):
            self.viewer.rollback_edit_layer(self.layer_index)

        if not self.begin_edit():
            self.statusBar().showMessage("The edit session could not be started.")
            return

        for index, (x, y) in enumerate(POINTS):
            attributes = {
                "Name": f"Site {index + 1}",
                "Status": "Planned" if index % 2 == 0 else "Active",
                "Priority": index + 1,
            }
            self.viewer.add_point_to_edit_layer(
                self.layer_index,
                x,
                y,
                attributes,
            )

        self.clear_selection()
        self.viewer.set_tool(ViewerTool.INFO)
        self.select_action.setChecked(True)
        self.rebuild_table()
        self.refresh_viewer()
        self.update_action_state()
        self.statusBar().showMessage(
            "Select a point, edit attributes, then Apply Attributes."
        )

    def clear_selection(self) -> None:
        self.selected_shape_id = -1
        self.selected_label.setText("none")
        self.name_edit.clear()
        self.status_combo.setCurrentIndex(0)
        self.priority_spin.setValue(1)
        self.viewer.clear_selected_features()

    def toggle_select(self, checked: bool) -> None:
        tool = ViewerTool.INFO if checked else ViewerTool.PAN
        self.viewer.set_tool(tool)

    def on_event(self, event) -> None:
        if event.event_type == ViewerEventType.MAP_MOUSE_UP:
            if self.select_action.isChecked():
                self.select_at(
                    event.screen_rectangle.left,
                    event.screen_rectangle.top,
                )
            return

        if event.event_type == ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            self.rebuild_table()
            self.update_action_state()

    def select_at(self, x: int, y: int) -> None:
        hit = self.viewer.hit_test_top_feature_at(x, y, 8)
        if not hit or hit.get("layerIndex", -1) != self.layer_index:
            self.clear_selection()
            self.update_action_state()
            self.statusBar().showMessage("No editable point selected.")
            return

        if not self.viewer.select_top_feature_at(x, y, 8):
            self.clear_selection()
            self.update_action_state()
            return

        self.selected_shape_id = int(
            hit.get("shapeId", hit.get("featureId", -1))
        )
        attributes = hit.get("attributes", {})

        self.selected_label.setText(str(self.selected_shape_id))
        self.name_edit.setText(str(attributes.get("Name", "")))
        self.status_combo.setCurrentText(
            str(attributes.get("Status", "Planned"))
        )
        self.priority_spin.setValue(int(attributes.get("Priority", 1)))
        self.update_action_state()
        self.statusBar().showMessage(
            f"Selected shape {self.selected_shape_id}."
        )

    def apply_attributes(self) -> None:
        if self.selected_shape_id < 0:
            self.statusBar().showMessage("Select a feature first.")
            return

        attributes = {
            "Name": self.name_edit.text(),
            "Status": self.status_combo.currentText(),
            "Priority": self.priority_spin.value(),
        }
        succeeded = self.viewer.set_shape_attributes_in_edit_layer(
            self.layer_index,
            self.selected_shape_id,
            attributes,
        )

        if not succeeded:
            self.statusBar().showMessage("setShapeAttributesInEditLayer failed.")
            return

        self.rebuild_table()
        self.refresh_viewer()
        self.update_action_state()
        self.statusBar().showMessage(
            "setShapeAttributesInEditLayer"
            f"({self.layer_index}, {self.selected_shape_id}, attributes) succeeded."
        )

    def undo(self) -> None:
        self.viewer.undo_edit_layer(self.layer_index)
        self.rebuild_table()
        self.refresh_viewer()
        self.update_action_state()

    def redo(self) -> None:
        self.viewer.redo_edit_layer(self.layer_index)
        self.rebuild_table()
        self.refresh_viewer()
        self.update_action_state()

    def rebuild_table(self) -> None:
        if self.layer_index < 0:
            return

        feature_count = self.viewer.layer_feature_count(self.layer_index)
        self.table.setRowCount(feature_count)

        for row in range(feature_count):
            attributes = self.viewer.layer_feature_attributes(
                self.layer_index,
                row,
            )
            values = (
                row + 1,
                attributes.get("Name", ""),
                attributes.get("Status", ""),
                attributes.get("Priority", ""),
            )
            for column, value in enumerate(values):
                self.table.setItem(
                    row,
                    column,
                    QTableWidgetItem(str(value)),
                )

    def update_action_state(self) -> None:
        has_layer = self.layer_index >= 0
        has_selection = self.selected_shape_id >= 0
        can_undo = has_layer and self.viewer.can_undo_edit_layer(self.layer_index)
        can_redo = has_layer and self.viewer.can_redo_edit_layer(self.layer_index)

        self.apply_action.setEnabled(has_selection)
        self.undo_action.setEnabled(can_undo)
        self.redo_action.setEnabled(can_redo)

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
    app.setApplicationName("SetAttributes")
    app.setWindowIcon(application_icon())

    window = SetAttributesWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
