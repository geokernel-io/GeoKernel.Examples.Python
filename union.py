import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

LEFT_POLYGON = [
    (-4.2, -1.7),
    (0.8, -1.7),
    (0.8, 2.2),
    (-4.2, 2.2),
    (-4.2, -1.7),
]
RIGHT_POLYGON = [
    (1.0, 3.0),
    (1.7, 1.2),
    (3.7, 1.2),
    (2.1, 0.1),
    (2.8, -1.8),
    (1.0, -0.7),
    (-0.8, -1.8),
    (-0.1, 0.1),
    (-1.7, 1.2),
    (0.3, 1.2),
    (1.0, 3.0),
]
FULL_EXTENT = Extent(-5.2, -3.2, 5.2, 4.0)

class UnionWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.showing_result = False

        self.setWindowTitle("Union")
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
        toolbar_layout.addWidget(QLabel("Operation: Union(left, right)", toolbar))

        run_button = QPushButton("Run Union", toolbar)
        run_button.clicked.connect(self.run_union)
        toolbar_layout.addWidget(run_button)
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
            self.render_scene(False)
            self.show_full_extent()
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("Union initialization failed.")

    def run_union(self) -> None:
        if not self.initialized:
            return
        self.showing_result = True
        self.render_scene(True)

    def render_scene(self, show_result: bool) -> None:
        self.viewer.clear_shapes()
        self.add_source_shapes()

        left_extent = self.polygon_extent(LEFT_POLYGON)
        right_extent = self.polygon_extent(RIGHT_POLYGON)
        details = [
            "Union(left, right)",
            f"Left extent: {self.extent_text(left_extent)}",
            f"Right extent: {self.extent_text(right_extent)}",
        ]

        if not show_result:
            details.append("Result: click Run Union to calculate")
            self.statusBar().showMessage("Source polygons are ready. Click Run Union.")
        else:
            result_parts = self.viewer.union_polygons(LEFT_POLYGON, RIGHT_POLYGON)
            rings = [
                [(float(point["x"]), float(point["y"])) for point in part]
                for part in result_parts
                if part
            ]
            if not rings:
                details.append("Result: empty")
                self.statusBar().showMessage("Union returned an empty result.")
            else:
                for ring in rings:
                    if not self.viewer.add_polygon_shape(
                        ring,
                        {
                            "fillColor": "#F9C74F",
                            "fillOpacity": 120,
                            "lineColor": "#D95D39",
                            "lineWidth": 3.0,
                        },
                    ):
                        raise RuntimeError("Union result shape could not be rendered.")
                result_extent = self.parts_extent(rings)
                details.extend(
                    (
                        "Result type: polygon",
                        f"Result parts: {len(rings)}",
                        f"Result extent: {self.extent_text(result_extent)}",
                    )
                )
                self.statusBar().showMessage("Union result created.")

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.details_view.setPlainText("\n".join(details))

    def add_source_shapes(self) -> None:
        left_added = self.viewer.add_polygon_shape(
            LEFT_POLYGON,
            {
                "fillColor": "#BFD7EA",
                "fillOpacity": 135,
                "lineColor": "#2F80C2",
                "lineWidth": 2.0,
            },
        )
        right_added = self.viewer.add_polygon_shape(
            RIGHT_POLYGON,
            {
                "fillColor": "#CDE7D8",
                "fillOpacity": 135,
                "lineColor": "#2D6A4F",
                "lineWidth": 2.0,
            },
        )
        if not left_added or not right_added:
            raise RuntimeError("Source polygon shapes could not be rendered.")

    def polygon_extent(self, polygon: list[tuple[float, float]]) -> Extent:
        return self.parts_extent([polygon])

    def parts_extent(self, parts: list[list[tuple[float, float]]]) -> Extent:
        points = [point for part in parts for point in part]
        return Extent(
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        )

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
    app.setApplicationName("Union")
    app.setWindowIcon(application_icon())
    window = UnionWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
