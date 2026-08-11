import sys
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QMessageBox, QTableWidget, QTableWidgetItem, QToolBar
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

CONTROL_MODIFIER = 0x04000000

class SelectionSignalWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.INFO)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("SelectionSignal")
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
            QIcon(str(self.icons / "Select.svg")), "Select", self
        )
        self.select_action.setCheckable(True)
        self.select_action.setChecked(True)
        self.select_action.triggered.connect(self.activate_select)
        toolbar.addAction(self.select_action)

        self.pan_action = QAction(QIcon(str(self.icons / "Pan.svg")), "Pan", self)
        self.pan_action.setCheckable(True)
        self.pan_action.triggered.connect(self.activate_pan)
        toolbar.addAction(self.pan_action)

        clear_action = QAction(
            QIcon(str(self.icons / "Delete.svg")), "Clear Selection", self
        )
        clear_action.triggered.connect(self.clear_selection)
        toolbar.addAction(clear_action)

        full_extent_action = QAction(
            QIcon(str(self.icons / "FullExtent.svg")), "Full Extent", self
        )
        full_extent_action.triggered.connect(self.viewer.full_extent)
        toolbar.addAction(full_extent_action)

        self.state_label = QLabel(
            "Selected: 0 | Signal: selectionChanged(int count)", toolbar
        )
        self.state_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(self.state_label)

        self.selection_table = QTableWidget(0, 5, self)
        self.selection_table.setHorizontalHeaderLabels(
            ["#", "Layer", "Feature ID", "Type", "Display"]
        )
        self.selection_table.horizontalHeader().setStretchLastSection(True)
        self.selection_table.verticalHeader().setVisible(False)
        selection_dock = QDockWidget("Selection set", self)
        selection_dock.setWidget(self.selection_table)
        selection_dock.setMinimumWidth(360)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, selection_dock)

        self.signal_table = QTableWidget(0, 3, self)
        self.signal_table.setHorizontalHeaderLabels(["Time", "Signal", "Count"])
        self.signal_table.horizontalHeader().setStretchLastSection(True)
        self.signal_table.verticalHeader().setVisible(False)
        signal_dock = QDockWidget("selectionChanged(int count) log", self)
        signal_dock.setWidget(self.signal_table)
        signal_dock.setMaximumHeight(180)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, signal_dock)

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
            self.update_selection_table()
            self.statusBar().showMessage(
                "Click = add, Ctrl+Click = toggle. Watch selectionChanged log."
            )
        except Exception as error:
            QMessageBox.critical(self, "SelectionSignal", str(error))

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
            title="SelectionSignal",
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
            "Click = add, Ctrl+Click = toggle. Watch selectionChanged log."
        )

    def activate_pan(self) -> None:
        self.select_action.setChecked(False)
        self.pan_action.setChecked(True)
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan mode.")

    def clear_selection(self) -> None:
        self.viewer.clear_selected_features()
        self.update_selection_table()
        self.statusBar().showMessage("clearSelectedFeatures called.")

    def on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.MAP_MOUSE_UP:
            if self.viewer.get_tool() != ViewerTool.INFO:
                return
            x = event.screen_rectangle.left
            y = event.screen_rectangle.top
            modifiers = int(event.double_value)
            if modifiers & CONTROL_MODIFIER:
                changed = self.viewer.toggle_top_feature_selection_at(x, y, 8)
                operation = "toggleSelectedFeature"
            else:
                changed = self.viewer.add_top_feature_to_selection_at(x, y, 8)
                operation = "addSelectedFeature"
            self.statusBar().showMessage(
                f"{operation} succeeded." if changed else "No feature hit."
            )
            self.update_selection_table()
            return

        if event.event_type == ViewerEventType.SELECTION_CHANGED:
            count = self.viewer.selected_feature_count()
            self.append_signal(count)
            self.update_selection_table()
            self.statusBar().showMessage(f"selectionChanged({count})")

    def update_selection_table(self) -> None:
        selected = self.viewer.selected_features()
        self.state_label.setText(
            f"Selected: {len(selected)} | Signal: selectionChanged(int count)"
        )
        self.selection_table.setRowCount(len(selected))
        for row, hit in enumerate(selected):
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
                self.selection_table.setItem(row, column, QTableWidgetItem(str(value)))

    def append_signal(self, count: int) -> None:
        row = self.signal_table.rowCount()
        self.signal_table.insertRow(row)
        values = (
            datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "selectionChanged",
            count,
        )
        for column, value in enumerate(values):
            self.signal_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.signal_table.scrollToBottom()

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SelectionSignal")
    app.setWindowIcon(application_icon())
    window = SelectionSignalWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
