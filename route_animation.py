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
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget,
                               QMainWindow, QMessageBox, QPushButton, QToolBar,
                               QVBoxLayout, QWidget)

from geokernel import CoordinateSystemFactory, CoordinateSystemPreset, Point, Viewer, ViewerEventType, ViewerTool
from common import application_icon, ensure_sample_file


MAX_SNAP_DISTANCE = 2000.0
TRANSFORMER = CoordinateSystemFactory()


@dataclass(frozen=True)
class Route:
    edge_ids: tuple[int, ...]
    geometry: tuple[Point, ...]
    distance: float
    time: float


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
            distance = self.geodesic_distance(point, node.position)
            if distance < minimum:
                nearest, minimum = node, distance
        return nearest

    def find_route(self, start: int, finish: int) -> Route | None:
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
        distance = time = 0.0
        for edge_id in edge_ids:
            edge = self.edges[edge_id]
            distance += edge.distance
            if edge.speed_kmh > 0:
                time += edge.distance / (edge.speed_kmh * 1000 / 3600)
            for source in edge.geometry:
                x, y = TRANSFORMER.transform_point(4326, 3857, source.x, source.y)
                point = Point(x, y)
                if not geometry or geometry[-1] != point:
                    geometry.append(point)
        return Route(tuple(edge_ids), tuple(geometry), distance, time) if len(geometry) > 1 else None

    def road_steps(self, route: Route) -> list[tuple[str, float]]:
        result: list[tuple[str, float]] = []
        for edge_id in route.edge_ids:
            edge = self.edges[edge_id]
            name = str(edge.attributes.get("name") or "").strip() or "Unnamed road"
            if result and result[-1][0].casefold() == name.casefold():
                result[-1] = (result[-1][0], result[-1][1] + edge.distance)
            else:
                result.append((name, edge.distance))
        return result

    @staticmethod
    def geodesic_distance(first: Point, second: Point) -> float:
        lat1, lat2 = math.radians(first.y), math.radians(second.y)
        dlat = lat2 - lat1
        dlon = math.radians(second.x - first.x)
        value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 6371008.8 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


