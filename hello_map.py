import sys
from importlib.resources import files

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
from geokernel import Viewer, ViewerTool

ICON_DIR = files("geokernel").joinpath("assets/images")


def tool_action(icon_name: str, text: str, window: QMainWindow) -> QAction:
    action = QAction(QIcon(str(ICON_DIR / icon_name)), text, window)
    action.setToolTip(text)
    action.setStatusTip(text)
    return action


def main() -> None:

    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("HelloMap")
    window.resize(1200, 800)

    viewer = Viewer()
    viewer.set_activation_type("Developer")
    viewer.set_tool(ViewerTool.PAN)
    viewer.add_layer(r"D:\projects\GeoKernel.Examples.Qt\data\shapefile\world_4326.shp")
    # viewer.set_map_style("midnight-blue")
    # viewer.set_map_style("vintage-map")
    # viewer.set_map_style("arcgis-pro-modern")
    # viewer.set_map_style("neon")
    # viewer.set_map_style("blueprint")
    # viewer.set_map_style("google-light")
    

    window.setCentralWidget(viewer.qt_widget())

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

    window.show()
    app.processEvents()
    viewer.show()
    viewer.full_extent()
    app.exec()

if __name__ == "__main__":
    main()
