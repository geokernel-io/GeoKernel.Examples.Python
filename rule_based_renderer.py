import sys
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QDockWidget, QListWidget, QListWidgetItem, QMainWindow, QMessageBox
from geokernel import Viewer, ViewerTool
from common import application_icon, ensure_sample_file

MINIMUM_POINT_SIZE = 4.0
MAXIMUM_POINT_SIZE = 22.0
DEFAULT_CITY_STYLE = {
    "pointColor": "#917B8794",
    "lineColor": "#D24B5563",
    "pointSize": MINIMUM_POINT_SIZE,
    "lineWidth": 0.9,
}
RULE_DEFINITIONS = (
    ("Less than 50,000", "#917B8794", "#D24B5563", MINIMUM_POINT_SIZE),
    ("50,000 to 100,000", "#914FA3C4", "#D21D6D83", 5.5),
    ("100,000 to 250,000", "#9155B889", "#D22E7D59", 7.5),
    ("250,000 to 500,000", "#91F2B84B", "#D29B6B18", 10.0),
    ("500,000 to 1,000,000", "#91E56B5D", "#D29A3E32", 14.0),
    ("1,000,000 to 5,000,000", "#91A9423A", "#D261201C", 19.0),
)

class RuleBasedRendererWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("RuleBasedRenderer")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)

        self.legend = QListWidget(self)
        self.legend_dock = QDockWidget("POP_CLASS rules", self)
        self.legend_dock.setWidget(self.legend)
        self.legend_dock.setMinimumWidth(250)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.legend_dock)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.legend.addItem("Preparing USA cities sample data...")

        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/usa_cities.zip",
                zip_name="usa_cities.zip",
                target_folder="usa_cities",
                required_file="usa_cities.shp",
                title="RuleBasedRenderer",
            )

            self.viewer.add_open_street_map_layer()
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.viewer.set_layer_name(0, "Cities - rule based by POP_CLASS")
            self.viewer.set_layer_style(0, DEFAULT_CITY_STYLE)
            self.apply_renderer()
            self.update_legend()
            QTimer.singleShot(250, self.zoom_to_cities)
            self.statusBar().showMessage("Rule based renderer applied: POP_CLASS")
        except Exception as error:
            self.legend.clear()
            self.legend.addItem("Rule based renderer could not be created.")
            self.statusBar().showMessage("Rule based renderer could not be created.")
            QMessageBox.critical(self, "RuleBasedRenderer", str(error))

    def apply_renderer(self) -> None:
        rules = []
        for label, point_color, line_color, point_size in RULE_DEFINITIONS:
            rules.append(
                {
                    "field": "POP_CLASS",
                    "operator": "equals",
                    "value": label,
                    "label": label,
                    "enabled": True,
                    "style": {
                        "pointColor": point_color,
                        "lineColor": line_color,
                        "pointSize": point_size,
                        "lineWidth": max(0.8, min(1.5, point_size * 0.06)),
                    },
                }
            )

        renderer = {
            "type": "ruleBased",
            "defaultStyle": DEFAULT_CITY_STYLE,
            "rules": rules,
        }
        if not self.viewer.set_layer_symbol_renderer(0, renderer):
            raise RuntimeError("Rule based renderer could not be applied.")

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()

    def update_legend(self) -> None:
        renderer = self.viewer.layer_symbol_renderer(0)
        self.legend.clear()
        for rule in renderer.get("rules", []):
            if not rule.get("enabled", True):
                continue
            label = str(rule.get("label", "")).strip() or "(unnamed rule)"
            item = QListWidgetItem(self.legend_icon(rule.get("style", {})), label)
            item.setSizeHint(QSize(210, 44))
            self.legend.addItem(item)

    def legend_icon(self, style: dict) -> QIcon:
        pixmap = QPixmap(72, 42)
        pixmap.fill(Qt.GlobalColor.transparent)
        point_size = min(
            MAXIMUM_POINT_SIZE,
            max(MINIMUM_POINT_SIZE, float(style.get("pointSize", MINIMUM_POINT_SIZE))),
        )

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(
            QPen(
                QColor(str(style.get("lineColor", DEFAULT_CITY_STYLE["lineColor"]))),
                max(1.0, float(style.get("lineWidth", 0.9))),
            )
        )
        painter.setBrush(
            QColor(str(style.get("pointColor", DEFAULT_CITY_STYLE["pointColor"])))
        )
        radius = point_size / 2.0
        painter.drawEllipse(36.0 - radius, 21.0 - radius, point_size, point_size)
        painter.end()
        return QIcon(pixmap)

    def zoom_to_cities(self) -> None:
        if not self.viewer.zoom_to_layer(0):
            raise RuntimeError("Cities layer extent could not be displayed.")

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("RuleBasedRenderer")
    app.setWindowIcon(application_icon())
    window = RuleBasedRendererWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
