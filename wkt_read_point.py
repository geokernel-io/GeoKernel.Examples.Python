import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Extent, Viewer, ViewerTool
from common import application_icon

DEFAULT_WKT = "POINT(-122.4194 37.7749)"

class WktReadPointWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.transformer = CoordinateSystemFactory()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.point_layer_index = -1
        self.initialized = False

        self.setWindowTitle("WktReadPoint")
        self.setWindowIcon(application_icon())
        self.resize(1000, 700)
        self.create_ui()

    def create_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        input_bar = QWidget(root)
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(6, 4, 6, 4)
        input_layout.setSpacing(8)

        input_layout.addWidget(QLabel("WKT:", input_bar))

        self.wkt_edit = QLineEdit(DEFAULT_WKT, input_bar)
        self.wkt_edit.returnPressed.connect(self.read_point)
        input_layout.addWidget(self.wkt_edit, 1)

        read_button = QPushButton("Read Point", input_bar)
        read_button.clicked.connect(self.read_point)
        input_layout.addWidget(read_button)

        reset_button = QPushButton("Reset", input_bar)
        reset_button.clicked.connect(self.reset_sample)
        input_layout.addWidget(reset_button)

        content = QWidget(root)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.viewer_widget, 1)

        self.details_view = QTextEdit(content)
        self.details_view.setReadOnly(True)
        self.details_view.setMinimumWidth(340)
        content_layout.addWidget(self.details_view)

        root_layout.addWidget(input_bar)
        root_layout.addWidget(content, 1)
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
            osm_index = self.viewer.add_open_street_map_layer()
            if osm_index < 0:
                raise RuntimeError("OpenStreetMap layer could not be added.")
            self.read_point()
        except Exception as error:
            self.details_view.setPlainText(f"Initialization failed:\n{error}")
            self.statusBar().showMessage("WktReadPoint initialization failed.")

    def read_point(self) -> None:
        input_wkt = self.wkt_edit.text().strip()

        try:
            point = self.viewer.read_wkt_point(input_wkt)
            if point is None:
                raise ValueError("GisWktReader::readPoint returned no point.")

            longitude, latitude = point
            projected_x, projected_y = self.transformer.transform_point(
                4326,
                3857,
                longitude,
                latitude,
            )

            self.replace_point_layer(longitude, latitude)
            self.details_view.setPlainText(
                self.details_text(
                    input_wkt,
                    longitude,
                    latitude,
                    projected_x,
                    projected_y,
                )
            )
            self.viewer.set_view_extent(
                Extent(
                    projected_x - 2_500_000.0,
                    projected_y - 1_800_000.0,
                    projected_x + 2_500_000.0,
                    projected_y + 1_800_000.0,
                )
            )
            self.statusBar().showMessage(
                "GisWktReader::readPoint parsed lon/lat "
                f"POINT({longitude:.6f} {latitude:.6f}) over OSM."
            )
        except Exception as error:
            self.remove_point_layer()
            self.details_view.setPlainText(f"WKT parse failed:\n{error}")
            self.statusBar().showMessage("WKT parse failed.")

    def replace_point_layer(self, longitude: float, latitude: float) -> None:
        self.remove_point_layer()
        self.point_layer_index = self.viewer.add_point_layer(
            "WKT Point",
            [(longitude, latitude)],
            {
                "pointColor": "#D95D39",
                "lineColor": "#8C321D",
                "pointSize": 14.0,
                "lineWidth": 1.5,
            },
        )
        if self.point_layer_index < 0:
            raise RuntimeError("WKT point layer could not be created.")
        if not self.viewer.set_layer_coordinate_system_preset(
            self.point_layer_index,
            CoordinateSystemPreset.WGS84,
        ):
            raise RuntimeError("WKT point layer CRS could not be set to EPSG:4326.")

    def remove_point_layer(self) -> None:
        if self.point_layer_index < 0:
            return
        self.viewer.remove_layer(self.point_layer_index)
        self.point_layer_index = -1

    def details_text(
        self,
        input_wkt: str,
        longitude: float,
        latitude: float,
        projected_x: float,
        projected_y: float,
    ) -> str:
        round_trip_wkt = self.viewer.write_wkt_point(longitude, latitude)
        return "\n".join(
            (
                "WktReadPoint sample",
                "",
                "API",
                "GisWktReader::readPoint(wkt)",
                "",
                "Input WKT",
                input_wkt,
                "",
                "Parsed lon/lat point",
                f"X: {longitude:.6f}",
                f"Y: {latitude:.6f}",
                "",
                "Displayed over OSM",
                "Layer CRS: EPSG:4326",
                "Viewer/OSM CRS: EPSG:3857",
                f"WebMercator X: {projected_x:.3f}",
                f"WebMercator Y: {projected_y:.3f}",
                "",
                "Round-trip WKT",
                round_trip_wkt,
            )
        )

    def reset_sample(self) -> None:
        self.wkt_edit.setText(DEFAULT_WKT)
        self.read_point()

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WktReadPoint")
    app.setWindowIcon(application_icon())

    window = WktReadPointWindow()
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
