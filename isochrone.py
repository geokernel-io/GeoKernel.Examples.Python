import heapq
import math
import sys
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox, QPushButton, QToolBar, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Point, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file


MAX_SNAP_DISTANCE = 2000.0
TRANSFORMER = CoordinateSystemFactory()
BAND_COLORS = (QColor("#16A34A"), QColor("#F59E0B"), QColor("#DC2626"))


@dataclass(frozen=True)
class IsochroneBand:
    lines: tuple[tuple[Point, ...], ...]
    cumulative_nodes: int
    edge_count: int


@dataclass(frozen=True)
class IsochroneResult:
    origin: Point
    snap_distance: float
    bands: tuple[IsochroneBand, ...]


class RoutingEngine:
    def __init__(self, snapshot: Any) -> None:
        self.nodes = {
            node.id: Point(node.position.x, node.position.y)
            for node in snapshot.nodes
        }
        self.out_edges: dict[int, list[tuple[int, float]]] = {}
        self.edge_records: list[tuple[int, int, tuple[int, int]]] = []
        self.world_geometry: dict[tuple[int, int], tuple[Point, ...]] = {}
        for edge in snapshot.edges:
            speed = edge.speed_kmh if edge.speed_kmh > 0.0 else 50.0
            travel_time = edge.distance / (speed * 1000.0 / 3600.0)
            self.out_edges.setdefault(edge.from_id, []).append((edge.to_id, travel_time))
            key = (min(edge.from_id, edge.to_id), max(edge.from_id, edge.to_id))
            self.edge_records.append((edge.from_id, edge.to_id, key))
            if key not in self.world_geometry and len(edge.geometry) >= 2:
                self.world_geometry[key] = tuple(
                    self.to_web_mercator(point.x, point.y) for point in edge.geometry
                )

    def largest_component(self) -> set[int]:
        visited: set[int] = set()
        largest: set[int] = set()
        for seed in self.nodes:
            if seed in visited:
                continue
            component = {seed}
            queue = deque([seed])
            visited.add(seed)
            while queue:
                for neighbor_id, _travel_time in self.out_edges.get(queue.popleft(), ()):
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        component.add(neighbor_id)
                        queue.append(neighbor_id)
            if len(component) > len(largest):
                largest = component
        return largest

    def calculate(self, component: set[int], source: Point) -> IsochroneResult | None:
        origin = None
        snap_distance = MAX_SNAP_DISTANCE
        for node_id in component:
            position = self.nodes.get(node_id)
            if position is None:
                continue
            distance = self.geodesic_distance(source, position)
            if distance < snap_distance:
                origin, snap_distance = node_id, distance
        if origin is None:
            return None

        costs = {origin: 0.0}
        queue = [(0.0, origin)]
        while queue:
            cost, node_id = heapq.heappop(queue)
            if cost > costs.get(node_id, math.inf) or cost > 900.0:
                continue
            for neighbor_id, travel_time in self.out_edges.get(node_id, ()):
                candidate = cost + travel_time
                if candidate > 900.0 or candidate >= costs.get(neighbor_id, math.inf):
                    continue
                costs[neighbor_id] = candidate
                heapq.heappush(queue, (candidate, neighbor_id))

        lines: list[list[tuple[Point, ...]]] = [[], [], []]
        drawn: list[set[tuple[int, int]]] = [set(), set(), set()]
        edge_counts = [0, 0, 0]
        for from_id, to_id, key in self.edge_records:
            if from_id not in costs or to_id not in costs or key not in self.world_geometry:
                continue
            value = max(costs[from_id], costs[to_id])
            band = 0 if value <= 300.0 else 1 if value <= 600.0 else 2 if value <= 900.0 else -1
            if band < 0:
                continue
            edge_counts[band] += 1
            if key in drawn[band]:
                continue
            drawn[band].add(key)
            lines[band].append(self.world_geometry[key])

        limits = (300.0, 600.0, 900.0)
        bands = tuple(
            IsochroneBand(
                tuple(lines[index]),
                sum(1 for value in costs.values() if value <= limit),
                edge_counts[index],
            )
            for index, limit in enumerate(limits)
        )
        position = self.nodes[origin]
        return IsochroneResult(self.to_web_mercator(position.x, position.y), snap_distance, bands)

    @staticmethod
    def to_web_mercator(longitude: float, latitude: float) -> Point:
        limit = 20037508.342789244
        latitude = max(-85.05112878, min(85.05112878, latitude))
        x = longitude * limit / 180.0
        y = math.log(math.tan((90.0 + latitude) * math.pi / 360.0)) * limit / math.pi
        return Point(x, y)

    @staticmethod
    def geodesic_distance(first: Point, second: Point) -> float:
        latitude_1 = math.radians(first.y)
        latitude_2 = math.radians(second.y)
        delta_latitude = latitude_2 - latitude_1
        delta_longitude = math.radians(second.x - first.x)
        value = math.sin(delta_latitude / 2.0) ** 2 + math.cos(latitude_1) * math.cos(latitude_2) * math.sin(delta_longitude / 2.0) ** 2
        return 6371008.8 * 2.0 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value))


