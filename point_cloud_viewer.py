"""GUI-thread bridge to the SDK's LAS/LAZ model-preview window."""

import ctypes
import json
from pathlib import Path

from PySide6.QtCore import QThread

from terrain_viewer import TerrainViewer


class PointCloudViewer(TerrainViewer):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent, library=library)
        signatures = {
            "CreatePointCloud": (ctypes.c_void_p, [ctypes.c_void_p]),
            "LoadPointCloud": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]),
            "SetPointCloudStyle": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
            "GetPointCloudState": (ctypes.c_int, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]),
        }
        for name, (result, arguments) in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Required Viewer3D API is missing. Install GeoKernel 1.5.32 or newer.") from error
            function.restype = result
            function.argtypes = arguments

    def initialize(self):
        if QThread.currentThread() != self.thread():
            raise RuntimeError("Viewer3D must run on the GUI thread.")
        if self._handle:
            return
        self._handle = self._api.GeoKernel3D_CreatePointCloud(int(self.winId()))
        if not self._handle:
            self._check(-1)
        self._resize()

    def load_cloud(self, path, limit):
        self.initialize()
        self._check(self._api.GeoKernel3D_LoadPointCloud(
            self._handle, str(Path(path).resolve()).encode("utf-8"), limit))

    def set_point_style(self, height_colors):
        self._check(self._api.GeoKernel3D_SetPointCloudStyle(self._handle, int(height_colors)))

    def cloud_state(self):
        value = ctypes.c_char_p()
        self._check(self._api.GeoKernel3D_GetPointCloudState(self._handle, ctypes.byref(value)))
        if value.value is None:
            raise RuntimeError("SDK returned no point cloud state.")
        return json.loads(value.value.decode("utf-8"))
