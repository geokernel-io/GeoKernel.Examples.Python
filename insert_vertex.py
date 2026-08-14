import sys
import math
from pathlib import Path
from PySide6.QtCore import QSize,Qt,QTimer
from PySide6.QtGui import QAction,QIcon
from PySide6.QtWidgets import QApplication,QDockWidget,QLabel,QMainWindow,QMessageBox,QPlainTextEdit,QSpinBox,QToolBar
from geokernel import Extent,ShapeType,Viewer,ViewerEventType,ViewerTool
from common import application_icon,ensure_sample_file

EXTENT=Extent(-132.0,15.0,-55.0,55.0)
POLYGON=[(-119,28),(-109,45),(-91,42),(-83,30),(-99,22),(-115,23.5),(-119,28)]

class InsertVertexWindow(QMainWindow):
    def __init__(self,app:QApplication)->None:
        super().__init__()
        self.app=app
        self.icons=Path(__file__).with_name("images")
        self.viewer=Viewer()
        self.viewer.set_tool(ViewerTool.INFO)
        self.viewer.set_event_callback(self.on_event)
        self.widget=self.viewer.qt_widget()
        self.layer=-1
        self.vertices=list(POLYGON)
        self.initialized=False
        self.setWindowTitle("InsertVertex")
        self.setWindowIcon(application_icon())
        self.resize(1200,800)
        self.setCentralWidget(self.widget)
        self.create_toolbar()

    def create_toolbar(self)->None:
        bar=QToolBar("Editing",self)
        bar.setIconSize(QSize(32,32))
        bar.setMovable(False)
        self.addToolBar(bar)
        self.pan_action=self.make("Pan.png","Pan",self.activate_pan,True)
        self.select_action=self.make("Select.png","Select",self.activate_select,True)
        bar.addAction(self.pan_action)
        bar.addAction(self.select_action)
        self.select_action.setChecked(True)
        bar.addSeparator()
        bar.addWidget(QLabel("Part:",bar))
        self.part_spin=QSpinBox(bar)
        self.part_spin.setRange(0,0)
        bar.addWidget(self.part_spin)
        bar.addWidget(QLabel("Insert index:",bar))
        self.index_spin=QSpinBox(bar)
        self.index_spin.setRange(1,6)
        self.index_spin.setValue(2);bar.addWidget(self.index_spin)
        self.insert_action=self.make("Add.png","Insert Vertex",self.insert_vertex)
        self.reset_action=self.make("Refresh.png","Reset Shape",self.reset_shape)
        self.extent_action=self.make("FullExtent.png","Full Extent",self.viewer.full_extent)
        for action in (self.insert_action,self.reset_action,self.extent_action):
            bar.addAction(action)
            action.setEnabled(False)
        self.info=QPlainTextEdit(self)
        self.info.setReadOnly(True)
        self.info.setMinimumWidth(360)
        dock=QDockWidget("insertFeatureVertexInEditLayer",self)
        dock.setWidget(self.info)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,dock)
        self.index_spin.valueChanged.connect(self.update_info)

    def make(self,icon,text,slot,check=False)->QAction:
        action=QAction(QIcon(str(self.icons/icon)),text,self)
        action.setCheckable(check)
        action.triggered.connect(slot)
        return action

    def initialize_viewer(self)->None:
        if self.initialized:return
        self.initialized=True
        self.viewer.resize(self.widget.width(),self.widget.height())
        self.viewer.show()

        try:
            path=ensure_sample_file(
                app=self.app,
                zip_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/world_4326.zip",
                zip_name="world_4326.zip",
                target_folder="world_4326",
                required_file="world_4326.shp",
                title="InsertVertex"
            )

            self.viewer.add_layer(str(path))
            self.viewer.set_layer_style(0,{"fillColor":"#D8E5E1","fillOpacity":150,"lineColor":"#6F8883"})
            self.layer=self.viewer.add_empty_vector_layer("Insert Target",ShapeType.POLYGON,{"fillColor":"#F2D27A","fillOpacity":160,"lineColor":"#D95D39","lineWidth":2.0})
            self.reset_shape()

            for action in (self.insert_action,self.reset_action,self.extent_action):
                action.setEnabled(True)

            self.viewer.set_view_extent(EXTENT);
            self.statusBar().showMessage("Select a polygon, then click Insert Vertex.")
        except Exception as error:
            QMessageBox.critical(self,"InsertVertex",str(error))

    def begin_edit(self)->bool:
        if self.layer<0:return False
        if not self.viewer.is_layer_editing(self.layer) and not self.viewer.begin_edit_layer(self.layer):
            return False
        return self.viewer.set_active_edit_layer_index(self.layer)

    def reset_shape(self)->None:
        if self.layer<0:
            return
        if self.viewer.is_layer_editing(self.layer):
            self.viewer.rollback_edit_layer(self.layer)
        if not self.begin_edit():
            return
        self.vertices=list(POLYGON)
        self.viewer.add_polygon_to_edit_layer(self.layer,self.vertices,{"Name":"Insert target"})
        self.viewer.clear_selected_features()
        self.viewer.set_tool(ViewerTool.INFO)
        self.select_action.setChecked(True)
        self.pan_action.setChecked(False)
        self.index_spin.setRange(1,len(self.vertices)-1)
        self.index_spin.setValue(2)
        self.refresh()
        self.update_info()
        self.statusBar().showMessage("Shape reset. Select the polygon, then insert a vertex.")

    def activate_pan(self)->None:
        self.pan_action.setChecked(True)
        self.select_action.setChecked(False)
        self.viewer.set_tool(ViewerTool.PAN)

    def activate_select(self)->None:
        self.pan_action.setChecked(False)
        self.select_action.setChecked(True)
        self.viewer.set_tool(ViewerTool.INFO)

    def on_event(self,event)->None:
        if event.event_type==ViewerEventType.MAP_MOUSE_UP and self.select_action.isChecked():
            x, y=event.screen_rectangle.left, event.screen_rectangle.top
            hit=self.viewer.hit_test_top_feature_at(x,y,8)
            if not hit or hit.get("layerIndex")!=self.layer:
                self.viewer.clear_selected_features()
                self.statusBar().showMessage("No editable polygon selected.")
            elif self.viewer.select_top_feature_at(x,y,8):
                self.statusBar().showMessage(f"Selected feature {hit.get('featureId')}.")
            self.update_info()

    def insert_vertex(self)->None:
        if self.viewer.selected_feature_count()<=0:
            self.statusBar().showMessage("Select a polygon first.")
            return
        index=self.index_spin.value()
        if index<=0 or index>=len(self.vertices):
            self.statusBar().showMessage("Invalid part/index for selected feature.")
            return
        a=self.vertices[index-1]
        b=self.vertices[index]
        dx=b[0]-a[0]
        dy=b[1]-a[1]
        length=math.hypot(dx,dy)
        offset=length*0.22 if length>0.0 else 1.0
        divisor=length if length>0.0 else 1.0
        x=(a[0]+b[0])*0.5-(dy/divisor)*offset
        y=(a[1]+b[1])*0.5+(dx/divisor)*offset

        if self.viewer.insert_selected_feature_vertex_in_edit_layer(0,index,x,y):
            self.vertices.insert(index,(x,y))
            self.refresh()
            self.index_spin.setRange(1,len(self.vertices)-1)
            self.index_spin.setValue(min(index+1,len(self.vertices)-1))
            self.update_info()
            self.statusBar().showMessage(f"insertFeatureVertexInEditLayer(feature, 0, {index}, point) succeeded.")
        else:
            self.statusBar().showMessage("insertFeatureVertexInEditLayer failed.")

    def update_info(self)->None:
        selected=self.viewer.selected_features() if self.layer>=0 else []
        lines=[
            "Workflow:",
            "1. Choose Select and click the editable polygon.",
            "2. Choose the insertion index.",
            "3. Click Insert Vertex. A visible offset point is added near the segment.",
            "",
            f"Layer index: {self.layer}",
            f"Selected features: {len(selected)}",
            f"Part index: {self.part_spin.value()}",
            f"Insert index: {self.index_spin.value()}",
            f"Vertex count: {max(0,len(self.vertices)-1)}",
        ]
        self.info.setPlainText("\n".join(lines))

    def refresh(self)->None:
        self.viewer.invalidate_render_cache(False,True)
        self.viewer.refresh_layers()

    def closeEvent(self,event)->None:
        try:self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)

def main()->None:
    app=QApplication(sys.argv)
    app.setApplicationName("InsertVertex")
    app.setWindowIcon(application_icon())
    window=InsertVertexWindow(app)
    window.show()
    QTimer.singleShot(0,window.initialize_viewer)
    sys.exit(app.exec())

if __name__=="__main__":
    main()
