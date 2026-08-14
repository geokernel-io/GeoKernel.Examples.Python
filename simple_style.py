import sys
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QColorDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

INITIAL_EXTENT = Extent(-19.5, -14.2, 20.5, 18.9)
DEFAULT_FILL_COLOR = "#F1D58A"
DEFAULT_LINE_COLOR = "#266D8F"
DEFAULT_LINE_WIDTH = 2.0
DEFAULT_POINT_SIZE = 10.0

class SimpleStyleWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.fill_color = DEFAULT_FILL_COLOR
        self.line_color = DEFAULT_LINE_COLOR
        self.polygon_layer_index = 2
        self.polyline_layer_index = 1
        self.point_layer_index = 0

        self.setWindowTitle("SimpleStyle")
        self.setWindowIcon(application_icon())
        self.resize(1100, 720)

        self.fill_color_button = QPushButton(self)
        self.line_color_button = QPushButton(self)
        self.line_width_spin = self.create_spin_box(0.5, 12.0, DEFAULT_LINE_WIDTH)
        self.point_size_spin = self.create_spin_box(2.0, 32.0, DEFAULT_POINT_SIZE)
        self.reset_button = QPushButton("Reset Style", self)

        self.create_layout()
        self.connect_controls()
        self.update_color_buttons()

    def create_spin_box(self, minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin_box = QDoubleSpinBox(self)
        spin_box.setRange(minimum, maximum)
        spin_box.setDecimals(1)
        spin_box.setSingleStep(0.5)
        spin_box.setValue(value)
        return spin_box

    def create_layout(self) -> None:
        central_widget = QWidget(self)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        side_panel = QWidget(central_widget)
        side_panel.setFixedWidth(230)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(10, 10, 10, 10)
        side_layout.setSpacing(8)
        side_layout.addWidget(QLabel("Fill Color", side_panel))
        side_layout.addWidget(self.fill_color_button)
        side_layout.addWidget(QLabel("Line Color", side_panel))
        side_layout.addWidget(self.line_color_button)
        side_layout.addWidget(QLabel("Line Width", side_panel))
        side_layout.addWidget(self.line_width_spin)
        side_layout.addWidget(QLabel("Point Size", side_panel))
        side_layout.addWidget(self.point_size_spin)
        side_layout.addWidget(self.reset_button)
        side_layout.addStretch(1)

        main_layout.addWidget(side_panel)
        main_layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central_widget)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.create_layers()
        self.apply_style()
        self.viewer.set_view_extent(INITIAL_EXTENT)

    def create_layers(self) -> None:
        polygon = [[
            (-8.0, -3.0),
            (1.0, -3.0),
            (3.0, 4.0),
            (-6.0, 6.0),
            (-10.0, 2.0),
            (-8.0, -3.0),
        ]]
        polyline = [[
            (-12.0, -7.0),
            (-5.0, -1.0),
            (1.0, -5.0),
            (8.0, 2.0),
            (13.0, -2.0),
        ]]
        points = [(-6.0, 9.0), (0.0, 8.0), (7.0, 7.0)]
        self.viewer.add_polygon_layer("Styled Polygon", polygon)
        self.viewer.add_polyline_layer("Styled Polyline", polyline)
        self.viewer.add_point_layer("Styled Points", points)

    def connect_controls(self) -> None:
        self.fill_color_button.clicked.connect(self.choose_fill_color)
        self.line_color_button.clicked.connect(self.choose_line_color)
        self.line_width_spin.valueChanged.connect(self.apply_style)
        self.point_size_spin.valueChanged.connect(self.apply_style)
        self.reset_button.clicked.connect(self.reset_style)

    def choose_fill_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.fill_color), self, "Fill Color")
        if not color.isValid():
            return
        self.fill_color = color.name()
        self.update_color_buttons()
        self.apply_style()

    def choose_line_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.line_color), self, "Line Color")
        if not color.isValid():
            return
        self.line_color = color.name()
        self.update_color_buttons()
        self.apply_style()

    def update_color_buttons(self) -> None:
        self.set_color_button_swatch(self.fill_color_button, self.fill_color)
        self.set_color_button_swatch(self.line_color_button, self.line_color)

    def set_color_button_swatch(self, button: QPushButton, color: str) -> None:
        button.setStyleSheet(
            f"QPushButton {{ background:{color}; border:1px solid #7f8c8d; min-height:24px; }}"
        )

    def apply_style(self) -> None:
        self.viewer.set_layer_style(
            self.polygon_layer_index,
            {
                "fillColor": self.fill_color,
                "fillOpacity": 185,
                "lineColor": self.line_color,
                "lineWidth": self.line_width_spin.value(),
            },
        )
        self.viewer.set_layer_style(
            self.polyline_layer_index,
            {"lineColor": self.line_color, "lineWidth": self.line_width_spin.value()},
        )
        self.viewer.set_layer_style(
            self.point_layer_index,
            {"pointColor": "#D95F35", "pointSize": self.point_size_spin.value()},
        )
        self.viewer.refresh_layers()

    def reset_style(self) -> None:
        self.fill_color = DEFAULT_FILL_COLOR
        self.line_color = DEFAULT_LINE_COLOR
        self.line_width_spin.setValue(DEFAULT_LINE_WIDTH)
        self.point_size_spin.setValue(DEFAULT_POINT_SIZE)
        self.update_color_buttons()
        self.apply_style()

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SimpleStyle")
    app.setWindowIcon(application_icon())
    window = SimpleStyleWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
