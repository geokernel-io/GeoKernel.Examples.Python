import sys
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QColorDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

INITIAL_EXTENT = Extent(-15.0, -9.0, 15.0, 11.0)
DEFAULT_SELECTED_COLOR = "#F59E0B"
DEFAULT_SELECTED_WIDTH = 4.0

class SelectionStyleWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.SELECT)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.selected_color = DEFAULT_SELECTED_COLOR
        self.polygon_layer_index = 2
        self.polyline_layer_index = 1
        self.point_layer_index = 0

        self.setWindowTitle("SelectionStyle")
        self.setWindowIcon(application_icon())
        self.resize(1100, 720)

        self.selected_color_button = QPushButton(self)
        self.selected_width_spin = QDoubleSpinBox(self)
        self.selected_width_spin.setRange(1.0, 16.0)
        self.selected_width_spin.setDecimals(1)
        self.selected_width_spin.setSingleStep(0.5)
        self.selected_width_spin.setValue(DEFAULT_SELECTED_WIDTH)
        self.clear_selection_button = QPushButton("Clear Selection", self)
        self.reset_button = QPushButton("Reset Style", self)

        self.create_layout()
        self.connect_controls()
        self.update_color_button()

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
        side_layout.addWidget(QLabel("Selected Line Color", side_panel))
        side_layout.addWidget(self.selected_color_button)
        side_layout.addWidget(QLabel("Selected Line Width", side_panel))
        side_layout.addWidget(self.selected_width_spin)
        side_layout.addWidget(self.clear_selection_button)
        side_layout.addWidget(self.reset_button)
        side_layout.addStretch(1)

        main_layout.addWidget(side_panel)
        main_layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central_widget)

    def connect_controls(self) -> None:
        self.selected_color_button.clicked.connect(self.choose_selected_color)
        self.selected_width_spin.valueChanged.connect(self.apply_selection_style)
        self.clear_selection_button.clicked.connect(self.clear_selection)
        self.reset_button.clicked.connect(self.reset_style)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.create_layers()
        self.apply_selection_style()
        self.viewer.set_view_extent(INITIAL_EXTENT)

    def create_layers(self) -> None:
        polygons = [
            [(-11.0, -4.0), (-4.0, -4.0), (-3.0, 2.0), (-8.0, 5.0), (-12.0, 1.0), (-11.0, -4.0)],
            [(2.0, -4.0), (10.0, -4.0), (12.0, 2.0), (6.0, 5.0), (1.0, 1.0), (2.0, -4.0)],
        ]
        polyline = [[(-12.0, -7.0), (-6.0, -1.0), (0.0, -5.5), (6.0, -0.5), (13.0, -5.0)]]
        points = [(-8.0, 8.0), (0.0, 7.0), (8.0, 8.0)]

        self.viewer.add_polygon_layer("Selectable Polygons", polygons)
        self.viewer.add_polyline_layer("Selectable Polyline", polyline)
        self.viewer.add_point_layer("Selectable Points", points)
        self.viewer.set_layer_style(self.polygon_layer_index, {"fillColor": "#F1D58A", "fillOpacity": 180, "lineColor": "#266D8F", "lineWidth": 1.8})
        self.viewer.set_layer_style(self.polyline_layer_index, {"lineColor": "#266D8F", "lineWidth": 2.2})
        self.viewer.set_layer_style(self.point_layer_index, {"pointColor": "#D95F35", "pointSize": 10.0})

    def choose_selected_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.selected_color), self, "Selected Line Color")
        if not color.isValid():
            return
        self.selected_color = color.name()
        self.update_color_button()
        self.apply_selection_style()

    def update_color_button(self) -> None:
        self.selected_color_button.setStyleSheet(
            f"QPushButton {{ background:{self.selected_color}; border:1px solid #7f8c8d; min-height:24px; }}"
        )

    def apply_selection_style(self) -> None:
        if not self.initialized:
            return
        selection_style = {"selectedLineColor": self.selected_color, "selectedLineWidth": self.selected_width_spin.value()}
        for layer_index in (self.polygon_layer_index, self.polyline_layer_index, self.point_layer_index):
            self.viewer.set_layer_style(layer_index, selection_style)
        self.viewer.refresh_layers()

    def clear_selection(self) -> None:
        if self.initialized:
            self.viewer.clear_selected_features()

    def reset_style(self) -> None:
        self.selected_color = DEFAULT_SELECTED_COLOR
        self.selected_width_spin.setValue(DEFAULT_SELECTED_WIDTH)
        self.update_color_button()
        self.apply_selection_style()

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SelectionStyle")
    app.setWindowIcon(application_icon())
    window = SelectionStyleWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
