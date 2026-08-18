from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSpinBox, QTextEdit, QToolBar, QVBoxLayout, QWidget,
)
from geokernel import DuckConnection, DuckGeoParquet, DuckGeoParquetQuery, Extent, Viewer, ViewerTool
from common import application_icon, ensure_sample_file

DATA_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/stockholm_data.zip"
X_MIN, Y_MIN, X_MAX, Y_MAX = 18.04, 59.30, 18.10, 59.35


@dataclass
class Metrics:
    elapsed_ms: int
    source_rows: int
    result_rows: int
    payload_bytes: int
    columns: int


@dataclass
class Result:
    baseline: Metrics
    optimized: Metrics
    dataset_rows: int
    class_name: str
    geometries: list[bytes]


def payload_size(result) -> int:
    return sum(len(value) if isinstance(value, bytes) else len(str(value).encode()) if value is not None else 0 for row in result.rows for value in row)


def compare(path: Path, class_name: str, limit: int) -> Result:
    with DuckConnection() as connection:
        metadata = DuckGeoParquet.inspect(connection, path)
        connection.query("SELECT count(*) FROM read_parquet(?)", [str(path)])
        started = time.perf_counter()
        all_rows = connection.query(
            "SELECT id,class,geometry,bbox.xmin AS xmin,bbox.ymin AS ymin,bbox.xmax AS xmax,bbox.ymax AS ymax FROM read_parquet(?)",
            [str(path)],
        )
        matched = 0
        for row in range(all_rows.row_count):
            if matched >= limit:
                break
            if (all_rows.value(row, "class") == class_name and
                float(all_rows.value(row, "xmax")) >= X_MIN and float(all_rows.value(row, "xmin")) <= X_MAX and
                float(all_rows.value(row, "ymax")) >= Y_MIN and float(all_rows.value(row, "ymin")) <= Y_MAX):
                matched += 1
        baseline = Metrics(round((time.perf_counter() - started) * 1000), all_rows.row_count, matched, payload_size(all_rows), all_rows.column_count)

        started = time.perf_counter()
        filtered = DuckGeoParquet.query(connection, path, DuckGeoParquetQuery(
            columns=["id", "class", metadata.primary_geometry_column],
            extent=Extent(X_MIN, Y_MIN, X_MAX, Y_MAX),
            predicate_sql="class = ?", predicate_parameters=[class_name], limit=limit,
        ))
        geometries = [filtered.value(row, metadata.primary_geometry_column) for row in range(filtered.row_count) if filtered.value(row, metadata.primary_geometry_column)]
        optimized = Metrics(round((time.perf_counter() - started) * 1000), filtered.row_count, len(geometries), payload_size(filtered), filtered.column_count)
        return Result(baseline, optimized, metadata.feature_count, class_name, geometries)


def human_bytes(value: int) -> str:
    return f"{value / 1024 / 1024:.2f} MiB" if value >= 1024 * 1024 else f"{value / 1024:.1f} KiB"


def report_text(result: Result, materialization_ms: int) -> str:
    elapsed = result.optimized.elapsed_ms + materialization_ms
    speedup = result.baseline.elapsed_ms / elapsed if elapsed else 0
    reduction = lambda before, after: 100 * (1 - after / before) if before else 0
    return "\n".join([
        "DUCKDB GEOPARQUET ANALYTICS", "", "Dataset: stockholm_buildings.parquet",
        f"Dataset rows: {result.dataset_rows}", f"Filter: class = '{result.class_name}'",
        f"BBOX: {X_MIN}, {Y_MIN}, {X_MAX}, {Y_MAX}", f"Result rows: {result.optimized.result_rows}", "",
        "FULL TRANSFER + APPLICATION FILTER", f"Rows transferred: {result.baseline.source_rows}",
        f"Columns transferred: {result.baseline.columns}", f"Payload approximation: {human_bytes(result.baseline.payload_bytes)}",
        f"Elapsed: {result.baseline.elapsed_ms} ms", "", "DUCKDB PUSHDOWN",
        f"Rows transferred: {result.optimized.source_rows}", f"Columns transferred: {result.optimized.columns}",
        f"Payload approximation: {human_bytes(result.optimized.payload_bytes)}", f"Elapsed + Viewer materialization: {elapsed} ms", "",
        "MEASURED GAIN", f"Speedup: {speedup:.2f}x",
        f"Row transfer reduction: {reduction(result.baseline.source_rows, result.optimized.source_rows):.2f}%",
        f"Payload reduction: {reduction(result.baseline.payload_bytes, result.optimized.payload_bytes):.2f}%", "",
        "The optimized path pushes class, BBOX, projection and limit into DuckDB before WKB crosses into the Viewer.",
    ])


