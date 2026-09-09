import json
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit
from geokernel import CoordinateSystemFactory
from common import application_icon

class CrsByAuthorityWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        self.setWindowTitle("CrsByAuthority")
        self.setWindowIcon(application_icon())
        self.resize(900, 650)
        self.setCentralWidget(self.output)
        definition = CoordinateSystemFactory().from_authority("EPSG", 4326)
        self.output.setPlainText(json.dumps(definition, indent=2))

def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = CrsByAuthorityWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
