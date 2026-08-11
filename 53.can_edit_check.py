import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

class CanEditCheckWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_event)
        self.widget = self.viewer.qt_widget()
        self.layer = -1
        self.initialized = False
        self.setWindowTitle("CanEditCheck")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.widget)
        self.create_ui()

    def create_ui(self) -> None:
        bar = QToolBar("Editing", self)
        bar.setMovable(False)
        bar.setIconSize(QSize(32, 32))
        self.addToolBar(bar)
        self.begin_action = self.make("Edit.svg", "Begin Edit", self.begin_edit)
        self.commit_action = self.make("Save.svg", "Commit Edit", self.commit)
        self.rollback_action = self.make("Rollback.svg", "Rollback Edit", self.rollback)
        self.select_action = self.make("Select.svg", "Select", self.toggle_select, True)
        self.clear_action = self.make(
            "Delete.svg", "Clear Selection", self.clear_selection
        )
        self.reset_action = self.make(
            "Refresh.svg", "Reset Points", self.populate_points
        )
        self.extent_action = self.make(
            "FullExtent.svg", "Full Extent", self.viewer.full_extent
        )
        self.actions = (
            self.begin_action,
            self.commit_action,
            self.rollback_action,
            self.select_action,
            self.clear_action,
            self.reset_action,
            self.extent_action,
        )
        for action in self.actions:
            bar.addAction(action)
            action.setEnabled(False)
        self.status_table = QTableWidget(3, 3, self)
        self.status_table.setHorizontalHeaderLabels(
            ["Capability", "Result", "Requirement"]
        )
        dock = QDockWidget("Edit capability checks", self)
        dock.setWidget(self.status_table)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.info = QPlainTextEdit(self)
        self.info.setReadOnly(True)
        info_dock = QDockWidget("Selected feature", self)
        info_dock.setWidget(self.info)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, info_dock)

    def make(self, icon, text, slot, check=False) -> QAction:
        action = QAction(QIcon(str(self.icons / icon)), text, self)
        action.setCheckable(check)
        action.triggered.connect(slot)
        return action

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.widget.width(), self.widget.height())
        self.viewer.show()
        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="CanEditCheck",
            )
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_style(
                0, {"fillColor": "#D8E5E1", "lineColor": "#6F8883"}
            )
            self.layer = self.viewer.add_empty_vector_layer(
                "Capability Points",
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
            self.populate_points()
            for action in self.actions:
                action.setEnabled(True)
            self.viewer.set_view_extent(Extent(-130, 20, -65, 55))
            self.update_checks()
            self.statusBar().showMessage(
                "Use Begin Edit and Select to see canEdit* capability checks change."
            )
        except Exception as error:
            QMessageBox.critical(self, "CanEditCheck", str(error))

    def populate_points(self) -> None:
        if self.layer < 0:
            return
        if self.viewer.is_layer_editing(self.layer):
            self.viewer.rollback_edit_layer(self.layer)
        self.viewer.begin_edit_layer(self.layer)
        self.viewer.set_active_edit_layer_index(self.layer)
        for i in range(14):
            self.viewer.add_point_to_edit_layer(
                self.layer,
                -121 + i % 7 * 8,
                31 + i // 7 * 5.5,
                {"Name": f"Point {i + 1}"},
            )
        self.viewer.commit_edit_layer(self.layer)
        self.viewer.clear_selected_features()
        self.viewer.set_tool(ViewerTool.PAN)
        self.select_action.setChecked(False)
        self.viewer.refresh_layers()
        self.info.setPlainText(
            "No selected feature.\n\ncanEditSelectedFeatures and canMoveSelectedFeatures require at least one selected feature."
        )
        self.update_checks()

    def begin_edit(self) -> None:
        if self.viewer.begin_edit_layer(self.layer):
            self.viewer.set_active_edit_layer_index(self.layer)
            self.statusBar().showMessage(
                "Edit session started. Select a point to enable selected-feature checks."
            )
        self.update_checks()

    def commit(self) -> None:
        if self.viewer.commit_edit_layer(self.layer):
            self.statusBar().showMessage(
                "Edit session committed. Selection checks are false until editing starts again."
            )
        self.update_checks()

    def rollback(self) -> None:
        if self.viewer.rollback_edit_layer(self.layer):
            self.viewer.clear_selected_features()
            self.statusBar().showMessage("Edit session rolled back.")
        self.update_checks()

    def toggle_select(self, checked: bool) -> None:
        self.viewer.set_tool(ViewerTool.INFO if checked else ViewerTool.PAN)
        self.statusBar().showMessage(
            "Select mode: click a point." if checked else "Pan mode."
        )

    def clear_selection(self) -> None:
        self.viewer.clear_selected_features()
        self.info.setPlainText("No selected feature.")
        self.update_checks()
        self.statusBar().showMessage("Selection cleared.")

    def on_event(self, event) -> None:
        if (
            event.event_type == ViewerEventType.MAP_MOUSE_UP
            and self.select_action.isChecked()
        ):
            x, y = (event.screen_rectangle.left, event.screen_rectangle.top)
            hit = self.viewer.hit_test_top_feature_at(x, y, 8)
            if hit and hit.get("layerIndex", -1) == self.layer:
                self.viewer.select_top_feature_at(x, y, 8)
                self.info.setPlainText(
                    f"Selected feature {hit.get('featureId')}: {hit.get('attributes', {}).get('Name', '')}"
                )
            else:
                self.viewer.clear_selected_features()
                self.info.setPlainText("No selected feature.")
            self.update_checks()
        elif event.event_type in (
            ViewerEventType.SELECTION_CHANGED,
            ViewerEventType.LAYER_EDIT_STATE_CHANGED,
            ViewerEventType.LAYER_EDIT_SESSION_STARTED,
            ViewerEventType.LAYER_EDIT_SESSION_COMMITTED,
            ViewerEventType.LAYER_EDIT_SESSION_ROLLED_BACK,
        ):
            self.update_checks()

    def update_checks(self) -> None:
        if self.layer < 0:
            return
        values = [
            (
                "canEditLayer(index)",
                self.viewer.can_edit_layer(self.layer),
                "Editable vector layer",
            ),
            (
                "canEditSelectedFeatures()",
                self.viewer.can_edit_selected_features(),
                "Editing + selected feature",
            ),
            (
                "canMoveSelectedFeatures()",
                self.viewer.can_move_selected_features(),
                "Editing + movable selection",
            ),
        ]
        for row, (name, result, requirement) in enumerate(values):
            for column, value in enumerate(
                (name, "true" if result else "false", requirement)
            ):
                self.status_table.setItem(row, column, QTableWidgetItem(str(value)))
        editing = self.viewer.is_layer_editing(self.layer)
        self.begin_action.setEnabled(
            not editing and self.viewer.can_edit_layer(self.layer)
        )
        self.commit_action.setEnabled(editing)
        self.rollback_action.setEnabled(editing)
        self.clear_action.setEnabled(self.viewer.selected_feature_count() > 0)

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("CanEditCheck")
    app.setWindowIcon(application_icon())
    window = CanEditCheckWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
