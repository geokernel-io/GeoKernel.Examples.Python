import sys
from importlib.resources import files
from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QDockWidget, QFormLayout, QMainWindow, QMessageBox, QSpinBox, QTextEdit, QToolBar, QWidget
from geokernel import Viewer, ViewerEvent, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file

RASTER_LAYER_NAME = "World Raster"
MARKER_LAYER_NAME = "Pixel Marker"

class RasterWorldTransformWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.icons = files("geokernel").joinpath("assets/images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("RasterWorldTransform")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.viewer_widget)
        self.create_ui()

    def create_ui(self) -> None:
        self.pixel_x = QSpinBox(self)
        self.pixel_x.setEnabled(False)
        self.pixel_x.valueChanged.connect(self.update_from_pixel)

        self.pixel_y = QSpinBox(self)
        self.pixel_y.setEnabled(False)
        self.pixel_y.valueChanged.connect(self.update_from_pixel)

        self.details_view = QTextEdit(self)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(430)

        panel = QWidget(self)
        panel_layout = QFormLayout(panel)
        panel_layout.addRow("Pixel X", self.pixel_x)
        panel_layout.addRow("Pixel Y", self.pixel_y)
        panel_layout.addRow(self.details_view)

        details_dock = QDockWidget("Raster world transform", self)
        details_dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, details_dock)

        toolbar = QToolBar("Raster world transform", self)
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
            self.viewer.full_extent,
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

        self.pick_action = self.add_action(
            toolbar,
            "Identify.svg",
            "Pick World Point",
            self.activate_info,
        )
        self.pick_action.setCheckable(True)
        tool_group.addAction(self.pick_action)
        self.tool_group = tool_group

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

        try:
            raster_path = ensure_sample_file(
                app=self.app,
                zip_url=(
                    "https://github.com/geokernel-io/GeoKernel.SampleData/"
                    "releases/download/v1/world_8km_tif.zip"
                ),
                zip_name="world_8km_tif.zip",
                target_folder="world_8km_tif",
                required_file="world_8km.tif",
                title="RasterWorldTransform",
            )
            self.viewer.add_layer(str(raster_path))
            self.viewer.set_layer_name(0, RASTER_LAYER_NAME)

            transform = self.viewer.raster_world_transform(self.raster_index())
            width = int(transform["width"])
            height = int(transform["height"])
            self.configure_pixel_controls(width, height)
            self.update_from_pixel()
            self.viewer.full_extent()
        except Exception as error:
            QMessageBox.critical(
                self,
                "RasterWorldTransform",
                f"GeoTIFF could not be loaded:\n{error}",
            )

    def configure_pixel_controls(self, width: int, height: int) -> None:
        block_x = QSignalBlocker(self.pixel_x)
        block_y = QSignalBlocker(self.pixel_y)
        self.pixel_x.setRange(0, max(0, width - 1))
        self.pixel_y.setRange(0, max(0, height - 1))
        self.pixel_x.setValue(width // 2)
        self.pixel_y.setValue(height // 2)
        del block_x, block_y
        self.pixel_x.setEnabled(True)
        self.pixel_y.setEnabled(True)

    def raster_index(self) -> int:
        info = self.viewer.layer_info_by_name(RASTER_LAYER_NAME)
        index = int(info.get("index", -1))
        if index < 0:
            raise RuntimeError("Raster layer is not available.")
        return index

    def update_from_pixel(self, *_args) -> None:
        if not self.initialized or not self.pixel_x.isEnabled():
            return

        try:
            result = self.viewer.raster_world_transform(
                self.raster_index(),
                self.pixel_x.value(),
                self.pixel_y.value(),
            )
            world_x = float(result["worldX"])
            world_y = float(result["worldY"])
            self.replace_marker(world_x, world_y)
            self.details_view.setPlainText(
                self.transform_text(result, world_x, world_y)
            )
            self.viewer.invalidate_render_cache(True, True)
            self.viewer.refresh_layers()
            self.statusBar().showMessage(
                f"Pixel ({self.pixel_x.value()}, {self.pixel_y.value()}) -> "
                f"World ({world_x:.2f}, {world_y:.2f})"
            )
        except Exception as error:
            self.details_view.setPlainText(
                f"World transform could not be read:\n{error}"
            )

    def replace_marker(self, world_x: float, world_y: float) -> None:
        self.viewer.remove_layer_by_name(MARKER_LAYER_NAME)
        self.viewer.add_point_layer(
            MARKER_LAYER_NAME,
            [(world_x, world_y)],
            {
                "pointColor": "#D95D39",
                "pointSize": 13,
                "pointOutlineColor": "#8C321D",
                "lineWidth": 1.5,
            },
        )

    def transform_text(self, result: dict, world_x: float, world_y: float) -> str:
        lines = [
            "RasterWorldTransform sample",
            "",
            "Raster",
            f"Path: {result['path']}",
            f"Size: {result['width']} x {result['height']} px",
            f"EPSG: {result['epsgCode'] or 'unknown'}",
            "",
            "GisRasterWorldTransform",
            f"upperLeftCenterX: {result['upperLeftCenterX']:.6f}",
            f"upperLeftCenterY: {result['upperLeftCenterY']:.6f}",
            f"pixelSizeX: {result['pixelSizeX']:.6f}",
            f"pixelSizeY: {result['pixelSizeY']:.6f}",
            f"rotationX: {result['rotationX']:.6f}",
            f"rotationY: {result['rotationY']:.6f}",
            "",
            "Selected pixel",
            f"Pixel X/Y: {self.pixel_x.value()}, {self.pixel_y.value()}",
            f"World X/Y: {world_x:.3f}, {world_y:.3f}",
            "Reverse pixel X/Y: "
            f"{result.get('reversePixelX', 0):.3f}, "
            f"{result.get('reversePixelY', 0):.3f}",
            "",
            "Formula",
            "worldX = upperLeftCenterX + pixelX * pixelSizeX + pixelY * rotationY",
            "worldY = upperLeftCenterY + pixelX * rotationX + pixelY * pixelSizeY",
        ]
        return "\n".join(lines)

    def on_viewer_event(self, event: ViewerEvent) -> None:
        if event.event_type != ViewerEventType.MAP_MOUSE_UP:
            return
        if self.viewer.get_tool() != ViewerTool.INFO:
            return

        transform = self.viewer.raster_world_transform(self.raster_index())
        pixel = self.world_to_pixel(
            transform,
            event.extent.x_min,
            event.extent.y_min,
        )
        if pixel is None:
            return

        pixel_x = max(
            self.pixel_x.minimum(), min(self.pixel_x.maximum(), round(pixel[0]))
        )
        pixel_y = max(
            self.pixel_y.minimum(), min(self.pixel_y.maximum(), round(pixel[1]))
        )
        block_x = QSignalBlocker(self.pixel_x)
        block_y = QSignalBlocker(self.pixel_y)
        self.pixel_x.setValue(pixel_x)
        self.pixel_y.setValue(pixel_y)
        del block_x, block_y
        self.update_from_pixel()

    def world_to_pixel(
        self,
        transform: dict,
        world_x: float,
        world_y: float,
    ) -> tuple[float, float] | None:
        delta_x = world_x - float(transform["upperLeftCenterX"])
        delta_y = world_y - float(transform["upperLeftCenterY"])
        pixel_size_x = float(transform["pixelSizeX"])
        pixel_size_y = float(transform["pixelSizeY"])
        rotation_x = float(transform["rotationX"])
        rotation_y = float(transform["rotationY"])
        determinant = pixel_size_x * pixel_size_y - rotation_y * rotation_x
        if abs(determinant) < 1e-12:
            return None

        pixel_x = (delta_x * pixel_size_y - rotation_y * delta_y) / determinant
        pixel_y = (pixel_size_x * delta_y - delta_x * rotation_x) / determinant
        return pixel_x, pixel_y

    def activate_zoom_box(self) -> None:
        self.viewer.set_tool(ViewerTool.ZOOM_BOX)

    def activate_pan(self) -> None:
        self.viewer.set_tool(ViewerTool.PAN)

    def activate_info(self) -> None:
        self.viewer.set_tool(ViewerTool.INFO)

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("RasterWorldTransform")
    app.setWindowIcon(application_icon())
    window = RasterWorldTransformWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
