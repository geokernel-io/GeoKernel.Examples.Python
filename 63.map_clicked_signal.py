import sys
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QAbstractItemView, QDockWidget, QLabel, QMainWindow, QMessageBox, QTableWidget, QTableWidgetItem, QToolBar
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

SHIFT_MODIFIER = 0x02000000
CONTROL_MODIFIER = 0x04000000
ALT_MODIFIER = 0x08000000
META_MODIFIER = 0x10000000

class MapClickedSignalWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.INFO)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("MapClickedSignal")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Tools", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.info_action = QAction(QIcon(str(self.icons / "Select.svg")), "Info", self)
        self.info_action.setCheckable(True)
        self.info_action.setChecked(True)
        self.info_action.triggered.connect(self.activate_info)
        toolbar.addAction(self.info_action)

        self.pan_action = QAction(QIcon(str(self.icons / "Pan.svg")), "Pan", self)
        self.pan_action.setCheckable(True)
        self.pan_action.triggered.connect(self.activate_pan)
        toolbar.addAction(self.pan_action)

        full_extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.svg")), "Full Extent", self
        )
        full_extent_action.triggered.connect(self.viewer.full_extent)
        toolbar.addAction(full_extent_action)

        state_label = QLabel(
            "Signal: MAP_MOUSE_UP(tool, screen point, world point, modifiers)",
            toolbar,
        )
        state_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(state_label)

        self.log_table = QTableWidget(0, 8, self)
        self.log_table.setHorizontalHeaderLabels(
            [
                "Time",
                "Tool",
                "Screen point",
                "World point",
                "Modifiers",
                "Hit layer",
                "Feature ID",
                "Shape type",
            ]
        )
        self.log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.verticalHeader().setVisible(False)

        log_dock = QDockWidget("MAP_MOUSE_UP signal log", self)
        log_dock.setWidget(self.log_table)
        log_dock.setMinimumWidth(500)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, log_dock)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.viewer.resize(
            self.viewer_widget.width(),
            self.viewer_widget.height(),
        )
        self.viewer.show()

        try:
            self.load_layers()
            self.viewer.set_view_extent(Extent(-130.0, 22.0, -65.0, 55.0))
            self.statusBar().showMessage(
                "Click the map to log tool, screen point, world point and modifiers."
            )
        except Exception as error:
            QMessageBox.critical(self, "MapClickedSignal", str(error))

    def sample_path(self, zip_name: str, folder: str, filename: str):
        return ensure_sample_file(
            app=self.app,
            zip_url=(
                "https://github.com/geokernel-io/GeoKernel.SampleData/"
                f"releases/download/v1/{zip_name}"
            ),
            zip_name=zip_name,
            target_folder=folder,
            required_file=filename,
            title="MapClickedSignal",
        )

    def load_layers(self) -> None:
        samples = [
            (
                "world_4326.zip",
                "world_4326",
                "world_4326.shp",
                "World",
                {
                    "fillColor": "#D8E5E1",
                    "fillOpacity": 210,
                    "lineColor": "#708984",
                    "lineWidth": 0.6,
                    "selectedLineColor": "#F59E0B",
                    "selectedLineWidth": 3.0,
                },
            ),
            (
                "usa_states.zip",
                "usa_states",
                "usa_states.shp",
                "USA States",
                {
                    "fillColor": "#C7DEE7",
                    "fillOpacity": 160,
                    "lineColor": "#2D6F8E",
                    "lineWidth": 1.0,
                    "selectedLineColor": "#F59E0B",
                    "selectedLineWidth": 4.0,
                },
            ),
            (
                "world_cities_4326.zip",
                "world_cities_4326",
                "world_cities_4326.shp",
                "Cities",
                {
                    "pointColor": "#D95D39",
                    "lineColor": "#8C321D",
                    "pointSize": 8.0,
                    "lineWidth": 1.0,
                    "selectedLineColor": "#F59E0B",
                    "selectedLineWidth": 4.0,
                    "showLabels": True,
                    "labelField": "NAME",
                    "labelFontSize": 9.0,
                    "labelColor": "#263238",
                    "labelHaloEnabled": True,
                    "labelHaloColor": "#FFFFFF",
                    "labelHaloWidth": 2.0,
                },
            ),
        ]

        for zip_name, folder, filename, name, style in samples:
            path = self.sample_path(zip_name, folder, filename)
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_name(0, name)
            self.viewer.set_layer_style(0, style)

    def activate_info(self) -> None:
        self.info_action.setChecked(True)
        self.pan_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.INFO)
        self.statusBar().showMessage("Info tool active. Click to emit MAP_MOUSE_UP.")

    def activate_pan(self) -> None:
        self.info_action.setChecked(False)
        self.pan_action.setChecked(True)
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan mode.")

    def on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.MAP_MOUSE_UP:
            return

        screen_x = event.screen_rectangle.left
        screen_y = event.screen_rectangle.top
        world_x = event.extent.x_min
        world_y = event.extent.y_min
        modifiers = int(event.double_value)
        tool = self.event_tool(event.int_value)
        hit = self.viewer.hit_test_top_feature_at(screen_x, screen_y, 8)

        self.append_click_log(
            tool,
            screen_x,
            screen_y,
            world_x,
            world_y,
            modifiers,
            hit,
        )

        if hit:
            self.viewer.select_top_feature_at(screen_x, screen_y, 8)
        else:
            self.viewer.clear_selected_features()

        self.statusBar().showMessage(
            f"MAP_MOUSE_UP: tool={self.tool_name(tool)} "
            f"screen=({screen_x:.1f}, {screen_y:.1f}) "
            f"world=({world_x:.6f}, {world_y:.6f}) "
            f"modifiers={self.modifiers_text(modifiers)}"
        )

    def append_click_log(
        self,
        tool,
        screen_x: int,
        screen_y: int,
        world_x: float,
        world_y: float,
        modifiers: int,
        hit,
    ) -> None:
        row = self.log_table.rowCount()
        self.log_table.insertRow(row)
        values = [
            datetime.now().strftime("%H:%M:%S.%f")[:-3],
            self.tool_name(tool),
            f"({screen_x:.1f}, {screen_y:.1f})",
            f"({world_x:.6f}, {world_y:.6f})",
            self.modifiers_text(modifiers),
            hit.get("layerName", "-") if hit else "-",
            hit.get("featureId", "-") if hit else "-",
            self.shape_type_name(hit.get("shapeType")) if hit else "-",
        ]
        for column, value in enumerate(values):
            self.log_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.log_table.scrollToBottom()

    @staticmethod
    def event_tool(value: int):
        try:
            return ViewerTool(value)
        except ValueError:
            return value

    @staticmethod
    def tool_name(tool) -> str:
        names = {
            ViewerTool.PAN: "Pan",
            ViewerTool.ZOOM_BOX: "ZoomBox",
            ViewerTool.INFO: "Info",
            ViewerTool.SELECT: "Select",
            ViewerTool.ADD_POINT: "AddPoint",
            ViewerTool.ADD_POLYLINE: "AddPolyline",
            ViewerTool.ADD_POLYGON: "AddPolygon",
            ViewerTool.MOVE_FEATURE: "MoveFeature",
            ViewerTool.ROUTE: "Route",
            ViewerTool.EDIT_VERTICES: "EditVertices",
        }
        return names.get(tool, "Unknown")

    @staticmethod
    def modifiers_text(modifiers: int) -> str:
        parts = []
        if modifiers & SHIFT_MODIFIER:
            parts.append("Shift")
        if modifiers & CONTROL_MODIFIER:
            parts.append("Ctrl")
        if modifiers & ALT_MODIFIER:
            parts.append("Alt")
        if modifiers & META_MODIFIER:
            parts.append("Meta")
        return "+".join(parts) if parts else "-"

    @staticmethod
    def shape_type_name(shape_type) -> str:
        names = {
            1: "Point",
            3: "Polyline",
            5: "Polygon",
            8: "MultiPoint",
            11: "Point",
            13: "Polyline",
            15: "Polygon",
            18: "MultiPoint",
        }
        if isinstance(shape_type, str) and not shape_type.isdigit():
            return shape_type
        try:
            return names.get(int(shape_type), "Unknown")
        except (TypeError, ValueError):
            return "Unknown"

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MapClickedSignal")
    app.setWindowIcon(application_icon())

    window = MapClickedSignalWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