class RouteOverlay(QWidget):
    def __init__(self, viewer: Viewer, target: QWidget, owner: QWidget) -> None:
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                 Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowTransparentForInput |
                 Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(owner, flags)
        self.viewer, self.target, self.owner = viewer, target, owner
        self.start: Point | None = None
        self.finish: Point | None = None
        self.route: Route | None = None
        self.progress = -1.0
        self.closing = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        target.installEventFilter(self)
        owner.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        relevant = (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.WindowStateChange)
        if not self.closing and watched in (self.target, self.owner) and event.type() in relevant:
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

    def set_state(self, start: Point | None, finish: Point | None, route: Route | None, progress: float = -1.0) -> None:
        self.start, self.finish, self.route, self.progress = start, finish, route, progress
        self.sync_geometry()

    def set_progress(self, progress: float) -> None:
        self.progress = max(0.0, min(1.0, progress))
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
            if self.route is not None:
                self.draw_line(painter, self.route.geometry)
            self.draw_marker(painter, self.start, QColor("#22C55E"), QColor("#14532D"))
            self.draw_marker(painter, self.finish, QColor("#EF4444"), QColor("#7F1D1D"))
            self.draw_vehicle(painter)
        finally:
            painter.end()

    def screen(self, world: Point) -> QPointF | None:
        point = self.viewer.world_to_screen(world.x, world.y)
        if point is None or not math.isfinite(point.x) or not math.isfinite(point.y):
            return None
        return QPointF(point.x, point.y)

    def draw_line(self, painter: QPainter, geometry: tuple[Point, ...]) -> None:
        if len(geometry) < 2:
            return
        first = self.screen(geometry[0])
        if first is None:
            return
        path = QPainterPath(first)
        for world in geometry[1:]:
            point = self.screen(world)
            if point is not None:
                path.lineTo(point)
        pen = QPen(QColor("#EF4444"), 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def draw_marker(self, painter: QPainter, world: Point | None, fill: QColor, outline: QColor) -> None:
        if world is None:
            return
        point = self.screen(world)
        if point is None:
            return
        painter.setPen(QPen(outline, 2))
        painter.setBrush(fill)
        painter.drawEllipse(point, 8, 8)

    def draw_vehicle(self, painter: QPainter) -> None:
        if self.route is None or self.progress < 0 or len(self.route.geometry) < 2:
            return
        geometry = self.route.geometry
        lengths = [math.hypot(b.x - a.x, b.y - a.y) for a, b in zip(geometry, geometry[1:])]
        total = sum(lengths)
        if total <= 0:
            return
        target, traversed = total * self.progress, 0.0
        position, direction = geometry[0], geometry[1]
        for index, length in enumerate(lengths, 1):
            if target <= traversed + length or index == len(geometry) - 1:
                ratio = max(0.0, min(1.0, (target - traversed) / length)) if length else 0.0
                first, last = geometry[index - 1], geometry[index]
                position = Point(first.x + (last.x - first.x) * ratio, first.y + (last.y - first.y) * ratio)
                direction = last
                break
            traversed += length
        point, next_point = self.screen(position), self.screen(direction)
        if point is None or next_point is None:
            return
        angle = math.atan2(next_point.y() - point.y(), next_point.x() - point.x())
        painter.setPen(QPen(QColor("#1E3A8A"), 2))
        painter.setBrush(QColor("#2563EB"))
        painter.drawEllipse(point, 10, 10)
        arrow = QPen(QColor("white"), 3)
        arrow.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arrow)
        painter.drawLine(point, point + QPointF(math.cos(angle) * 7, math.sin(angle) * 7))


