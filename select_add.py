import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDockWidget,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
)
from geokernel import Extent, Viewer, ViewerEventType, ViewerTool

from common import application_icon, ensure_sample_file


CONTROL_MODIFIER = 0x04000000
IMAGES_DIR = Path(__file__).resolve().parent / "images"


class SelectAddWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("SelectAdd")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.statusBar().showMessage(
            "Click a feature to add it to the selection. Ctrl+Click toggles it."
        )

        self._build_ui()
        self.viewer.set_event_callback(self._on_viewer_event)
        self.viewer.set_tool(ViewerTool.INFO)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.viewer.resize(
            self.viewer_widget.width(),
            self.viewer_widget.height(),
        )
        self.viewer.show()

        if not self._load_layers():
            return

        self.viewer.set_view_extent(Extent(-130.0, 22.0, -65.0, 55.0))
        self._update_selection_table()

    def _build_ui(self) -> None:
        self.setCentralWidget(self.viewer_widget)

        toolbar = QToolBar("Selection", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.select_action = QAction(
            QIcon(str(IMAGES_DIR / "Select.png")), "Select Add", self
        )
        self.select_action.setCheckable(True)
        self.select_action.setChecked(True)
        self.select_action.triggered.connect(self._activate_select)
        toolbar.addAction(self.select_action)

        self.pan_action = QAction(QIcon(str(IMAGES_DIR / "Pan.png")), "Pan", self)
        self.pan_action.setCheckable(True)
        self.pan_action.triggered.connect(self._activate_pan)
        toolbar.addAction(self.pan_action)

        clear_action = QAction(
            QIcon(str(IMAGES_DIR / "Delete.png")), "Clear Selection", self
        )
        clear_action.triggered.connect(self._clear_selection)
        toolbar.addAction(clear_action)

        full_extent_action = QAction(
            QIcon(str(IMAGES_DIR / "FullExtent.png")), "Full Extent", self
        )
        full_extent_action.triggered.connect(self.viewer.full_extent)
        toolbar.addAction(full_extent_action)

        self.state_label = QLabel(self)
        self.state_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(self.state_label)

        self.selection_table = QTableWidget(0, 5, self)
        self.selection_table.setHorizontalHeaderLabels(
            ["#", "Layer", "Feature ID", "Type", "Display"]
        )
        self.selection_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.selection_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.selection_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.selection_table.horizontalHeader().setStretchLastSection(True)
        self.selection_table.verticalHeader().setVisible(False)

        selection_dock = QDockWidget("Selection set", self)
        selection_dock.setWidget(self.selection_table)
        self.addDockWidget(Qt.RightDockWidgetArea, selection_dock)

    def _sample_path(self, zip_name: str, folder: str, filename: str):
        return ensure_sample_file(
            app=self.app,
            zip_url=(
                "https://github.com/geokernel-io/GeoKernel.SampleData/"
                f"releases/download/v1/{zip_name}"
            ),
            zip_name=zip_name,
            target_folder=folder,
            required_file=filename,
            title="SelectAdd",
        )

    def _load_layers(self) -> bool:
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
                "cities_4326.zip",
                "cities_4326",
                "cities_4326.shp",
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
                    "labelMinVisibleScale": 0.0,
                    "labelMaxVisibleScale": 0.0,
                },
            ),
        ]

        for zip_name, folder, filename, display_name, style in samples:
            try:
                path = self._sample_path(zip_name, folder, filename)
                self.viewer.add_layer(str(path))
                self.viewer.set_layer_name(0, display_name)
                self.viewer.set_layer_style(0, style)
            except Exception as error:
                QMessageBox.critical(
                    self,
                    "SelectAdd",
                    f"Layer could not be loaded:\n{error}",
                )
                return False

        return True

    def _activate_select(self, checked: bool) -> None:
        if checked:
            self.pan_action.setChecked(False)
            self.viewer.set_tool(ViewerTool.INFO)
            self.statusBar().showMessage("Click = add, Ctrl+Click = toggle.")
        elif self.viewer.get_tool() == ViewerTool.INFO:
            self.select_action.setChecked(True)

    def _activate_pan(self, checked: bool) -> None:
        if checked:
            self.select_action.setChecked(False)
            self.viewer.set_tool(ViewerTool.PAN)
            self.statusBar().showMessage("Pan mode.")
        elif self.viewer.get_tool() == ViewerTool.PAN:
            self.pan_action.setChecked(True)

    def _clear_selection(self) -> None:
        self.viewer.clear_selected_features()
        self._update_selection_table()
        self.statusBar().showMessage("Selection cleared.")

    def _on_viewer_event(self, event) -> None:
        if event.event_type == ViewerEventType.SELECTION_CHANGED:
            self._update_selection_table()
            return

        if event.event_type != ViewerEventType.MAP_MOUSE_UP:
            return
        if self.viewer.get_tool() != ViewerTool.INFO:
            return

        screen_x = event.screen_rectangle.left
        screen_y = event.screen_rectangle.top
        modifiers = int(event.double_value)
        hit = self.viewer.hit_test_top_feature_at(screen_x, screen_y, 8)
        if not hit:
            self.statusBar().showMessage("No feature hit.")
            return

        if modifiers & CONTROL_MODIFIER:
            changed = self.viewer.toggle_top_feature_selection_at(
                screen_x, screen_y, 8
            )
            operation = "toggleSelectedFeature"
        else:
            changed = self.viewer.add_top_feature_to_selection_at(
                screen_x, screen_y, 8
            )
            operation = "addSelectedFeature"

        if changed:
            layer_name = hit.get("layerName", hit.get("layer", "-"))
            feature_id = hit.get("featureId", "-")
            self.statusBar().showMessage(
                f"{operation}: {layer_name} feature {feature_id}"
            )
        else:
            self.statusBar().showMessage("No feature hit.")

        self._update_selection_table()

    def _update_selection_table(self) -> None:
        selected = self.viewer.selected_features()
        self.state_label.setText(
            "Selected: "
            f"{len(selected)} | Click = addSelectedFeature | "
            "Ctrl+Click = toggleSelectedFeature"
        )
        self.selection_table.setRowCount(len(selected))

        for row, hit in enumerate(selected):
            attributes = hit.get("attributes", {})
            display = self._display_name(attributes, hit.get("featureId", "-"))
            values = (
                row + 1,
                hit.get("layerName", hit.get("layer", "-")),
                hit.get("featureId", "-"),
                self._shape_type_name(hit.get("shapeType", hit.get("type"))),
                display,
            )
            for column, value in enumerate(values):
                self.selection_table.setItem(
                    row, column, QTableWidgetItem(str(value))
                )

        self.selection_table.resizeColumnsToContents()
        self.selection_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch
        )

    @staticmethod
    def _display_name(attributes: dict, feature_id) -> str:
        for key in ("NAME", "Name", "STATE", "STATE_NAME", "COUNTRY", "ADMIN"):
            value = attributes.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return f"Feature {feature_id}"

    @staticmethod
    def _shape_type_name(shape_type) -> str:
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


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SelectAdd")
    app.setWindowIcon(application_icon())
    window = SelectAddWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
