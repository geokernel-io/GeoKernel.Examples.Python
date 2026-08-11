import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QSlider, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

MIN_DISTANCE = 0.35
MAX_DISTANCE = 3.0
DISTANCE_STEP = 0.08
FULL_EXTENT = Extent(-4.2, -3.5, 4.2, 3.5)

class BufferAnimatedWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.distance = MIN_DISTANCE
        self.direction = 1
        self.frame = 0
        self.initialized = False
        self.closing = False

        self.timer = QTimer(self)
        self.timer.setInterval(60)
        self.timer.timeout.connect(self.advance_frame)

        self.setWindowTitle("Buffer Animated")
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

        self.play_pause_button = QPushButton("Pause", toolbar)
        self.play_pause_button.clicked.connect(self.toggle_animation)
        toolbar_layout.addWidget(self.play_pause_button)

        full_extent_button = QPushButton("Full Extent", toolbar)
        full_extent_button.clicked.connect(self.show_full_extent)
        toolbar_layout.addWidget(full_extent_button)
        toolbar_layout.addWidget(QLabel("Interval:", toolbar))

        self.speed_slider = QSlider(Qt.Orientation.Horizontal, toolbar)
        self.speed_slider.setRange(20, 200)
        self.speed_slider.setValue(60)
        self.speed_slider.setFixedWidth(160)
        self.speed_slider.valueChanged.connect(self.change_interval)
        toolbar_layout.addWidget(self.speed_slider)
        toolbar_layout.addWidget(QLabel("Distance:", toolbar))

        self.distance_label = QLabel(toolbar)
        self.distance_label.setMinimumWidth(80)
        toolbar_layout.addWidget(self.distance_label)
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
            self.render_frame()
            self.show_full_extent()
            self.timer.start()
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("BufferAnimated initialization failed.")

    def advance_frame(self) -> None:
        if self.closing or not self.initialized:
            return

        self.distance += DISTANCE_STEP * self.direction
        if self.distance >= MAX_DISTANCE:
            self.distance = MAX_DISTANCE
            self.direction = -1
        elif self.distance <= MIN_DISTANCE:
            self.distance = MIN_DISTANCE
            self.direction = 1

        self.frame += 1
        self.render_frame()

    def render_frame(self) -> None:
        if self.closing:
            return
        self.viewer.clear_shapes()

        opacity_ratio = (self.distance - MIN_DISTANCE) / (MAX_DISTANCE - MIN_DISTANCE)
        opacity = 55 + int(opacity_ratio * 90.0)
        buffer_added = self.viewer.add_point_buffer_shape(
            0.0,
            0.0,
            self.distance,
            18,
            {
                "fillColor": "#78B7D0",
                "fillOpacity": opacity,
                "lineColor": "#1E6F8C",
                "lineWidth": 2.2,
            },
        )
        pulse_distance = max(MIN_DISTANCE, self.distance - 0.28)
        pulse_added = self.viewer.add_point_buffer_shape(
            0.0,
            0.0,
            pulse_distance,
            18,
            {
                "fillColor": "#FFFFFF",
                "fillOpacity": 0,
                "lineColor": "#D95D39",
                "lineWidth": 1.3,
            },
        )
        point_added = self.viewer.add_point_shape(
            0.0,
            0.0,
            {
                "fillColor": "#D95D39",
                "fillOpacity": 255,
                "lineColor": "#7A2F1E",
                "lineWidth": 1.2,
                "pointColor": "#D95D39",
                "pointSize": 13.0,
            },
        )
        if not buffer_added or not pulse_added or not point_added:
            raise RuntimeError("Animated buffer frame could not be rendered.")

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.distance_label.setText(f"{self.distance:.2f} units")
        result_extent = Extent(
            -self.distance,
            -self.distance,
            self.distance,
            self.distance,
        )
        self.details_view.setPlainText(
            "\n".join(
                (
                    "QTimer animated buffer",
                    "Operation: MakeBuffer(point, distance)",
                    f"Frame: {self.frame}",
                    f"Distance: {self.distance:.2f} map units",
                    "Source point: (0.00, 0.00)",
                    "Result parts: 1",
                    f"Result extent: {self.extent_text(result_extent)}",
                )
            )
        )
        self.statusBar().showMessage(
            f"Animated point buffer: frame {self.frame}, distance {self.distance:.2f}"
        )

    def toggle_animation(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.play_pause_button.setText("Play")
        elif not self.closing:
            self.timer.start()
            self.play_pause_button.setText("Pause")

    def change_interval(self, interval: int) -> None:
        self.timer.setInterval(interval)

    def show_full_extent(self) -> None:
        if self.initialized and not self.closing:
            self.viewer.set_view_extent(FULL_EXTENT)

    def extent_text(self, extent: Extent) -> str:
        return (
            f"({extent.x_min:.2f}, {extent.y_min:.2f}) - "
            f"({extent.x_max:.2f}, {extent.y_max:.2f})"
        )

    def closeEvent(self, event) -> None:
        self.closing = True
        self.timer.stop()
        self.timer.timeout.disconnect(self.advance_frame)
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BufferAnimated")
    app.setWindowIcon(application_icon())
    window = BufferAnimatedWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
