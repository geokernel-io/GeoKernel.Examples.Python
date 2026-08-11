import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, ShapeType, Viewer, ViewerTool
from common import application_icon

FULL_EXTENT = Extent(-5.8, -3.0, 5.4, 3.6)

class ExtentOperationsWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("ExtentOperations")
        self.setWindowIcon(application_icon())
        self.resize(1040, 680)
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
            QLabel(
                "Operations: expand / inflate / intersects / contains",
                toolbar,
            )
        )
        toolbar_layout.addStretch(1)

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(content)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(350)
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
            self.render_scene()
            self.show_full_extent()
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("ExtentOperations initialization failed.")

    def render_scene(self) -> None:
        base = Extent(-4.4, -1.8, 0.8, 1.8)
        other = Extent(-0.8, -0.6, 4.2, 2.6)
        expanded = base.expand(other)
        inflated = base.inflate(0.9, 0.7)
        inside = (-2.0, 0.4)
        outside = (2.8, -1.2)

        polygon_specs = (
            (
                "Expanded",
                expanded,
                "A.expand(B)",
                self.extent_style("#CDE7D8", "#2A9D8F", 55, 3.0),
            ),
            (
                "Inflated",
                inflated,
                "A.inflate(0.9, 0.7)",
                self.extent_style("#E6D5F7", "#7B2CBF", 35, 3.0),
            ),
            ("Base A", base, "A", self.extent_style("#BFD7EA", "#2F80C2", 90, 2.2)),
            ("Other B", other, "B", self.extent_style("#F6D6AD", "#D95D39", 90, 2.2)),
        )
        for name, extent, label, style in polygon_specs:
            index = self.viewer.add_empty_vector_layer(name, ShapeType.POLYGON, style)
            if index < 0 or not self.viewer.begin_edit_layer(index):
                raise RuntimeError(f"{name} layer could not be created.")
            if not self.viewer.add_polygon_to_edit_layer(
                index,
                self.extent_ring(extent),
                {"LABEL": label},
            ):
                raise RuntimeError(f"{name} extent could not be added.")
            self.viewer.commit_edit_layer(index)

        point_specs = (
            (
                "Inside Point",
                inside,
                "contains: true",
                self.point_style("#2A9D8F", "#145A4B"),
            ),
            (
                "Outside Point",
                outside,
                "contains: false",
                self.point_style("#C1121F", "#7A0010"),
            ),
        )
        for name, point, label, style in point_specs:
            index = self.viewer.add_empty_vector_layer(name, ShapeType.POINT, style)
            if index < 0 or not self.viewer.begin_edit_layer(index):
                raise RuntimeError(f"{name} layer could not be created.")
            if not self.viewer.add_point_to_edit_layer(
                index,
                point[0],
                point[1],
                {"LABEL": label},
            ):
                raise RuntimeError(f"{name} could not be added.")
            self.viewer.commit_edit_layer(index)

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.details_view.setPlainText(
            "\n".join(
                (
                    "GisExtent operations",
                    "",
                    f"A: {self.extent_text(base)}",
                    f"B: {self.extent_text(other)}",
                    "",
                    f"A.expand(B): {self.extent_text(expanded)}",
                    f"A.inflate(0.9, 0.7): {self.extent_text(inflated)}",
                    "",
                    f"A.intersects(B): {str(base.intersects(other)).lower()}",
                    f"A.contains(inside point): {str(base.contains(*inside)).lower()}",
                    f"A.contains(outside point): {str(base.contains(*outside)).lower()}",
                    "",
                    "Visual guide:",
                    "Blue: base extent A",
                    "Orange: extent B",
                    "Green: A expanded to include B",
                    "Purple: A inflated by dx/dy",
                )
            )
        )
        self.statusBar().showMessage("Extent operations rendered.")

    def show_full_extent(self) -> None:
        if self.initialized:
            self.viewer.set_view_extent(FULL_EXTENT)

    def extent_ring(self, extent: Extent) -> list[tuple[float, float]]:
        return [
            (extent.x_min, extent.y_min),
            (extent.x_max, extent.y_min),
            (extent.x_max, extent.y_max),
            (extent.x_min, extent.y_max),
            (extent.x_min, extent.y_min),
        ]

    def extent_style(
        self,
        fill_color: str,
        line_color: str,
        fill_opacity: int,
        line_width: float,
    ) -> dict:
        return {
            "fillColor": fill_color,
            "fillOpacity": fill_opacity,
            "lineColor": line_color,
            "lineWidth": line_width,
            "showLabels": True,
            "labelField": "LABEL",
            "labelFontSize": 11.0,
            "labelColor": "#202124",
            "labelHaloEnabled": True,
            "labelHaloColor": "#FFFFFF",
            "labelHaloWidth": 2.0,
        }

    def point_style(self, point_color: str, line_color: str) -> dict:
        return {
            "pointColor": point_color,
            "pointSize": 11.0,
            "lineColor": line_color,
            "lineWidth": 1.0,
            "showLabels": True,
            "labelField": "LABEL",
            "labelFontSize": 10.0,
            "labelColor": line_color,
            "labelHaloEnabled": True,
            "labelHaloColor": "#FFFFFF",
            "labelHaloWidth": 2.0,
        }

    def extent_text(self, extent: Extent) -> str:
        if extent.is_empty:
            return "(empty)"
        return (
            f"({extent.x_min:.2f}, {extent.y_min:.2f}) - "
            f"({extent.x_max:.2f}, {extent.y_max:.2f}), "
            f"w={extent.width:.2f}, h={extent.height:.2f}"
        )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ExtentOperations")
    app.setWindowIcon(application_icon())
    window = ExtentOperationsWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
