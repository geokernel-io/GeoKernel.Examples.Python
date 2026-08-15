import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

POLYGON_A = [(-5, -2), (1, -2), (1, 3), (-5, 3), (-5, -2)]
POLYGON_B = [(-1, -1), (5, -1), (5, 4), (-1, 4), (-1, -1)]
LINE = [(-6, -3), (6, 4)]
INVALID_POLYGON = [(3.0, -6.4), (6.2, -3.2), (3.0, -3.2), (6.2, -6.4), (3.0, -6.4)]
ARC_A = [(-6.0, -5.5), (-4.4, -4.4), (-2.7, -5.4)]
ARC_B = [(-2.7, -5.4), (-0.7, -4.2), (1.5, -5.3)]
SPLIT_ARC = [(-5.7, -6.7), (2.2, -4.1)]
SPLIT_CUTTER = [(-2.0, -7.1), (-2.0, -3.7)]
FULL_EXTENT = Extent(-7.3, -7.4, 7.0, 5.0)
OPERATIONS = [
    "Buffer A",
    "Union A + B",
    "Intersection A / B",
    "Difference A - B",
    "Sym Difference A / B",
    "Convex Hull A + B",
    "Crossings Line / B",
    "Fix Invalid Polygon",
    "Arc Make Connected",
    "Arc Split On Cross",
    "Predicate Report",
]

class TopologyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.widget = self.viewer.qt_widget()
        self.initialized = False
        self.setWindowTitle("Topology")
        self.setWindowIcon(application_icon())
        self.resize(1100, 760)
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
        row.addWidget(self.combo)
        run = QPushButton("Run Operation", bar)
        run.clicked.connect(self.run)
        row.addWidget(run)
        full = QPushButton("Full Extent", bar)
        full.clicked.connect(lambda: self.viewer.set_view_extent(FULL_EXTENT))
        row.addWidget(full)
        row.addStretch()
        content = QWidget(root)
        split = QHBoxLayout(content)
        split.setContentsMargins(0, 0, 0, 0)
        split.addWidget(self.widget, 1)
        self.details = QTextEdit(content)
        self.details.setReadOnly(True)
        self.details.setMinimumWidth(320)
        split.addWidget(self.details)
        layout.addWidget(bar)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def initialize_viewer(self):
        self.initialized = True
        self.viewer.resize(self.widget.width(), self.widget.height())
        self.viewer.show()
        self.reset_sources()
        self.viewer.set_view_extent(FULL_EXTENT)

    def reset_sources(self):
        self.viewer.clear_shapes()
        self.viewer.add_polygon_shape(
            POLYGON_A,
            {
                "fillColor": "#60A5FA",
                "fillOpacity": 80,
                "lineColor": "#2563EB",
                "lineWidth": 2,
            },
        )
        self.viewer.add_polygon_shape(
            POLYGON_B,
            {
                "fillColor": "#86EFAC",
                "fillOpacity": 80,
                "lineColor": "#15803D",
                "lineWidth": 2,
            },
        )
        self.viewer.add_polyline_shape(LINE, {"lineColor": "#64748B", "lineWidth": 2})

    def polygon_parts(self, result):
        return [
            [(float(p["x"]), float(p["y"])) for p in part] for part in result if part
        ]

    def run(self):
        extent = self.viewer.get_view_extent()
        self.reset_sources()
        choice = self.combo.currentText()
        parts = []
        lines = [choice]
        if choice == "Buffer A":
            self.viewer.add_polygon_buffer_shape(
                POLYGON_A,
                0.75,
                8,
                {
                    "fillColor": "#F9C74F",
                    "fillOpacity": 135,
                    "lineColor": "#D95D39",
                    "lineWidth": 3,
                },
            )
            lines.append("MakeBuffer(Polygon A, 0.75)")
        elif choice == "Union A + B":
            parts = self.polygon_parts(self.viewer.union_polygons(POLYGON_A, POLYGON_B))
        elif choice == "Intersection A / B":
            parts = self.polygon_parts(
                self.viewer.intersection_polygons(POLYGON_A, POLYGON_B)
            )
        elif choice == "Difference A - B":
            parts = self.polygon_parts(
                self.viewer.difference_polygons(POLYGON_A, POLYGON_B)
            )
        elif choice == "Sym Difference A / B":
            parts = self.polygon_parts(
                self.viewer.symmetrical_difference_polygons(POLYGON_A, POLYGON_B)
            )
        elif choice == "Convex Hull A + B":
            parts = self.polygon_parts(
                self.viewer.convex_hull_two_polygons(POLYGON_A, POLYGON_B)
            )
        elif choice == "Crossings Line / B":
            crossings = self.viewer.polyline_crossings(LINE, POLYGON_B)
            lines.append(f"Crossings: {len(crossings)}")
            for p in crossings:
                self.viewer.add_point_shape(
                    float(p["x"]),
                    float(p["y"]),
                    {"pointColor": "#F59E0B", "pointSize": 11},
                )
        elif choice == "Fix Invalid Polygon":
            parts = self.polygon_parts(self.viewer.fix_polygon(INVALID_POLYGON))
            lines.extend(
                (
                    "FixShape(bow-tie polygon)",
                    f"Check before: {self.viewer.check_polygon_ring(INVALID_POLYGON)}",
                    f"Check after: {all(self.viewer.check_polygon_ring(part) for part in parts)}",
                )
            )
        elif choice == "Arc Make Connected":
            connected = self.polygon_parts(
                self.viewer.arc_make_connected(ARC_A, [ARC_B])
            )
            for part in connected:
                self.viewer.add_polyline_shape(
                    part, {"lineColor": "#2A9D8F", "lineWidth": 4}
                )
            lines.extend(
                ("ArcMakeConnected(Arc A, [Arc B])", f"Result parts: {len(connected)}")
            )
        elif choice == "Arc Split On Cross":
            split = self.polygon_parts(
                self.viewer.arc_split_on_cross(SPLIT_ARC, [SPLIT_CUTTER])
            )
            for index, part in enumerate(split):
                self.viewer.add_polyline_shape(
                    part,
                    {"lineColor": ["#D95D39", "#7B2CBF"][index % 2], "lineWidth": 4},
                )
            lines.extend(
                (
                    "ArcSplitOnCross(split arc, [vertical cutter])",
                    f"Result parts: {len(split)}",
                )
            )
        else:
            matrix = self.viewer.relate_polygon_rings(POLYGON_A, POLYGON_B)
            lines.extend(
                (
                    "Predicate report for Polygon A and Polygon B",
                    f"Relate matrix: {matrix}",
                    f"Intersect: {self.viewer.relate_polygon_rings_pattern(POLYGON_A, POLYGON_B, 'T********')}",
                    f"Disjoint: {self.viewer.relate_polygon_rings_pattern(POLYGON_A, POLYGON_B, 'FF*FF****')}",
                    f"CheckShape(A): {self.viewer.check_polygon_ring(POLYGON_A)}",
                )
            )
        if parts:
            self.viewer.add_polygon_parts_shape(
                parts,
                {
                    "fillColor": "#F9C74F",
                    "fillOpacity": 135,
                    "lineColor": "#D95D39",
                    "lineWidth": 3,
                },
            )
            lines.extend(
                (
                    "Result type: polygon",
                    f"Parts: {len(parts)}",
                    f"Vertices: {sum(map(len, parts))}",
                )
            )
        self.details.setPlainText("\n".join(lines))
        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.viewer.set_view_extent(extent)
        self.statusBar().showMessage(f"Topology operation: {choice}")

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = TopologyWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
