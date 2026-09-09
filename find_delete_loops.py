import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

PARTS = [
    [(-5.0, -1.7), (-1.7, -1.7), (-1.7, 1.6), (-5.0, 1.6), (-5.0, -1.7)],
    [(0.4, -1.7), (4.5, 1.6), (0.4, 1.6), (4.5, -1.7), (0.4, -1.7)],
]
FULL_EXTENT = Extent(-5.7, -2.8, 5.2, 2.6)

class FindDeleteLoopsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("FindDeleteLoops")
        self.setWindowIcon(application_icon())
        self.resize(980, 680)
        self.create_ui()

    def create_ui(self):
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QWidget(root)
        row = QHBoxLayout(bar)
        full = QPushButton("Full Extent", bar)
        full.clicked.connect(lambda: self.viewer.set_view_extent(FULL_EXTENT))
        row.addWidget(full)
        row.addWidget(QLabel("Operation: FindAndDeleteLoops", bar))
        run = QPushButton("Run FindAndDeleteLoops", bar)
        run.clicked.connect(self.run)
        row.addWidget(run)
        row.addStretch()
        content = QWidget(root)
        split = QHBoxLayout(content)
        split.setContentsMargins(0, 0, 0, 0)
        split.addWidget(self.widget, 1)
        self.details = QTextEdit(content)
        self.details.setReadOnly(True)
        self.details.setMinimumWidth(290)
        split.addWidget(self.details)
        layout.addWidget(bar)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def initialize_viewer(self):
        self.initialized = True
        self.viewer.resize(self.widget.width(), self.widget.height())
        self.viewer.show()
        self.render(False)
        self.viewer.set_view_extent(FULL_EXTENT)

    def run(self):
        self.render(True)

    def render(self, show):
        extent = self.viewer.get_view_extent() if show else None
        self.viewer.clear_shapes()
        self.viewer.add_polygon_parts_shape_with_attributes(
            PARTS,
            {"LABEL": "source: one valid part, one self-intersecting loop"},
            {
                "fillColor": "#F6D6AD",
                "fillOpacity": 115,
                "lineColor": "#D95D39",
                "lineWidth": 2.4,
                "showLabels": True,
                "labelField": "LABEL",
                "labelFontSize": 11.5,
                "labelColor": "#111111",
                "labelHaloEnabled": True,
                "labelHaloColor": "#FFFFFF",
                "labelHaloWidth": 2.0,
            },
        )
        text = [
            "FindAndDeleteLoops - remove self-intersecting polygon parts",
            "",
            "Source geometry:",
            "- left part is a normal valid rectangle",
            "- right part is a bow-tie loop that crosses itself",
            "",
            f"Source parts: {len(PARTS)}",
            f"Source vertices: {sum(map(len, PARTS))}",
            "Source extent: (-5.00, -1.70) - (4.50, 1.60)",
            "Source part details:",
            "part 1: 5 vertices",
            "part 2: 5 vertices",
        ]
        if show:
            result = [
                [(float(p["x"]), float(p["y"])) for p in part]
                for part in self.viewer.find_and_delete_loops(PARTS)
                if part
            ]
            self.viewer.add_polygon_parts_shape_with_attributes(
                result,
                {"LABEL": "result: loop removed"},
                {
                    "fillColor": "#CDE7D8",
                    "fillOpacity": 170,
                    "lineColor": "#2A9D8F",
                    "lineWidth": 4.0,
                    "showLabels": True,
                    "labelField": "LABEL",
                    "labelFontSize": 11.5,
                    "labelColor": "#111111",
                    "labelHaloEnabled": True,
                    "labelHaloColor": "#FFFFFF",
                    "labelHaloWidth": 2.0,
                },
            )
            text.extend(
                (
                    "",
                    "Result:",
                    f"Result parts: {len(result)}",
                    f"Result vertices: {sum(map(len, result))}",
                    "Result extent: (-5.00, -1.70) - (-1.70, 1.60)",
                    "Result part details:",
                    "part 1: 5 vertices",
                    "",
                    "The self-intersecting bow-tie part is removed; the valid part remains.",
                )
            )
            self.statusBar().showMessage("FindAndDeleteLoops result created.")
        else:
            text.extend(
                (
                    "",
                    "Click Run FindAndDeleteLoops to remove the self-intersecting part.",
                )
            )
            self.statusBar().showMessage(
                "Source polygon is ready. Click Run FindAndDeleteLoops."
            )
        self.details.setPlainText("\n".join(text))
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        if extent is not None:
            self.viewer.set_view_extent(extent)

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FindDeleteLoops")
    app.setWindowIcon(application_icon())
    window = FindDeleteLoopsWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
