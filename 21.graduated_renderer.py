import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QDockWidget, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QToolBar
from geokernel import ClassificationMethod, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

COUNTY_STYLE = {
    "fillColor": "#DCE8E4",
    "fillOpacity": 225,
    "lineColor": "#536B68",
    "lineWidth": 0.8,
}

class GraduatedRendererWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("GraduatedRenderer")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)

        self.ramp_combo = QComboBox(self)
        self.ramp_combo.setEnabled(False)

        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.addWidget(QLabel("Color ramp: ", self.toolbar))
        self.toolbar.addWidget(self.ramp_combo)
        self.addToolBar(self.toolbar)

        self.legend = QListWidget(self)
        self.legend_dock = QDockWidget("POPULATION classes", self)
        self.legend_dock.setWidget(self.legend)
        self.legend_dock.setMinimumWidth(230)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.legend_dock)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.legend.addItem("Preparing California sample data...")

        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/california.zip",
                zip_name="california.zip",
                target_folder="california",
                required_file="california.shp",
                title="GraduatedRenderer",
            )

            self.viewer.add_open_street_map_layer()
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.viewer.set_layer_name(0, "California counties - graduated by POPULATION")
            self.viewer.set_layer_style(0, COUNTY_STYLE)

            self.ramp_combo.addItems(self.viewer.color_ramp_names())
            green_blue_index = self.ramp_combo.findText(
                "GreenBlue", Qt.MatchFlag.MatchFixedString
            )
            if green_blue_index >= 0:
                self.ramp_combo.setCurrentIndex(green_blue_index)

            self.apply_renderer()
            self.ramp_combo.currentTextChanged.connect(self.apply_renderer)
            self.ramp_combo.setEnabled(True)
            QTimer.singleShot(250, self.zoom_to_counties)
        except Exception as error:
            self.legend.clear()
            self.legend.addItem("Graduated renderer could not be created.")
            self.statusBar().showMessage("Graduated renderer could not be created.")
            QMessageBox.critical(self, "GraduatedRenderer", str(error))

    def apply_renderer(self) -> None:
        ramp_name = self.ramp_combo.currentText()
        if not ramp_name:
            return

        if not self.viewer.apply_graduated_renderer(
            0,
            "POPULATION",
            ClassificationMethod.NATURAL_BREAKS,
            5,
            ramp_name,
        ):
            self.legend.clear()
            self.legend.addItem("Graduated renderer could not be created.")
            self.statusBar().showMessage("Graduated renderer could not be created.")
            QMessageBox.critical(
                self,
                "GraduatedRenderer",
                "Could not create graduated renderer from POPULATION field.",
            )
            return

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.update_legend()
        self.statusBar().showMessage(
            f"Graduated renderer applied: POPULATION / {ramp_name}"
        )

    def zoom_to_counties(self) -> None:
        self.viewer.zoom_to_layer(0)

    def update_legend(self) -> None:
        renderer = self.viewer.layer_symbol_renderer(0)
        self.legend.clear()
        for range_item in renderer.get("ranges", []):
            if not range_item.get("enabled", True):
                continue
            label = str(range_item.get("label", "")).strip() or "(empty)"
            style = range_item.get("style", {})
            self.legend.addItem(QListWidgetItem(self.legend_icon(style), label))

    def legend_icon(self, style: dict) -> QIcon:
        pixmap = QPixmap(42, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        fill = QColor(str(style.get("fillColor", "#DCE8E4")))
        fill.setAlpha(int(style.get("fillOpacity", 225)))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(str(style.get("lineColor", "#536B68"))), 1.5))
        painter.setBrush(fill)
        painter.drawRect(5, 4, 32, 16)
        painter.end()
        return QIcon(pixmap)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GraduatedRenderer")
    app.setWindowIcon(application_icon())
    window = GraduatedRendererWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
