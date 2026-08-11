import sys
from importlib.resources import files
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QCheckBox, QDockWidget, QLabel, QLineEdit, QMainWindow, QMessageBox, QSpinBox, QTextEdit, QToolBar
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

DEFAULT_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_EXTENT_3857 = Extent(-1400000.0, 4100000.0, 4200000.0, 7800000.0)

class XyzCustomUrlWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.icons = files("geokernel").joinpath("assets/images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("XyzCustomUrl")
        self.setWindowIcon(application_icon())
        self.resize(1280, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        self.details_view = QTextEdit(self)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(360)
        details_dock = QDockWidget("Custom XYZ details", self)
        details_dock.setWidget(self.details_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        toolbar = QToolBar("Custom XYZ", self)
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
        url_label = QLabel("URL:", toolbar)
        url_label.setContentsMargins(4, 0, 4, 0)
        toolbar.addWidget(url_label)

        self.url_edit = QLineEdit(DEFAULT_URL, toolbar)
        self.url_edit.setMinimumWidth(470)
        self.url_edit.returnPressed.connect(self.apply_custom_url)
        toolbar.addWidget(self.url_edit)

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

        self.cache_check = QCheckBox("Local cache", toolbar)
        self.cache_check.setChecked(True)
        toolbar.addWidget(self.cache_check)

        apply_action = QAction("Apply URL", self)
        apply_action.triggered.connect(self.apply_custom_url)
        toolbar.addAction(apply_action)

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
        self.apply_custom_url()

    def apply_custom_url(self) -> None:
        if not self.initialized:
            return

        url_template = self.url_edit.text().strip()
        if not self.is_supported_tile_template(url_template):
            QMessageBox.warning(
                self,
                "XyzCustomUrl",
                "Tile URL template must include {z}, {x}, and {y}, or Bing-style {q}.",
            )
            return

        try:
            self.viewer.clear_layers()
            layer_index = self.viewer.add_xyz_layer(
                "Custom XYZ",
                url_template,
                self.minimum_zoom.value(),
                self.maximum_zoom.value(),
                256,
                "",
                self.cache_check.isChecked(),
            )
            if layer_index < 0:
                raise RuntimeError("add_xyz_layer returned an invalid layer index.")

            self.show_default_extent()
            self.show_layer_details(url_template)
            self.statusBar().showMessage("Custom XYZ URL applied.")
        except Exception as error:
            QMessageBox.critical(
                self,
                "XyzCustomUrl",
                f"Custom XYZ layer could not be loaded:\n{error}",
            )

    def is_supported_tile_template(self, url_template: str) -> bool:
        has_xyz = all(token in url_template for token in ("{z}", "{x}", "{y}"))
        return has_xyz or "{q}" in url_template

    def show_layer_details(self, url_template: str) -> None:
        cache_state = "enabled" if self.cache_check.isChecked() else "disabled"
        lines = [
            "Custom XYZ URL sample",
            "",
            "Active URL template:",
            url_template,
            "",
            f"Min zoom: {self.minimum_zoom.value()}",
            f"Max zoom: {self.maximum_zoom.value()}",
            "Tile size: 256",
            f"Local cache: {cache_state}",
            "",
            "SDK flow:",
            "viewer.add_xyz_layer(name, url_template, min_zoom, "
            "max_zoom, tile_size, attribution, cache_enabled)",
            "",
            "Template requirements:",
            "- XYZ: {z}, {x}, {y}",
            "- or Bing style: {q}",
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
    app.setApplicationName("XyzCustomUrl")
    app.setWindowIcon(application_icon())

    window = XyzCustomUrlWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
