import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QToolBar, QVBoxLayout, QWidget
from geokernel import Extent, GeoKernelError, Viewer, ViewerEventType, ViewerTool
from common import ensure_sample_file

INITIAL_EXTENT = Extent(-151.2, 16.4, -41.6, 55.6)
WORLD_STYLE = {"fillColor": "#D8E5E1", "fillOpacity": 220, "lineColor": "#6F8883", "lineWidth": 0.8}

class MultiWindowSyncWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icon_dir = Path(__file__).resolve().parent / "images"
        self.left_viewer = Viewer()
        self.right_viewer = Viewer()
        self.left_viewer.set_tool(ViewerTool.PAN)
        self.right_viewer.set_tool(ViewerTool.PAN)
        self.left_widget = self.left_viewer.qt_widget()
        self.right_widget = self.right_viewer.qt_widget()
        self.synchronizing = False
        self.closing = False
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("MultiWindowSync")
        self.resize(1200, 800)
        self.create_layout()
        self.create_toolbar()
        self.left_viewer.set_event_callback(self.on_left_viewer_event)
        self.right_viewer.set_event_callback(self.on_right_viewer_event)

    def create_layout(self) -> None:
        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addWidget(self.create_viewer_pane("Viewer A", self.left_widget), 1)
        layout.addWidget(self.create_viewer_pane("Viewer B", self.right_widget), 1)
        self.setCentralWidget(central)

    def create_viewer_pane(self, title: str, viewer_widget: QWidget) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        label = QLabel(title, pane)
        label.setFixedHeight(28)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background:#eef2f1; border-bottom:1px solid #c7d1ce;")
        layout.addWidget(label)
        layout.addWidget(viewer_widget, 1)
        return pane

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        self.sync_action = toolbar.addAction("Sync ON")
        self.sync_action.setCheckable(True)
        self.sync_action.setChecked(True)
        self.sync_action.toggled.connect(self.update_sync_text)
        toolbar.addSeparator()
        self.zoom_in_action = self.add_tool(toolbar, "ZoomIn.png", "Zoom In", self.zoom_in)
        self.zoom_out_action = self.add_tool(toolbar, "ZoomOut.png", "Zoom Out", self.zoom_out)
        self.full_extent_action = self.add_tool(toolbar, "FullExtent.png", "Full Extent", self.full_extent)
        self.zoom_box_action = self.add_tool(toolbar, "RectangularZoom.png", "Zoom Box", self.activate_zoom_box)
        self.pan_action = self.add_tool(toolbar, "Pan.png", "Pan", self.activate_pan)
        self.zoom_box_action.setCheckable(True)
        self.pan_action.setCheckable(True)
        self.pan_action.setChecked(True)
        group = QActionGroup(self)
        group.setExclusive(True)
        group.addAction(self.zoom_box_action)
        group.addAction(self.pan_action)
        self.navigation_actions = (self.zoom_in_action, self.zoom_out_action, self.full_extent_action, self.zoom_box_action, self.pan_action)
        for action in self.navigation_actions:
            action.setEnabled(False)

    def add_tool(self, toolbar: QToolBar, icon_name: str, text: str, callback) -> QAction:
        action = QAction(QIcon(str(self.icon_dir.joinpath(icon_name))), text, self)
        action.triggered.connect(callback)
        toolbar.addAction(action)
        return action

    def initialize_viewers(self) -> None:
        for viewer, widget in ((self.left_viewer, self.left_widget), (self.right_viewer, self.right_widget)):
            viewer.resize(widget.width(), widget.height())
            viewer.show()
        try:
            path = ensure_sample_file(app=self.app, zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip", zip_name="world_4326.zip", target_folder="world_4326", required_file="world_4326.shp", title="MultiWindowSync")
            self.load_world(self.left_viewer, path, "World A")
            self.load_world(self.right_viewer, path, "World B")
            self.left_viewer.set_view_extent(INITIAL_EXTENT)
            self.right_viewer.set_view_extent(INITIAL_EXTENT)
            for action in self.navigation_actions:
                action.setEnabled(True)
        except Exception as error:
            QMessageBox.critical(self, "MultiWindowSync", f"Layers could not be loaded:\n\n{error}")

    def load_world(self, viewer: Viewer, path: Path, name: str) -> None:
        viewer.add_layer(str(path))
        viewer.set_layer_name(0, name)
        viewer.set_layer_style(0, WORLD_STYLE)
        viewer.refresh_layers()

    def update_sync_text(self, checked: bool) -> None:
        self.sync_action.setText("Sync ON" if checked else "Sync OFF")
        if checked:
            self.copy_extent(self.left_viewer, self.right_viewer)

    def zoom_in(self) -> None:
        self.left_viewer.zoom_in()

    def zoom_out(self) -> None:
        self.left_viewer.zoom_out()

    def full_extent(self) -> None:
        self.left_viewer.full_extent()

    def activate_zoom_box(self) -> None:
        self.left_viewer.set_tool(ViewerTool.ZOOM_BOX)
        self.right_viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.left_viewer.set_tool(ViewerTool.PAN)
        self.right_viewer.set_tool(ViewerTool.PAN)

    def on_left_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.VISIBLE_EXTENT_CHANGED:
            self.copy_extent(self.left_viewer, self.right_viewer)

    def on_right_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.VISIBLE_EXTENT_CHANGED:
            self.copy_extent(self.right_viewer, self.left_viewer)

    def copy_extent(self, source: Viewer, target: Viewer) -> None:
        if self.closing or not self.sync_action.isChecked() or self.synchronizing:
            return
        try:
            extent = source.get_view_extent()
        except GeoKernelError:
            return
        if extent is None:
            return
        self.synchronizing = True
        try:
            try:
                target.set_view_extent(Extent(extent.x_min, extent.y_min, extent.x_max, extent.y_max))
            except GeoKernelError:
                return
        finally:
            self.synchronizing = False

    def closeEvent(self, event) -> None:
        self.closing = True
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("MultiWindowSync")
    app.setWindowIcon(icon)
    window = MultiWindowSyncWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewers)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
