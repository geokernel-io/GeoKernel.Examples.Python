"""Small PySide6 adapter for the Viewer3D C API shipped in GeoKernel 1.5.30."""

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QWidget
from geokernel.dll import GeoKernelDll, load_library


class TerrainViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        if sys.platform != "win32":
            raise RuntimeError("This example requires the Windows x64 Viewer3D runtime.")
        self._handle = None
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setStyleSheet("background: #090f16")
        self._runtime = GeoKernelDll()
        library = self._runtime.bin_dir / "GeoKernel.Viewer3D.dll"
        if not library.is_file():
            raise RuntimeError("Install geokernel==1.5.30 to use TerrainLoading.")
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
