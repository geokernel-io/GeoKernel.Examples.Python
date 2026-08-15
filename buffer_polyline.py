import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

SOURCE_POLYLINE = [
    (-4.6, -1.5),
    (-2.8, 0.4),
    (-1.0, -0.8),
    (0.7, 1.2),
    (2.5, 0.1),
    (4.4, 1.6),
]
FULL_EXTENT = Extent(-5.8, -3.2, 5.8, 3.4)

class BufferPolylineWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("Buffer Polyline")
        self.setWindowIcon(application_icon())
        self.resize(980, 680)
        self.create_ui()

    def create_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        toolbar = QWidget(root)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(8)

        full_extent_button = QPushButton("Full Extent", toolbar)
        full_extent_button.clicked.connect(self.show_full_extent)
        toolbar_layout.addWidget(full_extent_button)
        toolbar_layout.addWidget(QLabel("Distance:", toolbar))

        self.distance_spin = QDoubleSpinBox(toolbar)
        self.distance_spin.setDecimals(2)
        self.distance_spin.setRange(0.10, 2.0)
        self.distance_spin.setSingleStep(0.10)
        self.distance_spin.setValue(0.55)
        self.distance_spin.setSuffix(" units")
        self.distance_spin.setMinimumWidth(120)
        self.distance_spin.valueChanged.connect(self.update_buffer)
        toolbar_layout.addWidget(self.distance_spin)
        toolbar_layout.addStretch(1)

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(content)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(280)
        content_layout.addWidget(self.details_view)

        root_layout.addWidget(toolbar)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()

        try:
            self.update_buffer()
            self.show_full_extent()
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("BufferPolyline initialization failed.")

    def update_buffer(self, distance: float | None = None) -> None:
        if not self.initialized:
            return

        buffer_distance = (
            self.distance_spin.value() if distance is None else float(distance)
        )
        self.viewer.clear_shapes()

        buffer_added = self.viewer.add_polyline_buffer_shape(
            SOURCE_POLYLINE,
            buffer_distance,
            12,
            {
                "fillColor": "#F9C74F",
                "fillOpacity": 105,
                "lineColor": "#D95D39",
                "lineWidth": 2.0,
            },
        )
        if not buffer_added:
            self.show_empty_result(buffer_distance)
            self.add_source_polyline()
            return

        self.add_source_polyline()
        result_extent = self.buffer_extent(buffer_distance)
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.details_view.setPlainText(
            "\n".join(
                (
                    "MakeBuffer(polyline, distance)",
                    "Source parts: 1",
                    f"Source vertices: {len(SOURCE_POLYLINE)}",
                    f"Distance: {buffer_distance:.2f} map units",
                    "Result type: polygon",
                    "Result parts: 1",
                    f"Result extent: {self.extent_text(result_extent)}",
                )
            )
        )
        self.statusBar().showMessage(
            f"Polyline buffer distance: {buffer_distance:.2f} map units"
        )

    def add_source_polyline(self) -> None:
        added = self.viewer.add_polyline_shape(
            SOURCE_POLYLINE,
            {
                "fillColor": "#FFFFFF",
                "fillOpacity": 0,
                "lineColor": "#1E5678",
                "lineWidth": 3.0,
                "pointColor": "#1E5678",
                "pointSize": 8.0,
            },
        )
        if not added:
            raise RuntimeError("Source polyline shape could not be created.")

    def buffer_extent(self, distance: float) -> Extent:
        x_values = [point[0] for point in SOURCE_POLYLINE]
        y_values = [point[1] for point in SOURCE_POLYLINE]
        return Extent(
            min(x_values) - distance,
            min(y_values) - distance,
            max(x_values) + distance,
            max(y_values) + distance,
        )

    def show_empty_result(self, distance: float) -> None:
        self.details_view.setPlainText(
            f"MakeBuffer(polyline, {distance:.2f}) returned an empty shape."
        )
        self.statusBar().showMessage("Empty buffer result")

    def show_full_extent(self) -> None:
        if self.initialized:
            self.viewer.set_view_extent(FULL_EXTENT)

    def extent_text(self, extent: Extent) -> str:
        return (
            f"({extent.x_min:.2f}, {extent.y_min:.2f}) - "
            f"({extent.x_max:.2f}, {extent.y_max:.2f})"
        )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BufferPolyline")
    app.setWindowIcon(application_icon())
    window = BufferPolylineWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
