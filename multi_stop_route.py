import heapq
import math
import sys
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox, QPushButton, QToolBar, QVBoxLayout, QWidget
from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Point, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file


MAX_SNAP_DISTANCE = 2000.0
TRANSFORMER = CoordinateSystemFactory()


@dataclass(frozen=True)
class RouteLeg:
    edge_ids: tuple[int, ...]
    geometry: tuple[Point, ...]
    distance: float
    time: float


@dataclass(frozen=True)
class RoadStep:
    name: str
    distance: float
    geometry: tuple[Point, ...]


class RoutingEngine:
    def __init__(self, snapshot: Any) -> None:
        self.nodes = {node.id: node for node in snapshot.nodes}
        self.edges = {edge.id: edge for edge in snapshot.edges}
        self.out_edges: dict[int, list[Any]] = {}
        for edge in snapshot.edges:
            self.out_edges.setdefault(edge.from_id, []).append(edge)

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
                for edge in self.out_edges.get(queue.popleft(), ()):
                    if edge.to_id not in visited:
                        visited.add(edge.to_id)
                        component.add(edge.to_id)
                        queue.append(edge.to_id)
            if len(component) > len(largest):
                largest = component
        return largest

    def reachable(self, start: int) -> set[int]:
        result = {start}
        queue = deque([start])
        while queue:
            for edge in self.out_edges.get(queue.popleft(), ()):
                if edge.to_id not in result:
                    result.add(edge.to_id)
                    queue.append(edge.to_id)
        return result

    def nearest(self, candidates: set[int], point: Point):
        nearest = None
        minimum = MAX_SNAP_DISTANCE
        for node_id in candidates:
            node = self.nodes.get(node_id)
            if node is None:
                continue
            current = self.distance(point, node.position)
            if current < minimum:
                nearest, minimum = node, current
        return nearest

    def find_leg(self, start: int, finish: int) -> RouteLeg | None:
        costs = {start: 0.0}
        previous: dict[int, Any] = {}
        queue = [(0.0, start)]
        while queue:
            cost, node_id = heapq.heappop(queue)
            if cost > costs.get(node_id, math.inf):
                continue
            if node_id == finish:
                break
            for edge in self.out_edges.get(node_id, ()):
                candidate = cost + edge.distance
                if candidate >= costs.get(edge.to_id, math.inf):
                    continue
                costs[edge.to_id] = candidate
                previous[edge.to_id] = edge
                heapq.heappush(queue, (candidate, edge.to_id))
        if finish not in costs:
            return None
        edge_ids: list[int] = []
        node_id = finish
        while node_id != start:
            edge = previous.get(node_id)
            if edge is None:
                return None
            edge_ids.insert(0, edge.id)
            node_id = edge.from_id
        geometry: list[Point] = []
        total_distance = total_time = 0.0
        for edge_id in edge_ids:
            edge = self.edges[edge_id]
            total_distance += edge.distance
            if edge.speed_kmh > 0:
                total_time += edge.distance / (edge.speed_kmh * 1000 / 3600)
            self.append_points(geometry, self.world_geometry(edge.geometry))
        return RouteLeg(tuple(edge_ids), tuple(geometry), total_distance, total_time) if len(geometry) > 1 else None

    def road_steps(self, legs: list[RouteLeg]) -> list[RoadStep]:
        result: list[RoadStep] = []
        for edge_id in (edge_id for leg in legs for edge_id in leg.edge_ids):
            edge = self.edges[edge_id]
            name = str(edge.attributes.get("name") or "").strip() or "Unnamed road"
            geometry = self.world_geometry(edge.geometry)
            if result and result[-1].name.casefold() == name.casefold():
                points = list(result[-1].geometry)
                self.append_points(points, geometry)
                result[-1] = RoadStep(result[-1].name, result[-1].distance + edge.distance, tuple(points))
            else:
                result.append(RoadStep(name, edge.distance, tuple(geometry)))
        return result

    @staticmethod
    def world_geometry(points) -> list[Point]:
        result = []
        for point in points:
            x, y = TRANSFORMER.transform_point(4326, 3857, point.x, point.y)
            result.append(Point(x, y))
        return result

    @staticmethod
    def append_points(target: list[Point], points) -> None:
        for point in points:
            if not target or target[-1] != point:
                target.append(point)

    @staticmethod
    def distance(first: Point, second: Point) -> float:
        latitude_1 = math.radians(first.y)
        latitude_2 = math.radians(second.y)
        delta_latitude = latitude_2 - latitude_1
        delta_longitude = math.radians(second.x - first.x)
        value = math.sin(delta_latitude / 2) ** 2 + math.cos(latitude_1) * math.cos(latitude_2) * math.sin(delta_longitude / 2) ** 2
        return 6371008.8 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


