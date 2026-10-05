"""Per-layer appearance, attribute coloring and filtering on 3D terrain."""
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDockWidget,
    QDoubleSpinBox, QFileDialog, QFormLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QWidget,
)

from common import application_icon, ensure_sample_file
from project_viewer import ProjectViewer


class ProjectWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ready = self.loading = self.downloading = self.syncing = False
        self.layers = []
        self.active_id = ""
        self.project_path = None
        self.pending_project = None
        self.setWindowTitle("ProjectSaveLoad — GeoKernel")
        self.setWindowIcon(application_icon())
        self.resize(1250, 850)
        self.viewer = ProjectViewer(
            self)
        self.setCentralWidget(self.viewer)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(250)
        self.debounce.timeout.connect(lambda: self.safe(self.apply_filter))
        panel = QWidget()
        form = QFormLayout(panel)

        def caption(text, layout=form):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addRow(label)
            return label

        def button(text, callback, layout=form):
            control = QPushButton(text)
            control.clicked.connect(callback)
            layout.addRow(control)
            return control

        caption("Sagrada Família — project save/load")
        self.open = button("Open project…", self.open_project)
        self.save = button("Save", lambda: self.save_project(False))
        self.save_as = button("Save as…", lambda: self.save_project(True))
        self.project_info = caption("Unsaved sample scene")
        caption("Projects reference local files; they do not embed data. Keep the data cache. "
                "Open/reload replaces the current scene; save changes first.")
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.activated.connect(lambda: self.save_project(False))
        self.save_as_shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        self.save_as_shortcut.activated.connect(lambda: self.save_project(True))
        self.reload = button("Reload sample", self.load_sample)
        self.cancel = button("Cancel loading", self.viewer.cancel_load)
        self.imagery = QCheckBox("Show orthophoto")
        self.imagery.setChecked(True)
        self.imagery.toggled.connect(lambda value: self.safe(
            lambda: self.viewer.set_imagery_visible(value)))
        form.addRow(self.imagery)
        self.styles = QWidget()
        styles = QFormLayout(self.styles)
        styles.setContentsMargins(0, 0, 0, 0)
        form.addRow(self.styles)
        self.layer = QComboBox()
        styles.addRow("Layer", self.layer)
        self.layer.activated.connect(lambda *_: self.safe(self.change_layer))
        self.visible = QCheckBox("Visible")
        self.visible.toggled.connect(lambda *_: self.safe(self.appearance))
        styles.addRow(self.visible)
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix("%")
        self.opacity.valueChanged.connect(lambda *_: self.safe(self.appearance))
        styles.addRow("Opacity", self.opacity)
        self.color = button("Choose uniform color", lambda: self.safe(self.choose_color), styles)
        button("Restore source color", lambda: self.safe(lambda: self.color_action("")), styles)
        self.theme = QComboBox()
        self.theme.activated.connect(lambda *_: self.safe(self.change_theme))
        styles.addRow("Color by attribute", self.theme)
        self.field = QComboBox()
        self.field.activated.connect(lambda *_: self.safe(self.change_field))
        styles.addRow("Filter attribute", self.field)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Contains text (case-insensitive)")
        self.text.textChanged.connect(self.queue_filter)
        styles.addRow("Contains", self.text)
        self.values = QComboBox()
        self.values.activated.connect(lambda index: self.text.setText(self.values.itemText(index))
                                      if index > 0 else None)
        styles.addRow("Example values", self.values)
        button("Clear this filter", lambda: self.safe(self.clear_filter), styles)
        self.count = caption("No layer loaded.", styles)
        self.focus = button("Zoom to matching features", lambda: self.safe(self.focus_layer), styles)
        button("Reset all styles and filters", lambda: self.safe(self.reset_styles), styles)
        self.height = QDoubleSpinBox()
        self.height.setRange(.25, 10)
        self.height.setSingleStep(.25)
        self.height.setValue(1)
        self.height.valueChanged.connect(lambda value: self.safe(lambda: self.viewer.set_height_scale(value)))
        form.addRow("Vertical exaggeration", self.height)
        button("Reset view", lambda: self.safe(self.viewer.reset_camera))
        caption("Filters use literal, case-insensitive substring matching and affect drawing and "
                "selection. Attribute coloring overrides uniform color. Changes are session-only.")
        caption("Example lists contain up to 200 values per field; filters search all records. "
                "Counts include records without drawable geometry. Building heights are illustrative "
                "(9 m). DEM heights are metres; the vertical datum is unverified.")
        caption("Left drag: pan\nWheel/right drag: zoom\nMiddle/Ctrl+left drag: orbit")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        dock = QDockWidget("Layer styling", self)
        dock.setMinimumWidth(340)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(160)
        self.statusBar().addPermanentWidget(self.progress)
        self.poll = QTimer(self)
        self.poll.setInterval(50)
        self.poll.timeout.connect(self.poll_load)
        self.set_busy(False)

    def safe(self, action):
        if not self.ready or self.loading or self.syncing:
            return
        try:
            action()
        except Exception as error:
            self.debounce.stop()
            self.statusBar().showMessage(str(error))

    def current(self):
        return next((item for item in self.layers if item["id"] == self.active_id), None)

    def command(self, action, **values):
        self.viewer.update_style(action, self.active_id, **values)

    def queue_filter(self, *_):
        if self.ready and not self.syncing and not self.loading:
            self.debounce.start()

    def apply_filter(self):
        self.debounce.stop()
        if self.active_id:
            self.command("filter", field=self.field.currentData() or "", text=self.text.text())
            self.update_counts()

    def change_layer(self):
        if self.debounce.isActive():
            self.apply_filter()
        self.active_id = self.layer.currentData() or ""
        self.refresh_layers()

    def appearance(self):
        self.command("appearance", visible=self.visible.isChecked(), opacity=self.opacity.value() / 100)
        self.update_counts()

    def choose_color(self):
        self.apply_filter()
        color = QColorDialog.getColor(QColor(self.current()["color"] or "#ffffff"), self, "Layer color")
        if color.isValid():
            self.color_action(color.name())

    def color_action(self, color):
        self.apply_filter()
        self.command("color", color=color)
        self.refresh_layers()

    def change_theme(self):
        self.apply_filter()
        self.command("theme", field=self.theme.currentData() or "")
        self.refresh_layers()

    def change_field(self):
        self.populate_values()
        self.apply_filter()

    def clear_filter(self):
        self.text.clear()
        self.apply_filter()

    def focus_layer(self):
        self.apply_filter()
        self.command("focus")

    def reset_styles(self):
        self.debounce.stop()
        self.command("reset")
        self.refresh_layers()

    def update_counts(self):
        self.layers = self.viewer.layers()
        current = self.current()
        if current:
            self.count.setText(f'Matching records: {current["matchingRecords"]:,} / {current["records"]:,}\n'
                               f'Drawable matching ranges: {current["drawableRanges"]:,}')
            self.focus.setEnabled(current["drawableRanges"] > 0 and current["visible"] and current["opacity"] > 0)

    def refresh_layers(self):
        self.layers = self.viewer.layers()
        self.syncing = True
        try:
            self.layer.clear()
            for item in self.layers:
                self.layer.addItem(item["name"], item["id"])
            current = self.current() or next(iter(self.layers), None)
            self.active_id = current["id"] if current else ""
            self.styles.setEnabled(current is not None and not self.loading)
            if current is None:
                return
            self.layer.setCurrentIndex(self.layer.findData(self.active_id))
            self.visible.setChecked(current["visible"])
            self.opacity.setValue(round(current["opacity"] * 100))
            self.color.setText("Uniform color: " + current["color"] if current["color"] else "Choose uniform color")
            for combo, title, value in (
                (self.field, "All attributes / source IDs", current["field"]),
                (self.theme, "Uniform / source color", current["theme"]),
            ):
                combo.clear()
                combo.addItem(title, "")
                for key in sorted(current["attributes"], key=str.casefold):
                    combo.addItem(key, key)
                combo.setCurrentIndex(max(0, combo.findData(value)))
            self.text.setText(current["text"])
            self.populate_values()
        finally:
            self.syncing = False
        self.update_counts()

    def populate_values(self):
        self.values.clear()
        self.values.addItem("Choose a value or type text")
        current = self.current()
        if current:
            self.values.addItems(current["attributes"].get(self.field.currentData(), []))
        self.values.setEnabled(self.values.count() > 1)

    def set_busy(self, busy):
        self.loading = busy
        self.reload.setEnabled(not busy)
        self.open.setEnabled(not busy)
        self.save.setEnabled(self.ready and not busy)
        self.save_as.setEnabled(self.ready and not busy)
        self.cancel.setEnabled(busy and not self.downloading)
        self.progress.setVisible(busy)
        self.styles.setEnabled(self.ready and bool(self.layers) and not busy)
        self.imagery.setEnabled(self.ready and not busy)
        self.height.setEnabled(not busy)

    def sample_file(self, dataset, filename):
        sample = "sagrada_familia_" + dataset
        return ensure_sample_file(
            self.app, f"https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/{sample}.zip",
            sample + ".zip", sample, filename, "ProjectSaveLoad")

    def shapefile(self, dataset):
        path = self.sample_file(dataset, dataset + ".shp")
        for extension in ("shx", "dbf", "prj"):
            part = self.sample_file(dataset, f"{dataset}.{extension}")
            if part.parent != path.parent:
                raise RuntimeError("Shapefile components must share a directory.")
        return path

    def save_project(self, choose_path):
        if not self.ready or self.loading:
            return
        try:
            self.apply_filter()
            path = self.project_path
            if choose_path or not path:
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save project", path or str(Path.home() / "SagradaFamilia.gk3d"),
                    "GeoKernel 3D project (*.gk3d)")
                if not path:
                    return
                if not Path(path).suffix:
                    path += ".gk3d"
            self.viewer.save_project(path)
            self.project_path = str(Path(path).resolve())
            self.project_info.setText(self.project_path)
            self.statusBar().showMessage("Project saved. Local source files remain separate.")
        except Exception as error:
            self.statusBar().showMessage(str(error))
            QMessageBox.critical(self, "Save failed", str(error))

    def open_project(self):
        if self.loading:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open project", self.project_path or str(Path.home()),
            "GeoKernel 3D project (*.gk3d *.json)")
        if not path:
            return
        try:
            if self.ready:
                self.apply_filter()
            self.debounce.stop()
            self.pending_project = str(Path(path).resolve())
            self.set_busy(True)
            self.viewer.open_project(path)
            self.statusBar().showMessage("Opening project…")
            self.poll.start()
        except Exception as error:
            self.pending_project = None
            self.fail(error)

    def load_sample(self):
        if self.loading:
            return
        if self.ready:
            self.safe(self.apply_filter)
        self.debounce.stop()
        self.pending_project = None
        self.downloading = True
        self.set_busy(True)
        try:
            dem = self.sample_file("terrain", "sagrada_familia_terrain.tif")
            imagery = self.sample_file("ortophoto", "sagrada_familia_ortophoto.tif")
            roads = self.shapefile("roads")
            buildings = self.shapefile("buildings")
            self.viewer.load_features(dem, imagery, roads, buildings)
            self.cancel.setEnabled(True)
            self.statusBar().showMessage("Loading terrain, roads and buildings…")
            self.poll.start()
        except Exception as error:
            self.fail(error)
        finally:
            self.downloading = False

    def poll_load(self):
        try:
            state = self.viewer.poll_load()
            if state == 0:
                return
            self.poll.stop()
            if state == 1:
                self.ready = True
                if self.pending_project:
                    height, imagery = self.viewer.project_display()
                    self.syncing = True
                    try:
                        self.height.setValue(height)
                        self.imagery.setChecked(imagery)
                    finally:
                        self.syncing = False
                else:
                    self.viewer.set_height_scale(self.height.value())
                    self.viewer.set_imagery_visible(self.imagery.isChecked())
                self.project_path = self.pending_project
                self.pending_project = None
                self.project_info.setText(self.project_path or "Unsaved sample scene")
                self.refresh_layers()
                self.statusBar().showMessage("Ready — choose a layer to style or filter.")
            elif state == -2:
                self.pending_project = None
                self.statusBar().showMessage("Loading cancelled. Previous scene retained.")
            else:
                raise RuntimeError("Loading ended without a scene.")
            self.set_busy(False)
        except Exception as error:
            self.fail(error)

    def fail(self, error):
        self.pending_project = None
        self.poll.stop()
        self.set_busy(False)
        self.statusBar().showMessage(str(error))
        QMessageBox.critical(self, "ProjectSaveLoad", str(error))

    def closeEvent(self, event):
        if self.downloading:
            event.ignore()
            return
        self.debounce.stop()
        self.poll.stop()
        self.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ProjectSaveLoad")
    app.setWindowIcon(application_icon())
    try:
        window = ProjectWindow(app)
    except Exception as error:
        QMessageBox.critical(None, "ProjectSaveLoad", str(error))
        return 1
    app.aboutToQuit.connect(window.viewer.close_viewer)
    window.show()
    QTimer.singleShot(0, window.load_sample)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
