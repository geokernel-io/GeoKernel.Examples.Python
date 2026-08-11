import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

INITIAL_EXTENT = Extent(-0.8, -0.2, 11.2, 6.4)
DEFAULT_STYLE = {
    "fillColor": "#AAE5E7EB",
    "fillOpacity": 170,
    "lineColor": "#EB6B7280",
    "lineWidth": 1.2,
}
ZONE_STYLES = {
    "Residential": {
        "fillColor": "#AAF5DFA1",
        "fillOpacity": 170,
        "lineColor": "#EBA16207",
        "lineWidth": 1.2,
    },
    "Commercial": {
        "fillColor": "#AA9DD7F5",
        "fillOpacity": 170,
        "lineColor": "#EB0369A1",
        "lineWidth": 1.2,
    },
    "Industrial": {
        "fillColor": "#AAC4B5FD",
        "fillOpacity": 170,
        "lineColor": "#EB6D28D9",
        "lineWidth": 1.2,
    },
    "Park": {
        "fillColor": "#AA9AD9A8",
        "fillOpacity": 170,
        "lineColor": "#EB15803D",
        "lineWidth": 1.2,
    },
    "Mixed": {
        "fillColor": "#AAFDBA9A",
        "fillOpacity": 170,
        "lineColor": "#EBC2410C",
        "lineWidth": 1.2,
    },
}
PARCELS = (
    ("Parcel A", "Residential", 0.0, 3.0, 3.0, 5.7),
    ("Parcel B", "Commercial", 3.4, 3.3, 6.8, 5.4),
    ("Parcel C", "Industrial", 7.1, 3.1, 10.4, 5.7),
    ("Parcel D", "Park", 1.0, 0.5, 4.8, 2.7),
    ("Parcel E", "Mixed", 5.2, 0.7, 9.8, 2.8),
)

class StylePerFeatureWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.layer_index = -1
        self.loading_selection = False
        self.parcel_states = {
            shape_id: {"name": name, "zone": zone}
            for shape_id, (name, zone, *_bounds) in enumerate(PARCELS, start=1)
        }

        self.setWindowTitle("StylePerFeature")
        self.setWindowIcon(application_icon())
        self.resize(1100, 760)
        self.create_layout()

    def create_layout(self) -> None:
        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        panel = QWidget(central)
        panel.setFixedWidth(250)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)

        self.feature_list = QListWidget(panel)
        self.feature_list.currentRowChanged.connect(self.sync_zone_combo)
        self.zone_combo = QComboBox(panel)
        self.zone_combo.addItems(ZONE_STYLES)
        self.apply_button = QPushButton("Apply Feature Style", panel)
        self.apply_button.clicked.connect(self.apply_selected_zone)
        self.zone_combo.setEnabled(False)
        self.apply_button.setEnabled(False)

        controls = QGroupBox("Selected Feature", panel)
        controls_layout = QVBoxLayout(controls)
        controls_layout.addWidget(QLabel("Zone attribute", controls))
        controls_layout.addWidget(self.zone_combo)
        controls_layout.addWidget(self.apply_button)

        panel_layout.addWidget(QLabel("Feature attributes", panel))
        panel_layout.addWidget(self.feature_list, 1)
        panel_layout.addWidget(controls)

        layout.addWidget(panel)
        layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()

        try:
            rings = [self.parcel_ring(parcel) for parcel in PARCELS]
            self.layer_index = self.viewer.add_polygon_layer(
                "Parcels - style from zone attribute",
                rings,
                DEFAULT_STYLE,
            )
            if self.layer_index < 0:
                raise RuntimeError("Parcel layer could not be created.")

            self.set_initial_attributes()
            self.apply_zone_renderer()
            self.refresh_feature_list(1)
            self.viewer.set_view_extent(INITIAL_EXTENT)
            self.zone_combo.setEnabled(True)
            self.apply_button.setEnabled(True)
            self.statusBar().showMessage(
                "Per-feature style is driven by each shape's zone attribute."
            )
        except Exception as error:
            self.statusBar().showMessage("Per-feature style could not be created.")
            QMessageBox.critical(self, "StylePerFeature", str(error))

    def set_initial_attributes(self) -> None:
        if not self.viewer.begin_edit_layer(self.layer_index):
            raise RuntimeError("Parcel edit session could not be started.")
        try:
            for shape_id, state in self.parcel_states.items():
                if not self.viewer.set_shape_attributes_in_edit_layer(
                    self.layer_index, shape_id, state
                ):
                    raise RuntimeError(
                        f"Attributes could not be assigned to shape {shape_id}."
                    )
            if not self.viewer.commit_edit_layer(self.layer_index):
                raise RuntimeError("Parcel attributes could not be committed.")
        except Exception:
            self.viewer.rollback_edit_layer(self.layer_index)
            raise

    def apply_zone_renderer(self) -> None:
        rules = []
        for zone, style in ZONE_STYLES.items():
            rules.append(
                {
                    "field": "zone",
                    "operator": "equals",
                    "value": zone,
                    "label": zone,
                    "enabled": True,
                    "style": style,
                }
            )

        if not self.viewer.set_layer_symbol_renderer(
            self.layer_index,
            {
                "type": "ruleBased",
                "defaultStyle": DEFAULT_STYLE,
                "rules": rules,
            },
        ):
            raise RuntimeError("Zone rule renderer could not be applied.")

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()

    def refresh_feature_list(self, selected_shape_id: int) -> None:
        self.loading_selection = True
        self.feature_list.clear()
        selected_row = -1
        for row, (shape_id, state) in enumerate(self.parcel_states.items()):
            zone = state["zone"]
            item = QListWidgetItem(
                self.style_icon(ZONE_STYLES.get(zone, DEFAULT_STYLE)),
                f"{state['name']} - {zone}",
            )
            item.setData(Qt.ItemDataRole.UserRole, shape_id)
            self.feature_list.addItem(item)
            if shape_id == selected_shape_id:
                selected_row = row
        self.feature_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
        self.loading_selection = False
        self.sync_zone_combo(self.feature_list.currentRow())

    def sync_zone_combo(self, row: int) -> None:
        if self.loading_selection or row < 0:
            return
        item = self.feature_list.item(row)
        shape_id = int(item.data(Qt.ItemDataRole.UserRole))
        zone = self.parcel_states[shape_id]["zone"]
        index = self.zone_combo.findText(zone, Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            self.zone_combo.setCurrentIndex(index)

    def apply_selected_zone(self) -> None:
        item = self.feature_list.currentItem()
        if item is None or self.layer_index < 0:
            return
        shape_id = int(item.data(Qt.ItemDataRole.UserRole))
        state = self.parcel_states[shape_id]
        zone = self.zone_combo.currentText()

        if not self.viewer.begin_edit_layer(self.layer_index):
            return
        try:
            attributes = {"name": state["name"], "zone": zone}
            if not self.viewer.set_shape_attributes_in_edit_layer(
                self.layer_index, shape_id, attributes
            ):
                raise RuntimeError("Selected feature attributes could not be updated.")
            if not self.viewer.commit_edit_layer(self.layer_index):
                raise RuntimeError("Selected feature update could not be committed.")
        except Exception as error:
            self.viewer.rollback_edit_layer(self.layer_index)
            QMessageBox.critical(self, "StylePerFeature", str(error))
            return

        state["zone"] = zone
        self.apply_zone_renderer()
        self.refresh_feature_list(shape_id)
        self.statusBar().showMessage(
            f"{state['name']} style updated from zone={zone}."
        )

    @staticmethod
    def parcel_ring(parcel: tuple) -> list[tuple[float, float]]:
        _, _, x_min, y_min, x_max, y_max = parcel
        return [
            (x_min, y_min),
            (x_max, y_min),
            (x_max, y_max),
            (x_min, y_max),
            (x_min, y_min),
        ]

    @staticmethod
    def style_icon(style: dict) -> QIcon:
        pixmap = QPixmap(46, 22)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(str(style["lineColor"])), 2.0))
        painter.setBrush(QColor(str(style["fillColor"])))
        painter.drawRect(7, 4, 32, 14)
        painter.end()
        return QIcon(pixmap)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("StylePerFeature")
    app.setWindowIcon(application_icon())
    window = StylePerFeatureWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
