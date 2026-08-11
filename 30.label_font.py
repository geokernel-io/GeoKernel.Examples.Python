import sys
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

INITIAL_EXTENT = Extent(-180.0, -58.0, 180.0, 82.0)

class LabelFontWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.world_layer_index = -1
        self.loading_controls = True

        self.setWindowTitle("LabelFont")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_layout()

    def create_layout(self) -> None:
        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        panel = QWidget(central)
        panel.setFixedWidth(245)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)

        self.font_family_combo = QComboBox(panel)
        self.font_family_combo.addItems(sorted(QFontDatabase.families()))
        arial_index = self.font_family_combo.findText("Arial")
        if arial_index >= 0:
            self.font_family_combo.setCurrentIndex(arial_index)

        self.bold_check = QCheckBox("Bold", panel)
        self.italic_check = QCheckBox("Italic", panel)
        self.font_family_combo.setEnabled(False)
        self.bold_check.setEnabled(False)
        self.italic_check.setEnabled(False)

        form = QFormLayout()
        form.addRow("Font family", self.font_family_combo)
        form.addRow(self.bold_check)
        form.addRow(self.italic_check)

        panel_layout.addWidget(QLabel("Label font", panel))
        panel_layout.addLayout(form)
        panel_layout.addStretch(1)

        layout.addWidget(panel)
        layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central)

        self.font_family_combo.currentTextChanged.connect(self.font_control_changed)
        self.bold_check.toggled.connect(self.font_control_changed)
        self.italic_check.toggled.connect(self.font_control_changed)

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
                title="LabelFont",
            )
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.world_layer_index = 0
            self.viewer.set_layer_name(self.world_layer_index, "World - label font")
            self.apply_label_font()
            self.viewer.set_view_extent(INITIAL_EXTENT)

            self.loading_controls = False
            self.font_family_combo.setEnabled(True)
            self.bold_check.setEnabled(True)
            self.italic_check.setEnabled(True)
            self.statusBar().showMessage(
                "Labels use labelFontFamily, labelBold and labelItalic."
            )
        except Exception as error:
            self.statusBar().showMessage("World layer could not be loaded.")
            QMessageBox.critical(self, "LabelFont", str(error))

    def font_control_changed(self) -> None:
        if self.loading_controls or self.world_layer_index < 0:
            return
        self.apply_label_font()
        self.statusBar().showMessage(
            f"Font: {self.font_family_combo.currentText()}, "
            f"bold: {str(self.bold_check.isChecked()).lower()}, "
            f"italic: {str(self.italic_check.isChecked()).lower()}"
        )

    def apply_label_font(self) -> None:
        if self.world_layer_index < 0 or not self.font_family_combo.currentText():
            return
        style = {
            "fillColor": "#D8E5E1",
            "fillOpacity": 215,
            "lineColor": "#6F8380",
            "lineWidth": 0.8,
            "showLabels": True,
            "labelField": "COUNTRY",
            "labelFontSize": 12.0,
            "labelColor": "#1F2933",
            "labelHaloEnabled": True,
            "labelHaloColor": "#FFFFFF",
            "labelHaloWidth": 2.0,
            "labelFontFamily": self.font_family_combo.currentText(),
            "labelBold": self.bold_check.isChecked(),
            "labelItalic": self.italic_check.isChecked(),
        }
        self.viewer.set_layer_style(self.world_layer_index, style)
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("LabelFont")
    app.setWindowIcon(application_icon())
    window = LabelFontWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
