import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMessageBox, QPlainTextEdit, QToolBar
from geokernel import Extent, ShapeType, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

class EditSessionSignalsWindow(QMainWindow):
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
        self.setWindowTitle("EditSessionSignals")
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
        dock = QDockWidget("Edit session signal log", self)
        dock.setWidget(self.log)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

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
                title="EditSessionSignals",
            )
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_style(
                0, {"fillColor": "#D8E5E1", "lineColor": "#6F8883"}
            )
            self.layer = self.viewer.add_empty_vector_layer(
                "Session Signal Points",
                ShapeType.POINT,
                {"pointColor": "#D95D39", "pointSize": 10.0},
            )
            self.viewer.set_view_extent(Extent(-130, 20, -65, 52))
            self.update_actions()
            self.statusBar().showMessage(
                "Begin an edit session, add a feature, then commit or rollback to see session signals."
            )
        except Exception as error:
            QMessageBox.critical(self, "EditSessionSignals", str(error))

    def begin_edit(self) -> None:
        if self.layer >= 0 and self.viewer.begin_edit_layer(self.layer):
            self.viewer.set_active_edit_layer_index(self.layer)
            self.log.appendPlainText(f"call beginEditLayer({self.layer})")
            self.statusBar().showMessage("Edit session started.")
        self.update_actions()

    def add_feature(self) -> None:
        if not self.viewer.is_layer_editing(self.layer):
            self.begin_edit()
        x = -122 + self.cursor % 10 * 5
        y = 29 + self.cursor // 10 * 4
        if self.viewer.add_point_to_edit_layer(self.layer, x, y):
            self.cursor += 1
            self.viewer.refresh_layers()
            self.log.appendPlainText(f"call addPointToEditLayer({self.layer})")
            self.statusBar().showMessage(
                "Feature added inside the active edit session."
            )

    def commit(self) -> None:
        if self.viewer.commit_edit_layer(self.layer):
            self.log.appendPlainText(f"call commitEditLayer({self.layer})")
            self.statusBar().showMessage("Edit session committed.")
        self.update_actions()

    def rollback(self) -> None:
        if self.viewer.rollback_edit_layer(self.layer):
            self.log.appendPlainText(f"call rollbackEditLayer({self.layer})")
            self.statusBar().showMessage("Edit session rolled back.")
        self.update_actions()

    def on_event(self, event) -> None:
        if event.event_type in (
            ViewerEventType.LAYER_EDIT_STATE_CHANGED,
            ViewerEventType.LAYER_EDIT_SESSION_STARTED,
            ViewerEventType.LAYER_EDIT_SESSION_COMMITTED,
            ViewerEventType.LAYER_EDIT_SESSION_ROLLED_BACK,
        ):
            self.log.appendPlainText(f"signal: {event.event_type.name}")
            self.update_actions()

    def update_actions(self) -> None:
        editing = self.layer >= 0 and self.viewer.is_layer_editing(self.layer)
        self.begin_action.setEnabled(self.layer >= 0 and (not editing))
        self.add_action.setEnabled(self.layer >= 0)
        self.commit_action.setEnabled(editing)
        self.rollback_action.setEnabled(editing)

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("EditSessionSignals")
    app.setWindowIcon(application_icon())
    window = EditSessionSignalsWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
