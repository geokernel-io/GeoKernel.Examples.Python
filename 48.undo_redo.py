import sys
from pathlib import Path
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

EXTENT = Extent(-132.0, 18.0, -60.0, 55.0)

class UndoRedoWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.ADD_POINT)
        self.viewer.set_event_callback(self.on_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.layer_index = -1
        self.initialized = False

        self.setWindowTitle("UndoRedo")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Editing", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.add_action = self.create_action(
            "Point.svg",
            "Add Point",
            self.activate_add_point,
        )
        self.undo_action = self.create_action("Undo.svg", "Undo", self.undo)
        self.redo_action = self.create_action("Redo.svg", "Redo", self.redo)
        self.undo_five_action = self.create_action(
            "Undo.svg",
            "Undo 5",
            self.undo_many,
        )
        self.redo_five_action = self.create_action(
            "Redo.svg",
            "Redo 5",
            self.redo_many,
        )
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
            self.add_action,
            self.undo_action,
            self.redo_action,
            self.undo_five_action,
            self.redo_five_action,
            self.reset_action,
            self.full_extent_action,
        )

        for action in self.actions:
            toolbar.addAction(action)
            action.setEnabled(False)

        self.state_label = QLabel(
            "Features: 0 | Undo: no | Redo: no",
            toolbar,
        )
        self.state_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(self.state_label)

    def create_action(self, icon_name: str, text: str, callback) -> QAction:
        action = QAction(QIcon(str(self.icons / icon_name)), text, self)
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
                title="UndoRedo",
            )

            self.viewer.add_layer(str(world_path))
            self.viewer.set_layer_style(
                0,
                {
                    "fillColor": "#D8E5E1",
                    "fillOpacity": 180,
                    "lineColor": "#6F8883",
                },
            )
            self.layer_index = self.viewer.add_empty_vector_layer(
                "Undo Redo Points",
                ShapeType.POINT,
                {
                    "pointColor": "#D95D39",
                    "pointSize": 10.0,
                    "lineColor": "#8C321D",
                },
            )
            self.reset()

            for action in self.actions:
                action.setEnabled(True)

            self.update_state()
            self.viewer.set_view_extent(EXTENT)
            self.statusBar().showMessage(
                "Click the map 5 times, then use Undo/Redo."
            )
        except Exception as error:
            QMessageBox.critical(self, "UndoRedo", str(error))

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

        self.viewer.set_tool(ViewerTool.ADD_POINT)
        self.refresh_viewer()
        self.update_state()
        self.statusBar().showMessage(
            "Reset complete. Click the map to create undoable edit steps."
        )

    def activate_add_point(self) -> None:
        if not self.begin_edit():
            self.statusBar().showMessage("The edit session could not be started.")
            return

        self.viewer.set_tool(ViewerTool.ADD_POINT)
        self.statusBar().showMessage(
            "Add Point active. Click the map to create an undoable step."
        )

    def undo(self) -> None:
        self.run_once(redo=False)

    def redo(self) -> None:
        self.run_once(redo=True)

    def run_once(self, redo: bool) -> None:
        if self.layer_index < 0:
            return

        if redo:
            succeeded = self.viewer.redo_edit_layer(self.layer_index)
            method_name = "redoEditLayer"
        else:
            succeeded = self.viewer.undo_edit_layer(self.layer_index)
            method_name = "undoEditLayer"

        self.refresh_viewer()
        self.update_state()

        result = "succeeded." if succeeded else "has no available step."
        self.statusBar().showMessage(
            f"{method_name}({self.layer_index}) {result}"
        )

    def undo_many(self) -> None:
        self.run_many(redo=False)

    def redo_many(self) -> None:
        self.run_many(redo=True)

    def run_many(self, redo: bool) -> None:
        if self.layer_index < 0:
            return

        completed_count = 0
        for _ in range(5):
            if redo:
                succeeded = self.viewer.redo_edit_layer(self.layer_index)
            else:
                succeeded = self.viewer.undo_edit_layer(self.layer_index)

            if not succeeded:
                break

            completed_count += 1

        self.refresh_viewer()
        self.update_state()

        operation = "redo" if redo else "undo"
        self.statusBar().showMessage(
            f"{operation} called successfully {completed_count} time(s)."
        )

    def on_event(self, event) -> None:
        if event.event_type == ViewerEventType.LAYER_EDIT_STATE_CHANGED:
            self.update_state()

    def update_state(self) -> None:
        if self.layer_index < 0:
            return

        feature_count = self.viewer.layer_feature_count(self.layer_index)
        can_undo = self.viewer.can_undo_edit_layer(self.layer_index)
        can_redo = self.viewer.can_redo_edit_layer(self.layer_index)

        self.state_label.setText(
            f"Features: {feature_count} | "
            f"Undo: {'yes' if can_undo else 'no'} | "
            f"Redo: {'yes' if can_redo else 'no'}"
        )
        self.undo_action.setEnabled(can_undo)
        self.undo_five_action.setEnabled(can_undo)
        self.redo_action.setEnabled(can_redo)
        self.redo_five_action.setEnabled(can_redo)

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
    app.setApplicationName("UndoRedo")
    app.setWindowIcon(application_icon())

    window = UndoRedoWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
