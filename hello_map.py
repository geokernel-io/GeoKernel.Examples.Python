import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file, tool_action

def main() -> None:

    app = QApplication(sys.argv)
    app_icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setWindowIcon(app_icon)

    world_layer = ensure_sample_file(
        app=app,
        zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
        zip_name="world_4326.zip",
        target_folder="world_4326",
        required_file="world_4326.shp",
    )

    window = QMainWindow()
    window.setWindowIcon(app_icon)
    window.setWindowTitle("HelloMap")
    window.resize(1200, 800)

    viewer = Viewer()
    viewer.set_license_key('G36U-F99B-83M4-FD8F-BMCZ')
    viewer.set_tool(ViewerTool.PAN)
    viewer.add_layer(str(world_layer))    

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
