import sys
from importlib.resources import files
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTextEdit, QToolBar
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_EXTENT_3857 = Extent(-1400000.0, 4100000.0, 4200000.0, 7800000.0)

class XyzMinMaxZoomWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.icons = files("geokernel").joinpath("assets/images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("XyzMinMaxZoom")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        self.details_view = QTextEdit(self)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(350)
        details_dock = QDockWidget("Min/max zoom details", self)
        details_dock.setWidget(self.details_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        toolbar = QToolBar("XYZ min/max zoom", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)

        self.add_action(toolbar, "ZoomIn.svg", "Zoom In", self.viewer.zoom_in)
        self.add_action(toolbar, "ZoomOut.svg", "Zoom Out", self.viewer.zoom_out)
        self.add_action(
            toolbar,
            "FullExtent.svg",
            "Full Extent",
            self.show_default_extent,
        )
        toolbar.addSeparator()

        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)

        self.zoom_box_action = self.add_action(
            toolbar,
            "RectangularZoom.svg",
            "Zoom Rect",
            self.activate_zoom_box,
        )
        self.zoom_box_action.setCheckable(True)
        tool_group.addAction(self.zoom_box_action)

        self.pan_action = self.add_action(
            toolbar,
            "Pan.svg",
            "Pan",
            self.activate_pan,
        )
        self.pan_action.setCheckable(True)
        self.pan_action.setChecked(True)
        tool_group.addAction(self.pan_action)
        self.tool_group = tool_group

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Min:", toolbar))
        self.minimum_zoom = QSpinBox(toolbar)
        self.minimum_zoom.setRange(0, 21)
        self.minimum_zoom.setValue(0)
        toolbar.addWidget(self.minimum_zoom)

        toolbar.addWidget(QLabel("Max:", toolbar))
        self.maximum_zoom = QSpinBox(toolbar)
        self.maximum_zoom.setRange(0, 21)
        self.maximum_zoom.setValue(19)
        toolbar.addWidget(self.maximum_zoom)

        apply_action = QAction("Apply Zoom Range", self)
        apply_action.triggered.connect(self.apply_zoom_range)
        toolbar.addAction(apply_action)

        low_range_button = QPushButton("0-5", toolbar)
        low_range_button.clicked.connect(self.apply_low_range)
        toolbar.addWidget(low_range_button)

        mid_range_button = QPushButton("4-10", toolbar)
        mid_range_button.clicked.connect(self.apply_mid_range)
        toolbar.addWidget(mid_range_button)

        high_range_button = QPushButton("8-14", toolbar)
        high_range_button.clicked.connect(self.apply_high_range)
        toolbar.addWidget(high_range_button)

    def add_action(self, toolbar, icon_name: str, text: str, callback) -> QAction:
        action = QAction(QIcon(str(self.icons.joinpath(icon_name))), text, self)
        action.setToolTip(text)
        action.triggered.connect(callback)
        toolbar.addAction(action)
        return action

    def initialize_viewer(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.viewer.resize(
            self.viewer_widget.width(),
            self.viewer_widget.height(),
        )
        self.viewer.show()
        self.apply_zoom_range()

    def apply_zoom_range(self) -> None:
        if not self.initialized:
            return

        minimum_zoom = self.minimum_zoom.value()
        maximum_zoom = self.maximum_zoom.value()
        if minimum_zoom > maximum_zoom:
            minimum_zoom, maximum_zoom = maximum_zoom, minimum_zoom

        previous_extent = DEFAULT_EXTENT_3857
        if self.viewer.layer_count() > 0:
            previous_extent = self.viewer.get_view_extent()

        try:
            self.viewer.clear_layers()
            layer_index = self.viewer.add_xyz_layer(
                f"OSM min {minimum_zoom} max {maximum_zoom}",
                OSM_URL,
                minimum_zoom,
                maximum_zoom,
                256,
                "OpenStreetMap contributors",
                True,
                str(self.cache_directory_for(minimum_zoom, maximum_zoom)),
            )
            if layer_index < 0:
                raise RuntimeError("add_xyz_layer returned an invalid layer index.")

            self.viewer.set_view_extent(previous_extent)
            self.show_range_details(minimum_zoom, maximum_zoom)
            self.statusBar().showMessage(
                f"XYZ min/max zoom applied: {minimum_zoom} - {maximum_zoom}"
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "XyzMinMaxZoom",
                f"XYZ layer could not be loaded:\n{error}",
            )

    def cache_directory_for(self, minimum_zoom: int, maximum_zoom: int) -> Path:
        return (
            Path(__file__).resolve().parent
            / "XyzMinMaxZoomCache"
            / f"{minimum_zoom}_{maximum_zoom}"
        )

    def apply_low_range(self) -> None:
        self.set_and_apply_range(0, 5)

    def apply_mid_range(self) -> None:
        self.set_and_apply_range(4, 10)

    def apply_high_range(self) -> None:
        self.set_and_apply_range(8, 14)

    def set_and_apply_range(self, minimum_zoom: int, maximum_zoom: int) -> None:
        self.minimum_zoom.setValue(minimum_zoom)
        self.maximum_zoom.setValue(maximum_zoom)
        self.apply_zoom_range()

    def show_range_details(self, minimum_zoom: int, maximum_zoom: int) -> None:
        lines = [
            "XYZ min/max zoom sample",
            "",
            "URL template:",
            OSM_URL,
            "",
            "Applied range:",
            f"Min zoom: {minimum_zoom}",
            f"Max zoom: {maximum_zoom}",
            "",
            "What it demonstrates:",
            "- setMinZoom limits the lowest tile zoom level.",
            "- setMaxZoom limits the highest tile zoom level.",
            "- Values are clamped by GisLayerXYZ to the safe internal range.",
            "- If min is greater than max, the range is normalized before applying it.",
            "",
            "SDK flow:",
            "viewer.add_xyz_layer(name, url_template, min_zoom, max_zoom, "
            "tile_size, attribution, cache_enabled, cache_directory)",
        ]
        self.details_view.setPlainText("\n".join(lines))

    def show_default_extent(self) -> None:
        if self.viewer.layer_count() > 0:
            self.viewer.set_view_extent(DEFAULT_EXTENT_3857)

    def activate_zoom_box(self) -> None:
        self.viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("XyzMinMaxZoom")
    app.setWindowIcon(application_icon())
    window = XyzMinMaxZoomWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
