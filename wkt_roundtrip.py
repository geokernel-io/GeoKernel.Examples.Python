import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget
from geokernel import Extent, Viewer, ViewerTool
from common import application_icon

INPUT_WKT = (
    "POLYGON((-123.25 37.15, -122.15 36.95, -121.55 37.65, "
    "-122.05 38.35, -123.05 38.15, -123.25 37.15))"
)
VIEW_EXTENT = Extent(-124.0, 36.4, -120.3, 38.7)

class WktRoundtripWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False

        self.setWindowTitle("WktRoundtrip")
        self.setWindowIcon(application_icon())
        self.resize(1100, 720)
        self.create_ui()

    def create_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(root)
        self.details_view.setReadOnly(True)
        self.details_view.setMaximumHeight(170)
        layout.addWidget(self.details_view)

        self.setCentralWidget(root)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return

        self.initialized = True
        self.viewer.resize(
            self.viewer_widget.width(),
            self.viewer_widget.height(),
        )
        self.viewer.show()

        try:
            self.run_roundtrip()
            self.viewer.set_view_extent(VIEW_EXTENT)
            self.statusBar().showMessage("WktRoundtrip ready.")
        except Exception as error:
            self.details_view.setPlainText(f"WKT round-trip failed:\n{error}")
            self.statusBar().showMessage("WktRoundtrip failed.")

    def run_roundtrip(self) -> None:
        data = self.viewer.read_wkt_polygon(INPUT_WKT)
        rings = [
            [(float(point["x"]), float(point["y"])) for point in ring] for ring in data
        ]
        if not rings:
            raise RuntimeError("GisWktReader::readPolygon returned no polygon.")

        output_wkt = self.viewer.write_wkt_polygon(rings)
        if not output_wkt:
            raise RuntimeError("GisWktWriter::writePolygon returned no WKT.")

        layer_index = self.viewer.add_polygon_layer(
            "Roundtrip Polygon",
            rings,
            {
                "fillColor": "#88D18A",
                "fillOpacity": 128,
                "lineColor": "#1F7A4D",
                "lineWidth": 2.2,
            },
        )
        if layer_index < 0:
            raise RuntimeError("Roundtrip Polygon layer could not be created.")

        self.details_view.setPlainText(
            "\n".join(
                (
                    "WktRoundtrip sample",
                    "",
                    "API",
                    "GisWktReader::readPolygon(wkt)",
                    "GisWktWriter::writePolygon(shape)",
                    "",
                    "Input WKT",
                    INPUT_WKT,
                    "",
                    "Output WKT",
                    output_wkt,
                )
            )
        )

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WktRoundtrip")
    app.setWindowIcon(application_icon())

    window = WktRoundtripWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
