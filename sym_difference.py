import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

LEFT_POLYGON = [
    (-4.4, -1.8),
    (1.2, -1.8),
    (1.2, 2.2),
    (-4.4, 2.2),
    (-4.4, -1.8),
]
RIGHT_POLYGON = [
    (-0.2, 3.0),
    (0.6, 1.2),
    (3.2, 1.2),
    (1.1, -0.1),
    (2.0, -2.0),
    (-0.2, -0.8),
    (-2.4, -2.0),
    (-1.5, -0.1),
    (-3.6, 1.2),
    (-1.0, 1.2),
    (-0.2, 3.0),
]
FULL_EXTENT = Extent(-5.2, -3.2, 5.0, 4.0)

class SymDifferenceWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("SymDifference")
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
        toolbar_layout.addWidget(
            QLabel("Operation: SymmetricalDifference(left, right)", toolbar)
        )
        run_button = QPushButton("Run Sym Difference", toolbar)
        run_button.clicked.connect(self.run_sym_difference)
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
            self.statusBar().showMessage("SymDifference initialization failed.")

    def run_sym_difference(self) -> None:
        if self.initialized:
            self.render_scene(True)

    def render_scene(self, show_result: bool) -> None:
        current_extent = self.viewer.get_view_extent() if show_result else None
        self.viewer.clear_shapes()
        self.add_source_shapes()
        details = [
            "SymmetricalDifference(left, right)",
            "This keeps areas that belong to only one source polygon.",
            f"Left extent: {self.extent_text(self.polygon_extent(LEFT_POLYGON))}",
            f"Right extent: {self.extent_text(self.polygon_extent(RIGHT_POLYGON))}",
        ]

        if not show_result:
            details.append("Result: click Run Sym Difference to calculate")
            self.statusBar().showMessage(
                "Source polygons are ready. Click Run Sym Difference."
            )
        else:
            result = self.viewer.symmetrical_difference_polygons(
                LEFT_POLYGON, RIGHT_POLYGON
            )
            rings = [
                [(float(point["x"]), float(point["y"])) for point in part]
                for part in result
                if part
            ]
            if not rings:
                details.append("Result: empty")
                self.statusBar().showMessage(
                    "Symmetrical difference returned an empty result."
                )
            else:
                added = self.viewer.add_polygon_parts_shape(
                    rings,
                    {
                        "fillColor": "#F9C74F",
                        "fillOpacity": 155,
                        "lineColor": "#D95D39",
                        "lineWidth": 3.0,
                    },
                )
                if not added:
                    raise RuntimeError(
                        "Symmetrical difference result could not be rendered."
                    )
                details.extend(
                    (
                        "Result type: polygon",
                        f"Result parts: {len(rings)}",
                        f"Result extent: {self.extent_text(self.parts_extent(rings))}",
                    )
                )
                self.statusBar().showMessage("Symmetrical difference result created.")

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        if current_extent is not None:
            self.viewer.set_view_extent(current_extent)
        self.details_view.setPlainText("\n".join(details))

    def add_source_shapes(self) -> None:
        left_added = self.viewer.add_polygon_shape(
            LEFT_POLYGON,
            {
                "fillColor": "#BFD7EA",
                "fillOpacity": 115,
                "lineColor": "#2F80C2",
                "lineWidth": 2.0,
            },
        )
        right_added = self.viewer.add_polygon_shape(
            RIGHT_POLYGON,
            {
                "fillColor": "#CDE7D8",
                "fillOpacity": 115,
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
    app.setApplicationName("SymDifference")
    app.setWindowIcon(application_icon())
    window = SymDifferenceWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
