import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMessageBox, QPlainTextEdit, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

class EditDirtyStateWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_event)
        self.widget = self.viewer.qt_widget()
        self.layer = -1
        self.cursor = 0
        self.initialized = False
        self.setWindowTitle("EditDirtyState")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.widget)
        self.create_ui()

    def create_ui(self) -> None:
        bar = QToolBar("Edit session", self)
        bar.setMovable(False)
        self.addToolBar(bar)
        self.begin_action = bar.addAction("Begin Edit")
        self.add_action = bar.addAction("Add Feature")
        self.commit_action = bar.addAction("Commit Edit")
        self.rollback_action = bar.addAction("Rollback Edit")
        self.extent_action = bar.addAction("Full Extent")
        self.begin_action.triggered.connect(self.begin_edit)
        self.add_action.triggered.connect(self.add_feature)
        self.commit_action.triggered.connect(self.commit)
        self.rollback_action.triggered.connect(self.rollback)
        self.extent_action.triggered.connect(self.viewer.full_extent)
        self.log = QPlainTextEdit(self)
        self.log.setReadOnly(True)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.make_dock("Dirty state log", self.log),
        )

    def make_dock(self, title, widget):
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        return dock

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
                title="EditDirtyState",
            )
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_style(
                0, {"fillColor": "#D8E5E1", "lineColor": "#6F8883"}
            )
            self.layer = self.viewer.add_empty_vector_layer(
                "Dirty State Points",
                ShapeType.POINT,
                {"pointColor": "#D95D39", "pointSize": 10.0},
            )
            self.viewer.set_view_extent(Extent(-130, 20, -65, 52))
            self.update_state()
            self.statusBar().showMessage(
                "Use Add Feature to turn isLayerDirty on, then commit or rollback."
            )
        except Exception as error:
            QMessageBox.critical(self, "EditDirtyState", str(error))

    def begin_edit(self) -> None:
        if self.layer >= 0 and self.viewer.begin_edit_layer(self.layer):
            self.viewer.set_active_edit_layer_index(self.layer)
            self.append("beginEditLayer")
            self.statusBar().showMessage(
                "Edit session started. Dirty is still false until a change is made."
            )
        self.update_state()

    def add_feature(self) -> None:
        if not self.viewer.is_layer_editing(self.layer):
            self.begin_edit()
        x = -122 + self.cursor % 10 * 5
        y = 29 + self.cursor // 10 * 4
        if self.viewer.add_point_to_edit_layer(self.layer, x, y):
            self.cursor += 1
            self.viewer.refresh_layers()
            self.append(f"addPointToEditLayer({self.layer})")
            self.append(f"isLayerDirty={self.viewer.is_layer_dirty(self.layer)}")
            self.statusBar().showMessage(
                "Feature added. isLayerDirty(index) is now true."
            )
        self.update_state()

    def commit(self) -> None:
        if self.viewer.commit_edit_layer(self.layer):
            self.append(f"commitEditLayer({self.layer})")
            self.append(f"isLayerDirty={self.viewer.is_layer_dirty(self.layer)}")
            self.statusBar().showMessage(
                "Edit committed. isLayerDirty(index) returned to false."
            )
        self.update_state()

    def rollback(self) -> None:
        if self.viewer.rollback_edit_layer(self.layer):
            self.append(f"rollbackEditLayer({self.layer})")
            self.append(f"isLayerDirty={self.viewer.is_layer_dirty(self.layer)}")
            self.statusBar().showMessage(
                "Edit rolled back. isLayerDirty(index) returned to false."
            )
        self.update_state()

    def on_event(self, event) -> None:
        if event.event_type in (
            ViewerEventType.LAYER_EDIT_STATE_CHANGED,
            ViewerEventType.LAYER_EDIT_SESSION_STARTED,
            ViewerEventType.LAYER_EDIT_SESSION_COMMITTED,
            ViewerEventType.LAYER_EDIT_SESSION_ROLLED_BACK,
        ):
            self.append(f"signal: {event.event_type.name}")
            self.update_state()

    def append(self, text) -> None:
        self.log.appendPlainText(text)

    def update_state(self) -> None:
        editing = self.layer >= 0 and self.viewer.is_layer_editing(self.layer)
        self.begin_action.setEnabled(self.layer >= 0 and (not editing))
        self.add_action.setEnabled(self.layer >= 0)
        self.commit_action.setEnabled(editing)
        self.rollback_action.setEnabled(editing)
        if self.layer >= 0:
            self.setWindowTitle(
                f"EditDirtyState - Editing: {('ON' if editing else 'OFF')} | Dirty: {self.viewer.is_layer_dirty(self.layer)}"
            )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("EditDirtyState")
    app.setWindowIcon(application_icon())
    window = EditDirtyStateWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
