import sys
import time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

def rectangle(x, y):
    return [(x, y), (x + 2.15, y), (x + 2.15, y + 1.35), (x, y + 1.35), (x, y)]

POLYGONS = [
    rectangle(-5.4 + col * 2.35 + (row % 2) * 0.45, -2.2 + row * 1.55)
    for row in range(3)
    for col in range(4)
]
POLYGONS += [
    [(-2.8, 2.2), (-1.35, 1.2), (-2.8, 0.2), (-4.25, 1.2), (-2.8, 2.2)],
    [(2.2, 0.0), (3.55, -0.9), (2.2, -1.8), (0.85, -0.9), (2.2, 0.0)],
]
FULL_EXTENT = Extent(-6.5, -3.0, 5.8, 3.6)

class TopologyBatchWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("TopologyBatch")
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
        row.addWidget(QLabel("Batch: CheckShape + UnionOnList", bar))
        run = QPushButton("Run Batch", bar)
        run.clicked.connect(self.run)
        row.addWidget(run)
        row.addStretch()
        content = QWidget(root)
        split = QHBoxLayout(content)
        split.setContentsMargins(0, 0, 0, 0)
        split.addWidget(self.widget, 1)
        self.details = QTextEdit(content)
        self.details.setReadOnly(True)
        self.details.setMinimumWidth(310)
        split.addWidget(self.details)
        layout.addWidget(bar)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def initialize_viewer(self):
        self.initialized = True
        self.viewer.resize(self.widget.width(), self.widget.height())
        self.viewer.show()
        self.render_sources()
        self.details.setPlainText(
            f"TopologyBatch\nBatch flow: CheckShape each polygon, then UnionOnList(valid polygons).\n\nSource polygon count: {len(POLYGONS)}\n\nClick Run Batch to validate all polygons and build the union."
        )
        self.viewer.set_view_extent(FULL_EXTENT)

    def render_sources(self):
        self.viewer.clear_shapes()
        for index, polygon in enumerate(POLYGONS):
            self.viewer.add_polygon_shape(
                polygon,
                {
                    "fillColor": ["#BFD7EA", "#D8EAC4", "#F3D6A3", "#D9C8F0"][
                        index % 4
                    ],
                    "fillOpacity": 90,
                    "lineColor": "#2F80C2",
                    "lineWidth": 1.5,
                },
            )

    def run(self):
        view_extent = self.viewer.get_view_extent()
        started = time.perf_counter()
        validity = [self.viewer.check_polygon_ring(p) for p in POLYGONS]
        valid = [p for p, ok in zip(POLYGONS, validity) if ok]
        result = [
            [(float(v["x"]), float(v["y"])) for v in part]
            for part in self.viewer.union_polygons_on_list(valid)
            if part
        ]
        elapsed = (time.perf_counter() - started) * 1000
        self.render_sources()
        if result:
            self.viewer.add_polygon_parts_shape(
                result,
                {
                    "fillColor": "#F9C74F",
                    "fillOpacity": 135,
                    "lineColor": "#D95D39",
                    "lineWidth": 4,
                },
            )
        lines = [
            "TopologyBatch",
            "Batch flow: CheckShape each polygon, then UnionOnList(valid polygons).",
            "",
            f"Source polygon count: {len(POLYGONS)}",
            "",
            "Validation:",
        ]
        lines.extend(
            f"P{i + 1}: {'valid' if ok else 'invalid'}, vertices={len(POLYGONS[i])}"
            for i, ok in enumerate(validity)
        )
        lines.extend(
            (
                "",
                f"Valid polygons used for union: {len(valid)}",
                f"Invalid polygons skipped: {len(POLYGONS) - len(valid)}",
                f"Source vertex total: {sum(map(len, POLYGONS))}",
                "",
                "Union result:",
                f"Type: {'polygon' if result else 'empty'}",
                f"Parts: {len(result)}",
                f"Vertices: {sum(map(len, result))}",
                f"Elapsed: {elapsed:.2f} ms",
            )
        )
        self.details.setPlainText("\n".join(lines))
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.set_view_extent(view_extent)
        QTimer.singleShot(0, lambda extent=view_extent: self.viewer.set_view_extent(extent))
        self.statusBar().showMessage(
            f"Batch topology completed: {len(valid)} valid polygon(s), {elapsed:.2f} ms."
        )

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = TopologyBatchWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
