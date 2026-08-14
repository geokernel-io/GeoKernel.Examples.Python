import math
import re
import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox, QGridLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget
from geokernel import ClassificationMethod, ColorRampMode, SymbolStyleTarget, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

BASE_STYLE = {
    "fillColor": "#DCE8E4",
    "fillOpacity": 220,
    "lineColor": "#536B68",
    "lineWidth": 0.8,
}
METHODS = (
    ("Equal Interval", ClassificationMethod.EQUAL_INTERVAL),
    ("Quantile", ClassificationMethod.QUANTILE),
    ("Quartile", ClassificationMethod.QUARTILE),
    ("Natural Breaks", ClassificationMethod.NATURAL_BREAKS),
    ("Geometrical Interval", ClassificationMethod.GEOMETRICAL_INTERVAL),
    ("K-Means", ClassificationMethod.KMEANS),
    ("K-Means Spatial", ClassificationMethod.KMEANS_SPATIAL),
    ("Standard Deviation", ClassificationMethod.STANDARD_DEVIATION),
    (
        "Standard Deviation with Central",
        ClassificationMethod.STANDARD_DEVIATION_WITH_CENTRAL,
    ),
    ("Defined Interval", ClassificationMethod.DEFINED_INTERVAL),
    ("Manual", ClassificationMethod.MANUAL),
)
STYLE_TARGETS = (
    ("Color", SymbolStyleTarget.COLOR),
    ("Size / Width", SymbolStyleTarget.SIZE_OR_WIDTH),
    ("Outline color", SymbolStyleTarget.OUTLINE_COLOR),
    ("Outline width", SymbolStyleTarget.OUTLINE_WIDTH),
)

class ClassificationWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.initialized = False
        self.layer_index = -1

        self.setWindowTitle("Classification")
        self.setWindowIcon(application_icon())
        self.resize(1240, 760)
        self.create_layout()
        self.connect_controls()
        self.sync_controls()

    def create_layout(self) -> None:
        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.controls = QWidget(central)
        controls_layout = QGridLayout(self.controls)
        controls_layout.setContentsMargins(8, 6, 8, 6)
        controls_layout.setHorizontalSpacing(8)
        controls_layout.setVerticalSpacing(4)

        self.renderer_combo = QComboBox(self.controls)
        self.renderer_combo.addItems(("Categorized", "Graduated"))
        self.renderer_combo.setCurrentText("Graduated")
        self.field_combo = QComboBox(self.controls)

        self.method_combo = QComboBox(self.controls)
        for name, method in METHODS:
            self.method_combo.addItem(name, method)
        self.method_combo.setCurrentIndex(
            self.method_combo.findData(ClassificationMethod.NATURAL_BREAKS)
        )

        self.class_count_label = QLabel("Classes", self.controls)
        self.class_count_spin = QSpinBox(self.controls)
        self.class_count_spin.setRange(2, 64)
        self.class_count_spin.setValue(15)

        self.interval_label = QLabel("Interval", self.controls)
        self.interval_spin = QDoubleSpinBox(self.controls)
        self.interval_spin.setDecimals(4)
        self.interval_spin.setRange(0.0001, 1_000_000_000.0)
        self.interval_spin.setValue(100000.0)

        self.manual_breaks_label = QLabel("Manual breaks", self.controls)
        self.manual_breaks_edit = QLineEdit(
            "0, 100000, 500000, 1000000, 5000000, 10000000", self.controls
        )

        self.target_combo = QComboBox(self.controls)
        for name, target in STYLE_TARGETS:
            self.target_combo.addItem(name, target)

        self.ramp_combo = QComboBox(self.controls)
        self.ramp_mode_combo = QComboBox(self.controls)
        self.ramp_mode_combo.addItem("Continuous", ColorRampMode.CONTINUOUS)
        self.ramp_mode_combo.addItem("Discrete", ColorRampMode.DISCRETE)
        self.reverse_check = QCheckBox("Reverse", self.controls)

        self.apply_button = QPushButton("Apply", self.controls)
        self.clear_button = QPushButton("Clear", self.controls)
        self.full_extent_button = QPushButton("Full extent", self.controls)

        controls_layout.addWidget(QLabel("Renderer", self.controls), 0, 0)
        controls_layout.addWidget(self.renderer_combo, 0, 1)
        controls_layout.addWidget(QLabel("Field", self.controls), 0, 2)
        controls_layout.addWidget(self.field_combo, 0, 3)
        controls_layout.addWidget(QLabel("Method", self.controls), 0, 4)
        controls_layout.addWidget(self.method_combo, 0, 5)
        controls_layout.addWidget(self.class_count_label, 0, 6)
        controls_layout.addWidget(self.class_count_spin, 0, 7)
        controls_layout.addWidget(self.interval_label, 1, 0)
        controls_layout.addWidget(self.interval_spin, 1, 1)
        controls_layout.addWidget(self.manual_breaks_label, 1, 2)
        controls_layout.addWidget(self.manual_breaks_edit, 1, 3, 1, 2)
        controls_layout.addWidget(QLabel("Render by", self.controls), 1, 5)
        controls_layout.addWidget(self.target_combo, 1, 6)
        controls_layout.addWidget(QLabel("Ramp", self.controls), 2, 0)
        controls_layout.addWidget(self.ramp_combo, 2, 1)
        controls_layout.addWidget(QLabel("Ramp mode", self.controls), 2, 2)
        controls_layout.addWidget(self.ramp_mode_combo, 2, 3)
        controls_layout.addWidget(self.reverse_check, 2, 4)
        controls_layout.addWidget(self.apply_button, 2, 5)
        controls_layout.addWidget(self.clear_button, 2, 6)
        controls_layout.addWidget(self.full_extent_button, 2, 7)
        controls_layout.setColumnStretch(3, 1)

        root_layout.addWidget(self.controls)
        root_layout.addWidget(self.viewer_widget, 1)
        self.setCentralWidget(central)

        self.legend = QListWidget(self)
        self.legend_dock = QDockWidget("Legend", self)
        self.legend_dock.setWidget(self.legend)
        self.legend_dock.setMinimumWidth(240)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.legend_dock)
        self.controls.setEnabled(False)

    def connect_controls(self) -> None:
        self.renderer_combo.currentIndexChanged.connect(self.renderer_changed)
        self.method_combo.currentIndexChanged.connect(self.method_changed)
        self.apply_button.clicked.connect(self.apply_classification)
        self.clear_button.clicked.connect(self.clear_renderer)
        self.full_extent_button.clicked.connect(self.viewer.full_extent)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.legend.addItem("Preparing California sample data...")
        self.statusBar().showMessage("Preparing California sample data...")

        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/california.zip",
                zip_name="california.zip",
                target_folder="california",
                required_file="california.shp",
                title="Classification",
            )
            self.viewer.add_open_street_map_layer()
            self.viewer.add_layer(str(path), {"buildFeatureSource": True})
            self.layer_index = 0
            self.viewer.set_layer_name(
                self.layer_index, "California counties - classification"
            )
            self.viewer.set_layer_style(self.layer_index, BASE_STYLE)

            self.ramp_combo.addItems(self.viewer.color_ramp_names())
            self.ramp_combo.setCurrentText("GreenBlue")
            self.populate_fields()
            self.controls.setEnabled(True)
            self.sync_controls()
            self.apply_classification()
            self.viewer.zoom_to_layer(self.layer_index)
        except Exception as error:
            self.legend.clear()
            self.legend.addItem("Classification could not be initialized.")
            self.statusBar().showMessage("Classification could not be initialized.")
            QMessageBox.critical(self, "Classification", str(error))

    def renderer_changed(self) -> None:
        if self.layer_index >= 0:
            self.populate_fields()
        preferred_ramp = "Unique" if self.is_categorized() else "GreenBlue"
        if self.ramp_combo.findText(preferred_ramp) >= 0:
            self.ramp_combo.setCurrentText(preferred_ramp)
        self.sync_controls()

    def method_changed(self) -> None:
        method = self.current_method()
        if method in {
            ClassificationMethod.STANDARD_DEVIATION,
            ClassificationMethod.STANDARD_DEVIATION_WITH_CENTRAL,
        } and self.interval_spin.value() > 10.0:
            self.interval_spin.setValue(1.0)
        self.sync_controls()

    def populate_fields(self) -> None:
        selected = self.field_combo.currentText()
        self.field_combo.clear()
        numeric_only = not self.is_categorized()
        for definition in self.viewer.layer_attribute_definitions(self.layer_index):
            name = str(definition.get("name", "")).strip()
            field_type = int(definition.get("type", -1))
            if name and (not numeric_only or field_type in {1, 2}):
                self.field_combo.addItem(name)

        if self.field_combo.count() == 0:
            raise RuntimeError(
                "No compatible attribute fields were found in the California layer schema."
            )
        preferred = "STATEFP" if self.is_categorized() else "POPULATION"
        index = self.field_combo.findText(selected, Qt.MatchFlag.MatchFixedString)
        if index < 0:
            index = self.field_combo.findText(preferred, Qt.MatchFlag.MatchFixedString)
        self.field_combo.setCurrentIndex(index if index >= 0 else 0)

    def sync_controls(self) -> None:
        graduated = not self.is_categorized()
        method = self.current_method()
        fixed_class_methods = {
            ClassificationMethod.MANUAL,
            ClassificationMethod.DEFINED_INTERVAL,
            ClassificationMethod.QUARTILE,
            ClassificationMethod.STANDARD_DEVIATION,
            ClassificationMethod.STANDARD_DEVIATION_WITH_CENTRAL,
        }
        interval_methods = {
            ClassificationMethod.DEFINED_INTERVAL,
            ClassificationMethod.STANDARD_DEVIATION,
            ClassificationMethod.STANDARD_DEVIATION_WITH_CENTRAL,
        }
        uses_class_count = not graduated or method not in fixed_class_methods
        uses_interval = graduated and method in interval_methods
        uses_manual_breaks = graduated and method == ClassificationMethod.MANUAL

        self.method_combo.setEnabled(graduated)
        self.class_count_label.setText("Classes" if graduated else "Categories")
        self.class_count_label.setEnabled(uses_class_count)
        self.class_count_spin.setEnabled(uses_class_count)
        self.interval_label.setText(
            "Std dev step"
            if method
            in {
                ClassificationMethod.STANDARD_DEVIATION,
                ClassificationMethod.STANDARD_DEVIATION_WITH_CENTRAL,
            }
            else "Interval"
        )
        self.interval_label.setEnabled(uses_interval)
        self.interval_spin.setEnabled(uses_interval)
        self.manual_breaks_label.setEnabled(uses_manual_breaks)
        self.manual_breaks_edit.setEnabled(uses_manual_breaks)
        self.ramp_mode_combo.setEnabled(graduated)

    def apply_classification(self) -> bool:
        if self.layer_index < 0:
            return False
        field_name = self.field_combo.currentText().strip()
        if not field_name:
            QMessageBox.information(self, "Classification", "Select a field first.")
            return False

        if self.is_categorized():
            ok = self.viewer.apply_categorized_renderer(
                self.layer_index,
                field_name,
                self.ramp_combo.currentText(),
                category_limit=self.class_count_spin.value(),
                reverse_color_ramp=self.reverse_check.isChecked(),
                style_target=self.current_style_target(),
            )
        else:
            manual_breaks = self.parse_manual_breaks()
            if self.current_method() == ClassificationMethod.MANUAL and len(manual_breaks) < 2:
                QMessageBox.information(
                    self,
                    "Classification",
                    "Manual mode needs at least two numeric break values.",
                )
                return False
            ok = self.viewer.apply_graduated_renderer(
                self.layer_index,
                field_name,
                self.current_method(),
                self.class_count_spin.value(),
                self.ramp_combo.currentText(),
                interval=self.interval_spin.value(),
                manual_breaks=manual_breaks,
                color_ramp_mode=self.ramp_mode_combo.currentData(),
                reverse_color_ramp=self.reverse_check.isChecked(),
                style_target=self.current_style_target(),
            )

        if not ok:
            self.statusBar().showMessage(
                f"Renderer could not be created for field '{field_name}'."
            )
            QMessageBox.information(
                self,
                "Classification",
                f"Renderer could not be created for field '{field_name}'.",
            )
            return False

        self.viewer.invalidate_render_cache(True, True)
        self.viewer.refresh_layers()
        self.update_legend()
        self.statusBar().showMessage(f"Classification applied on {field_name}")
        return True

    def clear_renderer(self) -> None:
        if self.layer_index < 0:
            return
        if self.viewer.clear_layer_symbol_renderer(self.layer_index):
            self.viewer.set_layer_style(self.layer_index, BASE_STYLE)
            self.legend.clear()
            self.viewer.invalidate_render_cache(True, True)
            self.viewer.refresh_layers()
            self.statusBar().showMessage("Renderer cleared")

    def update_legend(self) -> None:
        renderer = self.viewer.layer_symbol_renderer(self.layer_index)
        items = renderer.get("categories", renderer.get("ranges", []))
        self.legend.clear()
        for item in items:
            if not item.get("enabled", True):
                continue
            label = str(item.get("label", "")).strip() or "(unlabeled)"
            self.legend.addItem(
                QListWidgetItem(self.legend_icon(item.get("style", {})), label)
            )

    @staticmethod
    def legend_icon(style: dict) -> QIcon:
        pixmap = QPixmap(38, 22)
        pixmap.fill(Qt.GlobalColor.transparent)
        fill = QColor(str(style.get("fillColor", BASE_STYLE["fillColor"])))
        fill.setAlpha(int(style.get("fillOpacity", BASE_STYLE["fillOpacity"])))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(str(style.get("lineColor", BASE_STYLE["lineColor"]))), 2.0))
        painter.setBrush(fill)
        painter.drawRect(5, 4, 28, 14)
        painter.end()
        return QIcon(pixmap)

    def parse_manual_breaks(self) -> list[float]:
        values = []
        for part in re.split(r"[,;\s]+", self.manual_breaks_edit.text().strip()):
            if not part:
                continue
            try:
                value = float(part)
            except ValueError:
                return []
            if not math.isfinite(value):
                return []
            values.append(value)
        return sorted(values)

    def is_categorized(self) -> bool:
        return self.renderer_combo.currentText() == "Categorized"

    def current_method(self) -> ClassificationMethod:
        return ClassificationMethod(self.method_combo.currentData())

    def current_style_target(self) -> SymbolStyleTarget:
        return SymbolStyleTarget(self.target_combo.currentData())

    def closeEvent(self, event) -> None:
        self.viewer.close()
        super().closeEvent(event)

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Classification")
    app.setWindowIcon(application_icon())
    window = ClassificationWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
