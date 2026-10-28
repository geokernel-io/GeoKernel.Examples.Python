"""SAM3 draft review example; native tasks own inference and temporary results."""
from dataclasses import replace
from pathlib import Path
import sys

from geoai_support import HOTOSM, check_cancel, prepare_asset
from geoai_window import QApplication, QFileDialog, GeoAiWindow, QMessageBox, ViewerEventType, ViewerTool
from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import QComboBox, QLineEdit, QLabel, QPushButton


ROOT = "https://pub-00d214f25f754884b22349c19ac37bbf.r2.dev/geokernel-models/"
HASHES = {
    "text": "95d9bc3ebdec6a6147a9bfa97325712bfbb77fccbd6bb3f20be453c381820931",
    "tracker": "c4309ed67b2292f64641d740f2558c2d4253476ca1ec40c17d49c4800c050896",
}
PROFILE = replace(HOTOSM, task="sam3-text", title="Meta SAM3 — segmentation", buildings=False,
                  run_label="Generate draft", legend="Draft instances · review before saving",
                  description="SAM3 text / point / box segmentation.\nNo predictions are loaded at startup.",
                  credits="Model: Meta SAM3; retain SAM License and package notices.\nImagery source/license not verified.")


class MapBridge(QObject):
    clicked = Signal(float, float)


