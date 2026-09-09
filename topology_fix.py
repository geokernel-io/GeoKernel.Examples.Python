import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, TopologyFixOperation, Viewer, ViewerTool
from common import application_icon

SOURCE_PARTS = [
    [
        (-5.2, -1.3),
        (-4.0, -0.2),
        (-4.0, -0.2),
        (-2.6, -1.1),
        (-1.2, 0.5),
        (-1.2, 0.5),
        (0.4, 0.1),
    ],
    [(1.5, 1.0)],
    [(2.8, -0.8), (2.8, -0.8)],
    [(3.7, -1.1), (4.8, 0.3), (5.4, -0.9)],
]
FULL_EXTENT = Extent(-5.9, -2.4, 5.9, 1.8)
OPERATIONS = {
    "FixShape": TopologyFixOperation.FIX_SHAPE,
    "FixShapeEx (preserve empty parts)": TopologyFixOperation.FIX_SHAPE_EX,
    "ClearShape": TopologyFixOperation.CLEAR_SHAPE,
}

class TopologyFixWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("TopologyFix")
        self.setWindowIcon(application_icon())
        self.resize(980, 680)
        self.create_ui()

    def create_ui(self):
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QWidget(root)
        row = QHBoxLayout(bar)
        row.addWidget(QLabel("Operation:", bar))
        self.combo = QComboBox(bar)
        self.combo.addItems(OPERATIONS)
        self.combo.currentIndexChanged.connect(self.render_result)
        row.addWidget(self.combo)
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
        self.render_result()
        self.viewer.set_view_extent(FULL_EXTENT)

    def render_result(self):
        if not self.initialized:
            return
        extent = self.viewer.get_view_extent()
        self.viewer.clear_shapes()
        self.add_parts(SOURCE_PARTS, "#6C757D", 2.0)
        operation = OPERATIONS[self.combo.currentText()]
        result = self.to_parts(self.viewer.fix_polyline(SOURCE_PARTS, operation))
        self.add_parts(result, "#D95D39", 4.0)
        self.details.setPlainText(
            "Topology fix functions\n\nSource: messy multipart polyline\n- part 1 has duplicate consecutive vertices\n- part 2 has only one vertex\n- part 3 collapses after duplicate cleanup\n- part 4 is already valid\n\n"
            + f"Source parts: {len(SOURCE_PARTS)}\nSource vertices: {sum(map(len, SOURCE_PARTS))}\n\nOperation: {self.combo.currentText()}\nResult parts: {len(result)}\nResult vertices: {sum(map(len, result))}"
        )
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.viewer.set_view_extent(extent)
        self.statusBar().showMessage(f"{self.combo.currentText()} applied.")

    def add_parts(self, parts, color, width):
        for part in parts:
            if len(part) >= 2:
                self.viewer.add_polyline_shape(
                    part, {"lineColor": color, "lineWidth": width}
                )

    def to_parts(self, result):
        return [
            [(float(p["x"]), float(p["y"])) for p in part] for part in result if part
        ]

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TopologyFix")
    app.setWindowIcon(application_icon())
    window = TopologyFixWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
