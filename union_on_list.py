import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

SOURCE_POLYGONS = [
    [(-4.8, -1.4), (-0.8, -1.4), (-0.8, 1.8), (-4.8, 1.8), (-4.8, -1.4)],
    [(-2.6, -2.3), (1.2, -2.3), (1.2, 0.6), (-2.6, 0.6), (-2.6, -2.3)],
    [
        (0.3, 2.8),
        (0.9, 1.1),
        (2.8, 1.1),
        (1.3, 0.1),
        (2.1, -1.6),
        (0.3, -0.6),
        (-1.5, -1.6),
        (-0.7, 0.1),
        (-2.2, 1.1),
        (-0.3, 1.1),
        (0.3, 2.8),
    ],
    [(1.5, -0.2), (4.6, -0.2), (4.6, 2.0), (1.5, 2.0), (1.5, -0.2)],
    [(2.0, -2.4), (4.8, -1.2), (3.3, 0.7), (2.0, -2.4)],
]
SOURCE_STYLES = [
    ("#BFD7EA", "#2F80C2"),
    ("#D8EAC4", "#5B8E3E"),
    ("#F3D6A3", "#B7791F"),
    ("#D9C8F0", "#7048A8"),
    ("#BFE3D9", "#2D6A4F"),
]
FULL_EXTENT = Extent(-5.8, -3.3, 5.8, 4.0)

class UnionOnListWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("UnionOnList")
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
        toolbar_layout.addWidget(QLabel("Operation: UnionOnList(shapes)", toolbar))

        run_button = QPushButton("Run UnionOnList", toolbar)
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
            self.statusBar().showMessage("UnionOnList initialization failed.")

    def run_union(self) -> None:
        if self.initialized:
            self.render_scene(True)

    def render_scene(self, show_result: bool) -> None:
        self.viewer.clear_shapes()
        self.add_source_shapes()

        details = [
            "UnionOnList(shapes)",
            f"Source polygons: {len(SOURCE_POLYGONS)}",
        ]
        for index, polygon in enumerate(SOURCE_POLYGONS, start=1):
            details.append(
                f"Source {index} extent: {self.extent_text(self.parts_extent([polygon]))}"
            )

        if not show_result:
            details.append("Result: click Run UnionOnList to calculate")
            self.statusBar().showMessage(
                "Source polygons are ready. Click Run UnionOnList."
            )
        else:
            result = self.viewer.union_polygons_on_list(SOURCE_POLYGONS)
            rings = [
                [(float(point["x"]), float(point["y"])) for point in part]
                for part in result
                if part
            ]
            if not rings:
                details.append("Result: empty")
                self.statusBar().showMessage("UnionOnList returned an empty result.")
            else:
                for ring in rings:
                    if not self.viewer.add_polygon_shape(
                        ring,
                        {
                            "fillColor": "#F9C74F",
                            "fillOpacity": 135,
                            "lineColor": "#D95D39",
                            "lineWidth": 3.0,
                        },
                    ):
                        raise RuntimeError(
                            "UnionOnList result shape could not be rendered."
                        )
                details.extend(
                    (
                        "Result type: polygon",
                        f"Result parts: {len(rings)}",
                        f"Result extent: {self.extent_text(self.parts_extent(rings))}",
                    )
                )
                self.statusBar().showMessage("UnionOnList result created.")

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.details_view.setPlainText("\n".join(details))

    def add_source_shapes(self) -> None:
        for polygon, colors in zip(SOURCE_POLYGONS, SOURCE_STYLES):
            if not self.viewer.add_polygon_shape(
                polygon,
                {
                    "fillColor": colors[0],
                    "fillOpacity": 110,
                    "lineColor": colors[1],
                    "lineWidth": 2.0,
                },
            ):
                raise RuntimeError("Source polygon shape could not be rendered.")

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
    app.setApplicationName("UnionOnList")
    app.setWindowIcon(application_icon())
    window = UnionOnListWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
