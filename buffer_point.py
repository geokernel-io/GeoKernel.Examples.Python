import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

SOURCE_POINT = (0.0, 0.0)
FULL_EXTENT = Extent(-5.0, -4.0, 5.0, 4.0)

class BufferPointWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("Buffer Point")
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
        self.distance_spin.setRange(0.25, 5.0)
        self.distance_spin.setSingleStep(0.25)
        self.distance_spin.setValue(2.0)
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
            self.statusBar().showMessage("BufferPoint initialization failed.")

    def update_buffer(self, distance: float | None = None) -> None:
        if not self.initialized:
            return

        buffer_distance = (
            self.distance_spin.value() if distance is None else float(distance)
        )
        self.viewer.clear_shapes()

        buffer_added = self.viewer.add_point_buffer_shape(
            SOURCE_POINT[0],
            SOURCE_POINT[1],
            buffer_distance,
            16,
            {
                "fillColor": "#78B7D0",
                "fillOpacity": 85,
                "lineColor": "#1E6F8C",
                "lineWidth": 2.0,
            },
        )
        if not buffer_added:
            self.show_empty_result(buffer_distance)
            self.add_source_point()
            return

        self.add_source_point()
        result_extent = Extent(
            SOURCE_POINT[0] - buffer_distance,
            SOURCE_POINT[1] - buffer_distance,
            SOURCE_POINT[0] + buffer_distance,
            SOURCE_POINT[1] + buffer_distance,
        )

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.details_view.setPlainText(
            "\n".join(
                (
                    "MakeBuffer(point, distance)",
                    f"Source point: ({SOURCE_POINT[0]:.2f}, {SOURCE_POINT[1]:.2f})",
                    f"Distance: {buffer_distance:.2f} map units",
                    "Result type: polygon",
                    "Result parts: 1",
                    f"Result extent: {self.extent_text(result_extent)}",
                )
            )
        )
        self.statusBar().showMessage(
            f"Point buffer distance: {buffer_distance:.2f} map units"
        )

    def add_source_point(self) -> None:
        added = self.viewer.add_point_shape(
            SOURCE_POINT[0],
            SOURCE_POINT[1],
            {
                "fillColor": "#D95D39",
                "fillOpacity": 255,
                "lineColor": "#7A2F1E",
                "lineWidth": 1.3,
                "pointColor": "#D95D39",
                "pointSize": 13.0,
            },
        )
        if not added:
            raise RuntimeError("Source point shape could not be created.")

    def show_empty_result(self, distance: float) -> None:
        self.details_view.setPlainText(
            f"MakeBuffer(point, {distance:.2f}) returned an empty shape."
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
    app.setApplicationName("BufferPoint")
    app.setWindowIcon(application_icon())
    window = BufferPointWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
