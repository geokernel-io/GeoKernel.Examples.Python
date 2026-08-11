import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QMessageBox, QTableWidget, QTableWidgetItem, QToolBar
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

class SelectClearWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.INFO)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("SelectClear")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        toolbar = QToolBar("Selection", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.select_action = QAction(
            QIcon(str(self.icons / "Select.svg")),
            "Select",
            self,
        )
        self.select_action.setCheckable(True)
        self.select_action.setChecked(True)
        self.select_action.triggered.connect(self.activate_select)
        toolbar.addAction(self.select_action)

        self.pan_action = QAction(
            QIcon(str(self.icons / "Pan.svg")),
            "Pan",
            self,
        )
        self.pan_action.setCheckable(True)
        self.pan_action.triggered.connect(self.activate_pan)
        toolbar.addAction(self.pan_action)

        clear_action = QAction(
            QIcon(str(self.icons / "Delete.svg")),
            "Clear Selection",
            self,
        )
        clear_action.triggered.connect(self.clear_selection)
        toolbar.addAction(clear_action)

        full_extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.svg")),
            "Full Extent",
            self,
        )
        full_extent_action.triggered.connect(self.viewer.full_extent)
        toolbar.addAction(full_extent_action)

        self.state_label = QLabel("Selected: 0", toolbar)
        self.state_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(self.state_label)

        self.results = QTableWidget(0, 5, self)
        self.results.setHorizontalHeaderLabels(
            ["#", "Layer", "Feature ID", "Type", "Display"]
        )
        self.results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results.horizontalHeader().setStretchLastSection(True)
        self.results.verticalHeader().setVisible(False)

        results_dock = QDockWidget("Selection set", self)
        results_dock.setWidget(self.results)
        results_dock.setMinimumWidth(360)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, results_dock)

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
            self.update_selection_ui()
            self.statusBar().showMessage("Click features to add them to the selection.")
        except Exception as error:
            QMessageBox.critical(self, "SelectClear", str(error))

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
            title="SelectClear",
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

    def activate_select(self) -> None:
        self.select_action.setChecked(True)
        self.pan_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.INFO)
        self.statusBar().showMessage(
            "Select mode. Click features to add them to the selection."
        )

    def activate_pan(self) -> None:
        self.select_action.setChecked(False)
        self.pan_action.setChecked(True)
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan mode.")

    def clear_selection(self) -> None:
        self.viewer.clear_selected_features()
        self.update_selection_ui()
        self.statusBar().showMessage("Selection cleared.")

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.MAP_MOUSE_UP:
            if self.viewer.get_tool() != ViewerTool.INFO:
                return

            x = event.screen_rectangle.left
            y = event.screen_rectangle.top
            added = self.viewer.add_top_feature_to_selection_at(x, y, 8)
            if added:
                self.statusBar().showMessage("Feature added to the selection.")
            else:
                self.statusBar().showMessage("No feature hit.")
            self.update_selection_ui()
            return

        if event.event_type == ViewerEventType.SELECTION_CHANGED:
            self.update_selection_ui()

    def update_selection_ui(self) -> None:
        selected_features = self.viewer.selected_features()
        self.state_label.setText(f"Selected: {len(selected_features)}")
        self.results.setRowCount(len(selected_features))

        for row, hit in enumerate(selected_features):
            attributes = hit.get("attributes", {})
            display = (
                attributes.get("CITY_NAME")
                or attributes.get("NAME")
                or attributes.get("STATE")
                or "-"
            )
            values = (
                row + 1,
                hit.get("layerName", ""),
                hit.get("featureId", ""),
                hit.get("shapeType", ""),
                display,
            )
            for column, value in enumerate(values):
                self.results.setItem(
                    row,
                    column,
                    QTableWidgetItem(str(value)),
                )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass

        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SelectClear")
    app.setWindowIcon(application_icon())
    window = SelectClearWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
