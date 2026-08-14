import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QMessageBox, QTableWidget, QTableWidgetItem, QToolBar
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

class FeatureAttributesWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.INFO)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("FeatureAttributes")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Selection", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.inspect_action = QAction(
            QIcon(str(self.icons / "Select.png")),
            "Feature Attributes",
            self,
        )
        self.inspect_action.setCheckable(True)
        self.inspect_action.setChecked(True)
        self.inspect_action.triggered.connect(self.activate_inspect)
        toolbar.addAction(self.inspect_action)

        self.pan_action = QAction(QIcon(str(self.icons / "Pan.png")), "Pan", self)
        self.pan_action.setCheckable(True)
        self.pan_action.triggered.connect(self.activate_pan)
        toolbar.addAction(self.pan_action)

        full_extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.png")), "Full Extent", self
        )
        full_extent_action.triggered.connect(self.viewer.full_extent)
        toolbar.addAction(full_extent_action)

        state_label = QLabel("API: FeatureHitTestResult.attributes", toolbar)
        state_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(state_label)

        self.attributes_table = QTableWidget(0, 2, self)
        self.attributes_table.setHorizontalHeaderLabels(["Field", "Value"])
        self.attributes_table.horizontalHeader().setStretchLastSection(True)
        self.attributes_table.verticalHeader().setVisible(False)

        dock = QDockWidget("Attributes", self)
        dock.setWidget(self.attributes_table)
        dock.setMinimumWidth(380)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.show_empty_attributes()

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
                "Click a feature to show all attribute values."
            )
        except Exception as error:
            QMessageBox.critical(self, "FeatureAttributes", str(error))

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
            title="FeatureAttributes",
        )

    def load_layers(self) -> None:
        samples = [
            (
                "world_4326.zip",
                "world_4326",
                "world_4326.shp",
                "World",
                {"fillColor": "#D8E5E1", "lineColor": "#708984"},
            ),
            (
                "usa_states.zip",
                "usa_states",
                "usa_states.shp",
                "States",
                {
                    "fillColor": "#C7DEE7",
                    "fillOpacity": 160,
                    "lineColor": "#2D6F8E",
                },
            ),
            (
                "world_cities_4326.zip",
                "world_cities_4326",
                "world_cities_4326.shp",
                "Cities",
                {"pointColor": "#D95D39", "pointSize": 8.0},
            ),
        ]

        for zip_name, folder, filename, name, style in samples:
            path = self.sample_path(zip_name, folder, filename)
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_name(0, name)
            self.viewer.set_layer_style(0, style)

    def activate_inspect(self) -> None:
        self.inspect_action.setChecked(True)
        self.pan_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.INFO)
        self.statusBar().showMessage("Click a feature to read its attributes.")

    def activate_pan(self) -> None:
        self.inspect_action.setChecked(False)
        self.pan_action.setChecked(True)
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan mode.")

    def on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.MAP_MOUSE_UP:
            return
        if self.viewer.get_tool() != ViewerTool.INFO:
            return

        x = event.screen_rectangle.left
        y = event.screen_rectangle.top
        hit = self.viewer.hit_test_top_feature_at(x, y, 8)
        if not hit:
            self.viewer.clear_selected_features()
            self.show_empty_attributes()
            self.statusBar().showMessage("No feature hit.")
            return

        self.viewer.select_top_feature_at(x, y, 8)
        self.show_attributes(hit)
        attributes = hit.get("attributes", {})
        self.statusBar().showMessage(
            f"attributes returned {len(attributes)} field(s) for "
            f"{hit.get('layerName', '-')} feature {hit.get('featureId', '-')}."
        )

    def show_empty_attributes(self) -> None:
        self.attributes_table.setRowCount(1)
        self.attributes_table.setItem(0, 0, QTableWidgetItem("Attributes"))
        self.attributes_table.setItem(
            0,
            1,
            QTableWidgetItem("Click a feature to read its attribute values."),
        )

    def show_attributes(self, hit: dict) -> None:
        attributes = hit.get("attributes", {})
        fixed_values = [
            ("Layer", hit.get("layerName", "-")),
            ("Layer index", hit.get("layerIndex", "-")),
            ("Shape ID", hit.get("shapeId", "-")),
            ("Feature ID", hit.get("featureId", "-")),
            ("Shape type", hit.get("shapeType", "-")),
            ("attributes count", len(attributes)),
        ]
        attribute_values = sorted(attributes.items(), key=lambda item: item[0])
        rows = fixed_values + attribute_values
        self.attributes_table.setRowCount(len(rows))

        for row, (field, value) in enumerate(rows):
            self.attributes_table.setItem(row, 0, QTableWidgetItem(str(field)))
            self.attributes_table.setItem(row, 1, QTableWidgetItem(str(value)))

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("FeatureAttributes")
    app.setWindowIcon(application_icon())

    window = FeatureAttributesWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
