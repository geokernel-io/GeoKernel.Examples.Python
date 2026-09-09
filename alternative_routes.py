import heapq
import math
import sys
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from geokernel import (
    CoordinateSystemFactory,
    CoordinateSystemPreset,
    Point,
    RoutingGraphEdge,
    RoutingGraphSnapshot,
    Viewer,
    ViewerEventType,
    ViewerTool,
)

from common import application_icon, ensure_sample_file


MAX_SNAP_DISTANCE = 2000.0
ROUTE_COLORS = (QColor("#2563EB"), QColor("#F97316"), QColor("#9333EA"))
TRANSFORMER = CoordinateSystemFactory()


@dataclass(frozen=True)
class AlternativeRoute:
    node_ids: tuple[int, ...]
    edge_ids: tuple[int, ...]
    world_geometry: tuple[Point, ...]
    distance: float
    time: float


class RoutingEngine:
    def __init__(self, snapshot: RoutingGraphSnapshot) -> None:
        self.nodes = {node.id: node for node in snapshot.nodes}
        self.edges = {edge.id: edge for edge in snapshot.edges}
        self.out_edges: dict[int, list[RoutingGraphEdge]] = {}
        self.neighbors: dict[int, set[int]] = {}
        self.reverse_edges: dict[tuple[int, int], RoutingGraphEdge] = {}
        for edge in snapshot.edges:
            self.out_edges.setdefault(edge.from_id, []).append(edge)
            self.neighbors.setdefault(edge.from_id, set()).add(edge.to_id)
            self.reverse_edges[(edge.from_id, edge.to_id)] = edge

    def largest_connected_component(self) -> set[int]:
        visited: set[int] = set()
        largest: set[int] = set()
        for seed in self.nodes:
            if seed in visited:
                continue
            component: set[int] = set()
            queue = deque([seed])
            visited.add(seed)
            while queue:
                node_id = queue.popleft()
                component.add(node_id)
                for neighbor_id in self.neighbors.get(node_id, ()):
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        queue.append(neighbor_id)
            if len(component) > len(largest):
                largest = component
        return largest

    def reachable_nodes(self, start_node: int) -> set[int]:
        reachable = {start_node}
        queue = deque([start_node])
        while queue:
            node_id = queue.popleft()
            for neighbor_id in self.neighbors.get(node_id, ()):
                if neighbor_id not in reachable:
                    reachable.add(neighbor_id)
                    queue.append(neighbor_id)
        return reachable

    def nearest_node(self, component: set[int], point: Point, max_distance: float):
        nearest = None
        nearest_distance = math.inf
        for node_id in component:
            node = self.nodes.get(node_id)
            if node is None:
                continue
            distance = self.geodesic_distance(point, node.position)
            if distance <= max_distance and distance < nearest_distance:
                nearest = node
                nearest_distance = distance
        return nearest

    def find_alternatives(self, start_node: int, finish_node: int) -> list[AlternativeRoute]:
        routes: list[AlternativeRoute] = []
        penalties: dict[int, float] = {}
        signatures: set[tuple[int, ...]] = set()
        for _attempt in range(12):
            if len(routes) >= 3:
                break
            candidate = self.find_route(start_node, finish_node, penalties)
            if candidate is None:
                break
            if candidate.edge_ids not in signatures:
                signatures.add(candidate.edge_ids)
                routes.append(candidate)
            for edge_id in candidate.edge_ids:
                penalties[edge_id] = penalties.get(edge_id, 1.0) * 4.0
                edge = self.edges.get(edge_id)
                if edge is None:
                    continue
                reverse = self.reverse_edges.get((edge.to_id, edge.from_id))
                if reverse is not None:
                    penalties[reverse.id] = penalties.get(reverse.id, 1.0) * 4.0
        return routes

    def find_route(
        self,
        start_node: int,
        finish_node: int,
        penalties: dict[int, float],
    ) -> AlternativeRoute | None:
        distances = {start_node: 0.0}
        previous_node: dict[int, int] = {}
        previous_edge: dict[int, int] = {}
        queue = [(0.0, start_node)]
        while queue:
            distance, node_id = heapq.heappop(queue)
            if distance > distances.get(node_id, math.inf):
                continue
            if node_id == finish_node:
                break
            for edge in self.out_edges.get(node_id, ()):
                candidate = distance + edge.distance * penalties.get(edge.id, 1.0)
                if candidate >= distances.get(edge.to_id, math.inf):
                    continue
                distances[edge.to_id] = candidate
                previous_node[edge.to_id] = node_id
                previous_edge[edge.to_id] = edge.id
                heapq.heappush(queue, (candidate, edge.to_id))
        if finish_node not in distances:
            return None

        node_ids = [finish_node]
        edge_ids: list[int] = []
        node_id = finish_node
        while node_id != start_node:
            if node_id not in previous_node or node_id not in previous_edge:
                return None
            edge_ids.insert(0, previous_edge[node_id])
            node_id = previous_node[node_id]
            node_ids.insert(0, node_id)

        geometry: list[Point] = []
        total_distance = 0.0
        total_time = 0.0
        for edge_id in edge_ids:
            edge = self.edges.get(edge_id)
            if edge is None:
                continue
            total_distance += edge.distance
            if edge.speed_kmh > 0.0:
                total_time += edge.distance / (edge.speed_kmh * 1000.0 / 3600.0)
            for point in edge.geometry:
                x, y = TRANSFORMER.transform_point(4326, 3857, point.x, point.y)
                world_point = Point(x, y)
                if not geometry or geometry[-1] != world_point:
                    geometry.append(world_point)
        if len(geometry) < 2:
            return None
        return AlternativeRoute(
            tuple(node_ids),
            tuple(edge_ids),
            tuple(geometry),
            total_distance,
            total_time,
        )

    def road_steps(self, route: AlternativeRoute) -> list[tuple[str, float]]:
        steps: list[tuple[str, float]] = []
        for edge_id in route.edge_ids:
            edge = self.edges.get(edge_id)
            if edge is None:
                continue
            name = str(edge.attributes.get("name") or "").strip() or "Unnamed road"
            if steps and steps[-1][0].casefold() == name.casefold():
                steps[-1] = (steps[-1][0], steps[-1][1] + edge.distance)
            else:
                steps.append((name, edge.distance))
        return steps

    @staticmethod
    def geodesic_distance(first: Point, second: Point) -> float:
        latitude_1 = math.radians(first.y)
        latitude_2 = math.radians(second.y)
        delta_latitude = latitude_2 - latitude_1
        delta_longitude = math.radians(second.x - first.x)
        value = (
            math.sin(delta_latitude / 2.0) ** 2
            + math.cos(latitude_1)
            * math.cos(latitude_2)
            * math.sin(delta_longitude / 2.0) ** 2
        )
        return 6371008.8 * 2.0 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value))


