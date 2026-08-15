import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

SOURCE_POLYGON = [
    (-4.0, -2.0),
    (3.8, -2.0),
    (4.5, 0.5),
    (2.5, 2.4),
    (-1.5, 2.1),
    (-4.4, 0.6),
    (-4.0, -2.0),
]
SPLIT_ARC = [
    (-5.2, 1.4),
    (-1.8, 0.7),
    (0.2, -0.2),
    (2.0, -0.6),
    (5.1, -1.0),
]
RESULT_COLORS = ("#F9C74F", "#A7D8F0", "#CDE7D8")
FULL_EXTENT = Extent(-5.7, -3.0, 5.7, 3.2)

class SplitByArcWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("SplitByArc")
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
            QLabel("Operation: SplitByArc(polygon, line)", toolbar)
        )
        run_button = QPushButton("Run SplitByArc", toolbar)
        run_button.clicked.connect(self.run_split_by_arc)
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
            self.statusBar().showMessage("SplitByArc initialization failed.")

    def run_split_by_arc(self) -> None:
        if self.initialized:
            self.render_scene(True)

    def render_scene(self, show_result: bool) -> None:
        current_extent = self.viewer.get_view_extent() if show_result else None
        self.viewer.clear_shapes()
        self.add_source_shapes()
        details = [
            "SplitByArc(polygon, line)",
            "Source polygon parts: 1",
            "Split arc parts: 1",
            f"Polygon extent: {self.extent_text(self.parts_extent([SOURCE_POLYGON]))}",
            f"Arc extent: {self.extent_text(self.parts_extent([SPLIT_ARC]))}",
        ]

        if not show_result:
            details.append("Result: click Run SplitByArc to calculate")
            self.statusBar().showMessage(
                "Source polygon and split arc are ready. Click Run SplitByArc."
            )
        else:
            result = self.viewer.split_polygon_by_arc(SOURCE_POLYGON, SPLIT_ARC)
            pieces = [
                [(float(point["x"]), float(point["y"])) for point in part]
                for part in result
                if part
            ]
            details.append(f"Result shapes: {len(pieces)}")
            for index, piece in enumerate(pieces):
                added = self.viewer.add_polygon_shape(
                    piece,
                    {
                        "fillColor": RESULT_COLORS[index % len(RESULT_COLORS)],
                        "fillOpacity": 155,
                        "lineColor": "#D95D39",
                        "lineWidth": 2.8,
                    },
                )
                if not added:
                    raise RuntimeError(
                        f"Result piece {index + 1} could not be rendered."
                    )
                details.append(
                    f"Piece {index + 1} parts: 1 extent: "
                    f"{self.extent_text(self.parts_extent([piece]))}"
                )
            if pieces:
                self.viewer.add_polyline_shape(
                    SPLIT_ARC,
                    {"lineColor": "#2D3436", "lineWidth": 2.8},
                )
                self.statusBar().showMessage("SplitByArc result created.")
            else:
                self.statusBar().showMessage("SplitByArc returned an empty result.")

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        if current_extent is not None:
            self.viewer.set_view_extent(current_extent)
        self.details_view.setPlainText("\n".join(details))

    def add_source_shapes(self) -> None:
        polygon_added = self.viewer.add_polygon_shape(
            SOURCE_POLYGON,
            {
                "fillColor": "#BFD7EA",
                "fillOpacity": 115,
                "lineColor": "#2F80C2",
                "lineWidth": 2.2,
            },
        )
        arc_added = self.viewer.add_polyline_shape(
            SPLIT_ARC,
            {"lineColor": "#2D3436", "lineWidth": 2.8},
        )
        if not polygon_added or not arc_added:
            raise RuntimeError("Source shapes could not be rendered.")

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
    app.setApplicationName("SplitByArc")
    app.setWindowIcon(application_icon())
    window = SplitByArcWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
