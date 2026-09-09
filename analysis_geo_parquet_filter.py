from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QHBoxLayout, QLabel, QMainWindow,
    QProgressBar, QPushButton, QSpinBox, QTextEdit, QToolBar, QVBoxLayout, QWidget,
)
from geokernel import (
    AnalysisBackend, AnalysisDataKind, AnalysisExecutor, AnalysisOperation,
    Viewer, ViewerTool,
)
from common import application_icon, ensure_sample_file


DATA_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/stockholm_data.zip"


def attempts_text(value: dict) -> str:
    plan = value["plan"]
    lines = [
        "ANALYSIS PLAN",
        "Requested backend: Auto",
        f"Selected backend: {value['backend']}",
        f"Predicate pushdown: {'yes' if plan['usesPredicatePushdown'] else 'no'}",
        f"Projection pushdown: {'yes' if plan['usesProjectionPushdown'] else 'no'}",
        "", plan["explanation"], "", "EXECUTION ATTEMPTS",
    ]
    for attempt in value["attempts"]:
        state = "success" if attempt["succeeded"] else "failed"
        suffix = f" — {attempt['message']}" if attempt.get("message") else ""
        lines.append(f"{attempt['backend']}: {state} ({attempt['elapsedMilliseconds']} ms){suffix}")
    return "\n".join(lines)