class IsochroneOverlay(QWidget):
    def __init__(self, viewer: Viewer, target: QWidget, owner: QWidget) -> None:
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.viewer, self.target, self.owner = viewer, target, owner
        self.result: IsochroneResult | None = None
        self.active_band = 0
        self.paths: list[QPainterPath | None] = [None, None, None]
        self.render_cache: QPixmap | None = None
        self.closing = False
        self.view_refresh_timer = QTimer(self)
        self.view_refresh_timer.setSingleShot(True)
        self.view_refresh_timer.setInterval(60)
        self.view_refresh_timer.timeout.connect(self.invalidate_paths)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        target.installEventFilter(self)
        owner.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self.closing and watched in (self.target, self.owner):
            if event.type() in (QEvent.Type.Move, QEvent.Type.Show, QEvent.Type.WindowStateChange):
                QTimer.singleShot(0, self.sync_geometry)
            elif event.type() == QEvent.Type.Resize:
                QTimer.singleShot(0, self.sync_and_invalidate)
        return False

    def sync_geometry(self) -> None:
        if self.closing:
            return
        if not self.owner.isVisible() or self.owner.isMinimized():
            self.hide()
            return
        origin = self.target.mapToGlobal(QPoint(0, 0))
        self.setGeometry(origin.x(), origin.y(), self.target.width(), self.target.height())
        if not self.isVisible():
            self.show()
        self.raise_()

    def sync_and_invalidate(self) -> None:
        self.sync_geometry()
        self.invalidate_paths()

    def schedule_view_refresh(self) -> None:
        self.view_refresh_timer.start()

    def shutdown(self) -> None:
        self.closing = True
        self.target.removeEventFilter(self)
        self.owner.removeEventFilter(self)
        self.hide()
        self.close()

    def set_result(self, result: IsochroneResult | None) -> None:
        self.result = result
        self.active_band = 0
        self.invalidate_paths()

    def set_active_band(self, band: int) -> None:
        self.active_band = band
        self.render_cache = None
        self.update()

    def invalidate_paths(self) -> None:
        self.paths = [None, None, None]
        self.render_cache = None
        self.update()

    def path_for(self, band: int) -> QPainterPath:
        cached = self.paths[band]
        if cached is not None:
            return cached
        path = QPainterPath()
        if self.result is not None:
            for line in self.result.bands[band].lines:
                first = True
                for world in line:
                    screen = self.viewer.world_to_screen(world.x, world.y)
                    if screen is None or not math.isfinite(screen.x) or not math.isfinite(screen.y):
                        continue
                    if first:
                        path.moveTo(QPointF(screen.x, screen.y))
                        first = False
                    else:
                        path.lineTo(QPointF(screen.x, screen.y))
        self.paths[band] = path
        return path

    def paintEvent(self, _event) -> None:
        if self.render_cache is None or self.render_cache.size() != self.size():
            self.render_cache = QPixmap(self.size())
            self.render_cache.fill(Qt.GlobalColor.transparent)
            cache_painter = QPainter(self.render_cache)
            cache_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self.draw_content(cache_painter)
            cache_painter.end()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.render_cache)

    def draw_content(self, painter: QPainter) -> None:
        if self.result is not None:
            for band in range(2, -1, -1):
                color = QColor(BAND_COLORS[band])
                color.setAlpha(250 if band == self.active_band else 135)
                pen = QPen(color, 4.5 if band == self.active_band else 2.5)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(self.path_for(band))
            screen = self.viewer.world_to_screen(self.result.origin.x, self.result.origin.y)
            if screen is not None and math.isfinite(screen.x) and math.isfinite(screen.y):
                painter.setPen(QPen(QColor("#14532D"), 2.0))
                painter.setBrush(QColor("#22C55E"))
                painter.drawEllipse(QPointF(screen.x, screen.y), 9.0, 9.0)


class IsochroneWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.overlay = IsochroneOverlay(self.viewer, self.viewer_widget, self)
        self.engine: RoutingEngine | None = None
        self.main_component: set[int] = set()
        self.result: IsochroneResult | None = None
        self.stockholm_extent = None
        self.initialized = False
        self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="isochrone")
        self.future: Future | None = None
        self.future_kind = ""
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(50)
        self.poll_timer.timeout.connect(self.poll_future)
        self.setWindowTitle("Isochrone")
        self.setWindowIcon(application_icon())
        self.resize(1200, 760)
        self.create_ui()

    def create_ui(self) -> None:
        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.viewer_widget, 1)
        panel = QWidget(central)
        panel.setFixedWidth(310)
        panel_layout = QVBoxLayout(panel)
        title = QLabel("Travel-time isochrone", panel)
        font = title.font(); font.setBold(True); title.setFont(font)
        self.summary = QLabel("Select an origin point.", panel)
        self.summary.setWordWrap(True)
        self.band_list = QListWidget(panel)
        self.band_list.currentRowChanged.connect(self.select_band)
        help_label = QLabel("Click a band to highlight it.\n\nGreen: 0–5 min\nOrange: 5–10 min\nRed: 10–15 min", panel)
        panel_layout.addWidget(title)
        panel_layout.addWidget(self.summary)
        panel_layout.addWidget(self.band_list, 1)
        panel_layout.addWidget(help_label)
        layout.addWidget(panel)
        self.setCentralWidget(central)
        self.create_navigation_toolbar()
        self.addToolBarBreak()
        toolbar = QToolBar("Routing", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.select_button = QPushButton("Select isochrone origin", toolbar)
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.begin_selection)
        toolbar.addWidget(self.select_button)
        legend = QLabel("  <b><font color='#16A34A'>●</font> Origin</b>", toolbar)
        legend.setTextFormat(Qt.TextFormat.RichText)
        toolbar.addWidget(legend)

    def create_navigation_toolbar(self) -> None:
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)
        group = QActionGroup(self); group.setExclusive(True)
        zoom_in = QAction(QIcon(str(self.icons / "ZoomIn.png")), "Zoom In", self); zoom_in.triggered.connect(self.viewer.zoom_in); toolbar.addAction(zoom_in)
        zoom_out = QAction(QIcon(str(self.icons / "ZoomOut.png")), "Zoom Out", self); zoom_out.triggered.connect(self.viewer.zoom_out); toolbar.addAction(zoom_out)
        full_extent = QAction(QIcon(str(self.icons / "FullExtent.png")), "Full Extent", self); full_extent.triggered.connect(self.show_stockholm_extent); toolbar.addAction(full_extent)
        self.zoom_box_action = QAction(QIcon(str(self.icons / "RectangularZoom.png")), "Zoom Box", self); self.zoom_box_action.setCheckable(True); self.zoom_box_action.triggered.connect(lambda: self.viewer.set_tool(ViewerTool.ZOOM_BOX)); group.addAction(self.zoom_box_action); toolbar.addAction(self.zoom_box_action)
        self.pan_action = QAction(QIcon(str(self.icons / "Pan.png")), "Pan", self); self.pan_action.setCheckable(True); self.pan_action.setChecked(True); self.pan_action.triggered.connect(lambda: self.viewer.set_tool(ViewerTool.PAN)); group.addAction(self.pan_action); toolbar.addAction(self.pan_action)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        self.overlay.sync_geometry()
        self.statusBar().showMessage("Loading Stockholm road network...")
        self.app.processEvents()
        try:
            path = ensure_sample_file(self.app, "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/stockholm.zip", "stockholm.zip", "stockholm", "stockholm.shp", "Isochrone")
            self.viewer.add_layer(str(path))
            if not self.viewer.set_layer_coordinate_system_preset(0, CoordinateSystemPreset.WGS84):
                raise RuntimeError("The Stockholm layer CRS could not be set to EPSG:4326.")
            if not self.viewer.set_coordinate_system_preset(CoordinateSystemPreset.WEB_MERCATOR):
                raise RuntimeError("The viewer CRS could not be set to EPSG:3857.")
            self.viewer.set_layer_style(0, {"lineColor": "#718684", "lineWidth": 1.0})
            self.stockholm_extent = self.viewer.layer_projected_extent(0)
            if not self.viewer.build_routing_graph_for_layer(0, 1e-6, True, "maxspeed", "name", "oneway", 50.0):
                raise RuntimeError("Routing graph could not be built.")
            self.show_stockholm_extent()
            self.statusBar().showMessage("Preparing routing graph...")
            self.future_kind = "prepare"
            self.future = self.executor.submit(self.prepare_engine)
            self.poll_timer.start()
        except Exception as error:
            self.show_error(error)

    def prepare_engine(self):
        snapshot = self.viewer.get_routing_graph_snapshot()
        if snapshot is None:
            raise RuntimeError("Routing graph is unavailable.")
        engine = RoutingEngine(snapshot)
        component = engine.largest_component()
        if not component:
            raise RuntimeError("The main connected road network could not be identified.")
        return engine, component

    def begin_selection(self) -> None:
        if self.future is not None:
            return
        self.result = None
        self.band_list.clear()
        self.summary.setText("Select an origin point.")
        self.overlay.set_result(None)
        self.pan_action.setChecked(False)
        self.zoom_box_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.ROUTE)
        self.statusBar().showMessage("Click the map to choose an isochrone origin.")

    def on_viewer_event(self, event) -> None:
        if self.closing:
            return
        if event.event_type in (ViewerEventType.VIEW_CHANGED, ViewerEventType.VISIBLE_EXTENT_CHANGED):
            self.overlay.schedule_view_refresh()
            return
        if event.event_type != ViewerEventType.MAP_MOUSE_UP or event.int_value != ViewerTool.ROUTE or self.engine is None or self.future is not None:
            return
        world = Point(event.extent.x_min, event.extent.y_min)
        longitude, latitude = TRANSFORMER.transform_point(3857, 4326, world.x, world.y)
        self.select_button.setEnabled(False)
        self.statusBar().showMessage("Calculating isochrone...")
        self.future_kind = "calculate"
        self.future = self.executor.submit(self.engine.calculate, self.main_component, Point(longitude, latitude))
        self.poll_timer.start()

    def poll_future(self) -> None:
        future = self.future
        if future is None or not future.done():
            return
        self.poll_timer.stop()
        kind = self.future_kind
        self.future = None
        if self.closing:
            return
        try:
            value = future.result()
            if kind == "prepare":
                self.engine, self.main_component = value
                self.select_button.setEnabled(True)
                self.begin_selection()
                return
            self.select_button.setEnabled(True)
            if value is None:
                QMessageBox.warning(self, "Isochrone", "No main-network road node was found nearby.")
                self.statusBar().showMessage("Click the map to choose an isochrone origin.")
                return
            self.result = value
            self.overlay.set_result(value)
            self.band_list.clear()
            for index, band in enumerate(value.bands):
                self.band_list.addItem(f"Within {(index + 1) * 5} minutes\n{band.cumulative_nodes} cumulative nodes • {band.edge_count} band edges")
            self.band_list.setCurrentRow(0)
            self.summary.setText(f"Origin snap: {value.snap_distance:.1f} m\n{value.bands[2].cumulative_nodes} nodes reachable within 15 minutes.")
            self.statusBar().showMessage("Isochrone calculated successfully.")
        except Exception as error:
            self.select_button.setEnabled(self.engine is not None)
            self.show_error(error)

    def select_band(self, row: int) -> None:
        if row >= 0:
            self.overlay.set_active_band(row)

    def show_stockholm_extent(self) -> None:
        if self.stockholm_extent is not None:
            self.viewer.set_view_extent(self.stockholm_extent)

    def show_error(self, error: Exception) -> None:
        self.statusBar().showMessage("The Stockholm routing sample could not be loaded.")
        QMessageBox.critical(self, "Isochrone", str(error))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.initialize_viewer)

    def closeEvent(self, event) -> None:
        self.closing = True
        self.poll_timer.stop()
        self.overlay.shutdown()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.viewer.set_event_callback(None)
        self.viewer.close()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Isochrone")
    window = IsochroneWindow(app)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
