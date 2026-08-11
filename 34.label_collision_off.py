import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QSplitter, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

CONTINENTAL_US_EXTENT = Extent(-127.0, 23.0, -66.0, 50.0)

class LabelCollisionOffWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.initialized = False
        self.collision_on_viewer = Viewer()
        self.collision_off_viewer = Viewer()
        self.collision_on_viewer.set_tool(ViewerTool.PAN)
        self.collision_off_viewer.set_tool(ViewerTool.PAN)
        self.collision_on_widget = self.collision_on_viewer.qt_widget()
        self.collision_off_widget = self.collision_off_viewer.qt_widget()

        self.setWindowTitle("LabelCollisionOff")
        self.setWindowIcon(application_icon())
        self.resize(1300, 800)
        self.create_layout()

    def create_layout(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(
            self.create_viewer_pane(
                "labelAllowOverlap = false",
                self.collision_on_widget,
                splitter,
            )
        )
        splitter.addWidget(
            self.create_viewer_pane(
                "labelAllowOverlap = true",
                self.collision_off_widget,
                splitter,
            )
        )
        splitter.setSizes([650, 650])
        self.setCentralWidget(splitter)

    def create_viewer_pane(
        self,
        title: str,
        viewer_widget: QWidget,
        parent: QWidget,
    ) -> QWidget:
        pane = QWidget(parent)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        caption = QLabel(title, pane)
        caption.setContentsMargins(8, 6, 8, 6)
        caption.setStyleSheet("background:#eeeeee;font-weight:600;")
        layout.addWidget(caption)
        layout.addWidget(viewer_widget, 1)
        return pane

    def initialize_viewers(self) -> None:
        if self.initialized:
            return
        self.initialized = True

        self.collision_on_viewer.resize(
            self.collision_on_widget.width(), self.collision_on_widget.height()
        )
        self.collision_off_viewer.resize(
            self.collision_off_widget.width(), self.collision_off_widget.height()
        )
        self.collision_on_viewer.show()
        self.collision_off_viewer.show()
        self.statusBar().showMessage("Preparing world and city sample data...")

        try:
            world_path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="LabelCollisionOff",
            )
            cities_path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_cities_4326.zip",
                zip_name="world_cities_4326.zip",
                target_folder="world_cities_4326",
                required_file="world_cities_4326.shp",
                title="LabelCollisionOff",
            )

            self.load_comparison_layers(
                self.collision_on_viewer,
                world_path,
                cities_path,
                False,
            )
            self.load_comparison_layers(
                self.collision_off_viewer,
                world_path,
                cities_path,
                True,
            )
            self.collision_on_viewer.set_view_extent(CONTINENTAL_US_EXTENT)
            self.collision_off_viewer.set_view_extent(CONTINENTAL_US_EXTENT)
            self.statusBar().showMessage(
                "Left: collision filtering. Right: label overlap allowed."
            )
        except Exception as error:
            self.statusBar().showMessage("Comparison layers could not be loaded.")
            QMessageBox.critical(self, "LabelCollisionOff", str(error))

    def load_comparison_layers(
        self,
        viewer: Viewer,
        world_path,
        cities_path,
        allow_overlap: bool,
    ) -> None:
        viewer.add_layer(str(world_path), {"buildFeatureSource": True})
        viewer.add_layer(str(cities_path), {"buildFeatureSource": True})

        cities_layer_index = 0
        world_layer_index = 1
        viewer.set_layer_name(world_layer_index, "World")
        viewer.set_layer_name(
            cities_layer_index,
            "Cities - labelAllowOverlap true"
            if allow_overlap
            else "Cities - labelAllowOverlap false",
        )
        viewer.set_layer_style(world_layer_index, self.world_style())
        viewer.set_layer_style(cities_layer_index, self.city_style(allow_overlap))
        viewer.invalidate_render_cache(True, True)
        viewer.refresh_layers()

    def world_style(self) -> dict:
        return {
            "fillColor": "#D8E5E1",
            "fillOpacity": 215,
            "lineColor": "#6F8380",
            "lineWidth": 0.8,
        }

    def city_style(self, allow_overlap: bool) -> dict:
        return {
            "pointColor": "#D56037",
            "lineColor": "#A23D23",
            "pointSize": 5.5,
            "lineWidth": 0.8,
            "showLabels": True,
            "labelField": "CITY_NAME",
            "labelFontSize": 8.0,
            "labelColor": "#1F2933",
            "labelHaloEnabled": True,
            "labelHaloColor": "#FFFFFF",
            "labelHaloWidth": 1.5,
            "labelAllowOverlap": allow_overlap,
            "labelPlacementMode": 1,
            "labelOffsetX": 7.0,
            "labelOffsetY": -7.0,
        }

    def closeEvent(self, event) -> None:
        self.collision_on_viewer.close()
        self.collision_off_viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("LabelCollisionOff")
    app.setWindowIcon(application_icon())
    window = LabelCollisionOffWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewers)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
