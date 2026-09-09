import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

VALID_POLYGON = [
    (-5.0, -1.6),
    (-2.0, -1.6),
    (-2.0, 1.4),
    (-5.0, 1.4),
    (-5.0, -1.6),
]
SELF_INTERSECTING_POLYGON = [
    (0.0, -1.6),
    (3.3, 1.4),
    (0.0, 1.4),
    (3.3, -1.6),
    (0.0, -1.6),
]
FULL_EXTENT = Extent(-5.8, -2.7, 5.9, 2.4)

class TopologyCheckWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("TopologyCheck")
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
        toolbar_layout.addWidget(QLabel("Operation: CheckShape", toolbar))
        run_button = QPushButton("Run CheckShape", toolbar)
        run_button.clicked.connect(self.run_check)
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
            self.statusBar().showMessage("TopologyCheck initialization failed.")

    def run_check(self) -> None:
        if self.initialized:
            self.render_scene(True)

    def render_scene(self, checked: bool) -> None:
        current_extent = self.viewer.get_view_extent() if checked else None
        self.viewer.clear_shapes()
        self.add_polygon(
            VALID_POLYGON,
            "A - valid polygon",
            "#BFD7EA",
            "#2F80C2",
            False,
        )
        self.add_polygon(
            SELF_INTERSECTING_POLYGON,
            "B - self-intersecting polygon",
            "#F6D6AD",
            "#D95D39",
            False,
        )
        details = [
            "CheckShape - geometry validation",
            "",
            "This sample compares two polygon rings:",
            "",
            "A - valid polygon",
            "Closed ring, non-zero area, no self-intersection.",
            f"Extent: {self.extent_text(VALID_POLYGON)}",
            "",
            "B - self-intersecting polygon",
            "Bow-tie ring crosses itself, so CheckShape must reject it.",
            f"Extent: {self.extent_text(SELF_INTERSECTING_POLYGON)}",
        ]
        if not checked:
            details.extend(("", "Click Run CheckShape to validate both polygons."))
            self.statusBar().showMessage(
                "Two polygons are ready. Click Run CheckShape."
            )
        else:
            valid_ok = self.viewer.check_polygon_ring(VALID_POLYGON)
            bow_tie_ok = self.viewer.check_polygon_ring(SELF_INTERSECTING_POLYGON)
            details.extend(
                (
                    "",
                    "Result:",
                    f"A - valid polygon: CheckShape = {self.bool_text(valid_ok)}",
                    "B - self-intersecting polygon: CheckShape = "
                    f"{self.bool_text(bow_tie_ok)}",
                    "",
                    "Invalid means the geometry should be fixed or rejected before "
                    "topology operations.",
                )
            )
            self.add_polygon(
                VALID_POLYGON,
                "A - CheckShape: valid",
                "#CDE7D8",
                "#2A9D8F",
                True,
            )
            self.add_polygon(
                SELF_INTERSECTING_POLYGON,
                "B - CheckShape: invalid",
                "#F4A261",
                "#D62828",
                True,
            )
            self.statusBar().showMessage("Topology check completed.")
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        if current_extent is not None:
            self.viewer.set_view_extent(current_extent)
        self.details_view.setPlainText("\n".join(details))

    def add_polygon(
        self,
        ring: list[tuple[float, float]],
        label: str,
        fill: str,
        line: str,
        checked: bool,
    ) -> None:
        added = self.viewer.add_polygon_shape_with_attributes(
            ring,
            {"LABEL": label},
            {
                "fillColor": fill,
                "fillOpacity": 165 if checked else 125,
                "lineColor": line,
                "lineWidth": 4.0 if checked else 2.4,
                "showLabels": True,
                "labelField": "LABEL",
                "labelFontSize": 12.0,
                "labelColor": "#111111",
                "labelHaloEnabled": True,
                "labelHaloColor": "#FFFFFF",
                "labelHaloWidth": 2.5,
            },
        )
        if not added:
            raise RuntimeError("Polygon shape could not be rendered.")

    def extent_text(self, points: list[tuple[float, float]]) -> str:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return f"({min(xs):.2f}, {min(ys):.2f}) - ({max(xs):.2f}, {max(ys):.2f})"

    def bool_text(self, value: bool) -> str:
        return "valid" if value else "invalid"

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
    app.setApplicationName("TopologyCheck")
    app.setWindowIcon(application_icon())
    window = TopologyCheckWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
