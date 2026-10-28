"""SEN2SR scientific RGB+NIR super-resolution with session-only comparison previews."""
from dataclasses import replace
from pathlib import Path
import sys

from geoai_support import PRUE, PreparedRaster, asset_cache, prepare_asset
from geoai_window import QApplication, QFileDialog, GeoAiWindow, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QDockWidget, QWidget, QHBoxLayout, QVBoxLayout


PROFILE = replace(
    PRUE, task="sen2sr-super-resolution", title="ESAOpenSR SEN2SRLite — super resolution",
    run_label="Run 4× super resolution",
    model_url="https://pub-00d214f25f754884b22349c19ac37bbf.r2.dev/geokernel-models/esaopensr-sen2srlite-rgbn-x4-geokernel-onnx-v1.zip",
    model_sha="bcad3673c73429fddc6f6277fff823b01bdc77a268aee8b09540566d510d1017",
    description="Sentinel-2 RGB + NIR · 578 × 379 input\nClick Run to generate a 4× result. No predictions are loaded at startup.",
    legend="RGB comparison · scientific output retains all four bands",
    credits="Model: ESAOpenSR / SEN2SRLite; CC0-1.0 and inherited Apache-2.0 notices.\nImagery: Sentinel-2 / FTW sample; retain source notices.",
    export_name="sen2sr-reflectance.tif",
)


class Window(GeoAiWindow):
    def __init__(self, app):
        self.source_display = None
        super().__init__(app, PROFILE)
        self.save_button.setText("Save GeoTIFF")
        self.opacity.setValue(100)
        hint = QLabel("Zoom in to compare detail. Left: original; right: enhanced.")
        hint.setWordWrap(True)
        controls = self.opacity.parentWidget().layout()
        controls.insertWidget(controls.indexOf(self.opacity) + 1, hint)
        self.apply_opacity(self.opacity.value())
        self.comparison = QDockWidget("4× detail comparison — same area, same contrast", self)
        panel = QWidget()
        row = QHBoxLayout(panel)
        self.original_detail, self.enhanced_detail = QLabel(), QLabel()
        for title, image in (("Original — enlarged 4× for display", self.original_detail),
                             ("SEN2SR — actual 4× output", self.enhanced_detail)):
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setMinimumSize(320, 320)
            column.addWidget(image)
            row.addLayout(column)
        self.comparison.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.comparison)
        self.comparison.hide()
        self.menuBar().addMenu("View").addAction(self.comparison.toggleViewAction())

    def _controls(self):
        super()._controls()
        self.opacity.setEnabled(self.overlay and not self.busy and not self.closing)
        if hasattr(self, "comparison"):
            self.comparison.toggleViewAction().setEnabled(self.result is not None and not self.busy)

    def _input(self):
        from geoai_raster import prepare_super_resolution_rgb
        raster = prepare_asset(self.profile.data_url, self.profile.data_sha, self.profile.raster_name,
                               self.cancel_event, lambda p, m: self.messages.put((p, m)), archive=False)
        self.messages.put((0, "Preparing RGB source display…"))
        display = prepare_super_resolution_rgb(raster, asset_cache(self.profile.data_sha), self.cancel_event)
        return PreparedRaster(raster, display)

    def _show_source(self, prepared):
        self.source_display = prepared.display
        super()._show_source(prepared)

    def _detach_result(self):
        if not self.overlay:
            return
        # A completed SR job owns both comparison images. Detach both before releasing its workspace.
        extent = self.viewer.get_view_extent()
        self.comparison.hide()
        self.original_detail.clear()
        self.enhanced_detail.clear()
        self.viewer.clear_layers()
        self.overlay = False
        if self.source_display is not None:
            self.viewer.add_layer(self.source_display)
            self.viewer.set_layer_name(0, "RGB source")
            if extent is not None:
                self.viewer.set_view_extent(extent)
        self.apply_opacity(self.opacity.value())

    def apply_opacity(self, value):
        self.opacity_label.setText(
            "Original image - run 4× super resolution" if not self.overlay
            else "Original image" if value == 0
            else "Enhanced image (100%)" if value == 100
            else f"Original / enhanced blend: {value}% enhanced"
        )
        if self.overlay:
            self.viewer.set_layer_opacity(0, value / 100)
            self.viewer.refresh_layers()

    def _completed(self):
        result = self.job.result()
        self.running = False
        self._progress(95, "Preparing original / enhanced detail comparison…")

        def prepare():
            from sen2sr_comparison import read_detail
            return read_detail(Path(result["sourcePreviewPath"]), Path(result["previewPath"]), self.cancel_event)

        self._submit("comparison", prepare, lambda detail: self._show_result(result, detail))

    def _show_result(self, result, detail):
        from geoai_support import check_cancel
        check_cancel(self.cancel_event)
        # Native comparison images use one shared contrast stretch for a meaningful comparison.
        extent = self.viewer.get_view_extent()
        self.viewer.clear_layers()
        self.viewer.add_layer(result["sourcePreviewPath"])
        self.viewer.set_layer_name(0, "Source — shared contrast")
        self.viewer.add_layer(result["previewPath"])
        self.viewer.set_layer_name(0, "4× enhanced — shared contrast")
        if extent is not None:
            self.viewer.set_view_extent(extent)
        else:
            self.viewer.full_extent()
        self.overlay = True
        self.apply_opacity(self.opacity.value())
        self.result = result
        self.running = self.busy = False
        for key, label, edge in (("source", self.original_detail, detail["source_size"]),
                                 ("enhanced", self.enhanced_detail, detail["enhanced_size"])):
            image = QImage(detail[key], edge, edge, edge * 3, QImage.Format.Format_RGB888).copy()
            image = image.scaled(detail["enhanced_size"], detail["enhanced_size"],
                                 Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            label.setPixmap(QPixmap.fromImage(image))
        self.comparison.show()
        self.details.setPlainText(
            f"{self.profile.title}\nProvider: {result['provider']}\n"
            f"Source: {result['sourceWidth']} × {result['sourceHeight']}\n"
            f"Output: {result['width']} × {result['height']} · 4 bands · Float32\n"
            f"Elapsed: {result['elapsedMilliseconds']} ms\n\n"
            "The detail panel shows the same center area: original on the left, 4× output on the right.\n"
            "Save GeoTIFF retains RGB + NIR, source footprint and AI provenance.\n"
            "Estimated detail on a finer grid, not new sensor measurements."
        )
        self._progress(100, "Super resolution complete.")

    def save(self):
        if self.job is None or self.busy or self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save enhanced reflectance", self.profile.export_name,
                                             "GeoTIFF (*.tif)")
        if path:
            self._submit("export", lambda: self.job.export(path, "geotiff"),
                         lambda _: self._progress(100, "Four-band GeoTIFF saved."))


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
