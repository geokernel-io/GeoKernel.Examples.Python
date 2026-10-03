"""Camera presets and persistent views for the fixed Sagrada Familia sample."""

import json
import math
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QWidget,
)


class CameraPanel(QWidget):
    def __init__(self, viewer, parent=None, storage=None):
        super().__init__(parent)
        self.viewer = viewer
        self.home = None
        self.storage = Path(storage) if storage else Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        ) / "sagrada-camera-views-v1.json"
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.presets = QComboBox()
        self.presets.addItems(["Overview", "Top view", "East view", "West view", "Close oblique"])
        form.addRow(self.presets)
        self._button(form, "Go to preset", lambda: self.go_preset(self.presets.currentIndex()))
        self.smooth = QCheckBox("Smooth transition (1.2 seconds)")
        self.smooth.setChecked(True)
        self.smooth.toggled.connect(self.viewer.stop_camera)
        form.addRow(self.smooth)
        self._button(form, "Stop transition", self.viewer.stop_camera)
        self._button(form, "Zoom in", lambda: self.zoom(0.7))
        self._button(form, "Zoom out", lambda: self.zoom(1 / 0.7))
        self._button(form, "North up", self.north_up)
        self.views = QComboBox()
        form.addRow("Saved views", self.views)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Saved view name")
        form.addRow(self.name)
        self._button(form, "Save current view", lambda: self.save_view(self.name.text()))
        self._button(form, "Restore saved view", self.restore_view)
        self._button(form, "Delete saved view", self.delete_view)
        self.status = QLabel()
        self.status.setWordWrap(True)
        form.addRow(self.status)
        help_text = QLabel("Mouse or keyboard input stops transitions.\nViews belong to this sample dataset.")
        help_text.setWordWrap(True)
        form.addRow(help_text)
        try:
            if self.storage.is_file():
                entries = json.loads(self.storage.read_text(encoding="utf-8"))
                if not isinstance(entries, list):
                    raise ValueError("Expected a list of views")
                for entry in entries:
                    if (isinstance(entry, dict) and isinstance(entry.get("name"), str)
                            and entry["name"].strip() and self.valid(entry.get("camera"))
                            and self.views.count() < 20):
                        self.views.addItem(entry["name"], entry["camera"])
        except (OSError, ValueError):
            self.status.setText("Saved views could not be read.")
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def _button(self, form, text, action):
        button = QPushButton(text)
        def invoke():
            try:
                action()
            except (OSError, ValueError, RuntimeError) as error:
                QMessageBox.critical(self, "Camera navigation", str(error))
        button.clicked.connect(invoke)
        form.addRow(button)

    @staticmethod
    def valid(c):
        return (isinstance(c, list) and len(c) == 6
                and all(type(v) in (int, float) and math.isfinite(v) for v in c)
                and -85 <= c[1] <= 85 and 0.005 <= c[2] <= 20)

    def set_home(self):
        self.viewer.stop_camera()
        self.home = self.viewer.get_camera()

    def move_to(self, camera):
        self.viewer.move_camera(camera, 1200 if self.smooth.isChecked() else 0)

    def go_preset(self, index):
        if self.home is None:
            return
        c = self.home.copy()
        if index == 1:
            c[0], c[1] = 0, 85
        elif index == 2:
            c[0], c[1] = 90, 35
        elif index == 3:
            c[0], c[1] = -90, 35
        elif index == 4:
            c[1], c[2] = 30, max(0.005, c[2] * 0.55)
        self.move_to(c)

    def zoom(self, factor):
        c = self.viewer.get_camera()
        c[2] = min(20, max(0.005, c[2] * factor))
        self.move_to(c)

    def north_up(self):
        c = self.viewer.get_camera()
        c[0] = 0
        self.move_to(c)

    def save_view(self, name):
        if self.home is None or not name.strip() or self.views.count() >= 20:
            return
        self.viewer.stop_camera()
        self.views.addItem(name.strip(), self.viewer.get_camera())
        self.views.setCurrentIndex(self.views.count() - 1)
        self.persist()

    def restore_view(self):
        if self.views.currentIndex() >= 0:
            self.move_to(self.views.currentData())

    def delete_view(self):
        if self.views.currentIndex() >= 0:
            self.views.removeItem(self.views.currentIndex())
            self.persist()

    def persist(self):
        entries = [{"name": self.views.itemText(i), "camera": self.views.itemData(i)}
                   for i in range(self.views.count())]
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.storage.with_suffix(".tmp")
        temporary.write_text(json.dumps(entries, allow_nan=False), encoding="utf-8")
        temporary.replace(self.storage)

    def refresh(self):
        if self.home is not None and self.isEnabled():
            c = self.viewer.get_camera()
            self.status.setText(f"Heading: {c[0] % 360:.1f} degrees\nTilt: {c[1]:.1f} degrees")
