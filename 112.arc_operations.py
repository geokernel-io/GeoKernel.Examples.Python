import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

FIND_QUERY = [(-5.2, 2.2), (-3.2, 2.2)]
FIND_CANDIDATES = [[(-1.8, 2.7), (0.4, 2.7)], [(-5.2, 2.2), (-3.2, 2.2)]]
CONNECT_BASE = [(-5.2, 0.2), (-3.6, 0.2), (-2.6, 0.8)]
CONNECT_CONTINUATION = [(-2.6, 0.8), (-1.1, 0.1), (0.4, 0.4)]
SPLIT_ARC = [(-5.2, -2.0), (-1.0, -2.0)]
SPLIT_CUTTER = [(-3.1, -3.0), (-3.1, -1.0)]
RESULT_COLORS = ("#D95D39", "#2A9D8F", "#7B2CBF")
FULL_EXTENT = Extent(-5.8, -3.3, 1.0, 3.2)

class ArcOperationsWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("ArcOperations")
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
            QLabel("Operations: ArcFind / ArcMakeConnected / ArcSplitOnCross", toolbar)
        )
        run_button = QPushButton("Run Arc Operations", toolbar)
        run_button.clicked.connect(self.run_operations)
        toolbar_layout.addWidget(run_button)
        toolbar_layout.addStretch(1)

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.viewer_widget, 1)
        self.details_view = QTextEdit(content)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(290)
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
            self.statusBar().showMessage("ArcOperations initialization failed.")

    def run_operations(self) -> None:
        if self.initialized:
            self.render_scene(True)

    def render_scene(self, show_results: bool) -> None:
        current_extent = self.viewer.get_view_extent() if show_results else None
        self.viewer.clear_shapes()
        self.add_source_shapes()
        details = [
            "ArcFind / ArcMakeConnected / ArcSplitOnCross",
            "",
            "1. ArcFind",
            f"Query arc extent: {self.extent_text(FIND_QUERY)}",
            f"Candidate count: {len(FIND_CANDIDATES)}",
            "",
            "2. ArcMakeConnected",
            f"Base vertices: {len(CONNECT_BASE)}",
            f"Continuation vertices: {len(CONNECT_CONTINUATION)}",
            "",
            "3. ArcSplitOnCross",
            f"Split arc vertices: {len(SPLIT_ARC)}",
            f"Cutter vertices: {len(SPLIT_CUTTER)}",
        ]
        if not show_results:
            details.extend(("", "Result: click Run Arc Operations to calculate"))
            self.statusBar().showMessage(
                "Source arcs are ready. Click Run Arc Operations."
            )
        else:
            self.add_results(details)
            self.statusBar().showMessage("Arc operations calculated.")
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        if current_extent is not None:
            self.viewer.set_view_extent(current_extent)
        self.details_view.setPlainText("\n".join(details))

    def add_results(self, details: list[str]) -> None:
        found_index = self.viewer.find_matching_arc_index(FIND_QUERY, FIND_CANDIDATES)
        found = found_index >= 0
        details.extend(
            (
                "",
                f"ArcFind result: {'found' if found else 'not found'}, index: {found_index}",
            )
        )
        if found:
            self.add_line(FIND_CANDIDATES[found_index], RESULT_COLORS[0], 4.0)

        connected = self.to_parts(
            self.viewer.arc_make_connected(CONNECT_BASE, [CONNECT_CONTINUATION])
        )
        details.append(
            f"ArcMakeConnected result parts: {len(connected)}, vertices: "
            f"{sum(len(part) for part in connected)}"
        )
        for part in connected:
            self.add_line(part, RESULT_COLORS[1], 4.0)

        split = self.to_parts(self.viewer.arc_split_on_cross(SPLIT_ARC, [SPLIT_CUTTER]))
        details.append(f"ArcSplitOnCross result parts: {len(split)}")
        for index, part in enumerate(split):
            self.add_line(part, RESULT_COLORS[(index + 2) % len(RESULT_COLORS)], 4.0)

    def add_source_shapes(self) -> None:
        for candidate in FIND_CANDIDATES:
            self.add_line(candidate, "#6C757D", 2.0)
        self.add_line(FIND_QUERY, "#2F80C2", 3.0)
        self.add_line(CONNECT_BASE, "#6C757D", 2.0)
        self.add_line(CONNECT_CONTINUATION, "#6C757D", 2.0)
        self.add_line(SPLIT_ARC, "#2F80C2", 3.0)
        self.add_line(SPLIT_CUTTER, "#212529", 2.6)

    def add_line(
        self, points: list[tuple[float, float]], color: str, width: float
    ) -> None:
        if not self.viewer.add_polyline_shape(
            points, {"lineColor": color, "lineWidth": width}
        ):
            raise RuntimeError("Polyline shape could not be rendered.")

    def to_parts(
        self, result: list[list[dict[str, float]]]
    ) -> list[list[tuple[float, float]]]:
        return [
            [(float(point["x"]), float(point["y"])) for point in part]
            for part in result
            if part
        ]

    def extent_text(self, points: list[tuple[float, float]]) -> str:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return f"({min(xs):.2f}, {min(ys):.2f}) - ({max(xs):.2f}, {max(ys):.2f})"

    def show_full_extent(self) -> None:
        if self.initialized:
            self.viewer.set_view_extent(FULL_EXTENT)

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ArcOperations")
    app.setWindowIcon(application_icon())
    window = ArcOperationsWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
