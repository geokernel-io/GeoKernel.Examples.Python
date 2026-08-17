import heapq
import math
import sys
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
class Route:
    edge_ids: tuple[int, ...]
    world_geometry: tuple[Point, ...]
    distance: float
    time: float


class RoutingEngine:
    def __init__(self, snapshot: Any) -> None:
        self.nodes = {node.id: node for node in snapshot.nodes}
        self.edges = {edge.id: edge for edge in snapshot.edges}
        self.out_edges: dict[int, list[Any]] = {}
        for edge in snapshot.edges:
            self.out_edges.setdefault(edge.from_id, []).append(edge)

    def nearest_node(self, point: Point, max_distance: float):
        nearest = None
        nearest_distance = max_distance
        for node in self.nodes.values():
            distance = self.geodesic_distance(point, node.position)
            if distance < nearest_distance:
                nearest = node
                nearest_distance = distance
        return nearest, nearest_distance if nearest is not None else math.inf

    def find_route(self, start_node: int, finish_node: int) -> Route | None:
        distances = {start_node: 0.0}
        previous: dict[int, Any] = {}
        queue = [(0.0, start_node)]
        while queue:
            distance, node_id = heapq.heappop(queue)
            if distance > distances.get(node_id, math.inf):
                continue
            if node_id == finish_node:
                break
            for edge in self.out_edges.get(node_id, ()):
                candidate = distance + edge.distance
                if candidate >= distances.get(edge.to_id, math.inf):
                    continue
                distances[edge.to_id] = candidate
                previous[edge.to_id] = edge
                heapq.heappush(queue, (candidate, edge.to_id))
        if finish_node not in distances:
            return None

        edge_ids: list[int] = []
        node_id = finish_node
        while node_id != start_node:
            edge = previous.get(node_id)
            if edge is None:
                return None
            edge_ids.insert(0, edge.id)
            node_id = edge.from_id

        geometry: list[Point] = []
        total_distance = 0.0
        total_time = 0.0
        for edge_id in edge_ids:
            edge = self.edges[edge_id]
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
        return Route(tuple(edge_ids), tuple(geometry), total_distance, total_time)

    def road_steps(self, route: Route) -> list[tuple[str, float]]:
        steps: list[tuple[str, float]] = []
        for edge_id in route.edge_ids:
            edge = self.edges[edge_id]
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
        value = math.sin(delta_latitude / 2.0) ** 2 + math.cos(latitude_1) * math.cos(latitude_2) * math.sin(delta_longitude / 2.0) ** 2
        return 6371008.8 * 2.0 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value))


class RouteOverlay(QWidget):
    def __init__(self, viewer: Viewer, target: QWidget, owner: QWidget) -> None:
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.viewer = viewer
        self.target = target
        self.owner = owner
        self.route: Route | None = None
        self.start: Point | None = None
        self.finish: Point | None = None
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

    def set_state(self, start: Point | None, finish: Point | None, route: Route | None) -> None:
        self.start, self.finish, self.route = start, finish, route
        self.sync_geometry()

    def shutdown(self) -> None:
        self.closing = True
        self.target.removeEventFilter(self)
        self.owner.removeEventFilter(self)
        self.close()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.route is not None and len(self.route.world_geometry) > 1:
            first = self.viewer.world_to_screen(self.route.world_geometry[0].x, self.route.world_geometry[0].y)
            if first is not None:
                path = QPainterPath(QPointF(first.x, first.y))
                for world in self.route.world_geometry[1:]:
                    point = self.viewer.world_to_screen(world.x, world.y)
                    if point is not None and math.isfinite(point.x) and math.isfinite(point.y):
                        path.lineTo(QPointF(point.x, point.y))
                pen = QPen(QColor("#EF4444"), 4.0)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
        self.draw_marker(painter, self.start, QColor("#22C55E"), QColor("#14532D"))
        self.draw_marker(painter, self.finish, QColor("#EF4444"), QColor("#7F1D1D"))

    def draw_marker(self, painter: QPainter, point: Point | None, fill: QColor, outline: QColor) -> None:
        if point is None:
            return
        screen = self.viewer.world_to_screen(point.x, point.y)
        if screen is None or not math.isfinite(screen.x) or not math.isfinite(screen.y):
            return
        painter.setPen(QPen(outline, 2.0))
        painter.setBrush(fill)
        painter.drawEllipse(QPointF(screen.x, screen.y), 8.0, 8.0)


