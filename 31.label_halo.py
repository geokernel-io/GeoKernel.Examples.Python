import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

INITIAL_EXTENT = Extent(-180.0, -58.0, 180.0, 82.0)
HALO_COLORS = (
    ("White", "#FFFFFF"),
    ("Black", "#000000"),
    ("Yellow", "#FFF2A8"),
    ("Blue", "#BAE6FD"),
)

class LabelHaloWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.world_layer_index = -1
        self.loading_controls = True

        self.setWindowTitle("LabelHalo")
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

        self.halo_enabled_check = QCheckBox("Halo enabled", panel)
        self.halo_enabled_check.setChecked(True)
        self.halo_color_combo = QComboBox(panel)
        for label, color in HALO_COLORS:
            self.halo_color_combo.addItem(label, color)
        self.halo_color_combo.setCurrentIndex(2)

        self.halo_width_spin = QDoubleSpinBox(panel)
        self.halo_width_spin.setRange(0.5, 8.0)
        self.halo_width_spin.setDecimals(1)
        self.halo_width_spin.setSingleStep(0.5)
        self.halo_width_spin.setValue(2.5)

        self.halo_enabled_check.setEnabled(False)
        self.halo_color_combo.setEnabled(False)
        self.halo_width_spin.setEnabled(False)

        form = QFormLayout()
        form.addRow(self.halo_enabled_check)
        form.addRow("Halo color", self.halo_color_combo)
        form.addRow("Halo width", self.halo_width_spin)

        panel_layout.addWidget(QLabel("Label halo", panel))
        panel_layout.addLayout(form)
        panel_layout.addStretch(1)

        layout.addWidget(panel)
        layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central)

        self.halo_enabled_check.toggled.connect(self.halo_control_changed)
        self.halo_color_combo.currentIndexChanged.connect(self.halo_control_changed)
        self.halo_width_spin.valueChanged.connect(self.halo_control_changed)

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
                title="LabelHalo",
            )
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.world_layer_index = 0
            self.viewer.set_layer_name(self.world_layer_index, "World - label halo")
            self.apply_halo_style()
            self.viewer.set_view_extent(INITIAL_EXTENT)

            self.loading_controls = False
            self.halo_enabled_check.setEnabled(True)
            self.halo_color_combo.setEnabled(True)
            self.halo_width_spin.setEnabled(True)
            self.statusBar().showMessage(
                "Labels use labelHaloEnabled, labelHaloColor and labelHaloWidth."
            )
        except Exception as error:
            self.statusBar().showMessage("World layer could not be loaded.")
            QMessageBox.critical(self, "LabelHalo", str(error))

    def halo_control_changed(self) -> None:
        if self.loading_controls or self.world_layer_index < 0:
            return
        self.apply_halo_style()
        if self.halo_enabled_check.isChecked():
            self.statusBar().showMessage(
                f"Halo color: {self.current_halo_color()}, "
                f"width: {self.halo_width_spin.value():.1f}"
            )
        else:
            self.statusBar().showMessage("Label halo disabled.")

    def apply_halo_style(self) -> None:
        if self.world_layer_index < 0:
            return
        style = {
            "fillColor": "#D8E5E1",
            "fillOpacity": 215,
            "lineColor": "#6F8380",
            "lineWidth": 0.8,
            "showLabels": True,
            "labelField": "COUNTRY",
            "labelFontSize": 12.0,
            "labelColor": "#253238",
            "labelHaloEnabled": self.halo_enabled_check.isChecked(),
            "labelHaloColor": self.current_halo_color(),
            "labelHaloWidth": self.halo_width_spin.value(),
        }
        self.viewer.set_layer_style(self.world_layer_index, style)
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()

    def current_halo_color(self) -> str:
        return str(self.halo_color_combo.currentData())

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("LabelHalo")
    app.setWindowIcon(application_icon())
    window = LabelHaloWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
