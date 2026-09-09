import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QDockWidget, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QToolBar
from geokernel import ClassificationMethod, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

POPULATION_FIELD = "POPULATION"
COUNTY_STYLE = {
    "fillColor": "#DCE8E4",
    "fillOpacity": 225,
    "lineColor": "#536B68",
    "lineWidth": 0.8,
}
METHODS = (
    ("Equal Interval", ClassificationMethod.EQUAL_INTERVAL),
    ("Quantile", ClassificationMethod.QUANTILE),
    ("Standard Deviation", ClassificationMethod.STANDARD_DEVIATION),
)

class ClassificationMethodsWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.county_layer_index = -1

        self.setWindowTitle("ClassificationMethods")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)

        self.method_combo = QComboBox(self)
        self.method_combo.addItems(name for name, _ in METHODS)
        self.method_combo.setEnabled(False)

        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.addWidget(QLabel("Method: ", self.toolbar))
        self.toolbar.addWidget(self.method_combo)
        self.addToolBar(self.toolbar)

        self.legend = QListWidget(self)
        self.legend_dock = QDockWidget("POPULATION - Equal Interval", self)
        self.legend_dock.setWidget(self.legend)
        self.legend_dock.setMinimumWidth(245)
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
                title="ClassificationMethods",
            )

            self.viewer.add_open_street_map_layer()
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.county_layer_index = 0
            self.viewer.set_layer_name(
                self.county_layer_index,
                "California counties - classification methods",
            )
            self.viewer.set_layer_style(self.county_layer_index, COUNTY_STYLE)

            self.apply_renderer()
            self.method_combo.currentIndexChanged.connect(self.apply_renderer)
            self.method_combo.setEnabled(True)
            QTimer.singleShot(250, self.zoom_to_counties)
        except Exception as error:
            self.legend.clear()
            self.legend.addItem("Graduated renderer could not be created.")
            self.statusBar().showMessage("Graduated renderer could not be created.")
            QMessageBox.critical(self, "ClassificationMethods", str(error))

    def selected_method(self) -> tuple[str, ClassificationMethod]:
        index = max(0, self.method_combo.currentIndex())
        return METHODS[index]

    def apply_renderer(self) -> None:
        if self.county_layer_index < 0:
            return

        method_name, method = self.selected_method()
        interval = 1.0 if method == ClassificationMethod.STANDARD_DEVIATION else 0.0
        if not self.viewer.apply_graduated_renderer(
            self.county_layer_index,
            POPULATION_FIELD,
            method,
            5,
            "GreenBlue",
            interval=interval,
        ):
            self.legend.clear()
            self.legend.addItem("Graduated renderer could not be created.")
            self.statusBar().showMessage("Graduated renderer could not be created.")
            QMessageBox.critical(
                self,
                "ClassificationMethods",
                f"Could not create graduated renderer from {POPULATION_FIELD} field.",
            )
            return

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.update_legend(method_name)
        self.statusBar().showMessage(
            f"Classification method applied: {POPULATION_FIELD} / {method_name}"
        )

    def update_legend(self, method_name: str) -> None:
        renderer = self.viewer.layer_symbol_renderer(self.county_layer_index)
        self.legend.clear()
        self.legend_dock.setWindowTitle(f"{POPULATION_FIELD} - {method_name}")
        for range_item in renderer.get("ranges", []):
            if not range_item.get("enabled", True):
                continue
            label = str(range_item.get("label", "")).strip()
            if not label:
                lower = float(range_item.get("lower", 0.0))
                upper = float(range_item.get("upper", 0.0))
                label = f"{lower:,.0f} - {upper:,.0f}"
            self.legend.addItem(
                QListWidgetItem(self.legend_icon(range_item.get("style", {})), label)
            )

    def legend_icon(self, style: dict) -> QIcon:
        pixmap = QPixmap(42, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        fill = QColor(str(style.get("fillColor", COUNTY_STYLE["fillColor"])))
        fill.setAlpha(int(style.get("fillOpacity", COUNTY_STYLE["fillOpacity"])))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(
            QPen(QColor(str(style.get("lineColor", COUNTY_STYLE["lineColor"]))), 1.5)
        )
        painter.setBrush(fill)
        painter.drawRect(5, 4, 32, 16)
        painter.end()
        return QIcon(pixmap)

    def zoom_to_counties(self) -> None:
        if self.county_layer_index >= 0:
            self.viewer.zoom_to_layer(self.county_layer_index)

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ClassificationMethods")
    app.setWindowIcon(application_icon())
    window = ClassificationMethodsWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