class Window(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.parquet_path: Path | None = None
        self.executor = AnalysisExecutor()
        self.job = None
        self.layer = None
        self.closing = False
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)

        self.setWindowTitle("AnalysisGeoParquetFilter")
        self.setWindowIcon(application_icon())
        self.resize(1220, 790)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.viewer.qt_widget(), 1)

        controls = QWidget()
        controls.setFixedWidth(340)
        panel = QVBoxLayout(controls)
        title = QLabel("Backend-neutral analysis")
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        panel.addWidget(title)

        form = QFormLayout()
        self.class_box = QComboBox()
        self.class_box.addItems(["apartments", "house", "commercial", "industrial"])
        self.limit_box = QSpinBox()
        self.limit_box.setRange(1, 100000)
        self.limit_box.setValue(25000)
        form.addRow("Building class", self.class_box)
        form.addRow("Maximum results", self.limit_box)
        form.addRow("BBOX", QLabel("18.04, 59.30, 18.10, 59.35"))
        panel.addLayout(form)

        buttons = QHBoxLayout()
        self.run_button = QPushButton("Run automatic analysis")
        self.run_button.setEnabled(False)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        buttons.addWidget(self.run_button, 1)
        buttons.addWidget(self.cancel_button)
        panel.addLayout(buttons)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        panel.addWidget(self.progress)
        self.stage = QLabel("Ready.")
        self.stage.setWordWrap(True)
        panel.addWidget(self.stage)
        self.diagnostics = QTextEdit()
        self.diagnostics.setReadOnly(True)
        panel.addWidget(self.diagnostics, 1)
        root.addWidget(controls)
        self.setCentralWidget(central)

        self.add_navigation()
        self.run_button.clicked.connect(self.begin_analysis)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        self.poll = QTimer(self)
        self.poll.setInterval(40)
        self.poll.timeout.connect(self.poll_job)
        self.statusBar().showMessage("Loading sample data...")
        QTimer.singleShot(0, self.prepare_data)

    def add_navigation(self) -> None:
        icons = Path(__file__).resolve().parent / "images"
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)
        for icon, text, callback in [
            ("ZoomIn.png", "Zoom In", self.viewer.zoom_in),
            ("ZoomOut.png", "Zoom Out", self.viewer.zoom_out),
            ("FullExtent.png", "Full Extent", self.viewer.full_extent),
        ]:
            action = QAction(QIcon(str(icons / icon)), text, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)
        toolbar.addSeparator()
        group = QActionGroup(toolbar)
        group.setExclusive(True)
        for icon, text, tool in [
            ("RectangularZoom.png", "Zoom Box", ViewerTool.ZOOM_BOX),
            ("Pan.png", "Pan", ViewerTool.PAN),
        ]:
            action = QAction(QIcon(str(icons / icon)), text, self)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=tool: self.viewer.set_tool(value))
            toolbar.addAction(action)
            group.addAction(action)
            if tool == ViewerTool.PAN:
                action.setChecked(True)

    def prepare_data(self) -> None:
        try:
            self.parquet_path = ensure_sample_file(
                self.app, DATA_URL, "stockholm_data.zip", ".",
                "stockholm_data/stockholm_buildings.parquet", "AnalysisGeoParquetFilter",
            )
            if not self.parquet_path:
                self.stage.setText("Sample data is unavailable.")
                return
            self.run_button.setEnabled(True)
            self.begin_analysis()
        except Exception as error:
            self.stage.setText(f"Sample data could not be loaded: {error}")
            self.statusBar().showMessage("Sample data could not be loaded.")

    def request(self) -> dict:
        return {
            "operation": AnalysisOperation.SPATIAL_FILTER,
            "backend": AnalysisBackend.AUTO,
            "inputKind": AnalysisDataKind.GEOPARQUET,
            "source": str(self.parquet_path),
            "hasAttributeFilter": True,
            "hasSpatialFilter": True,
            "projectionRequired": True,
            "options": {
                "columns": ["id", "class", "geometry"],
                "predicateSql": "class = ?",
                "predicateParameters": [self.class_box.currentText()],
                "extent": [18.04, 59.30, 18.10, 59.35],
                "limit": self.limit_box.value(),
            },
        }

    def begin_analysis(self) -> None:
        if self.parquet_path is None or self.job is not None and not self.job.is_finished:
            return
        if self.job is not None:
            self.job.close()
        if self.layer is not None:
            self.layer.close()
            self.layer = None
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        self.diagnostics.clear()
        self.stage.setText("Queuing analysis...")
        self.statusBar().showMessage("Analysis queued...")
        self.job = self.executor.execute_async(self.request())
        self.poll.start()

    def cancel_analysis(self) -> None:
        if self.job is not None and not self.job.is_finished:
            self.job.cancel()

    def poll_job(self) -> None:
        if self.closing or self.job is None:
            return
        state = self.job.progress
        self.progress.setValue(max(0, min(100, int(state.get("percent", 0)))))
        self.stage.setText(f"{state.get('stage', 'Running')} — {state.get('message', '')}")
        self.statusBar().showMessage(state.get("message", ""))
        if not self.job.is_finished:
            return
        self.poll.stop()
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        with self.job.wait() as result:
            value = result.value
            if value["cancelled"]:
                self.stage.setText("Analysis cancelled.")
                return
            self.diagnostics.setPlainText(attempts_text(value))
            if not value["succeeded"]:
                self.stage.setText(value["message"])
                return
            self.layer = result.materialize({
                "name": f"Filtered {self.class_box.currentText()} buildings",
                "skipInvalidGeometries": True,
            })

        self.viewer.clear_layers()
        self.layer.add_to(self.viewer)
        self.viewer.set_layer_style(self.viewer.layer_count() - 1, {
            "fillColor": "#55B7E9", "lineColor": "#116A9B", "lineWidth": 0.8,
        })
        self.viewer.full_extent()
        materialized = self.layer.diagnostics
        self.diagnostics.append(
            "\nMATERIALIZATION\n"
            f"Source rows: {materialized.get('sourceRowCount', 0)}\n"
            f"Layer features: {materialized.get('materializedCount', 0)}\n"
            f"Skipped: {materialized.get('skippedCount', 0)}"
        )
        self.progress.setValue(100)
        self.stage.setText(
            f"{materialized.get('materializedCount', 0)} selected and displayed with {value['backend']}."
        )
        self.statusBar().showMessage("Analysis completed successfully.")

    def closeEvent(self, event) -> None:
        self.closing = True
        self.poll.stop()
        try:
            if self.job is not None and not self.job.is_finished:
                self.job.cancel()
        except Exception:
            pass
        if self.layer is not None:
            self.layer.close()
        if self.job is not None:
            self.job.close()
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = Window(app)
    window.show()
    app.processEvents()
    window.viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