class RouteOverlay(QWidget):
    def __init__(self, viewer: Viewer, target: QWidget, owner: QWidget) -> None:
        super().__init__(
            owner,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.viewer = viewer
        self.target = target
        self.owner = owner
        self.routes: list[AlternativeRoute] = []
        self.active_route = 0
        self.start: Point | None = None
        self.finish: Point | None = None
        self.closing = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        target.installEventFilter(self)
        owner.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if self.closing:
            return False
        if watched in (self.target, self.owner) and event.type() in (
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.WindowStateChange,
        ):
            QTimer.singleShot(0, self.sync_geometry)
        return False

    def sync_geometry(self) -> None:
        if self.closing:
            return
        if not self.owner.isVisible() or self.owner.isMinimized():
            self.hide()
            return
        origin = self.target.mapToGlobal(QPoint(0, 0))
        self.setGeometry(
            origin.x(),
            origin.y(),
            self.target.width(),
            self.target.height(),
        )
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def shutdown(self) -> None:
        self.closing = True
        self.target.removeEventFilter(self)
        self.owner.removeEventFilter(self)
        self.hide()
        self.close()

    def set_state(
        self,
        start: Point | None,
        finish: Point | None,
        routes: list[AlternativeRoute],
        active_route: int,
    ) -> None:
        self.start = start
        self.finish = finish
        self.routes = routes
        self.active_route = active_route
        self.sync_geometry()
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for index, route in enumerate(self.routes):
            if index != self.active_route:
                self.draw_route(painter, route, index, False)
        if 0 <= self.active_route < len(self.routes):
            self.draw_route(painter, self.routes[self.active_route], self.active_route, True)
        self.draw_marker(painter, self.start, QColor("#22C55E"), QColor("#14532D"))
        self.draw_marker(painter, self.finish, QColor("#EF4444"), QColor("#7F1D1D"))

    def draw_route(self, painter: QPainter, route: AlternativeRoute, index: int, active: bool) -> None:
        if len(route.world_geometry) < 2:
            return
        first = self.viewer.world_to_screen(route.world_geometry[0].x, route.world_geometry[0].y)
        if first is None or not math.isfinite(first.x) or not math.isfinite(first.y):
            return
        path = QPainterPath(QPointF(first.x, first.y))
        for world_point in route.world_geometry[1:]:
            point = self.viewer.world_to_screen(world_point.x, world_point.y)
            if point is not None and math.isfinite(point.x) and math.isfinite(point.y):
                path.lineTo(QPointF(point.x, point.y))
        color = QColor(ROUTE_COLORS[index % len(ROUTE_COLORS)])
        color.setAlpha(255 if active else 135)
        pen = QPen(color, 5.0 if active else 3.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def draw_marker(self, painter: QPainter, point: Point | None, fill: QColor, outline: QColor) -> None:
        if point is None:
            return
        screen = self.viewer.world_to_screen(point.x, point.y)
        if screen is None or not math.isfinite(screen.x) or not math.isfinite(screen.y):
            return
        painter.setPen(QPen(outline, 2.0))
        painter.setBrush(fill)
        painter.drawEllipse(QPointF(screen.x, screen.y), 8.0, 8.0)


class AlternativeRoutesWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.icons = Path(__file__).with_name("images")
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer.set_event_callback(self.on_viewer_event)
        self.viewer_widget = self.viewer.qt_widget()
        self.overlay = RouteOverlay(self.viewer, self.viewer_widget, self)
        self.engine: RoutingEngine | None = None
        self.main_component: set[int] = set()
        self.start_point: Point | None = None
        self.finish_point: Point | None = None
        self.start_node = -1
        self.routes: list[AlternativeRoute] = []
        self.stockholm_extent = None
        self.initialized = False
        self.closing = False
        self.routing_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="alternative-routes",
        )
        self.routing_future: Future | None = None
        self.routing_poll_timer = QTimer(self)
        self.routing_poll_timer.setInterval(50)
        self.routing_poll_timer.timeout.connect(self.poll_routing_preparation)

        self.setWindowTitle("AlternativeRoutes")
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
        panel.setFixedWidth(300)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        title = QLabel("Alternative routes", panel)
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        self.summary = QLabel("Select a start and finish point.", panel)
        self.summary.setWordWrap(True)
        self.alternatives = QListWidget(panel)
        self.alternatives.setMaximumHeight(150)
        self.alternatives.currentRowChanged.connect(self.select_alternative)
        road_title = QLabel("Road directions", panel)
        road_font = road_title.font()
        road_font.setBold(True)
        road_title.setFont(road_font)
        self.directions = QListWidget(panel)
        panel_layout.addWidget(title)
        panel_layout.addWidget(self.summary)
        panel_layout.addWidget(self.alternatives)
        panel_layout.addWidget(road_title)
        panel_layout.addWidget(self.directions, 1)
        layout.addWidget(panel)
        self.setCentralWidget(central)

        self.create_navigation_toolbar()
        self.addToolBarBreak()
        toolbar = QToolBar("Routing", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.route_button = QPushButton("Select route points", toolbar)
        self.route_button.setEnabled(False)
        self.route_button.clicked.connect(self.begin_selection)
        toolbar.addWidget(self.route_button)
        legend = QLabel(
            "  <b><font color='#16A34A'>●</font> Start</b> &nbsp;&nbsp; "
            "<b><font color='#DC2626'>●</font> Finish</b>",
            toolbar,
        )
        legend.setTextFormat(Qt.TextFormat.RichText)
        toolbar.addWidget(legend)

    def create_navigation_toolbar(self) -> None:
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)
        group = QActionGroup(self)
        group.setExclusive(True)

        zoom_in = QAction(QIcon(str(self.icons / "ZoomIn.png")), "Zoom In", self)
        zoom_in.triggered.connect(self.viewer.zoom_in)
        toolbar.addAction(zoom_in)
        zoom_out = QAction(QIcon(str(self.icons / "ZoomOut.png")), "Zoom Out", self)
        zoom_out.triggered.connect(self.viewer.zoom_out)
        toolbar.addAction(zoom_out)
        full_extent = QAction(QIcon(str(self.icons / "FullExtent.png")), "Full Extent", self)
        full_extent.triggered.connect(self.show_stockholm_extent)
        toolbar.addAction(full_extent)
        self.zoom_box_action = QAction(
            QIcon(str(self.icons / "RectangularZoom.png")), "Zoom Box", self
        )
        self.zoom_box_action.setCheckable(True)
        self.zoom_box_action.triggered.connect(
            lambda: self.viewer.set_tool(ViewerTool.ZOOM_BOX)
        )
        group.addAction(self.zoom_box_action)
        toolbar.addAction(self.zoom_box_action)
        self.pan_action = QAction(QIcon(str(self.icons / "Pan.png")), "Pan", self)
        self.pan_action.setCheckable(True)
        self.pan_action.setChecked(True)
        self.pan_action.triggered.connect(lambda: self.viewer.set_tool(ViewerTool.PAN))
        group.addAction(self.pan_action)
        toolbar.addAction(self.pan_action)

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
            path = ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/stockholm.zip",
                zip_name="stockholm.zip",
                target_folder="stockholm",
                required_file="stockholm.shp",
                title="AlternativeRoutes",
            )
            self.viewer.add_layer(str(path))
            if not self.viewer.set_layer_coordinate_system_preset(0, CoordinateSystemPreset.WGS84):
                raise RuntimeError("The Stockholm layer CRS could not be set to EPSG:4326.")
            if not self.viewer.set_coordinate_system_preset(CoordinateSystemPreset.WEB_MERCATOR):
                raise RuntimeError("The viewer CRS could not be set to EPSG:3857.")
            self.viewer.set_layer_style(0, {"lineColor": "#718684", "lineWidth": 1.0})
            self.stockholm_extent = self.viewer.layer_projected_extent(0)
            if not self.viewer.build_routing_graph_for_layer(
                0, 1e-6, True, "maxspeed", "name", "oneway", 50.0
            ):
                raise RuntimeError("Routing graph could not be built.")
            self.show_stockholm_extent()
            self.statusBar().showMessage("Preparing routing graph...")
            self.routing_future = self.routing_executor.submit(
                self.prepare_routing_engine
            )
            self.routing_poll_timer.start()
        except Exception as error:
            self.show_loading_error(error)

    def prepare_routing_engine(self) -> tuple[RoutingEngine, set[int]]:
        snapshot = self.viewer.get_routing_graph_snapshot()
        if snapshot is None:
            raise RuntimeError("Routing graph is unavailable.")
        engine = RoutingEngine(snapshot)
        component = engine.largest_connected_component()
        if not component:
            raise RuntimeError("The main connected road network could not be identified.")
        return engine, component

    def poll_routing_preparation(self) -> None:
        future = self.routing_future
        if future is None or not future.done():
            return
        self.routing_poll_timer.stop()
        self.routing_future = None
        if self.closing:
            return
        try:
            self.engine, self.main_component = future.result()
            self.route_button.setEnabled(True)
            self.begin_selection()
        except Exception as error:
            self.show_loading_error(error)

    def show_loading_error(self, error: Exception) -> None:
        self.statusBar().showMessage("The Stockholm routing sample could not be loaded.")
        QMessageBox.critical(self, "AlternativeRoutes", str(error))

    def begin_selection(self) -> None:
        self.start_point = None
        self.finish_point = None
        self.start_node = -1
        self.routes = []
        self.alternatives.clear()
        self.directions.clear()
        self.summary.setText("Select a start and finish point.")
        self.overlay.set_state(None, None, [], 0)
        self.pan_action.setChecked(False)
        self.zoom_box_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.ROUTE)
        self.statusBar().showMessage("Click the map to choose the start point.")

    def on_viewer_event(self, event) -> None:
        if self.closing:
            return
        if event.event_type in (ViewerEventType.VIEW_CHANGED, ViewerEventType.VISIBLE_EXTENT_CHANGED):
            self.overlay.update()
            return
        if event.event_type != ViewerEventType.MAP_MOUSE_UP or event.int_value != ViewerTool.ROUTE:
            return
        if self.engine is None:
            return
        world = Point(event.extent.x_min, event.extent.y_min)
        longitude, latitude = TRANSFORMER.transform_point(3857, 4326, world.x, world.y)
        source = Point(longitude, latitude)
        component = (
            self.engine.reachable_nodes(self.start_node)
            if self.start_point is not None and self.finish_point is None
            else self.main_component
        )
        snapped = self.engine.nearest_node(component, source, MAX_SNAP_DISTANCE)
        if snapped is None:
            QMessageBox.warning(
                self,
                "AlternativeRoutes",
                "No road node was found near the selected point.",
            )
            return
        x, y = TRANSFORMER.transform_point(
            4326, 3857, snapped.position.x, snapped.position.y
        )
        snapped_world = Point(x, y)

        if self.start_point is None or self.finish_point is not None:
            self.start_point = snapped_world
            self.finish_point = None
            self.start_node = snapped.id
            self.routes = []
            self.alternatives.clear()
            self.directions.clear()
            self.summary.setText("Select the finish point.")
            self.overlay.set_state(self.start_point, None, [], 0)
            self.statusBar().showMessage(
                "Start selected. Click the map to choose the finish point."
            )
            return

        self.finish_point = snapped_world
        self.routes = self.engine.find_alternatives(self.start_node, snapped.id)
        self.overlay.set_state(self.start_point, self.finish_point, self.routes, 0)
        if not self.routes:
            QMessageBox.warning(self, "AlternativeRoutes", "No connected route was found.")
            return
        self.alternatives.clear()
        for index, route in enumerate(self.routes, start=1):
            self.alternatives.addItem(
                f"{index}. {route.distance / 1000.0:.2f} km  •  {route.time / 60.0:.1f} min"
            )
        self.alternatives.setCurrentRow(0)
        self.statusBar().showMessage(f"{len(self.routes)} alternative route(s) found.")

    def select_alternative(self, route_index: int) -> None:
        if self.engine is None or route_index < 0 or route_index >= len(self.routes):
            return
        route = self.routes[route_index]
        self.summary.setText(
            f"Alternative {route_index + 1}\n"
            f"{route.distance / 1000.0:.2f} km  •  {route.time / 60.0:.1f} min"
        )
        self.directions.clear()
        for index, (name, distance) in enumerate(self.engine.road_steps(route), start=1):
            distance_text = (
                f"{distance / 1000.0:.1f} km" if distance >= 1000.0 else f"{distance:.0f} m"
            )
            self.directions.addItem(f"{index}. {name}\n    {distance_text}")
        self.overlay.set_state(
            self.start_point,
            self.finish_point,
            self.routes,
            route_index,
        )

    def show_stockholm_extent(self) -> None:
        if self.stockholm_extent is not None:
            self.viewer.set_view_extent(self.stockholm_extent)

    def closeEvent(self, event) -> None:
        self.closing = True
        self.routing_poll_timer.stop()
        self.routing_executor.shutdown(wait=True, cancel_futures=True)
        self.overlay.shutdown()
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AlternativeRoutes")
    app.setWindowIcon(application_icon())
    window = AlternativeRoutesWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
