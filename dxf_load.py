import sys
from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget
from geokernel import Viewer, ViewerTool
from common import ensure_sample_file

class DxfLoadWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.details = QTextEdit(self)
        self.details.setReadOnly(True)
        self.schema_table = QTableWidget(self)
        self.attributes_table = QTableWidget(self)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.setWindowTitle("DxfLoad")
        self.resize(1200, 760)
        self.create_layout()

    def create_layout(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        panel = QWidget(splitter)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Layer metadata", panel))
        layout.addWidget(self.details)
        layout.addWidget(QLabel("Attribute schema", panel))
        layout.addWidget(self.schema_table, 1)
        layout.addWidget(QLabel("First 12 attribute rows", panel))
        layout.addWidget(self.attributes_table, 2)
        splitter.addWidget(self.viewer_widget)
        splitter.addWidget(panel)
        splitter.setSizes([760, 440])
        self.setCentralWidget(splitter)

    def initialize_viewer(self) -> None:
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            path = ensure_sample_file(app=self.app, zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/geog_25000_dxf.zip", zip_name="geog_25000_dxf.zip", target_folder="geog_25000_dxf", required_file="geog_25000.dxf", title="DxfLoad")
            self.viewer.add_layer(str(path))
            self.populate_details(path)
            self.viewer.zoom_to_layer(0)
        except Exception as error:
            QMessageBox.critical(self, "DxfLoad", f"Layer could not be loaded:\n\n{error}")

    def populate_details(self, path: Path) -> None:
        info = self.viewer.layer_info(0)
        definitions = self.viewer.layer_attribute_definitions(0)
        self.details.setPlainText("DxfLoad sample\n\nAPI\nadd_layer(path)\nlayer_info(index)\nlayer_attribute_definitions(index)\n\nLoaded: " + str(path) + "\n\nLayer\n" + str(info))
        self.schema_table.setColumnCount(4)
        self.schema_table.setHorizontalHeaderLabels(["Name", "Type", "Length", "Decimals"])
        self.schema_table.setRowCount(len(definitions))
        for row, definition in enumerate(definitions):
            for column, key in enumerate(("name", "type", "length", "decimalCount")):
                self.schema_table.setItem(row, column, QTableWidgetItem(str(definition.get(key, ""))))
        rows = min(12, self.viewer.layer_feature_count(0))
        fields = [str(item.get("name", "")) for item in definitions]
        self.attributes_table.setColumnCount(len(fields))
        self.attributes_table.setHorizontalHeaderLabels(fields)
        self.attributes_table.setRowCount(rows)
        for row in range(rows):
            values = self.viewer.layer_feature_attributes(0, row)
            for column, field in enumerate(fields):
                self.attributes_table.setItem(row, column, QTableWidgetItem(str(values.get(field, ""))))
        self.statusBar().showMessage(f"DxfLoad loaded: {path.name}")

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    icon = QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico")))
    app.setApplicationName("DxfLoad")
    app.setWindowIcon(icon)
    window = DxfLoadWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