class Window(GeoAiWindow):
    def __init__(self, app):
        self.accepted = False
        self.points = []
        self.box = None
        self.corner = None
        self.prompt_layers = []
        super().__init__(app, PROFILE)
        self.map_bridge = MapBridge(self)
        self.map_bridge.clicked.connect(self.select_point)
        self.mode = QComboBox()
        self.mode.addItems(["Text segmentation", "Point / box segmentation"])
        self.text = QLineEdit("building")
        self.tool = QComboBox()
        self.tool.addItems(["Pan map", "Positive point", "Negative point", "Box: click two corners"])
        self.selection = QLabel("0 points · no box")
        self.clear_button = QPushButton("Clear prompts")
        self.accept_button = QPushButton("Accept draft")
        self.discard_button = QPushButton("Discard draft")
        self.tiff_button = QPushButton("Save accepted GeoTIFF")
        controls = self.run_button.parentWidget().layout()
        for i, widget in enumerate((self.mode, self.text, self.tool, self.selection, self.clear_button)):
            controls.insertWidget(1 + i, widget)
        for widget in (self.accept_button, self.discard_button, self.tiff_button):
            controls.insertWidget(controls.indexOf(self.cancel_button), widget)
        controls.insertWidget(controls.indexOf(self.opacity_label), self.threshold)
        self.threshold.show()
        self.threshold.setToolTip("Text score threshold; tracker uses its own quality scores.")
        self.mode.currentIndexChanged.connect(self._controls)
        self.tool.currentIndexChanged.connect(self._set_tool)
        self.clear_button.clicked.connect(self.clear_prompts)
        self.accept_button.clicked.connect(self.accept_draft)
        self.discard_button.clicked.connect(self.discard)
        self.tiff_button.clicked.connect(lambda: self.save_format("geotiff"))
        self._controls()

    def _controls(self, *_):
        super()._controls()
        if not hasattr(self, "mode"):
            return
        editable = not self.busy and not self.closing and self.result is None
        text_mode = self.mode.currentIndex() == 0
        self.run_button.setEnabled(editable)
        self.mode.setEnabled(editable)
        self.text.setEnabled(editable and text_mode)
        self.threshold.setEnabled(editable and text_mode)
        self.tool.setEnabled(editable and not text_mode)
        self.clear_button.setEnabled(editable)
        self.accept_button.setEnabled(not self.busy and self.result is not None and not self.accepted and not self.closing)
        self.discard_button.setEnabled(not self.busy and self.result is not None and not self.closing)
        allowed = not self.busy and self.accepted and self.result is not None and not self.closing
        self.save_button.setEnabled(allowed)
        self.tiff_button.setEnabled(allowed)
        self.viewer.set_tool(ViewerTool.INFO if editable and not text_mode and self.tool.currentIndex() else ViewerTool.PAN)

    def _set_tool(self, *_):
        self._controls()

    def _show_source(self, prepared):
        super()._show_source(prepared)
        self._restore_map_crs(None)
        self.viewer.full_extent()

    def _restore_map_crs(self, extent):
        # Removing a layer can make the native viewer adopt the source raster's
        # projected CRS. SAM3 clicks and prompt layers must remain in WGS84.
        if not self.viewer.set_coordinate_system_preset("wgs84"):
            raise RuntimeError("Cannot restore the SAM3 map coordinate system.")
        if extent is not None:
            self.viewer.set_view_extent(extent)

    def _detach_result(self):
        if self.overlay:
            extent = self.viewer.get_view_extent()
            super()._detach_result()
            self._restore_map_crs(extent)

    def _viewer_event(self, event):
        super()._viewer_event(event)
        if event.event_type == ViewerEventType.MAP_MOUSE_DOWN and event.int_value2 == 1 and hasattr(self, "map_bridge"):
            self.map_bridge.clicked.emit(event.extent.x_min, event.extent.y_min)

    def select_point(self, x, y):
        if self.busy or self.closing or self.result is not None or self.mode.currentIndex() == 0:
            return
        tool = self.tool.currentIndex()
        if tool in (1, 2):
            if len(self.points) + (2 if self.box else 0) >= 64:
                self.selection.setText("Prompt limit reached; clear prompts first.")
                return
            self.points.append(dict(x=x, y=y, positive=tool == 1))
        elif tool == 3:
            if len(self.points) > 62:
                self.selection.setText("A box needs two prompt tokens; clear points first.")
                return
            if self.corner is None:
                self.corner = (x, y)
                self.box = None
            else:
                a, b = self.corner
                self.corner = None
                if a == x or b == y:
                    self.selection.setText("Choose two different box corners.")
                    return
                self.box = [min(a, x), min(b, y), max(a, x), max(b, y)]
        else:
            return
        self._draw_prompts()

    def clear_prompts(self):
        if self.busy or self.result is not None:
            return
        self.points.clear()
        self.box = self.corner = None
        self._draw_prompts()

    def _draw_prompts(self):
        extent = self.viewer.get_view_extent()
        for name in self.prompt_layers:
            self.viewer.remove_layer_by_name(name)
        self.prompt_layers.clear()
        self._restore_map_crs(extent)
        def point(x, y, color):
            name = f"SAM3 prompt {len(self.prompt_layers)}"
            index = self.viewer.add_point_layer(name, [(x, y)], dict(pointColor=color, pointSize=10))
            self.viewer.set_layer_coordinate_system_preset(index, "wgs84")
            self.prompt_layers.append(name)
        for p in self.points:
            point(p['x'], p['y'], "#20df80" if p['positive'] else "#ff4848")
        if self.corner:
            point(*self.corner, "#ffe45a")
        if self.box:
            a, b, c, d = self.box
            name = "SAM3 prompt box"
            index = self.viewer.add_polygon_layer(name, [[(a,b),(c,b),(c,d),(a,d),(a,b)]],
                dict(fillColor="#ffe45a", fillOpacity=24, lineColor="#ffe45a", lineWidth=2))
            self.viewer.set_layer_coordinate_system_preset(index, "wgs84")
            self.prompt_layers.append(name)
        self.viewer.refresh_layers()
        self.selection.setText(f"{len(self.points)} points · " + ("box set" if self.box else "choose second corner" if self.corner else "no box"))

    def run(self):
        if self.busy or self.result is not None:
            return
        text_mode = self.mode.currentIndex() == 0
        text = self.text.text().strip()
        if text_mode and not text:
            self.details.setPlainText("Enter a concept, for example building.")
            return
        if not text_mode and not self.box and not any(p['positive'] for p in self.points):
            self.details.setPlainText("Add a positive point or a box around one object.")
            return
        name = "text" if text_mode else "tracker"
        points, box = [dict(p) for p in self.points], list(self.box) if self.box else None
        provider, score = self.provider.currentText().lower(), self.threshold.value()
        self.cancel_event.clear()
        self.accepted = False
        raster = self.raster
        def start():
            prepared = None if raster else self._input()
            source = raster or prepared.raster
            manifest = prepare_asset(ROOT + f"meta-sam3-{name}-fp32-geokernel-onnx-v1.zip", HASHES[name],
                "sam3-package.json", self.cancel_event, lambda p,m: self.messages.put((p,m)))
            request = dict(task="sam3-"+name, modelPackagePath=str(manifest.parent), rasterPath=str(source),
                           provider=provider, intraOpThreads=4, maximumMilliseconds=1800000)
            if text_mode:
                request.update(text=text, scoreThreshold=score)
            else:
                from sam3_coordinates import to_source
                converted, converted_box = to_source(source, points, box)
                request.update(coordinateSpace="source-crs", points=converted)
                if converted_box:
                    request['box'] = converted_box
            check_cancel(self.cancel_event)
            return prepared, self.tasks.start(request)
        def started(value):
            prepared, self.job = value
            if prepared:
                self._show_source(prepared)
            self.running = self.busy = True
            self._progress(0, "Loading SAM3 model…")
        self._submit("start", start, started)

    def _completed(self):
        from geoai_vector import prepare_vector_preview
        result = self.job.result()
        self.running = False
        self._progress(95, "Preparing draft polygon display…")

        def prepare():
            preview = prepare_vector_preview(Path(result['vectorPath']), self.cancel_event)
            return result, preview

        self._submit("preview", prepare, lambda value: self._show_draft(*value))

    def _show_draft(self, result, preview):
        check_cancel(self.cancel_event)
        self.viewer.add_layer(preview)
        self.overlay = True
        self.apply_opacity(self.opacity.value())
        self.result = result
        self.running = self.busy = False
        self.accepted = False
        self.details.setPlainText(f"{self.result['instances']} draft instances\nProvider: {self.result['provider']}\n"
            "Review the map, then Accept or Discard.\nPoint/box selects one object; a box is not an area scan for all buildings.")
        self._progress(100, "Draft ready. Review, then Accept or Discard.")

    def apply_opacity(self, value):
        self.opacity_label.setText(f"Output transparency: {100 - value}%")
        if self.overlay:
            from geoai_vector import apply_vector_opacity
            apply_vector_opacity(self.viewer, 0, value, fill_color="#ff963f", fill_alpha=120,
                                 line_rgb="ffd65a", line_width=1.1)

    def accept_draft(self):
        if self.result is not None and not self.busy:
            self.accepted = True
            self._progress(100, "Draft accepted. Save explicitly to retain it.")
            self._controls()

    def discard(self):
        if self.busy or self.result is None:
            return
        self._detach_result()
        old, self.job = self.job, None
        self.result = None
        self.accepted = False
        self._submit("cleanup", lambda: self._release(old), lambda _: self._progress(0, "Draft discarded."))

    def save(self):
        self.save_format("shapefile")

    def save_format(self, format):
        if not self.accepted or self.busy or self.result is None:
            return
        extension = "shp" if format == "shapefile" else "tif"
        path, _ = QFileDialog.getSaveFileName(self, "Save accepted result", "sam3-instances."+extension,
            f"Result (*.{extension})")
        if path:
            self._submit("export", lambda: self.job.export(path, format), lambda _: self._progress(100, "Accepted result saved."))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        window = Window(app)
        window.show()
        app.processEvents()
        window.viewer.show()
    except Exception as error:
        QMessageBox.critical(None, PROFILE.title, str(error))
        sys.exit(1)
    sys.exit(app.exec())
