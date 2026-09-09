import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QDockWidget, QListWidget, QListWidgetItem, QMainWindow, QMessageBox
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

INITIAL_EXTENT = Extent(-16831516.0, 1856556.0, -4631023.0, 7472472.0)
STATE_STYLE = {"fillColor": "#D8E5E1", "fillOpacity": 220, "lineColor": "#536B68", "lineWidth": 0.9}

class CategorizedRendererWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("CategorizedRenderer")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)

        self.legend = QListWidget(self)
        self.legend_dock = QDockWidget("STATE categories", self)
        self.legend_dock.setWidget(self.legend)
        self.legend_dock.setMinimumWidth(180)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.legend_dock)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.legend.addItem("Preparing USA states sample data...")
        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/usa_states_3857.zip",
                zip_name="usa_states_3857.zip",
                target_folder="usa_states_3857",
                required_file="usa_states_3857.shp",
                title="CategorizedRenderer",
            )
            self.viewer.add_open_street_map_layer()
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.viewer.set_layer_name(0, "USA States - categorized by STATE")
            self.viewer.set_layer_style(0, STATE_STYLE)
            if not self.viewer.apply_categorized_renderer(0, "STATE", "Unique"):
                raise RuntimeError("Could not create categorized renderer from STATE field.")
            self.viewer.invalidate_render_cache(False, True)
            self.viewer.refresh_layers()
            self.update_legend()
            QTimer.singleShot(250, self.apply_initial_extent)
            self.statusBar().showMessage("Categorized renderer applied: STATE")
        except Exception as error:
            self.legend.clear()
            self.legend.addItem("Categorized renderer could not be created.")
            self.statusBar().showMessage("Categorized renderer could not be created.")
            QMessageBox.critical(self, "CategorizedRenderer", str(error))

    def apply_initial_extent(self) -> None:
        self.viewer.set_view_extent(INITIAL_EXTENT)

    def update_legend(self) -> None:
        renderer = self.viewer.layer_symbol_renderer(0)
        categories = renderer.get("categories", [])
        self.legend.clear()
        for category in categories:
            if not category.get("enabled", True):
                continue
            label = str(category.get("label", "")).strip() or "(empty)"
            style = category.get("style", {})
            self.legend.addItem(QListWidgetItem(self.legend_icon(style), label))

    def legend_icon(self, style: dict) -> QIcon:
        pixmap = QPixmap(38, 22)
        pixmap.fill(Qt.GlobalColor.transparent)
        fill = QColor(str(style.get("fillColor", "#D8E5E1")))
        fill.setAlpha(int(style.get("fillOpacity", 220)))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(str(style.get("lineColor", "#536B68"))), 1.5))
        painter.setBrush(fill)
        painter.drawRect(5, 4, 28, 14)
        painter.end()
        return QIcon(pixmap)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("CategorizedRenderer")
    app.setWindowIcon(application_icon())
    window = CategorizedRendererWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
