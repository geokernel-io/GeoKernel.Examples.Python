import sys
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
from geokernel import Viewer, ViewerTool

def main() -> None:

    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("HelloMap")
    window.resize(1200, 800)

    viewer = Viewer()
    viewer.set_activation_type("Developer")
    viewer.set_background("#F4F6F5")
    viewer.set_tool(ViewerTool.PAN)
    viewer.add_layer(r"D:\projects\GeoKernel.Examples.Qt\data\shapefile\world_4326.shp")

    window.setCentralWidget(viewer.qt_widget())

    toolbar = QToolBar("Navigation", window)
    window.addToolBar(toolbar)

    zoom_in = QAction("Zoom In", window)
    zoom_in.triggered.connect(lambda: viewer.zoom_in())
    toolbar.addAction(zoom_in)

    zoom_out = QAction("Zoom Out", window)
    zoom_out.triggered.connect(lambda: viewer.zoom_out())
    toolbar.addAction(zoom_out)

    full_extent = QAction("Full Extent", window)
    full_extent.triggered.connect(lambda: viewer.full_extent())
    toolbar.addAction(full_extent)

    toolbar.addSeparator()

    zoom_rect = QAction("Zoom Rect", window)
    zoom_rect.triggered.connect(lambda: viewer.set_tool(ViewerTool.ZOOM_BOX))
    toolbar.addAction(zoom_rect)

    pan = QAction("Pan", window)
    pan.triggered.connect(lambda: viewer.set_tool(ViewerTool.PAN))
    toolbar.addAction(pan)

    window.show()
    app.processEvents()
    viewer.show()
    viewer.full_extent()
    app.exec()

if __name__ == "__main__":
    main()
