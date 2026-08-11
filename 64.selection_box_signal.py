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

class SelectionBoxSignalWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.SELECT)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.current_hits = []
        self.initialized = False

        self.setWindowTitle("SelectionBoxSignal")
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
            QIcon(str(self.icons / "Select.svg")), "Box Select", self
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

        state_label = QLabel(
            "Signal: MAP_SELECTION_BOX_FINISHED(rect, extent, modifiers)", toolbar
        )
        state_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(state_label)

        self.hits_table = QTableWidget(0, 5, self)
        self.hits_table.setHorizontalHeaderLabels(
            ["#", "Layer", "Feature ID", "Type", "Display"]
        )
        self.configure_table(self.hits_table)
        self.hits_table.currentCellChanged.connect(self.on_current_hit_changed)
        hits_dock = QDockWidget("Selected by box", self)
        hits_dock.setWidget(self.hits_table)
        hits_dock.setMinimumWidth(390)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, hits_dock)

        self.signal_table = QTableWidget(0, 5, self)
        self.signal_table.setHorizontalHeaderLabels(
            ["Time", "Screen rect", "World extent", "Modifiers", "Hit count"]
        )
        self.configure_table(self.signal_table)
        signal_dock = QDockWidget("MAP_SELECTION_BOX_FINISHED log", self)
        signal_dock.setWidget(self.signal_table)
        signal_dock.setMaximumHeight(190)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, signal_dock)

        self.attributes_table = QTableWidget(0, 2, self)
        self.attributes_table.setHorizontalHeaderLabels(["Property / Field", "Value"])
        self.configure_table(self.attributes_table)
        attributes_dock = QDockWidget("Selected hit details", self)
        attributes_dock.setWidget(self.attributes_table)
        attributes_dock.setMaximumHeight(220)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, attributes_dock)
        self.clear_attributes("Drag a selection box to list matching features.")

    @staticmethod
    def configure_table(table: QTableWidget) -> None:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)

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
                "Drag a box with Select to emit MAP_SELECTION_BOX_FINISHED."
            )
        except Exception as error:
            QMessageBox.critical(self, "SelectionBoxSignal", str(error))

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
            title="SelectionBoxSignal",
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
                    "fillOpacity": 155,
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

    def activate_select(self) -> None:
        self.select_action.setChecked(True)
        self.pan_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.SELECT)
        self.statusBar().showMessage("Drag a box to select intersecting features.")

    def activate_pan(self) -> None:
        self.select_action.setChecked(False)
        self.pan_action.setChecked(True)
        self.viewer.set_tool(ViewerTool.PAN)
        self.statusBar().showMessage("Pan mode.")

    def clear_selection(self) -> None:
        self.viewer.clear_selected_features()
        self.current_hits = []
        self.hits_table.setRowCount(0)
        self.clear_attributes("Selection cleared.")
        self.statusBar().showMessage("Selection cleared.")

    def on_viewer_event(self, event) -> None:
        if event.event_type != ViewerEventType.MAP_SELECTION_BOX_FINISHED:
            return

        rect = event.screen_rectangle
        modifiers = int(event.double_value)
        selection_mode = self.selection_mode(modifiers)
        box_hits = self.viewer.hit_test_features_in_screen_rect(
            rect.left,
            rect.top,
            rect.right,
            rect.bottom,
        )
        self.viewer.select_features_in_screen_rect(
            rect.left,
            rect.top,
            rect.right,
            rect.bottom,
            selection_mode,
        )
        hit_count = len(box_hits)
        self.current_hits = self.viewer.selected_features()

        self.append_signal_log(rect, event.extent, modifiers, hit_count)
        self.show_hits()
        if self.current_hits:
            self.hits_table.selectRow(0)
            self.show_attributes(self.current_hits[0])
        else:
            self.clear_attributes("No features intersect the selection box.")

        self.statusBar().showMessage(
            f"MAP_SELECTION_BOX_FINISHED: {self.rect_text(rect)} "
            f"extent={self.extent_text(event.extent)} "
            f"modifiers={self.modifiers_text(modifiers)} hits={hit_count}"
        )

    def show_hits(self) -> None:
        self.hits_table.setRowCount(len(self.current_hits))
        for row, hit in enumerate(self.current_hits):
            attributes = hit.get("attributes", {})
            display = next(
                (
                    attributes[key]
                    for key in (
                        "NAME",
                        "Name",
                        "STATE",
                        "STATE_NAME",
                        "COUNTRY",
                        "ADMIN",
                    )
                    if attributes.get(key) not in (None, "")
                ),
                f"Feature {hit.get('featureId', '-')}",
            )
            values = [
                row + 1,
                hit.get("layerName", "-"),
                hit.get("featureId", "-"),
                self.shape_type_name(hit.get("shapeType")),
                display,
            ]
            for column, value in enumerate(values):
                self.hits_table.setItem(row, column, QTableWidgetItem(str(value)))

    def on_current_hit_changed(self, current_row: int, *_args) -> None:
        if 0 <= current_row < len(self.current_hits):
            self.show_attributes(self.current_hits[current_row])

    def show_attributes(self, hit: dict) -> None:
        attributes = hit.get("attributes", {})
        rows = [
            ("Layer", hit.get("layerName", "-")),
            ("Layer index", hit.get("layerIndex", "-")),
            ("Feature ID", hit.get("featureId", "-")),
            ("Shape type", self.shape_type_name(hit.get("shapeType"))),
            ("Extent", self.extent_text(hit.get("extent"))),
        ]
        rows.extend(sorted(attributes.items(), key=lambda item: item[0]))
        self.set_attribute_rows(rows)

    def clear_attributes(self, message: str) -> None:
        self.set_attribute_rows([("Info", message)])

    def set_attribute_rows(self, rows) -> None:
        self.attributes_table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            text = "<null>" if value is None else str(value)
            self.attributes_table.setItem(row, 0, QTableWidgetItem(str(name)))
            self.attributes_table.setItem(row, 1, QTableWidgetItem(text))

    def append_signal_log(self, rect, extent, modifiers: int, hit_count: int) -> None:
        row = self.signal_table.rowCount()
        self.signal_table.insertRow(row)
        values = [
            datetime.now().strftime("%H:%M:%S.%f")[:-3],
            self.rect_text(rect),
            self.extent_text(extent),
            self.modifiers_text(modifiers),
            hit_count,
        ]
        for column, value in enumerate(values):
            self.signal_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.signal_table.scrollToBottom()

    @staticmethod
    def selection_mode(modifiers: int) -> int:
        if modifiers & CONTROL_MODIFIER:
            return 2
        if modifiers & SHIFT_MODIFIER:
            return 1
        return 0

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
    def rect_text(rect) -> str:
        width = rect.right - rect.left + 1
        height = rect.bottom - rect.top + 1
        return f"left={rect.left} top={rect.top} width={width} height={height}"

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
    app.setApplicationName("SelectionBoxSignal")
    app.setWindowIcon(application_icon())

    window = SelectionBoxSignalWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
