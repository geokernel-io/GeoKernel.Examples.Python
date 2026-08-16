import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from geokernel import Viewer, ViewerTool
from common import application_icon, ensure_sample_file

SHAPEFILE_SIDECARS = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix")


class ShapefileSaveAsWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.source_path = None
        self.saving = False
        self.initialized = False

        self.setWindowTitle("ShapefileSaveAs")
        self.setWindowIcon(application_icon())
        self.resize(1200, 760)
        self.create_ui()

    @property
    def output_path(self) -> Path:
        return (
            Path(__file__).resolve().parent
            / "ShapefileSaveAsData"
            / "world_4326_copy.shp"
        )

    def create_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top_bar = QWidget(root)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(8)

        self.save_button = QPushButton("Save As Shapefile", top_bar)
        self.save_button.clicked.connect(self.save_as_shapefile)
        self.progress_bar = QProgressBar(top_bar)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        top_layout.addWidget(self.save_button)
        top_layout.addWidget(self.progress_bar, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal, root)
        splitter.addWidget(self.viewer_widget)

        right_panel = QWidget(splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(6)

        self.details_view = QTextEdit(right_panel)
        self.details_view.setReadOnly(True)
        self.attributes_table = QTableWidget(right_panel)
        self.attributes_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.attributes_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.attributes_table.verticalHeader().setVisible(False)

        right_layout.addWidget(QLabel("SaveAs state", right_panel))
        right_layout.addWidget(self.details_view, 1)
        right_layout.addWidget(QLabel("Reloaded output attributes", right_panel))
        right_layout.addWidget(self.attributes_table, 1)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([760, 440])

        root_layout.addWidget(top_bar)
        root_layout.addWidget(splitter, 1)
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
            self.source_path = ensure_sample_file(
                app=self.app,
                zip_url=(
                    "https://github.com/geokernel-io/GeoKernel.SampleData/"
                    "releases/download/v1/world_4326.zip"
                ),
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="ShapefileSaveAs",
            )
            self.viewer.add_layer(str(self.source_path))
            self.viewer.set_layer_name(0, "World countries")
            self.viewer.set_layer_style(
                0,
                {
                    "fillColor": "#D7E5DF",
                    "lineColor": "#6D8C86",
                    "lineWidth": 1.0,
                },
            )
            self.viewer.full_extent()
            self.show_source_state()
            QTimer.singleShot(0, self.save_as_shapefile)
        except Exception as error:
            self.statusBar().showMessage("Shapefile sample data could not be prepared.")
            QMessageBox.critical(self, "ShapefileSaveAs", str(error))

    def save_as_shapefile(self, output_path=None) -> bool:
        if self.saving or self.source_path is None or self.viewer.layer_count() == 0:
            return False

        destination = Path(output_path) if output_path else self.output_path
        self.saving = True
        self.save_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Saving shapefile copy...")

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.remove_existing_shapefile(destination)
            self.progress_bar.setValue(20)
            QApplication.processEvents()

            if not self.viewer.save_layer_as_shapefile(0, destination):
                raise RuntimeError("save_layer_as_shapefile returned False.")

            self.progress_bar.setValue(75)
            QApplication.processEvents()
            definitions, rows, saved_info = self.read_saved_output(destination)
            self.fill_attribute_table(definitions, rows)
            self.show_details(destination, saved_info)
            self.progress_bar.setValue(100)
            self.statusBar().showMessage(f"SaveAs wrote {destination}")
            return True
        except Exception as error:
            self.show_details(destination, None)
            self.statusBar().showMessage("SaveAs failed.")
            if output_path is None:
                QMessageBox.critical(
                    self, "ShapefileSaveAs", f"SaveAs failed:\n{error}"
                )
            return False
        finally:
            self.saving = False
            self.save_button.setEnabled(True)

    def read_saved_output(self, path: Path):
        verifier = Viewer()
        try:
            verifier.add_layer(str(path))
            definitions = verifier.layer_attribute_definitions(0)
            feature_count = verifier.layer_feature_count(0)
            rows = self.sample_attribute_rows(verifier, 0, 12)
            info = verifier.layer_info(0)
            info["featureCount"] = feature_count
            return definitions, rows, info
        finally:
            verifier.close()

    def show_source_state(self) -> None:
        definitions = self.viewer.layer_attribute_definitions(0)
        rows = self.sample_attribute_rows(self.viewer, 0, 12)
        self.fill_attribute_table(definitions, rows)
        self.show_details(self.output_path, None)

    @staticmethod
    def sample_attribute_rows(viewer: Viewer, layer_index: int, max_rows: int):
        rows = []
        for row_index in range(max_rows):
            attributes = viewer.layer_feature_attributes(layer_index, row_index)
            if not attributes:
                break
            rows.append(attributes)
        return rows

    def fill_attribute_table(self, definitions, rows) -> None:
        field_names = [definition.get("name", "") for definition in definitions]
        self.attributes_table.clear()
        self.attributes_table.setColumnCount(len(field_names) + 1)
        self.attributes_table.setRowCount(max(1, len(rows)))
        self.attributes_table.setHorizontalHeaderLabels(["#", *field_names])

        if not rows:
            self.attributes_table.setItem(
                0, 0, QTableWidgetItem("No attribute rows returned.")
            )
        else:
            for row_index, attributes in enumerate(rows):
                self.attributes_table.setItem(
                    row_index, 0, QTableWidgetItem(str(row_index))
                )
                for column, field_name in enumerate(field_names, start=1):
                    value = attributes.get(field_name, "")
                    self.attributes_table.setItem(
                        row_index, column, QTableWidgetItem(str(value))
                    )
        self.attributes_table.resizeColumnsToContents()

    def show_details(self, destination: Path, saved_info) -> None:
        source_definitions = (
            self.viewer.layer_attribute_definitions(0)
            if self.viewer.layer_count() > 0
            else []
        )
        source_count = (
            self.viewer.layer_feature_count(0) if self.viewer.layer_count() > 0 else 0
        )
        lines = [
            "ShapefileSaveAs sample",
            "",
            "API",
            "viewer.add_layer(source_path)",
            "viewer.save_layer_as_shapefile(0, output_path)",
            "",
            "Source shapefile",
            str(self.source_path or "-"),
            f"Source fields: {len(source_definitions)}",
            f"Source feature count: {source_count}",
            "",
            "Output shapefile",
            str(destination),
            self.sidecar_report(destination),
        ]
        if saved_info is not None:
            lines.extend(
                [
                    "",
                    "Reloaded output",
                    f"Layer name: {saved_info.get('name', destination.stem)}",
                    f"Layer type: {saved_info.get('type', '-')}",
                    f"Feature count: {saved_info.get('featureCount', 0)}",
                ]
            )
        self.details_view.setPlainText("\n".join(lines))

    @staticmethod
    def remove_existing_shapefile(path: Path) -> None:
        base = path.with_suffix("")
        for extension in SHAPEFILE_SIDECARS:
            sidecar = base.with_suffix(extension)
            if sidecar.exists():
                sidecar.unlink()

    @staticmethod
    def sidecar_report(path: Path) -> str:
        base = path.with_suffix("")
        lines = []
        for extension in SHAPEFILE_SIDECARS:
            sidecar = base.with_suffix(extension)
            state = f"{sidecar.stat().st_size} bytes" if sidecar.exists() else "missing"
            lines.append(f"{extension}: {state}")
        return "\n".join(lines)

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ShapefileSaveAs")
    app.setWindowIcon(application_icon())
    window = ShapefileSaveAsWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