class Window(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.parquet_path: Path | None = None
        self.icon_dir = Path(__file__).resolve().parent / "images"
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.viewer = Viewer()
        self.setWindowTitle("DuckDbGeoParquetAnalytics")
        self.setWindowIcon(application_icon())
        self.resize(1220, 790)
        self.viewer.set_tool(ViewerTool.PAN)

        central = QWidget(); layout = QHBoxLayout(central); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        layout.addWidget(self.viewer.qt_widget(), 1)
        controls = QWidget(); controls.setFixedWidth(390); panel = QVBoxLayout(controls)
        title = QLabel("DuckDB GeoParquet analytics"); font = title.font(); font.setBold(True); font.setPointSize(font.pointSize() + 1); title.setFont(font); panel.addWidget(title)
        form = QFormLayout(); self.class_box = QComboBox(); self.class_box.setEditable(True); self.class_box.addItems(["apartments", "residential", "house"])
        self.limit_box = QSpinBox(); self.limit_box.setRange(1, 100000); self.limit_box.setValue(25000); self.limit_box.setSingleStep(5000)
        form.addRow("Building class", self.class_box); form.addRow("Maximum results", self.limit_box); form.addRow("Spatial filter", QLabel("Central Stockholm BBOX")); panel.addLayout(form)
        self.run_button = QPushButton("Run measured comparison"); self.run_button.setEnabled(False); self.run_button.clicked.connect(self.run); panel.addWidget(self.run_button)
        self.report = QTextEdit(); self.report.setReadOnly(True); self.report.setPlainText("Press Run measured comparison.\n\nThe baseline transfers every row and filters in the application. The optimized path pushes predicate, BBOX, projection and limit into DuckDB."); panel.addWidget(self.report, 1)
        layout.addWidget(controls); self.setCentralWidget(central); self.statusBar().showMessage("Loading sample data...")
        self.add_navigation(); self.poll = QTimer(self); self.poll.timeout.connect(self.check_result); self.poll.start(50)
        QTimer.singleShot(0, self.load_sample)

    def load_sample(self):
        try:
            self.parquet_path = ensure_sample_file(self.app, DATA_URL, "stockholm_data.zip", ".", "stockholm_data/stockholm_buildings.parquet", "DuckDbGeoParquetAnalytics")
            if not self.parquet_path:
                self.statusBar().showMessage("Sample data was not loaded.")
                return
            self.run_button.setEnabled(True)
            self.statusBar().showMessage(f"Ready: {self.parquet_path.name}")
        except Exception as error:
            self.report.setPlainText(f"Sample data could not be loaded:\n{error}")
            self.statusBar().showMessage("Sample data could not be loaded.")

    def add_navigation(self):
        toolbar = QToolBar("Navigation", self); toolbar.setMovable(False); toolbar.setIconSize(QSize(32, 32)); self.addToolBar(toolbar)
        for icon, text, callback in [("ZoomIn.svg", "Zoom In", self.viewer.zoom_in), ("ZoomOut.svg", "Zoom Out", self.viewer.zoom_out), ("FullExtent.svg", "Full Extent", self.viewer.full_extent)]:
            action = QAction(QIcon(str(self.icon_dir / icon.replace(".svg", ".png"))), text, self); action.triggered.connect(callback); toolbar.addAction(action)
        toolbar.addSeparator(); group = QActionGroup(toolbar); group.setExclusive(True)
        for icon, text, tool in [("RectangularZoom.svg", "Zoom Box", ViewerTool.ZOOM_BOX), ("Pan.svg", "Pan", ViewerTool.PAN)]:
            action = QAction(QIcon(str(self.icon_dir / icon.replace(".svg", ".png"))), text, self); action.setCheckable(True); action.triggered.connect(lambda _checked=False, value=tool: self.viewer.set_tool(value)); toolbar.addAction(action); group.addAction(action)
            if tool == ViewerTool.PAN: action.setChecked(True)

    def run(self):
        if self.parquet_path is None or self.future and not self.future.done(): return
        self.run_button.setEnabled(False); self.report.setPlainText("Running full transfer and DuckDB pushdown paths..."); self.statusBar().showMessage("Benchmark running in background...")
        self.future = self.executor.submit(compare, self.parquet_path, self.class_box.currentText().strip(), self.limit_box.value())

    def check_result(self):
        if not self.future or not self.future.done(): return
        future, self.future = self.future, None
        try:
            result = future.result(); started = time.perf_counter(); rings = []
            for wkb in result.geometries:
                geometry = self.viewer.read_wkb_geometry(wkb)
                rings.extend([[(float(p["x"]), float(p["y"])) for p in part] for part in geometry.get("parts", []) if part])
            self.viewer.clear_layers(); self.viewer.add_polygon_layer("DuckDB pushdown result", rings, {"fillColor": "#65B8E8", "lineColor": "#176B9C", "lineWidth": 0.8})
            self.viewer.full_extent(); materialization = round((time.perf_counter() - started) * 1000)
            self.report.setPlainText(report_text(result, materialization)); self.statusBar().showMessage("Comparison completed.")
        except Exception as error:
            self.report.setPlainText(f"Comparison failed:\n{error}"); self.statusBar().showMessage("Comparison failed.")
        self.run_button.setEnabled(True)

    def closeEvent(self, event):
        self.poll.stop(); self.executor.shutdown(wait=False, cancel_futures=True)
        try: self.viewer.close()
        except Exception: pass
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = Window(app); window.show(); app.processEvents(); window.viewer.show(); sys.exit(app.exec())


if __name__ == "__main__":
    main()