class ShortestRouteWindow(QMainWindow):
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
        self.start_point: Point | None = None
        self.finish_point: Point | None = None
        self.start_node = -1
        self.start_snap_distance = 0.0
        self.route: Route | None = None
        self.stockholm_extent = None
        self.initialized = False
        self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shortest-route")
        self.future: Future | None = None
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(50)
        self.poll_timer.timeout.connect(self.poll_preparation)
        self.setWindowTitle("ShortestRoute")
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
        title = QLabel("Route directions", panel)
        font = title.font(); font.setBold(True); title.setFont(font)
        self.summary = QLabel("Select a start and finish point.", panel)
        self.summary.setWordWrap(True)
        self.directions = QListWidget(panel)
        panel_layout.addWidget(title); panel_layout.addWidget(self.summary); panel_layout.addWidget(self.directions, 1)
        layout.addWidget(panel)
        self.setCentralWidget(central)
        self.create_navigation_toolbar()
        self.addToolBarBreak()
        toolbar = QToolBar("Routing", self); toolbar.setMovable(False); self.addToolBar(toolbar)
        self.route_button = QPushButton("Select route points", toolbar); self.route_button.setEnabled(False); self.route_button.clicked.connect(self.begin_selection); toolbar.addWidget(self.route_button)
        legend = QLabel("  <b><font color='#16A34A'>●</font> Start</b> &nbsp;&nbsp; <b><font color='#DC2626'>●</font> Finish</b>", toolbar); legend.setTextFormat(Qt.TextFormat.RichText); toolbar.addWidget(legend)

    def create_navigation_toolbar(self) -> None:
        toolbar = QToolBar("Navigation", self); toolbar.setMovable(False); toolbar.setIconSize(QSize(32, 32)); self.addToolBar(toolbar)
        group = QActionGroup(self); group.setExclusive(True)
        for image, text, callback in (("ZoomIn.png", "Zoom In", self.viewer.zoom_in), ("ZoomOut.png", "Zoom Out", self.viewer.zoom_out), ("FullExtent.png", "Full Extent", self.show_stockholm_extent)):
            action = QAction(QIcon(str(self.icons / image)), text, self); action.triggered.connect(callback); toolbar.addAction(action)
        self.zoom_box_action = QAction(QIcon(str(self.icons / "RectangularZoom.png")), "Zoom Box", self); self.zoom_box_action.setCheckable(True); self.zoom_box_action.triggered.connect(lambda: self.viewer.set_tool(ViewerTool.ZOOM_BOX)); group.addAction(self.zoom_box_action); toolbar.addAction(self.zoom_box_action)
        self.pan_action = QAction(QIcon(str(self.icons / "Pan.png")), "Pan", self); self.pan_action.setCheckable(True); self.pan_action.setChecked(True); self.pan_action.triggered.connect(lambda: self.viewer.set_tool(ViewerTool.PAN)); group.addAction(self.pan_action); toolbar.addAction(self.pan_action)

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height()); self.viewer.show(); self.overlay.sync_geometry(); self.statusBar().showMessage("Loading Stockholm road network..."); self.app.processEvents()
        try:
            path = ensure_sample_file(self.app, "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/stockholm.zip", "stockholm.zip", "stockholm", "stockholm.shp", "ShortestRoute")
            self.viewer.add_layer(str(path))
            if not self.viewer.set_layer_coordinate_system_preset(0, CoordinateSystemPreset.WGS84): raise RuntimeError("The Stockholm layer CRS could not be set to EPSG:4326.")
            if not self.viewer.set_coordinate_system_preset(CoordinateSystemPreset.WEB_MERCATOR): raise RuntimeError("The viewer CRS could not be set to EPSG:3857.")
            self.viewer.set_layer_style(0, {"lineColor": "#718684", "lineWidth": 1.0})
            self.stockholm_extent = self.viewer.layer_projected_extent(0)
            if not self.viewer.build_routing_graph_for_layer(0, 1e-6, True, "maxspeed", "name", "oneway", 50.0): raise RuntimeError("Routing graph could not be built.")
            self.show_stockholm_extent(); self.statusBar().showMessage("Preparing routing graph..."); self.future = self.executor.submit(self.prepare_engine); self.poll_timer.start()
        except Exception as error:
            self.show_error(error)

    def prepare_engine(self) -> RoutingEngine:
        snapshot = self.viewer.get_routing_graph_snapshot()
        if snapshot is None: raise RuntimeError("Routing graph is unavailable.")
        return RoutingEngine(snapshot)

    def poll_preparation(self) -> None:
        if self.future is None or not self.future.done(): return
        self.poll_timer.stop(); future, self.future = self.future, None
        if self.closing: return
        try:
            self.engine = future.result(); self.route_button.setEnabled(True); self.begin_selection()
        except Exception as error:
            self.show_error(error)

    def show_error(self, error: Exception) -> None:
        self.statusBar().showMessage("The Stockholm routing sample could not be loaded."); QMessageBox.critical(self, "ShortestRoute", str(error))

    def begin_selection(self) -> None:
        self.start_point = self.finish_point = None; self.start_node = -1; self.route = None; self.directions.clear(); self.summary.setText("Select a start and finish point."); self.overlay.set_state(None, None, None)
        self.pan_action.setChecked(False); self.zoom_box_action.setChecked(False); self.viewer.set_tool(ViewerTool.ROUTE); self.statusBar().showMessage("Click the map to choose the start point.")

    def on_viewer_event(self, event) -> None:
        if self.closing: return
        if event.event_type in (ViewerEventType.VIEW_CHANGED, ViewerEventType.VISIBLE_EXTENT_CHANGED): self.overlay.update(); return
        if event.event_type != ViewerEventType.MAP_MOUSE_UP or event.int_value != ViewerTool.ROUTE or self.engine is None: return
        longitude, latitude = TRANSFORMER.transform_point(3857, 4326, event.extent.x_min, event.extent.y_min)
        snapped, snap_distance = self.engine.nearest_node(Point(longitude, latitude), MAX_SNAP_DISTANCE)
        if snapped is None: QMessageBox.warning(self, "ShortestRoute", "No road node was found near the selected point."); return
        x, y = TRANSFORMER.transform_point(4326, 3857, snapped.position.x, snapped.position.y); snapped_world = Point(x, y)
        if self.start_point is None or self.finish_point is not None:
            self.start_point, self.finish_point, self.start_node, self.start_snap_distance, self.route = snapped_world, None, snapped.id, snap_distance, None
            self.directions.clear(); self.summary.setText("Select the finish point."); self.overlay.set_state(self.start_point, None, None); self.statusBar().showMessage("Start selected. Click the map to choose the finish point."); return
        self.finish_point = snapped_world; self.route = self.engine.find_route(self.start_node, snapped.id); self.overlay.set_state(self.start_point, self.finish_point, self.route)
        if self.route is None: QMessageBox.warning(self, "ShortestRoute", "No connected route was found."); self.statusBar().showMessage("No connected route found. Click once to choose a new start."); return
        self.summary.setText(f"{self.route.distance / 1000.0:.2f} km  •  {self.route.time / 60.0:.1f} min"); self.directions.clear()
        steps = self.engine.road_steps(self.route)
        for index, (name, distance) in enumerate(steps, 1): self.directions.addItem(f"{index}. {name}\n    {distance / 1000.0:.1f} km" if distance >= 1000.0 else f"{index}. {name}\n    {distance:.0f} m")
        if not steps: self.directions.addItem("Route has no named road segments.")
        self.statusBar().showMessage(f"Route: {self.route.distance / 1000.0:.2f} km, {self.route.time / 60.0:.1f} min | start snap {self.start_snap_distance:.1f} m, end snap {snap_distance:.1f} m")

    def show_stockholm_extent(self) -> None:
        if self.stockholm_extent is not None: self.viewer.set_view_extent(self.stockholm_extent)

    def closeEvent(self, event) -> None:
        self.closing = True; self.poll_timer.stop(); self.executor.shutdown(wait=True, cancel_futures=True); self.overlay.shutdown()
        try: self.viewer.close()
        except Exception: pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv); app.setApplicationName("ShortestRoute"); app.setWindowIcon(application_icon()); window = ShortestRouteWindow(app); window.show(); QTimer.singleShot(0, window.initialize_viewer); sys.exit(app.exec())


if __name__ == "__main__":
    main()
