import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

INITIAL_EXTENT = Extent(-180.0, -58.0, 180.0, 82.0)

class LabelOffsetWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.world_layer_index = -1
        self.loading_controls = True

        self.setWindowTitle("LabelOffset")
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

        self.offset_x_spin = QDoubleSpinBox(panel)
        self.offset_x_spin.setRange(-80.0, 80.0)
        self.offset_x_spin.setDecimals(1)
        self.offset_x_spin.setSingleStep(2.0)
        self.offset_x_spin.setValue(0.0)

        self.offset_y_spin = QDoubleSpinBox(panel)
        self.offset_y_spin.setRange(-80.0, 80.0)
        self.offset_y_spin.setDecimals(1)
        self.offset_y_spin.setSingleStep(2.0)
        self.offset_y_spin.setValue(0.0)

        self.reset_button = QPushButton("Reset Offset", panel)
        self.offset_x_spin.setEnabled(False)
        self.offset_y_spin.setEnabled(False)
        self.reset_button.setEnabled(False)

        form = QFormLayout()
        form.addRow("Offset X", self.offset_x_spin)
        form.addRow("Offset Y", self.offset_y_spin)

        panel_layout.addWidget(QLabel("Label offset", panel))
        panel_layout.addLayout(form)
        panel_layout.addWidget(self.reset_button)
        panel_layout.addStretch(1)

        layout.addWidget(panel)
        layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central)

        self.offset_x_spin.valueChanged.connect(self.offset_control_changed)
        self.offset_y_spin.valueChanged.connect(self.offset_control_changed)
        self.reset_button.clicked.connect(self.reset_offset)

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
                title="LabelOffset",
            )
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.world_layer_index = 0
            self.viewer.set_layer_name(self.world_layer_index, "World - label offset")
            self.apply_offset_style()
            self.viewer.set_view_extent(INITIAL_EXTENT)

            self.loading_controls = False
            self.offset_x_spin.setEnabled(True)
            self.offset_y_spin.setEnabled(True)
            self.reset_button.setEnabled(True)
            self.statusBar().showMessage(
                "Labels use labelOffsetX and labelOffsetY."
            )
        except Exception as error:
            self.statusBar().showMessage("World layer could not be loaded.")
            QMessageBox.critical(self, "LabelOffset", str(error))

    def offset_control_changed(self) -> None:
        if self.loading_controls or self.world_layer_index < 0:
            return
        self.apply_offset_style()
        self.statusBar().showMessage(
            f"Label offset X: {self.offset_x_spin.value():.1f}, "
            f"Y: {self.offset_y_spin.value():.1f}"
        )

    def reset_offset(self) -> None:
        self.loading_controls = True
        self.offset_x_spin.setValue(0.0)
        self.offset_y_spin.setValue(0.0)
        self.loading_controls = False
        self.offset_control_changed()

    def apply_offset_style(self) -> None:
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
            "labelHaloEnabled": True,
            "labelHaloColor": "#FFFFFF",
            "labelHaloWidth": 2.0,
            "labelOffsetX": self.offset_x_spin.value(),
            "labelOffsetY": self.offset_y_spin.value(),
        }
        self.viewer.set_layer_style(self.world_layer_index, style)
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("LabelOffset")
    app.setWindowIcon(application_icon())
    window = LabelOffsetWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