class RouteOverlay(QWidget):
    def __init__(self, viewer: Viewer, target: QWidget, owner: QWidget) -> None:
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.viewer, self.target, self.owner = viewer, target, owner
        self.stops: list[Point] = []
        self.legs: list[RouteLeg] = []
        self.highlight: tuple[Point, ...] = ()
        self.closing = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        target.installEventFilter(self)
        owner.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self.closing and watched in (self.target, self.owner) and event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.WindowStateChange):
            QTimer.singleShot(0, self.sync_geometry)
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
        self.update()

    def set_state(self, stops: list[Point], legs: list[RouteLeg]) -> None:
        self.stops, self.legs, self.highlight = list(stops), list(legs), ()
        self.sync_geometry()

    def set_highlight(self, geometry) -> None:
        self.highlight = tuple(geometry or ())
        self.update()

    def shutdown(self) -> None:
        self.closing = True
        self.target.removeEventFilter(self)
        self.owner.removeEventFilter(self)
        self.close()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            combined: list[Point] = []
            for leg in self.legs:
                RoutingEngine.append_points(combined, leg.geometry)
            self.draw_line(painter, combined, QColor("#2563EB"), 5)
            if self.highlight:
                color = QColor(255, 214, 10, 210)
                self.draw_line(painter, self.highlight, color, 10)
                self.draw_line(painter, self.highlight, QColor("#DC2626"), 4)
            for index, point in enumerate(self.stops):
                self.draw_marker(painter, point, index, len(self.stops))
        finally:
            painter.end()

    def draw_line(self, painter: QPainter, points, color: QColor, width: float) -> None:
        if len(points) < 2:
            return
        first = self.viewer.world_to_screen(points[0].x, points[0].y)
        if first is None or not math.isfinite(first.x) or not math.isfinite(first.y):
            return
        path = QPainterPath(QPointF(first.x, first.y))
        for world in points[1:]:
            point = self.viewer.world_to_screen(world.x, world.y)
            if point is not None and math.isfinite(point.x) and math.isfinite(point.y):
                path.lineTo(QPointF(point.x, point.y))
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def draw_marker(self, painter: QPainter, world: Point, index: int, count: int) -> None:
        screen = self.viewer.world_to_screen(world.x, world.y)
        if screen is None or not math.isfinite(screen.x) or not math.isfinite(screen.y):
            return
        fill = QColor("#22C55E" if index == 0 else "#EF4444" if index == count - 1 else "#F59E0B")
        outline = QColor("#14532D" if index == 0 else "#7F1D1D" if index == count - 1 else "#78350F")
        painter.setPen(QPen(outline, 2)); painter.setBrush(fill); painter.drawEllipse(QPointF(screen.x, screen.y), 8, 8)
        painter.setPen(QColor("white")); painter.drawText(int(screen.x - 8), int(screen.y - 8), 16, 16, Qt.AlignmentFlag.AlignCenter, str(index + 1))


class MultiStopRouteWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer(); self.viewer.set_tool(ViewerTool.PAN); self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget(); self.overlay = RouteOverlay(self.viewer, self.viewer_widget, self)
        self.engine: RoutingEngine | None = None
        self.main_component: set[int] = set()
        self.stops: list[Point] = []
        self.stop_nodes: list[int] = []
        self.route_legs: list[RouteLeg] = []
        self.road_steps: list[RoadStep] = []
        self.stockholm_extent = None
        self.initialized = self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="multi-stop-route")
        self.future: Future | None = None
        self.poll_timer = QTimer(self); self.poll_timer.setInterval(50); self.poll_timer.timeout.connect(self.poll_preparation)
        self.setWindowTitle("MultiStopRoute"); self.setWindowIcon(application_icon()); self.resize(1200, 760); self.create_ui()

    def create_ui(self) -> None:
        central = QWidget(self); layout = QHBoxLayout(central); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0); layout.addWidget(self.viewer_widget, 1)
        panel = QWidget(central); panel.setFixedWidth(320); panel_layout = QVBoxLayout(panel)
        title = QLabel("Multi-stop route", panel); font = title.font(); font.setBold(True); title.setFont(font)
        self.summary = QLabel("Add at least two stops.", panel); self.legs = QListWidget(panel); self.legs.setMaximumHeight(190); self.legs.currentRowChanged.connect(self.highlight_leg)
        roads_title = QLabel("Road directions", panel); font = roads_title.font(); font.setBold(True); roads_title.setFont(font)
        self.roads = QListWidget(panel); self.roads.currentRowChanged.connect(self.highlight_road)
        panel_layout.addWidget(title); panel_layout.addWidget(self.summary); panel_layout.addWidget(self.legs); panel_layout.addWidget(roads_title); panel_layout.addWidget(self.roads, 1); layout.addWidget(panel); self.setCentralWidget(central)
        self.create_navigation_toolbar(); self.addToolBarBreak(); toolbar = QToolBar("Routing", self); toolbar.setMovable(False); self.addToolBar(toolbar)
        self.reset_button = QPushButton("New multi-stop route", toolbar); self.reset_button.setEnabled(False); self.reset_button.clicked.connect(self.reset_route); toolbar.addWidget(self.reset_button)
        self.calculate_button = QPushButton("Calculate route", toolbar); self.calculate_button.setEnabled(False); self.calculate_button.clicked.connect(self.calculate); toolbar.addWidget(self.calculate_button)
        legend = QLabel("  <b><font color='#16A34A'>●</font> Start</b> &nbsp; <b><font color='#F59E0B'>●</font> Stop</b> &nbsp; <b><font color='#DC2626'>●</font> Finish</b>", toolbar); legend.setTextFormat(Qt.TextFormat.RichText); toolbar.addWidget(legend)

    def create_navigation_toolbar(self) -> None:
        toolbar = QToolBar("Navigation", self); toolbar.setMovable(False); toolbar.setIconSize(QSize(32, 32)); self.addToolBar(toolbar); group = QActionGroup(self); group.setExclusive(True)
        for image, text, callback in (("ZoomIn.png", "Zoom In", self.viewer.zoom_in), ("ZoomOut.png", "Zoom Out", self.viewer.zoom_out), ("FullExtent.png", "Full Extent", self.show_stockholm_extent)):
            action = QAction(QIcon(str(self.icons / image)), text, self); action.triggered.connect(callback); toolbar.addAction(action)
        self.zoom_box_action = QAction(QIcon(str(self.icons / "RectangularZoom.png")), "Zoom Box", self); self.zoom_box_action.setCheckable(True); self.zoom_box_action.triggered.connect(lambda: self.viewer.set_tool(ViewerTool.ZOOM_BOX)); group.addAction(self.zoom_box_action); toolbar.addAction(self.zoom_box_action)
        self.pan_action = QAction(QIcon(str(self.icons / "Pan.png")), "Pan", self); self.pan_action.setCheckable(True); self.pan_action.setChecked(True); self.pan_action.triggered.connect(lambda: self.viewer.set_tool(ViewerTool.PAN)); group.addAction(self.pan_action); toolbar.addAction(self.pan_action)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True; self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height()); self.viewer.show(); self.overlay.sync_geometry(); self.statusBar().showMessage("Loading Stockholm road network..."); self.app.processEvents()
        try:
            path = ensure_sample_file(self.app, "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/stockholm.zip", "stockholm.zip", "stockholm", "stockholm.shp", "MultiStopRoute")
            self.viewer.add_layer(str(path));
            if not self.viewer.set_layer_coordinate_system_preset(0, CoordinateSystemPreset.WGS84): raise RuntimeError("The Stockholm layer CRS could not be set to EPSG:4326.")
            if not self.viewer.set_coordinate_system_preset(CoordinateSystemPreset.WEB_MERCATOR): raise RuntimeError("The viewer CRS could not be set to EPSG:3857.")
            self.viewer.set_layer_style(0, {"lineColor": "#718684", "lineWidth": 1.0}); self.stockholm_extent = self.viewer.layer_projected_extent(0)
            if not self.viewer.build_routing_graph_for_layer(0, 1e-6, True, "maxspeed", "name", "oneway", 50.0): raise RuntimeError("Routing graph could not be built.")
            self.show_stockholm_extent(); self.statusBar().showMessage("Preparing routing graph..."); self.future = self.executor.submit(self.prepare_engine); self.poll_timer.start()
        except Exception as error:
            self.show_error(error)

    def prepare_engine(self):
        snapshot = self.viewer.get_routing_graph_snapshot()
        if snapshot is None: raise RuntimeError("Routing graph is unavailable.")
        engine = RoutingEngine(snapshot); component = engine.largest_component()
        if not component: raise RuntimeError("The main connected road network could not be identified.")
        return engine, component

    def poll_preparation(self) -> None:
        if self.future is None or not self.future.done(): return
        self.poll_timer.stop(); future, self.future = self.future, None
        if self.closing: return
        try: self.engine, self.main_component = future.result(); self.reset_button.setEnabled(True); self.reset_route()
        except Exception as error: self.show_error(error)

    def show_error(self, error: Exception) -> None:
        self.statusBar().showMessage("The Stockholm routing sample could not be loaded."); QMessageBox.critical(self, "MultiStopRoute", str(error))

    def reset_route(self) -> None:
        self.stops.clear(); self.stop_nodes.clear(); self.route_legs.clear(); self.road_steps.clear(); self.legs.clear(); self.roads.clear(); self.summary.setText("Add at least two stops."); self.calculate_button.setEnabled(False); self.overlay.set_state([], []); self.pan_action.setChecked(False); self.zoom_box_action.setChecked(False); self.viewer.set_tool(ViewerTool.ROUTE); self.statusBar().showMessage("Click the map to add the start point.")

    def on_viewer_event(self, event) -> None:
        if self.closing: return
        if event.event_type in (ViewerEventType.VIEW_CHANGED, ViewerEventType.VISIBLE_EXTENT_CHANGED): self.overlay.update(); return
        if event.event_type != ViewerEventType.MAP_MOUSE_UP or event.int_value != ViewerTool.ROUTE or self.engine is None: return
        longitude, latitude = TRANSFORMER.transform_point(3857, 4326, event.extent.x_min, event.extent.y_min)
        candidates = self.main_component if not self.stop_nodes else self.engine.reachable(self.stop_nodes[-1])
        node = self.engine.nearest(candidates, Point(longitude, latitude))
        if node is None: QMessageBox.warning(self, "MultiStopRoute", "No reachable road node was found near this point."); return
        if self.stop_nodes and self.stop_nodes[-1] == node.id: return
        x, y = TRANSFORMER.transform_point(4326, 3857, node.position.x, node.position.y); self.stop_nodes.append(node.id); self.stops.append(Point(x, y)); self.route_legs.clear(); self.road_steps.clear(); self.legs.clear(); self.roads.clear(); self.summary.setText(f"{len(self.stops)} stop(s) selected."); self.calculate_button.setEnabled(len(self.stops) >= 2); self.overlay.set_state(self.stops, []); self.statusBar().showMessage(f"Stop {len(self.stops)} added. Add another stop or calculate the route.")

    def calculate(self) -> None:
        if self.engine is None or len(self.stop_nodes) < 2: return
        legs = []
        for index in range(1, len(self.stop_nodes)):
            leg = self.engine.find_leg(self.stop_nodes[index - 1], self.stop_nodes[index])
            if leg is None: QMessageBox.warning(self, "MultiStopRoute", f"No route was found for leg {index}."); return
            legs.append(leg)
        self.route_legs = legs; self.road_steps = self.engine.road_steps(legs); self.legs.clear()
        for index, leg in enumerate(legs, 1): self.legs.addItem(f"{index} → {index + 1}   {leg.distance / 1000:.2f} km • {leg.time / 60:.1f} min")
        self.roads.clear()
        for index, step in enumerate(self.road_steps, 1): self.roads.addItem(f"{index}. {step.name}\n    {step.distance / 1000:.1f} km" if step.distance >= 1000 else f"{index}. {step.name}\n    {step.distance:.0f} m")
        self.summary.setText(f"{len(self.stops)} stops\n{sum(x.distance for x in legs) / 1000:.2f} km  •  {sum(x.time for x in legs) / 60:.1f} min"); self.overlay.set_state(self.stops, legs); self.statusBar().showMessage("Multi-stop route calculated successfully.")

    def highlight_leg(self, index: int) -> None:
        self.overlay.set_highlight(self.route_legs[index].geometry if 0 <= index < len(self.route_legs) else ())

    def highlight_road(self, index: int) -> None:
        self.overlay.set_highlight(self.road_steps[index].geometry if 0 <= index < len(self.road_steps) else ())

    def show_stockholm_extent(self) -> None:
        if self.stockholm_extent is not None: self.viewer.set_view_extent(self.stockholm_extent)

    def closeEvent(self, event) -> None:
        self.closing = True; self.poll_timer.stop(); self.executor.shutdown(wait=True, cancel_futures=True); self.overlay.shutdown()
        try: self.viewer.close()
        except Exception: pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv); app.setApplicationName("MultiStopRoute"); app.setWindowIcon(application_icon()); window = MultiStopRouteWindow(app); window.show(); QTimer.singleShot(0, window.initialize_viewer); sys.exit(app.exec())


if __name__ == "__main__":
    main()