class RouteAnimationWindow(QMainWindow):
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
        self.start: Point | None = None
        self.finish: Point | None = None
        self.start_node = -1
        self.route: Route | None = None
        self.stockholm_extent = None
        self.progress = 0.0
        self.duration_ms = 5000.0
        self.initialized = self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="route-animation")
        self.future: Future | None = None
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(50)
        self.poll_timer.timeout.connect(self.poll_preparation)
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(33)
        self.animation_timer.timeout.connect(self.animate)
        self.setWindowTitle("RouteAnimation")
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
        title = QLabel("Route directions", panel)
        font = title.font(); font.setBold(True); title.setFont(font)
        self.summary = QLabel("Select a start and finish point.", panel); self.summary.setWordWrap(True)
        self.animation_status = QLabel("Animation is waiting for a route.", panel); self.animation_status.setWordWrap(True)
        buttons = QWidget(panel); button_layout = QHBoxLayout(buttons); button_layout.setContentsMargins(0, 0, 0, 0)
        self.play_button = QPushButton("Play", buttons); self.play_button.setEnabled(False); self.play_button.clicked.connect(self.play)
        self.pause_button = QPushButton("Pause", buttons); self.pause_button.setEnabled(False); self.pause_button.clicked.connect(self.pause)
        self.reset_animation_button = QPushButton("Reset", buttons); self.reset_animation_button.setEnabled(False); self.reset_animation_button.clicked.connect(self.reset_animation)
        button_layout.addWidget(self.play_button); button_layout.addWidget(self.pause_button); button_layout.addWidget(self.reset_animation_button)
        self.directions = QListWidget(panel)
        panel_layout.addWidget(title); panel_layout.addWidget(self.summary); panel_layout.addWidget(self.animation_status); panel_layout.addWidget(buttons); panel_layout.addWidget(self.directions, 1)
        layout.addWidget(panel)
        self.setCentralWidget(central)
        self.create_navigation_toolbar()
        self.addToolBarBreak()
        toolbar = QToolBar("Routing", self); toolbar.setMovable(False); self.addToolBar(toolbar)
        self.select_button = QPushButton("Select route points", toolbar); self.select_button.setEnabled(False); self.select_button.clicked.connect(self.begin_selection); toolbar.addWidget(self.select_button)
        legend = QLabel("  <b><font color='#16A34A'>●</font> Start</b> &nbsp;&nbsp; <b><font color='#DC2626'>●</font> Finish</b>", toolbar)
        legend.setTextFormat(Qt.TextFormat.RichText); toolbar.addWidget(legend)

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
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height()); self.viewer.show(); self.overlay.sync_geometry()
        self.statusBar().showMessage("Loading Stockholm road network..."); self.app.processEvents()
        try:
            path = ensure_sample_file(self.app, "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/stockholm.zip", "stockholm.zip", "stockholm", "stockholm.shp", "RouteAnimation")
            self.viewer.add_layer(str(path))
            if not self.viewer.set_layer_coordinate_system_preset(0, CoordinateSystemPreset.WGS84):
                raise RuntimeError("The Stockholm layer CRS could not be set to EPSG:4326.")
            if not self.viewer.set_coordinate_system_preset(CoordinateSystemPreset.WEB_MERCATOR):
                raise RuntimeError("The viewer CRS could not be set to EPSG:3857.")
            self.viewer.set_layer_style(0, {"lineColor": "#718684", "lineWidth": 1.0})
            self.stockholm_extent = self.viewer.layer_projected_extent(0)
            if not self.viewer.build_routing_graph_for_layer(0, 1e-6, True, "maxspeed", "name", "oneway", 50.0):
                raise RuntimeError("Routing graph could not be built.")
            self.show_stockholm_extent(); self.statusBar().showMessage("Preparing routing graph...")
            self.future = self.executor.submit(self.prepare_engine); self.poll_timer.start()
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

    def poll_preparation(self) -> None:
        if self.future is None or not self.future.done():
            return
        self.poll_timer.stop(); future, self.future = self.future, None
        if self.closing:
            return
        try:
            self.engine, self.main_component = future.result()
            self.select_button.setEnabled(True)
            self.begin_selection()
        except Exception as error:
            self.show_error(error)

    def show_error(self, error: Exception) -> None:
        self.statusBar().showMessage("The Stockholm routing sample could not be loaded.")
        QMessageBox.critical(self, "RouteAnimation", str(error))

    def disable_animation(self) -> None:
        self.animation_timer.stop(); self.progress = 0.0
        self.play_button.setEnabled(False); self.pause_button.setEnabled(False); self.reset_animation_button.setEnabled(False)
        self.animation_status.setText("Animation is waiting for a route.")

    def begin_selection(self) -> None:
        self.disable_animation(); self.start = self.finish = None; self.start_node = -1; self.route = None
        self.directions.clear(); self.summary.setText("Select a start and finish point."); self.overlay.set_state(None, None, None)
        self.pan_action.setChecked(False); self.zoom_box_action.setChecked(False); self.viewer.set_tool(ViewerTool.ROUTE)
        self.statusBar().showMessage("Click the map to choose the start point.")

    def on_viewer_event(self, event) -> None:
        if self.closing:
            return
        if event.event_type in (ViewerEventType.VIEW_CHANGED, ViewerEventType.VISIBLE_EXTENT_CHANGED):
            self.overlay.update(); return
        if event.event_type != ViewerEventType.MAP_MOUSE_UP or event.int_value != ViewerTool.ROUTE or self.engine is None:
            return
        longitude, latitude = TRANSFORMER.transform_point(3857, 4326, event.extent.x_min, event.extent.y_min)
        candidates = self.engine.reachable(self.start_node) if self.start is not None and self.finish is None else self.main_component
        node = self.engine.nearest(candidates, Point(longitude, latitude))
        if node is None:
            QMessageBox.warning(self, "RouteAnimation", "No road node was found near the selected point."); return
        x, y = TRANSFORMER.transform_point(4326, 3857, node.position.x, node.position.y)
        world = Point(x, y)
        if self.start is None or self.finish is not None:
            self.disable_animation(); self.start, self.finish, self.start_node, self.route = world, None, node.id, None
            self.directions.clear(); self.summary.setText("Select the finish point."); self.overlay.set_state(self.start, None, None)
            self.statusBar().showMessage("Start selected. Click the map to choose the finish point."); return
        self.finish = world
        self.route = self.engine.find_route(self.start_node, node.id)
        if self.route is None:
            self.overlay.set_state(self.start, self.finish, None)
            QMessageBox.warning(self, "RouteAnimation", "No connected route was found.")
            self.statusBar().showMessage("No connected route found. Click once to choose a new start."); return
        self.progress = 0.0; self.duration_ms = max(5000.0, min(45000.0, self.route.time / 60 * 1000))
        self.overlay.set_state(self.start, self.finish, self.route, 0.0)
        self.play_button.setEnabled(True); self.pause_button.setEnabled(False); self.reset_animation_button.setEnabled(True)
        self.animation_status.setText(f"Ready: {self.route.distance / 1000:.2f} km • {self.route.time / 60:.1f} min\nAnimation speed adapts to route length.")
        self.summary.setText(f"{self.route.distance / 1000:.2f} km  •  {self.route.time / 60:.1f} min")
        self.directions.clear()
        steps = self.engine.road_steps(self.route)
        for index, (name, distance) in enumerate(steps, 1):
            value = f"{distance / 1000:.1f} km" if distance >= 1000 else f"{distance:.0f} m"
            self.directions.addItem(f"{index}. {name}\n    {value}")
        if not steps:
            self.directions.addItem("Route has no named road segments.")
        self.statusBar().showMessage(f"Route: {self.route.distance / 1000:.2f} km, {self.route.time / 60:.1f} min")

    def play(self) -> None:
        if self.route is None:
            return
        if self.progress >= 1:
            self.progress = 0.0; self.overlay.set_progress(0.0)
        self.animation_timer.start(); self.play_button.setEnabled(False); self.pause_button.setEnabled(True)

    def pause(self) -> None:
        self.animation_timer.stop(); self.play_button.setEnabled(True); self.pause_button.setEnabled(False)

    def reset_animation(self) -> None:
        if self.route is None:
            return
        self.animation_timer.stop(); self.progress = 0.0; self.overlay.set_progress(0.0)
        self.animation_status.setText(f"Ready: {self.route.distance / 1000:.2f} km • {self.route.time / 60:.1f} min")
        self.play_button.setEnabled(True); self.pause_button.setEnabled(False)

    def animate(self) -> None:
        if self.route is None:
            return
        self.progress = min(1.0, self.progress + self.animation_timer.interval() / self.duration_ms)
        self.overlay.set_progress(self.progress)
        remaining = 1 - self.progress
        self.animation_status.setText(f"Progress: {self.progress * 100:.0f}%\nRemaining: {self.route.distance * remaining / 1000:.2f} km • {self.route.time * remaining / 60:.1f} min")
        if self.progress >= 1:
            self.animation_timer.stop(); self.pause_button.setEnabled(False); self.animation_status.setText("Destination reached.")

    def show_stockholm_extent(self) -> None:
        if self.stockholm_extent is not None:
            self.viewer.set_view_extent(self.stockholm_extent)

    def closeEvent(self, event) -> None:
        self.closing = True; self.animation_timer.stop(); self.poll_timer.stop()
        self.executor.shutdown(wait=True, cancel_futures=True); self.overlay.shutdown()
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("RouteAnimation")
    app.setWindowIcon(application_icon())
    window = RouteAnimationWindow(app)
    window.show()
    QTimer.singleShot(0, window.initialize_viewer)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
