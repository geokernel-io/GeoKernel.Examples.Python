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
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox, QPushButton, QSpinBox, QToolBar, QVBoxLayout, QWidget
from geokernel import CoordinateSystemPreset, Point, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file


MAX_SNAP_DISTANCE = 2000.0
MERCATOR_LIMIT = 20037508.342789244
ROUTE_COLORS = ("#2563EB", "#F97316", "#9333EA", "#0891B2", "#DB2777", "#65A30D", "#CA8A04", "#4F46E5")


@dataclass(frozen=True)
class Edge:
    id: int
    from_id: int
    to_id: int
    distance: float
    travel_time: float
    geometry: tuple[Point, ...]
    name: str


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


@dataclass(frozen=True)
class VehicleRoute:
    order: tuple[int, ...]
    route: RouteLeg
    steps: tuple[RoadStep, ...]


@dataclass(frozen=True)
class OptimizationResult:
    vehicles: tuple[VehicleRoute, ...]
    total_distance: float
    total_time: float
    longest_distance: float


class RoutingEngine:
    def __init__(self, snapshot: Any) -> None:
        self.nodes = {node.id: Point(node.position.x, node.position.y) for node in snapshot.nodes}
        self.edges: dict[int, Edge] = {}
        self.out_edges: dict[int, list[Edge]] = {}
        for value in snapshot.edges:
            speed = value.speed_kmh if value.speed_kmh > 0 else 50.0
            edge = Edge(
                value.id,
                value.from_id,
                value.to_id,
                value.distance,
                value.distance / (speed * 1000.0 / 3600.0),
                tuple(self.to_web_mercator(point.x, point.y) for point in value.geometry),
                str(value.attributes.get("name") or "").strip() or "Unnamed road",
            )
            self.edges[edge.id] = edge
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
        nearest_id = None
        nearest_distance = MAX_SNAP_DISTANCE
        for node_id in candidates:
            position = self.nodes.get(node_id)
            if position is None:
                continue
            current = self.geodesic_distance(point, position)
            if current < nearest_distance:
                nearest_id, nearest_distance = node_id, current
        return nearest_id

    def distances_to(self, start: int, targets: set[int]) -> dict[int, float]:
        costs = {start: 0.0}
        remaining = set(targets)
        remaining.discard(start)
        queue = [(0.0, start)]
        while queue and remaining:
            cost, node_id = heapq.heappop(queue)
            if cost > costs.get(node_id, math.inf):
                continue
            remaining.discard(node_id)
            for edge in self.out_edges.get(node_id, ()):
                candidate = cost + edge.distance
                if candidate >= costs.get(edge.to_id, math.inf):
                    continue
                costs[edge.to_id] = candidate
                heapq.heappush(queue, (candidate, edge.to_id))
        return costs

    def find_leg(self, start: int, finish: int) -> RouteLeg | None:
        costs = {start: 0.0}
        previous: dict[int, Edge] = {}
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
            total_time += edge.travel_time
            self.append_unique(geometry, edge.geometry)
        return RouteLeg(tuple(edge_ids), tuple(geometry), total_distance, total_time) if len(geometry) > 1 else None

    def optimize(self, stop_nodes: tuple[int, ...], vehicle_count: int) -> OptimizationResult | None:
        count = len(stop_nodes)
        matrix = [[math.inf] * count for _ in range(count)]
        targets = set(stop_nodes)
        for index, node_id in enumerate(stop_nodes):
            costs = self.distances_to(node_id, targets)
            for target_index, target in enumerate(stop_nodes):
                matrix[index][target_index] = costs.get(target, math.inf)

        order = [0]
        remaining = set(range(1, count))
        while remaining:
            current = order[-1]
            best = min(remaining, key=lambda candidate: matrix[current][candidate])
            if not math.isfinite(matrix[current][best]):
                return None
            order.append(best)
            remaining.remove(best)

        def order_cost(value: list[int]) -> float:
            return sum(matrix[value[i - 1]][value[i]] for i in range(1, len(value))) + matrix[value[-1]][0]

        improved = True
        while improved:
            improved = False
            best_cost = order_cost(order)
            for first in range(1, len(order)):
                for second in range(first + 1, len(order)):
                    candidate = order.copy()
                    candidate[first], candidate[second] = candidate[second], candidate[first]
                    candidate_cost = order_cost(candidate)
                    if candidate_cost + 0.01 < best_cost:
                        order, best_cost, improved = candidate, candidate_cost, True

        vehicle_count = min(vehicle_count, count - 1)
        assignments = [[0] for _ in range(vehicle_count)]
        visit_count = len(order) - 1
        for position in range(1, len(order)):
            vehicle = min(vehicle_count - 1, ((position - 1) * vehicle_count) // visit_count)
            assignments[vehicle].append(order[position])

        vehicles: list[VehicleRoute] = []
        for assignment in assignments:
            edge_ids: list[int] = []
            geometry: list[Point] = []
            total_distance = total_time = 0.0
            for index in range(1, len(assignment) + 1):
                from_index = assignment[index - 1]
                to_index = 0 if index == len(assignment) else assignment[index]
                leg = self.find_leg(stop_nodes[from_index], stop_nodes[to_index])
                if leg is None:
                    return None
                edge_ids.extend(leg.edge_ids)
                self.append_unique(geometry, leg.geometry)
                total_distance += leg.distance
                total_time += leg.time
            route = RouteLeg(tuple(edge_ids), tuple(geometry), total_distance, total_time)
            vehicles.append(VehicleRoute(tuple(assignment), route, self.road_steps(edge_ids)))
        return OptimizationResult(
            tuple(vehicles),
            sum(vehicle.route.distance for vehicle in vehicles),
            sum(vehicle.route.time for vehicle in vehicles),
            max(vehicle.route.distance for vehicle in vehicles),
        )

    def road_steps(self, edge_ids: list[int]) -> tuple[RoadStep, ...]:
        result: list[RoadStep] = []
        for edge_id in edge_ids:
            edge = self.edges[edge_id]
            if result and result[-1].name.casefold() == edge.name.casefold():
                geometry = list(result[-1].geometry)
                self.append_unique(geometry, edge.geometry)
                result[-1] = RoadStep(edge.name, result[-1].distance + edge.distance, tuple(geometry))
            else:
                result.append(RoadStep(edge.name, edge.distance, edge.geometry))
        return tuple(result)

    @staticmethod
    def append_unique(target: list[Point], values) -> None:
        for value in values:
            if not target or target[-1] != value:
                target.append(value)

    @staticmethod
    def to_web_mercator(longitude: float, latitude: float) -> Point:
        latitude = max(-85.05112878, min(85.05112878, latitude))
        return Point(longitude * MERCATOR_LIMIT / 180.0, math.log(math.tan((90.0 + latitude) * math.pi / 360.0)) * MERCATOR_LIMIT / math.pi)

    @staticmethod
    def to_wgs84(point: Point) -> Point:
        return Point(point.x / MERCATOR_LIMIT * 180.0, math.atan(math.exp(point.y / MERCATOR_LIMIT * math.pi)) * 360.0 / math.pi - 90.0)

    @staticmethod
    def geodesic_distance(first: Point, second: Point) -> float:
        lat1, lat2 = math.radians(first.y), math.radians(second.y)
        dlat, dlon = lat2 - lat1, math.radians(second.x - first.x)
        value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 6371008.8 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


class RouteOverlay(QWidget):
    def __init__(self, viewer: Viewer, target: QWidget, owner: QWidget) -> None:
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.viewer, self.target, self.owner = viewer, target, owner
        self.stops: list[Point] = []
        self.routes: list[tuple[Point, ...]] = []
        self.highlight: tuple[Point, ...] = ()
        self.active_route = 0
        self.closing = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        target.installEventFilter(self); owner.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self.closing and watched in (self.target, self.owner) and event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.WindowStateChange):
            QTimer.singleShot(0, self.sync_geometry)
        return False

    def sync_geometry(self) -> None:
        if self.closing:
            return
        if not self.owner.isVisible() or self.owner.isMinimized():
            self.hide(); return
        origin = self.target.mapToGlobal(QPoint(0, 0))
        self.setGeometry(origin.x(), origin.y(), self.target.width(), self.target.height())
        if not self.isVisible(): self.show()
        self.raise_(); self.update()

    def set_state(self, stops, routes, highlight=(), active=0) -> None:
        self.stops, self.routes, self.highlight, self.active_route = list(stops), list(routes), tuple(highlight or ()), active
        self.update()

    def set_highlight(self, geometry) -> None:
        self.highlight = tuple(geometry or ())
        self.update()

    def shutdown(self) -> None:
        self.closing = True; self.target.removeEventFilter(self); self.owner.removeEventFilter(self); self.hide(); self.close()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for index, route in enumerate(self.routes):
            if index != self.active_route: self.draw_line(painter, route, QColor(ROUTE_COLORS[index % len(ROUTE_COLORS)]), 3.0, 135)
        if 0 <= self.active_route < len(self.routes): self.draw_line(painter, self.routes[self.active_route], QColor(ROUTE_COLORS[self.active_route % len(ROUTE_COLORS)]), 5.0, 255)
        if self.highlight:
            self.draw_line(painter, self.highlight, QColor("#FFD60A"), 10.0, 210)
            self.draw_line(painter, self.highlight, QColor("#DC2626"), 4.0, 255)
        for index, point in enumerate(self.stops): self.draw_marker(painter, point, index)

    def draw_line(self, painter, geometry, color, width, alpha) -> None:
        if len(geometry) < 2: return
        path = QPainterPath(); started = False
        for world in geometry:
            screen = self.viewer.world_to_screen(world.x, world.y)
            if screen is None or not math.isfinite(screen.x) or not math.isfinite(screen.y): continue
            if not started: path.moveTo(QPointF(screen.x, screen.y)); started = True
            else: path.lineTo(QPointF(screen.x, screen.y))
        color.setAlpha(alpha); pen = QPen(color, width); pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin); painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawPath(path)

    def draw_marker(self, painter, world, index) -> None:
        screen = self.viewer.world_to_screen(world.x, world.y)
        if screen is None or not math.isfinite(screen.x) or not math.isfinite(screen.y): return
        fill = QColor("#22C55E") if index == 0 else QColor("#F59E0B")
        outline = QColor("#14532D") if index == 0 else QColor("#78350F")
        painter.setPen(QPen(outline, 2)); painter.setBrush(fill); painter.drawEllipse(QPointF(screen.x, screen.y), 8, 8)
        painter.setPen(QColor("white")); painter.drawText(int(screen.x - 8), int(screen.y - 8), 16, 16, Qt.AlignmentFlag.AlignCenter, "D" if index == 0 else str(index))


class RouteOptimizationWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__(); self.app = app; self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer(); self.viewer.set_tool(ViewerTool.PAN); self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget(); self.overlay = RouteOverlay(self.viewer, self.viewer_widget, self)
        self.engine: RoutingEngine | None = None; self.component: set[int] = set(); self.stop_nodes: list[int] = []; self.stop_points: list[Point] = []; self.result: OptimizationResult | None = None; self.stockholm_extent = None
        self.initialized = self.closing = self.busy = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="route-optimization"); self.future: Future | None = None; self.future_kind = ""
        self.poll_timer = QTimer(self); self.poll_timer.setInterval(50); self.poll_timer.timeout.connect(self.poll_future)
        self.setWindowTitle("RouteOptimization"); self.setWindowIcon(application_icon()); self.resize(1200, 760); self.create_ui()

    def create_ui(self) -> None:
        central = QWidget(self); layout = QHBoxLayout(central); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0); layout.addWidget(self.viewer_widget, 1)
        panel = QWidget(central); panel.setFixedWidth(320); panel_layout = QVBoxLayout(panel)
        title = QLabel("Service vehicle routes", panel); font = title.font(); font.setBold(True); title.setFont(font)
        self.summary = QLabel("Select a depot and at least two visits.", panel); self.summary.setWordWrap(True)
        vehicle_row = QWidget(panel); vehicle_layout = QHBoxLayout(vehicle_row); vehicle_layout.setContentsMargins(0, 0, 0, 0); vehicle_layout.addWidget(QLabel("Service vehicles:", vehicle_row)); self.vehicle_spin = QSpinBox(vehicle_row); self.vehicle_spin.setRange(1, 1); vehicle_layout.addWidget(self.vehicle_spin)
        self.vehicle_list = QListWidget(panel); self.vehicle_list.setMaximumHeight(190); self.vehicle_list.currentRowChanged.connect(self.select_vehicle)
        road_title = QLabel("Road directions", panel); font = road_title.font(); font.setBold(True); road_title.setFont(font)
        self.road_list = QListWidget(panel); self.road_list.currentRowChanged.connect(self.select_road)
        panel_layout.addWidget(title); panel_layout.addWidget(self.summary); panel_layout.addWidget(vehicle_row); panel_layout.addWidget(self.vehicle_list); panel_layout.addWidget(road_title); panel_layout.addWidget(self.road_list, 1); layout.addWidget(panel); self.setCentralWidget(central)
        self.create_navigation_toolbar(); self.addToolBarBreak(); toolbar = QToolBar("Routing", self); toolbar.setMovable(False); self.addToolBar(toolbar)
        self.reset_button = QPushButton("New optimization", toolbar); self.reset_button.setEnabled(False); self.reset_button.clicked.connect(self.reset_optimization)
        self.calculate_button = QPushButton("Optimize route", toolbar); self.calculate_button.setEnabled(False); self.calculate_button.clicked.connect(self.optimize)
        toolbar.addWidget(self.reset_button); toolbar.addWidget(self.calculate_button)
        legend = QLabel("  <b><font color='#16A34A'>●</font> Depot</b> &nbsp; <b><font color='#F59E0B'>●</font> Visit</b>", toolbar); legend.setTextFormat(Qt.TextFormat.RichText); toolbar.addWidget(legend)

    def create_navigation_toolbar(self) -> None:
        toolbar = QToolBar("Navigation", self); toolbar.setMovable(False); toolbar.setIconSize(QSize(32, 32)); self.addToolBar(toolbar); group = QActionGroup(self); group.setExclusive(True)
        for icon, text, callback in (("ZoomIn.png", "Zoom In", self.viewer.zoom_in), ("ZoomOut.png", "Zoom Out", self.viewer.zoom_out), ("FullExtent.png", "Full Extent", self.show_stockholm_extent)):
            action = QAction(QIcon(str(self.icons / icon)), text, self); action.triggered.connect(callback); toolbar.addAction(action)
        self.zoom_box_action = QAction(QIcon(str(self.icons / "RectangularZoom.png")), "Zoom Box", self); self.zoom_box_action.setCheckable(True); self.zoom_box_action.triggered.connect(lambda: self.viewer.set_tool(ViewerTool.ZOOM_BOX)); group.addAction(self.zoom_box_action); toolbar.addAction(self.zoom_box_action)
        self.pan_action = QAction(QIcon(str(self.icons / "Pan.png")), "Pan", self); self.pan_action.setCheckable(True); self.pan_action.setChecked(True); self.pan_action.triggered.connect(lambda: self.viewer.set_tool(ViewerTool.PAN)); group.addAction(self.pan_action); toolbar.addAction(self.pan_action)

    def initialize_viewer(self) -> None:
        if self.initialized: return
        self.initialized = True; self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height()); self.viewer.show(); self.overlay.sync_geometry(); self.statusBar().showMessage("Loading Stockholm road network..."); self.app.processEvents()
        try:
            path = ensure_sample_file(self.app, "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/stockholm.zip", "stockholm.zip", "stockholm", "stockholm.shp", "RouteOptimization")
            self.viewer.add_layer(str(path)); self.viewer.set_layer_coordinate_system_preset(0, CoordinateSystemPreset.WGS84); self.viewer.set_coordinate_system_preset(CoordinateSystemPreset.WEB_MERCATOR); self.viewer.set_layer_style(0, {"lineColor": "#718684", "lineWidth": 1.0}); self.stockholm_extent = self.viewer.layer_projected_extent(0)
            if not self.viewer.build_routing_graph_for_layer(0, 1e-6, True, "maxspeed", "name", "oneway", 50.0): raise RuntimeError("Routing graph could not be built.")
            self.show_stockholm_extent(); self.statusBar().showMessage("Preparing routing graph..."); self.future_kind = "prepare"; self.future = self.executor.submit(self.prepare_engine); self.poll_timer.start()
        except Exception as error: self.show_error(error)

    def prepare_engine(self):
        snapshot = self.viewer.get_routing_graph_snapshot()
        if snapshot is None: raise RuntimeError("Routing graph is unavailable.")
        engine = RoutingEngine(snapshot); component = engine.largest_component()
        if not component: raise RuntimeError("The main connected road network could not be identified.")
        return engine, component

    def reset_optimization(self) -> None:
        if self.busy: return
        self.stop_nodes.clear(); self.stop_points.clear(); self.result = None; self.vehicle_list.clear(); self.road_list.clear(); self.summary.setText("Select a depot and at least two visits."); self.vehicle_spin.setRange(1, 1); self.vehicle_spin.setValue(1); self.calculate_button.setEnabled(False); self.overlay.set_state([], []); self.viewer.set_tool(ViewerTool.ROUTE); self.pan_action.setChecked(False); self.zoom_box_action.setChecked(False); self.statusBar().showMessage("Click the map to add the depot.")

    def on_viewer_event(self, event) -> None:
        if self.closing: return
        if event.event_type in (ViewerEventType.VIEW_CHANGED, ViewerEventType.VISIBLE_EXTENT_CHANGED): self.overlay.update(); return
        if event.event_type != ViewerEventType.MAP_MOUSE_UP or event.int_value != ViewerTool.ROUTE or self.engine is None or self.busy: return
        world = Point(event.extent.x_min, event.extent.y_min); source = RoutingEngine.to_wgs84(world); candidates = self.component if not self.stop_nodes else self.engine.reachable(self.stop_nodes[-1]); node_id = self.engine.nearest(candidates, source)
        if node_id is None: QMessageBox.warning(self, "RouteOptimization", "No reachable road node was found near this point."); return
        if self.stop_nodes and self.stop_nodes[-1] == node_id: return
        self.stop_nodes.append(node_id); self.stop_points.append(RoutingEngine.to_web_mercator(self.engine.nodes[node_id].x, self.engine.nodes[node_id].y)); self.result = None; self.vehicle_list.clear(); self.road_list.clear(); self.overlay.set_state(self.stop_points, [])
        visits = max(0, len(self.stop_points) - 1); self.summary.setText(f"Depot + {visits} visit(s) selected."); self.vehicle_spin.setMaximum(max(1, visits)); self.calculate_button.setEnabled(len(self.stop_points) >= 3); self.statusBar().showMessage("Depot selected. Add at least two visit points." if len(self.stop_points) == 1 else f"Visit {visits} added. Add another visit or optimize.")

    def optimize(self) -> None:
        if self.busy or self.engine is None or len(self.stop_nodes) < 3: return
        self.busy = True; self.reset_button.setEnabled(False); self.calculate_button.setEnabled(False); self.statusBar().showMessage("Optimizing service vehicle routes..."); self.future_kind = "optimize"; self.future = self.executor.submit(self.engine.optimize, tuple(self.stop_nodes), self.vehicle_spin.value()); self.poll_timer.start()

    def poll_future(self) -> None:
        if self.future is None or not self.future.done(): return
        self.poll_timer.stop(); future, kind = self.future, self.future_kind; self.future = None
        if self.closing: return
        try:
            value = future.result()
            if kind == "prepare": self.engine, self.component = value; self.reset_button.setEnabled(True); self.reset_optimization(); return
            self.busy = False; self.reset_button.setEnabled(True); self.calculate_button.setEnabled(len(self.stop_nodes) >= 3)
            if value is None: QMessageBox.warning(self, "RouteOptimization", "The selected visits cannot form connected vehicle routes."); return
            self.result = value; self.vehicle_list.clear()
            for index, vehicle in enumerate(value.vehicles):
                labels = " → ".join("D" if selected == 0 else str(selected) for selected in vehicle.order) + " → D"
                self.vehicle_list.addItem(f"Vehicle {index + 1}: {labels}\n{vehicle.route.distance / 1000:.2f} km • {vehicle.route.time / 60:.1f} min")
            self.summary.setText(f"{len(value.vehicles)} vehicles • {len(self.stop_nodes) - 1} visits\nFleet distance: {value.total_distance / 1000:.2f} km\nLongest route: {value.longest_distance / 1000:.2f} km\nCombined driving time: {value.total_time / 60:.1f} min")
            self.overlay.set_state(self.stop_points, [vehicle.route.geometry for vehicle in value.vehicles]); self.vehicle_list.setCurrentRow(0); self.statusBar().showMessage("Routes optimized for all service vehicles.")
        except Exception as error:
            self.busy = False; self.reset_button.setEnabled(self.engine is not None); self.calculate_button.setEnabled(len(self.stop_nodes) >= 3); self.show_error(error)

    def select_vehicle(self, index: int) -> None:
        if self.result is None or index < 0 or index >= len(self.result.vehicles): return
        vehicle = self.result.vehicles[index]; self.overlay.set_state(self.stop_points, [item.route.geometry for item in self.result.vehicles], vehicle.route.geometry, index); self.road_list.clear()
        for step_index, step in enumerate(vehicle.steps): self.road_list.addItem(f"{step_index + 1}. {step.name}\n    {step.distance / 1000:.1f} km" if step.distance >= 1000 else f"{step_index + 1}. {step.name}\n    {step.distance:.0f} m")

    def select_road(self, index: int) -> None:
        vehicle_index = self.vehicle_list.currentRow()
        if self.result is None or vehicle_index < 0 or index < 0: return
        steps = self.result.vehicles[vehicle_index].steps
        if index < len(steps): self.overlay.set_highlight(steps[index].geometry)

    def show_stockholm_extent(self) -> None:
        if self.stockholm_extent is not None: self.viewer.set_view_extent(self.stockholm_extent)

    def show_error(self, error: Exception) -> None:
        self.statusBar().showMessage("The Stockholm routing sample could not be loaded."); QMessageBox.critical(self, "RouteOptimization", str(error))

    def showEvent(self, event) -> None:
        super().showEvent(event); QTimer.singleShot(0, self.initialize_viewer)

    def closeEvent(self, event) -> None:
        self.closing = True
        self.poll_timer.stop()
        self.overlay.shutdown()
        self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.viewer.set_event_callback(None)
        except Exception:
            pass
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv); app.setApplicationName("RouteOptimization"); window = RouteOptimizationWindow(app); window.show(); return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
