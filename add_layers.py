import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
from common import ensure_sample_file, tool_action
from geokernel import Viewer, ViewerTool

SAMPLE_DATA_BASE_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/"

def load_sample_layers(app: QApplication, viewer: Viewer) -> None:
    raster_layer = ensure_sample_file(
        app=app,
        zip_url=f"{SAMPLE_DATA_BASE_URL}world_8km_png.zip",
        zip_name="world_8km_png.zip",
        target_folder="world_8km_png",
        required_file="world_8km.png",
    )

    world_layer = ensure_sample_file(
        app=app,
        zip_url=f"{SAMPLE_DATA_BASE_URL}world_4326.zip",
        zip_name="world_4326.zip",
        target_folder="world_4326",
        required_file="world_4326.shp",
    )

    cities_layer = ensure_sample_file(
        app=app,
        zip_url=f"{SAMPLE_DATA_BASE_URL}world_cities_4326.zip",
        zip_name="world_cities_4326.zip",
        target_folder="world_cities_4326",
        required_file="world_cities_4326.shp",
    )

    viewer.clear_layers()
    viewer.add_layer(str(raster_layer))
    viewer.set_layer_name(0, "World raster")
    
    viewer.add_layer(str(world_layer))
    viewer.set_layer_name(0, "Countries")
    viewer.set_layer_style(
        0,
        {
            "fillColor": "#35475B",
            "fillOpacity": 172,
            "lineColor": "#B7E8FF",
            "lineWidth": 0.85,
            "labelColor": "#FFFFFF",
            "labelHaloColor": "#10263A",
        },
    )

    viewer.add_layer(str(cities_layer))
    viewer.set_layer_name(0, "Cities")
    viewer.set_layer_style(
        0,
        {
            "pointColor": "#1D8FC7",
            "lineColor": "#74C3E8",
            "lineWidth": 0.9,
            "pointSize": 4.2,
        },
    )

    viewer.refresh_layers()

def add_navigation_toolbar(window: QMainWindow, viewer: Viewer) -> None:
    toolbar = QToolBar("Navigation", window)
    toolbar.setMovable(False)
    toolbar.setIconSize(QSize(32, 32))
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    window.addToolBar(toolbar)

    zoom_in = tool_action("ZoomIn.svg", "Zoom In", window)
    zoom_in.triggered.connect(lambda: viewer.zoom_in())
    toolbar.addAction(zoom_in)

    zoom_out = tool_action("ZoomOut.svg", "Zoom Out", window)
    zoom_out.triggered.connect(lambda: viewer.zoom_out())
    toolbar.addAction(zoom_out)

    full_extent = tool_action("FullExtent.svg", "Full Extent", window)
    full_extent.triggered.connect(lambda: viewer.full_extent())
    toolbar.addAction(full_extent)

    toolbar.addSeparator()

    zoom_rect = tool_action("RectangularZoom.svg", "Zoom Rect", window)
    zoom_rect.triggered.connect(lambda: viewer.set_tool(ViewerTool.ZOOM_BOX))
    toolbar.addAction(zoom_rect)

    pan = tool_action("Pan.svg", "Pan", window)
    pan.triggered.connect(lambda: viewer.set_tool(ViewerTool.PAN))
    toolbar.addAction(pan)

def main() -> None:
    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setWindowIcon(app_icon)

    window = QMainWindow()
    window.setWindowIcon(app_icon)
    window.setWindowTitle("AddLayers")
    window.resize(1200, 800)

    viewer = Viewer()
    viewer.set_tool(ViewerTool.PAN)
    window.setCentralWidget(viewer.qt_widget())

    add_navigation_toolbar(window, viewer)

    window.show()
    app.processEvents()

    load_sample_layers(app, viewer)
    viewer.show()
    viewer.full_extent()

    app.exec()

if __name__ == "__main__":
    main()
