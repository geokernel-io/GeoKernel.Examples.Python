import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QAbstractItemView, QDockWidget, QLabel, QMainWindow, QMessageBox, QTableWidget, QTableWidgetItem, QToolBar
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

class InfoToolWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.INFO)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("InfoTool")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Info", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.info_action = QAction(
            QIcon(str(self.icons / "Select.png")), "Info Tool", self
        )
        self.info_action.setCheckable(True)
        self.info_action.setChecked(True)
        self.info_action.triggered.connect(self.activate_info)
        toolbar.addAction(self.info_action)

        self.pan_action = QAction(QIcon(str(self.icons / "Pan.png")), "Pan", self)
        self.pan_action.setCheckable(True)
        self.pan_action.triggered.connect(self.activate_pan)
        toolbar.addAction(self.pan_action)

        full_extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.png")), "Full Extent", self
        )
        full_extent_action.triggered.connect(self.viewer.full_extent)
        toolbar.addAction(full_extent_action)

        state_label = QLabel("Tool: ViewerTool.INFO | Signal: MAP_MOUSE_UP", toolbar)
        state_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(state_label)

        self.details_table = QTableWidget(0, 2, self)
        self.details_table.setHorizontalHeaderLabels(["Property / Field", "Value"])
        self.details_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.details_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.details_table.horizontalHeader().setStretchLastSection(True)
        self.details_table.verticalHeader().setVisible(False)

        details_dock = QDockWidget("Info tool click details", self)
        details_dock.setWidget(self.details_table)
        details_dock.setMinimumWidth(380)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)
        self.show_empty_info()

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
                "Info tool is active. Click the map to receive MAP_MOUSE_UP."
            )
        except Exception as error:
            QMessageBox.critical(self, "InfoTool", str(error))

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
            title="InfoTool",
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
        self.statusBar().showMessage("ViewerTool.INFO active. Click the map.")

    def activate_pan(self) -> None:
        self.info_action.setChecked(False)
        self.pan_action.setChecked(True)
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan mode.")

    def on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.MAP_MOUSE_UP:
            return
        if self.viewer.get_tool() != ViewerTool.INFO:
            return

        screen_x = event.screen_rectangle.left
        screen_y = event.screen_rectangle.top
        world_x = event.extent.x_min
        world_y = event.extent.y_min
        hit = self.viewer.hit_test_top_feature_at(screen_x, screen_y, 8)

        if not hit:
            self.viewer.clear_selected_features()
            self.show_click_without_hit(screen_x, screen_y, world_x, world_y)
            self.statusBar().showMessage("MAP_MOUSE_UP received, no feature hit.")
            return

        self.viewer.select_top_feature_at(screen_x, screen_y, 8)
        self.show_info(screen_x, screen_y, world_x, world_y, hit)
        self.statusBar().showMessage(
            f"MAP_MOUSE_UP with ViewerTool.INFO: "
            f"{hit.get('layerName', '-')} feature {hit.get('featureId', '-')}"
        )

    def show_empty_info(self) -> None:
        self.set_rows(
            [("MAP_MOUSE_UP", "Click the map while ViewerTool.INFO is active.")]
        )

    def show_click_without_hit(
        self, screen_x: int, screen_y: int, world_x: float, world_y: float
    ) -> None:
        self.set_rows(
            [
                ("Tool", "ViewerTool.INFO"),
                ("Signal", "MAP_MOUSE_UP"),
                ("Screen point", f"({screen_x:.1f}, {screen_y:.1f})"),
                ("World point", f"({world_x:.6f}, {world_y:.6f})"),
            ]
        )

    def show_info(
        self,
        screen_x: int,
        screen_y: int,
        world_x: float,
        world_y: float,
        hit: dict,
    ) -> None:
        attributes = hit.get("attributes", {})
        rows = [
            ("Tool", "ViewerTool.INFO"),
            ("Signal", "MAP_MOUSE_UP"),
            ("Screen point", f"({screen_x:.1f}, {screen_y:.1f})"),
            ("World point", f"({world_x:.6f}, {world_y:.6f})"),
            ("Layer", hit.get("layerName", "-")),
            ("Feature ID", hit.get("featureId", "-")),
            ("Shape type", hit.get("shapeType", "-")),
            ("Extent", self.extent_text(hit.get("extent"))),
        ]
        rows.extend(sorted(attributes.items(), key=lambda item: item[0]))
        self.set_rows(rows)

    def set_rows(self, rows) -> None:
        self.details_table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            text = "<null>" if value is None else str(value)
            self.details_table.setItem(row, 0, QTableWidgetItem(str(name)))
            self.details_table.setItem(row, 1, QTableWidgetItem(text))

    @staticmethod
    def extent_text(extent) -> str:
        if extent is None:
            return "-"
        if isinstance(extent, dict):
            values = (
                extent.get("xMin", extent.get("x_min")),
                extent.get("yMin", extent.get("y_min")),
                extent.get("xMax", extent.get("x_max")),
                extent.get("yMax", extent.get("y_max")),
            )
        else:
            values = (
                getattr(extent, "x_min", None),
                getattr(extent, "y_min", None),
                getattr(extent, "x_max", None),
                getattr(extent, "y_max", None),
            )
        if any(value is None for value in values):
            return str(extent)
        return "({:.6f}, {:.6f}) - ({:.6f}, {:.6f})".format(*values)

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("InfoTool")
    app.setWindowIcon(application_icon())

    window = InfoToolWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
