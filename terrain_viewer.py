"""Small PySide6 adapter for the Viewer3D C API shipped in GeoKernel 1.5.32."""

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QWidget
from geokernel.dll import GeoKernelDll, load_library


class TerrainViewer(QWidget):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent)
        if sys.platform != "win32":
            raise RuntimeError("This example requires the Windows x64 Viewer3D runtime.")
        self._handle = None
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setStyleSheet("background: #090f16")
        self._runtime = GeoKernelDll()
        # Existing examples always use the installed SDK. New API development
        # may explicitly supply a DLL; no source-checkout fallback is performed.
        library = Path(library).resolve() if library else self._runtime.bin_dir / "GeoKernel.Viewer3D.dll"
        if not library.is_file():
            raise RuntimeError(f"Viewer3D library not found: {library}")
        self._api = load_library(library)
        signatures = {
            "Create": (ctypes.c_void_p, [ctypes.c_void_p]),
            "Destroy": (None, [ctypes.c_void_p]),
            "LastError": (ctypes.c_char_p, []),
            "Resize": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
            "LoadTerrain": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]),
            "PollLoad": (ctypes.c_int, [ctypes.c_void_p]),
            "CancelLoad": (None, [ctypes.c_void_p]),
            "SetColorRamp": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
            "SetHeightScale": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_float]),
            "ResetCamera": (ctypes.c_int, [ctypes.c_void_p]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self._api, "GeoKernel3D_" + name)
            function.restype = result
            function.argtypes = arguments

    def _check(self, result):
        if result < 0:
            message = self._api.GeoKernel3D_LastError()
            raise RuntimeError(message.decode("utf-8") if message else "Viewer3D failed.")
        return result

    def initialize(self):
        if QThread.currentThread() != self.thread():
            raise RuntimeError("Viewer3D must run on the GUI thread.")
        if self._handle:
            return
        self._handle = self._api.GeoKernel3D_Create(int(self.winId()))
        if not self._handle:
            self._check(-1)
        self._resize()

    def _resize(self):
        if self._handle:
            ratio = self.devicePixelRatioF()
            self._check(self._api.GeoKernel3D_Resize(
                self._handle, round(self.width() * ratio), round(self.height() * ratio)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize()

    def load_terrain(self, path, resolution):
        self.initialize()
        self._check(self._api.GeoKernel3D_LoadTerrain(
            self._handle, str(Path(path).resolve()).encode("utf-8"), resolution))

    def enable_imagery_api(self):
        """Resolve the newer imagery API before starting downloads or a native load."""
        signatures = {
            "LoadTerrainAndImagery": (
                ctypes.c_int,
                [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int],
            ),
            "SetImageryVisible": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
        }
        for name, (result, arguments) in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError(
                    "This SDK does not include the terrain imagery API. "
                    "Install geokernel==1.5.32 to use this Viewer3D API."
                ) from error
            function.restype = result
            function.argtypes = arguments

    def load_terrain_and_imagery(self, path, imagery_path, resolution):
        self.initialize()
        self._check(self._api.GeoKernel3D_LoadTerrainAndImagery(
            self._handle,
            str(Path(path).resolve()).encode("utf-8"),
            str(Path(imagery_path).resolve()).encode("utf-8"),
            resolution,
        ))

    def set_imagery_visible(self, visible):
        if self._handle:
            self._check(self._api.GeoKernel3D_SetImageryVisible(
                self._handle, int(visible)))

    def enable_roads_api(self):
        signatures = {
            "LoadRoadsOnTerrain": [ctypes.c_void_p, ctypes.c_char_p,
                                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int],
            "SetRoadStyle": [ctypes.c_void_p, ctypes.c_int, ctypes.c_float,
                             ctypes.c_int, ctypes.c_int, ctypes.c_int],
            "GetRoadVertexCount": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64)],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError(
                    "Install geokernel==1.5.32 to use this Viewer3D API."
                ) from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    def load_roads_on_terrain(self, path, imagery_path, roads_path, resolution):
        self.initialize()
        paths = [str(Path(p).resolve()).encode("utf-8")
                 for p in (path, imagery_path, roads_path)]
        self._check(self._api.GeoKernel3D_LoadRoadsOnTerrain(
            self._handle, *paths, resolution))

    def set_road_style(self, visible, opacity, color):
        if self._handle:
            self._check(self._api.GeoKernel3D_SetRoadStyle(
                self._handle, int(visible), opacity,
                color.red(), color.green(), color.blue()))

    def get_road_vertex_count(self):
        count = ctypes.c_uint64()
        self._check(self._api.GeoKernel3D_GetRoadVertexCount(
            self._handle, ctypes.byref(count)))
        return count.value

    def enable_buildings_api(self):
        signatures = {
            "LoadBuildingsOnTerrain": [ctypes.c_void_p, ctypes.c_char_p,
                                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_float, ctypes.c_int],
            "SetBuildingStyle": [ctypes.c_void_p, ctypes.c_int, ctypes.c_float,
                             ctypes.c_int, ctypes.c_int, ctypes.c_int],
            "GetBuildingVertexCount": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64)],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError(
                    "Install geokernel==1.5.32 to use this Viewer3D API."
                ) from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    def load_buildings_on_terrain(self, path, imagery_path, buildings_path, building_height, resolution):
        self.initialize()
        paths = [str(Path(p).resolve()).encode("utf-8")
                 for p in (path, imagery_path, buildings_path)]
        self._check(self._api.GeoKernel3D_LoadBuildingsOnTerrain(
            self._handle, *paths, building_height, resolution))

    def set_building_style(self, visible, opacity, color):
        if self._handle:
            self._check(self._api.GeoKernel3D_SetBuildingStyle(
                self._handle, int(visible), opacity,
                color.red(), color.green(), color.blue()))

    def get_building_vertex_count(self):
        count = ctypes.c_uint64()
        self._check(self._api.GeoKernel3D_GetBuildingVertexCount(
            self._handle, ctypes.byref(count)))
        return count.value

    def enable_model_api(self):
        signatures = {
            "LoadModelOnTerrain": [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
                                   ctypes.c_char_p, ctypes.c_char_p,
                                   ctypes.POINTER(ctypes.c_double), ctypes.c_int],
            "SetModelVisible": [ctypes.c_void_p, ctypes.c_int],
            "FocusModel": [ctypes.c_void_p],
            "GetModelVertexCount": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64)],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Install geokernel==1.5.32 for ModelPlacement.") from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    def load_model_on_terrain(self, dem, imagery, model, geoid, placement, resolution=512):
        import math
        if len(placement) != 7 or not all(math.isfinite(value) for value in placement):
            raise ValueError("Specify seven finite placement values.")
        self.initialize()
        paths = [str(Path(p).resolve()).encode("utf-8") for p in (dem, imagery, model, geoid)]
        values = (ctypes.c_double * 7)(*placement)
        self._check(self._api.GeoKernel3D_LoadModelOnTerrain(self._handle, *paths, values, resolution))

    def set_model_visible(self, visible):
        if self._handle:
            self._check(self._api.GeoKernel3D_SetModelVisible(self._handle, int(visible)))

    def focus_model(self):
        if self._handle:
            self._check(self._api.GeoKernel3D_FocusModel(self._handle))

    def get_model_vertex_count(self):
        count = ctypes.c_uint64()
        self._check(self._api.GeoKernel3D_GetModelVertexCount(self._handle, ctypes.byref(count)))
        return count.value

    def enable_camera_api(self):
        for name, args in {
            "GetCamera": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)],
            "MoveCamera": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int],
            "StopCamera": [ctypes.c_void_p],
        }.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Install geokernel==1.5.32 for camera navigation.") from error
            function.restype = ctypes.c_int
            function.argtypes = args

    def get_camera(self):
        values = (ctypes.c_float * 6)()
        self._check(self._api.GeoKernel3D_GetCamera(self._handle, values))
        return list(values)

    def move_camera(self, values, duration_ms=1200):
        if len(values) != 6:
            raise ValueError("A camera requires six values.")
        values = (ctypes.c_float * 6)(*values)
        self._check(self._api.GeoKernel3D_MoveCamera(self._handle, values, duration_ms))

    def stop_camera(self):
        if self._handle:
            self._check(self._api.GeoKernel3D_StopCamera(self._handle))

    def poll_load(self):
        state = self._api.GeoKernel3D_PollLoad(self._handle)
        return state if state == -2 else self._check(state)

    def cancel_load(self):
        if self._handle:
            self._api.GeoKernel3D_CancelLoad(self._handle)

    def set_color_ramp(self, ramp):
        if self._handle:
            self._check(self._api.GeoKernel3D_SetColorRamp(self._handle, ramp))

    def set_height_scale(self, value):
        if self._handle:
            self._check(self._api.GeoKernel3D_SetHeightScale(self._handle, value))

    def reset_camera(self):
        if self._handle:
            self._check(self._api.GeoKernel3D_ResetCamera(self._handle))

    def close_viewer(self):
        if self._handle:
            self._api.GeoKernel3D_Destroy(self._handle)
            self._handle = None
