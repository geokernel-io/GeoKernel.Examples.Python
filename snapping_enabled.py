import sys
from pathlib import Path
from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QToolBar,
)
from geokernel import Extent, ShapeType, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

EXTENT = Extent(-132.0, 18.0, -60.0, 55.0)


class SnappingEnabledWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.ADD_POLYLINE)
        self.viewer.set_edit_snapping_enabled(True)
        self.viewer.set_edit_snapping_tolerance_pixels(14.0)
        self.widget = self.viewer.qt_widget()
        self.layer = -1
        self.initialized = False
        self.setWindowTitle("SnappingEnabled")
        self.setWindowIcon(application_icon())
        self.resize(1200, 800)
        self.setCentralWidget(self.widget)
        self.create_toolbar()

    def create_toolbar(self) -> None:
        bar = QToolBar("Snapping", self)
        bar.setMovable(False)
        bar.setIconSize(QSize(32, 32))
        self.addToolBar(bar)
        self.add_action = self.make("Polyline.png", "Add Polyline", self.activate_add)
        self.snap_action = self.make(
            "Snapping.png", "Snapping", self.toggle_snapping, True
        )
        self.snap_action.setChecked(True)
        bar.addAction(self.add_action)
        bar.addAction(self.snap_action)
        bar.addWidget(QLabel("Tolerance:", bar))
        self.tolerance = QSpinBox(bar)
        self.tolerance.setRange(1, 60)
        self.tolerance.setValue(14)
        self.tolerance.setSuffix(" px")
        self.tolerance.valueChanged.connect(self.change_tolerance)
        bar.addWidget(self.tolerance)
        self.reset_action = self.make("Refresh.png", "Reset Guide", self.reset)
        self.extent_action = self.make(
            "FullExtent.png", "Full Extent", self.viewer.full_extent
        )
        bar.addAction(self.reset_action)
        bar.addAction(self.extent_action)
        self.actions = (
            self.add_action,
            self.snap_action,
            self.reset_action,
            self.extent_action,
        )
        for action in self.actions:
            action.setEnabled(False)

    def make(self, icon, text, slot, check=False) -> QAction:
        action = QAction(QIcon(str(self.icons / icon)), text, self)
        action.setCheckable(check)
        action.triggered.connect(slot)
        return action

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.widget.width(), self.widget.height())
        self.viewer.show()
        try:
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="SnappingEnabled",
            )
            self.viewer.add_layer(str(path))
            self.viewer.set_layer_style(
                0, {"fillColor": "#D8E5E1", "fillOpacity": 130, "lineColor": "#6F8883"}
            )
            self.layer = self.viewer.add_empty_vector_layer(
                "Snapping Lines",
                ShapeType.POLYLINE,
                {"lineColor": "#D95D39", "lineWidth": 2.6},
            )
            self.reset()
            for action in self.actions:
                action.setEnabled(True)
            self.viewer.set_view_extent(EXTENT)
            self.statusBar().showMessage(
                "Draw near the guide line. Toggle snapping and tolerance to compare."
            )
        except Exception as error:
            QMessageBox.critical(self, "SnappingEnabled", str(error))

    def begin_edit(self) -> bool:
        if self.layer < 0:
            return False
        if not self.viewer.is_layer_editing(self.layer) and (
            not self.viewer.begin_edit_layer(self.layer)
        ):
            return False
        return self.viewer.set_active_edit_layer_index(self.layer)

    def reset(self) -> None:
        if self.layer < 0:
            return
        if self.viewer.is_layer_editing(self.layer):
            self.viewer.rollback_edit_layer(self.layer)
        if not self.begin_edit():
            return
        self.viewer.add_polyline_to_edit_layer(
            self.layer,
            [(-124, 30), (-113, 38), (-101, 32), (-89, 41), (-75, 34)],
            {"Name": "Snap guide"},
        )
        self.viewer.set_tool(ViewerTool.ADD_POLYLINE)
        self.refresh()
        self.statusBar().showMessage("Guide line reset. Draw near it to test snapping.")

    def activate_add(self) -> None:
        self.begin_edit()
        self.viewer.set_tool(ViewerTool.ADD_POLYLINE)
        self.statusBar().showMessage(
            "Add Polyline active. Click vertices, then Enter or double-click."
        )

    def toggle_snapping(self, enabled: bool) -> None:
        self.viewer.set_edit_snapping_enabled(enabled)
        self.statusBar().showMessage(
            "Snapping enabled." if enabled else "Snapping disabled."
        )

    def change_tolerance(self, value: int) -> None:
        self.viewer.set_edit_snapping_tolerance_pixels(float(value))
        self.statusBar().showMessage(f"editSnappingTolerancePixels = {value}")

    def refresh(self) -> None:
        self.viewer.invalidate_render_cache(False, True)
        self.viewer.refresh_layers()

    def closeEvent(self, event) -> None:
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SnappingEnabled")
    app.setWindowIcon(application_icon())
    window = SnappingEnabledWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
