import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QToolBar,
)

from geokernel import Extent, ShapeType, Viewer, ViewerTool

from common import application_icon, ensure_sample_file


RED_LAYER_NAME = "Red Points"
BLUE_LAYER_NAME = "Blue Points"
SAMPLE_EXTENT = Extent(-130.0, 20.0, -65.0, 55.0)


class MultiLayerEditWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.red_layer_index = -1
        self.blue_layer_index = -1
        self.red_cursor = 0
        self.blue_cursor = 0
        self.initialized = False

        self.setWindowTitle("MultiLayerEdit")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_toolbar()
        self.create_info_panel()

    def create_toolbar(self) -> None:
        toolbar = QToolBar("Multi-layer editing", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        active_group = QActionGroup(self)
        active_group.setExclusive(True)

        self.red_action = toolbar.addAction("Active: Red Points")
        self.red_action.setCheckable(True)
        active_group.addAction(self.red_action)

        self.blue_action = toolbar.addAction("Active: Blue Points")
        self.blue_action.setCheckable(True)
        active_group.addAction(self.blue_action)

        toolbar.addSeparator()
        self.add_action = toolbar.addAction("Add To Active Layer")
        self.commit_action = toolbar.addAction("Commit Both")
        self.rollback_action = toolbar.addAction("Rollback Both")
        self.reset_action = toolbar.addAction("Reset")
        toolbar.addSeparator()
        self.extent_action = toolbar.addAction("Full Extent")

        self.state_label = QLabel("Active edit layer: -", toolbar)
        self.state_label.setContentsMargins(12, 0, 12, 0)
        toolbar.addWidget(self.state_label)

        self.red_action.triggered.connect(self.activate_red)
        self.blue_action.triggered.connect(self.activate_blue)
        self.add_action.triggered.connect(self.add_to_active_layer)
        self.commit_action.triggered.connect(self.commit_both)
        self.rollback_action.triggered.connect(self.rollback_both)
        self.reset_action.triggered.connect(
            lambda: self.reset_layers("Both edit layers reset. Red Points is active.")
        )
        self.extent_action.triggered.connect(self.show_extent)

    def create_info_panel(self) -> None:
        self.info_text = QPlainTextEdit(self)
        self.info_text.setReadOnly(True)
        self.info_text.setMinimumWidth(400)
        self.addDockWidget(
            self.info_text_dock_area(),
            self.make_info_dock(),
        )

    def info_text_dock_area(self):
        from PySide6.QtCore import Qt

        return Qt.DockWidgetArea.RightDockWidgetArea

    def make_info_dock(self):
        from PySide6.QtWidgets import QDockWidget

        dock = QDockWidget("MultiLayerEdit sample", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setWidget(self.info_text)
        return dock

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()

        try:
            world_path = ensure_sample_file(
                self.app,
                "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                "world_4326.zip",
                "world_4326",
                "world_4326.shp",
                "MultiLayerEdit",
            )
            self.viewer.add_layer(
                str(world_path), {"buildFeatureSource": True}
            )
            if self.viewer.layer_count() == 0:
                raise RuntimeError(f"World layer could not be loaded: {world_path}")

            self.viewer.set_layer_name(0, "World")
            self.viewer.set_layer_style(0, self.world_style())
            self.create_edit_layers()
            self.begin_both_layers()
            self.set_active_layer(self.red_layer_index)
            self.show_extent()
            self.update_ui(
                "Switch active edit layer, then add points to that layer."
            )
        except Exception as error:
            QMessageBox.critical(self, "MultiLayerEdit", str(error))

    def create_edit_layers(self) -> None:
        red_result = self.viewer.add_empty_vector_layer(
            RED_LAYER_NAME,
            ShapeType.POINT,
            self.point_style("#D95D39", "#8C321D"),
        )
        if red_result < 0:
            raise RuntimeError("Red Points layer could not be created.")
        self.viewer.add_layer_attribute_definition(red_result, "Name", 0, 64, 0)
        self.viewer.add_layer_attribute_definition(red_result, "Layer", 0, 32, 0)

        blue_result = self.viewer.add_empty_vector_layer(
            BLUE_LAYER_NAME,
            ShapeType.POINT,
            self.point_style("#2563EB", "#1E3A8A"),
        )
        if blue_result < 0:
            raise RuntimeError("Blue Points layer could not be created.")
        self.viewer.add_layer_attribute_definition(blue_result, "Name", 0, 64, 0)
        self.viewer.add_layer_attribute_definition(blue_result, "Layer", 0, 32, 0)

        self.resolve_edit_layer_indices()

    def resolve_edit_layer_indices(self) -> None:
        red_info = self.viewer.layer_info_by_name(RED_LAYER_NAME)
        blue_info = self.viewer.layer_info_by_name(BLUE_LAYER_NAME)
        self.red_layer_index = int(red_info.get("index", -1))
        self.blue_layer_index = int(blue_info.get("index", -1))
        if self.red_layer_index < 0 or self.blue_layer_index < 0:
            raise RuntimeError("Editable layer indices could not be resolved.")

    def begin_both_layers(self) -> None:
        self.begin_layer(self.red_layer_index)
        self.begin_layer(self.blue_layer_index)

    def begin_layer(self, layer_index: int) -> None:
        if layer_index >= 0 and not self.viewer.is_layer_editing(layer_index):
            if not self.viewer.begin_edit_layer(layer_index):
                raise RuntimeError(f"BeginEditLayer({layer_index}) failed.")

    def set_active_layer(self, layer_index: int) -> None:
        self.begin_both_layers()
        if layer_index < 0 or not self.viewer.set_active_edit_layer_index(layer_index):
            raise RuntimeError(f"SetActiveEditLayerIndex({layer_index}) failed.")

        self.red_action.setChecked(layer_index == self.red_layer_index)
        self.blue_action.setChecked(layer_index == self.blue_layer_index)
        self.update_ui(f"SetActiveEditLayerIndex({layer_index})")

    def activate_red(self) -> None:
        self.set_active_layer(self.red_layer_index)

    def activate_blue(self) -> None:
        self.set_active_layer(self.blue_layer_index)

    def add_to_active_layer(self) -> None:
        self.begin_both_layers()
        active_index = self.viewer.get_active_edit_layer_index()
        if active_index not in (self.red_layer_index, self.blue_layer_index):
            self.update_ui("No active edit layer.")
            return

        red_active = active_index == self.red_layer_index
        cursor = self.red_cursor if red_active else self.blue_cursor
        point = self.red_point_at(cursor) if red_active else self.blue_point_at(cursor)
        layer_name = RED_LAYER_NAME if red_active else BLUE_LAYER_NAME
        attributes = {
            "Name": f"{layer_name} {cursor + 1}",
            "Layer": layer_name,
        }

        if not self.viewer.add_point_to_edit_layer(
            active_index, point[0], point[1], attributes
        ):
            self.update_ui(f"AddPointToEditLayer({active_index}, ...) failed.")
            return

        if red_active:
            self.red_cursor += 1
        else:
            self.blue_cursor += 1
        self.refresh_map()
        self.update_ui(f"Added point to active layer: {layer_name}.")

    def commit_both(self) -> None:
        selected_index = self.viewer.get_active_edit_layer_index()
        self.commit_if_editing(self.red_layer_index)
        self.commit_if_editing(self.blue_layer_index)
        self.begin_both_layers()
        if selected_index not in (self.red_layer_index, self.blue_layer_index):
            selected_index = self.red_layer_index
        self.set_active_layer(selected_index)
        self.refresh_map()
        self.update_ui("Both edit layers committed and reopened for editing.")

    def rollback_both(self) -> None:
        self.reset_layers("Both edit layers rolled back. Red Points is active.")

    def reset_layers(self, message: str = "Both edit layers reset. Red Points is active.") -> None:
        self.rollback_if_editing(self.red_layer_index)
        self.rollback_if_editing(self.blue_layer_index)
        self.viewer.remove_layer_by_name(RED_LAYER_NAME)
        self.viewer.remove_layer_by_name(BLUE_LAYER_NAME)
        self.red_cursor = 0
        self.blue_cursor = 0
        self.red_layer_index = -1
        self.blue_layer_index = -1
        self.create_edit_layers()
        self.begin_both_layers()
        self.set_active_layer(self.red_layer_index)
        self.refresh_map()
        self.update_ui(message)

    def commit_if_editing(self, layer_index: int) -> None:
        if layer_index >= 0 and self.viewer.is_layer_editing(layer_index):
            if not self.viewer.commit_edit_layer(layer_index):
                raise RuntimeError(f"CommitEditLayer({layer_index}) failed.")

    def rollback_if_editing(self, layer_index: int) -> None:
        if layer_index >= 0 and self.viewer.is_layer_editing(layer_index):
            if not self.viewer.rollback_edit_layer(layer_index):
                raise RuntimeError(f"RollbackEditLayer({layer_index}) failed.")

    def update_ui(self, message: str) -> None:
        if self.red_layer_index < 0 or self.blue_layer_index < 0:
            return
        active_index = self.viewer.get_active_edit_layer_index()
        active_name = (
            RED_LAYER_NAME
            if active_index == self.red_layer_index
            else BLUE_LAYER_NAME
            if active_index == self.blue_layer_index
            else "-"
        )
        red_count = self.viewer.layer_feature_count(self.red_layer_index)
        blue_count = self.viewer.layer_feature_count(self.blue_layer_index)
        self.state_label.setText(
            f"Active edit layer: {active_name} ({active_index}) | "
            f"Red: {red_count} | Blue: {blue_count}"
        )
        self.info_text.setPlainText(
            "\n".join(
                [
                    "MultiLayerEdit sample",
                    "",
                    "Workflow:",
                    "1. Red Points and Blue Points are both editing.",
                    "2. Active layer buttons call SetActiveEditLayerIndex(index).",
                    "3. Add To Active Layer writes to the current active edit layer index.",
                    "4. Commit Both commits both edit sessions and reopens them.",
                    "5. Rollback Both discards uncommitted additions.",
                    "",
                    f"ActiveEditLayerIndex: {active_index}",
                    f"Active layer: {active_name}",
                    f"Red layer index: {self.red_layer_index}",
                    f"Blue layer index: {self.blue_layer_index}",
                    f"Red feature count: {red_count}",
                    f"Blue feature count: {blue_count}",
                    "",
                    "APIs:",
                    "begin_edit_layer(index)",
                    "set_active_edit_layer_index(index)",
                    "get_active_edit_layer_index()",
                    "add_point_to_edit_layer(active_index, x, y, attributes)",
                    "commit_edit_layer(index)",
                    "rollback_edit_layer(index)",
                ]
            )
        )
        self.statusBar().showMessage(message)

    def refresh_map(self) -> None:
        self.viewer.invalidate_render_cache(False, True)
        self.viewer.refresh_layers()

    def show_extent(self) -> None:
        self.viewer.set_view_extent(SAMPLE_EXTENT)

    @staticmethod
    def red_point_at(index: int) -> tuple[float, float]:
        return -124.0 + index % 7 * 7.5, 31.0 + index // 7 * 5.0

    @staticmethod
    def blue_point_at(index: int) -> tuple[float, float]:
        return -121.5 + index % 7 * 7.5, 33.0 + index // 7 * 5.0

    @staticmethod
    def world_style() -> dict[str, object]:
        return {
            "fillColor": "#D8E5E1",
            "fillOpacity": 210,
            "lineColor": "#6F8883",
            "lineWidth": 0.7,
        }

    @staticmethod
    def point_style(point_color: str, line_color: str) -> dict[str, object]:
        return {
            "pointColor": point_color,
            "lineColor": line_color,
            "pointSize": 11.0,
            "lineWidth": 1.3,
            "selectedLineColor": "#F59E0B",
            "selectedLineWidth": 4.0,
            "showLabels": True,
            "labelField": "Name",
            "labelFontSize": 10.0,
            "labelColor": "#263238",
            "labelHaloEnabled": True,
            "labelHaloColor": "#FFFFFF",
            "labelHaloWidth": 2.0,
            "labelOffsetY": -12.0,
            "labelAllowOverlap": True,
        }

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MultiLayerEdit")
    app.setWindowIcon(application_icon())
    window = MultiLayerEditWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
