import json
import sys
from PySide6.QtWidgets import QApplication, QLineEdit, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory
from common import application_icon

class CrsDatabaseWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.factory = CoordinateSystemFactory()
        self.query = QLineEdit("4326", self)
        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        run = QPushButton("Find EPSG", self)
        run.clicked.connect(self.find_epsg)
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.addWidget(self.query)
        layout.addWidget(run)
        layout.addWidget(self.output)
        self.setCentralWidget(root)
        self.setWindowTitle("CrsDatabase")
        self.setWindowIcon(application_icon())
        self.resize(900, 650)
        self.find_epsg()

    def find_epsg(self) -> None:
        try:
            definition = self.factory.from_epsg(int(self.query.text()))
            self.output.setPlainText(json.dumps(definition, indent=2))
        except (ValueError, RuntimeError) as error:
            self.output.setPlainText(str(error))

def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    window = CrsDatabaseWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
