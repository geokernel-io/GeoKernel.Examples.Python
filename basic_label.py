import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

INITIAL_EXTENT = Extent(-180.0, -58.0, 180.0, 82.0)

class BasicLabelWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.world_layer_index = -1
        self.loading_controls = True

        self.setWindowTitle("BasicLabel")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_layout()

    def create_layout(self) -> None:
        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        panel = QWidget(central)
        panel.setFixedWidth(230)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)

        self.show_labels_check = QCheckBox("Show labels", panel)
        self.show_labels_check.setChecked(True)
        self.field_combo = QComboBox(panel)
        self.font_size_spin = QDoubleSpinBox(panel)
        self.font_size_spin.setRange(5.0, 32.0)
        self.font_size_spin.setDecimals(1)
        self.font_size_spin.setSingleStep(1.0)
        self.font_size_spin.setValue(12.0)

        self.show_labels_check.setEnabled(False)
        self.field_combo.setEnabled(False)
        self.font_size_spin.setEnabled(False)

        form = QFormLayout()
        form.addRow(self.show_labels_check)
        form.addRow("Label field", self.field_combo)
        form.addRow("Font size", self.font_size_spin)

        panel_layout.addWidget(QLabel("Label style", panel))
        panel_layout.addLayout(form)
        panel_layout.addStretch(1)

        layout.addWidget(panel)
        layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central)

        self.show_labels_check.toggled.connect(self.label_control_changed)
        self.field_combo.currentTextChanged.connect(self.label_control_changed)
        self.font_size_spin.valueChanged.connect(self.label_control_changed)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.statusBar().showMessage("Preparing world sample data...")

        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="BasicLabel",
            )
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.world_layer_index = 0
            self.viewer.set_layer_name(self.world_layer_index, "World - labels")
            self.populate_label_fields()
            self.apply_label_style()
            self.viewer.set_view_extent(INITIAL_EXTENT)

            self.loading_controls = False
            self.show_labels_check.setEnabled(True)
            self.field_combo.setEnabled(True)
            self.font_size_spin.setEnabled(True)
            self.statusBar().showMessage(
                "Labels use showLabels, labelField and labelFontSize."
            )
        except Exception as error:
            self.statusBar().showMessage("World layer could not be loaded.")
            QMessageBox.critical(self, "BasicLabel", str(error))

    def populate_label_fields(self) -> None:
        self.field_combo.clear()
        for definition in self.viewer.layer_attribute_definitions(
            self.world_layer_index
        ):
            name = str(definition.get("name", "")).strip()
            if name:
                self.field_combo.addItem(name)

        if self.field_combo.count() == 0:
            raise RuntimeError("No label fields were found in the world layer schema.")
        country_index = self.field_combo.findText("COUNTRY")
        self.field_combo.setCurrentIndex(country_index if country_index >= 0 else 0)

    def label_control_changed(self) -> None:
        if self.loading_controls or self.world_layer_index < 0:
            return
        self.apply_label_style()
        if self.show_labels_check.isChecked():
            self.statusBar().showMessage(
                f"Label field: {self.field_combo.currentText()}, "
                f"font size: {self.font_size_spin.value():.1f}"
            )
        else:
            self.statusBar().showMessage("Labels disabled.")

    def apply_label_style(self) -> None:
        if self.world_layer_index < 0 or not self.field_combo.currentText():
            return
        style = {
            "fillColor": "#D8E5E1",
            "fillOpacity": 215,
            "lineColor": "#6F8380",
            "lineWidth": 0.8,
            "showLabels": self.show_labels_check.isChecked(),
            "labelField": self.field_combo.currentText(),
            "labelFontSize": self.font_size_spin.value(),
            "labelColor": "#FFFF00",
            "labelHaloEnabled": True,
            "labelHaloColor": "#000000",
            "labelHaloWidth": 2.0,
        }
        self.viewer.set_layer_style(self.world_layer_index, style)
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BasicLabel")
    app.setWindowIcon(application_icon())
    window = BasicLabelWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
