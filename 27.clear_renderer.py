import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

INITIAL_EXTENT = Extent(-16831516.0, 1856556.0, -4631023.0, 7472472.0)
STATE_STYLE = {
    "fillColor": "#D8E5E1",
    "fillOpacity": 220,
    "lineColor": "#536B68",
    "lineWidth": 0.9,
}

class ClearRendererWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.states_layer_index = -1

        self.setWindowTitle("ClearRenderer")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.create_layout()

    def create_layout(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        controls = QWidget(central)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(6, 4, 6, 4)
        controls_layout.setSpacing(6)

        self.apply_button = QPushButton("Apply Categorized Renderer", controls)
        self.clear_button = QPushButton("Clear Renderer", controls)
        self.renderer_state_label = QLabel("Preparing sample data...", controls)
        self.apply_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_categorized_renderer)
        self.clear_button.clicked.connect(self.clear_renderer)

        controls_layout.addWidget(self.apply_button)
        controls_layout.addWidget(self.clear_button)
        controls_layout.addWidget(self.renderer_state_label)
        controls_layout.addStretch(1)

        layout.addWidget(controls)
        layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()

        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/usa_states_3857.zip",
                zip_name="usa_states_3857.zip",
                target_folder="usa_states_3857",
                required_file="usa_states_3857.shp",
                title="ClearRenderer",
            )

            self.viewer.add_open_street_map_layer()
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.states_layer_index = 0
            self.viewer.set_layer_name(self.states_layer_index, "USA States")
            self.apply_base_style()
            if not self.apply_categorized_renderer():
                return

            self.apply_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            self.viewer.set_view_extent(INITIAL_EXTENT)
            self.statusBar().showMessage(
                "Categorized renderer applied. Use Clear Renderer to return to the default layer style."
            )
        except Exception as error:
            self.renderer_state_label.setText("Layer could not be loaded.")
            self.statusBar().showMessage("Layer could not be loaded.")
            QMessageBox.critical(self, "ClearRenderer", str(error))

    def apply_base_style(self) -> None:
        if self.states_layer_index >= 0:
            self.viewer.set_layer_style(self.states_layer_index, STATE_STYLE)

    def apply_categorized_renderer(self) -> bool:
        if self.states_layer_index < 0:
            return False

        self.apply_base_style()
        if not self.viewer.apply_categorized_renderer(
            self.states_layer_index,
            "STATE",
            "Unique",
            category_limit=64,
        ):
            self.renderer_state_label.setText(
                "Categorized renderer could not be created."
            )
            self.statusBar().showMessage(
                "Categorized renderer could not be created."
            )
            QMessageBox.critical(
                self,
                "ClearRenderer",
                "Could not create categorized renderer from STATE field.",
            )
            return False

        self.renderer_state_label.setText("Renderer: categorized by STATE")
        self.refresh_viewer()
        self.statusBar().showMessage("Categorized renderer applied.")
        return True

    def clear_renderer(self) -> None:
        if self.states_layer_index < 0:
            return
        if not self.viewer.clear_layer_symbol_renderer(self.states_layer_index):
            self.renderer_state_label.setText("Renderer could not be cleared.")
            self.statusBar().showMessage("Renderer could not be cleared.")
            return

        self.apply_base_style()
        self.renderer_state_label.setText("Renderer: none, default layer style")
        self.refresh_viewer()
        self.statusBar().showMessage(
            "Symbol renderer cleared. Layer is back to the default style."
        )

    def refresh_viewer(self) -> None:
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ClearRenderer")
    app.setWindowIcon(application_icon())
    window = ClearRendererWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
