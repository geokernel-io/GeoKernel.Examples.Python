"""Main-thread bridge to native .gk3d project persistence."""
import ctypes
from pathlib import Path

from layer_styling_viewer import LayerStylingViewer


class ProjectViewer(LayerStylingViewer):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent, library=library)
        signatures = {
            "OpenProject": [ctypes.c_void_p, ctypes.c_char_p],
            "SaveProject": [ctypes.c_void_p, ctypes.c_char_p],
            "GetProjectDisplay": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
                                  ctypes.POINTER(ctypes.c_int)],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Required Viewer3D API is missing. Install GeoKernel 1.5.32 or newer.") from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    def open_project(self, path):
        self.initialize()
        self._check(self._api.GeoKernel3D_OpenProject(
            self._handle, str(Path(path).resolve()).encode("utf-8")))

    def save_project(self, path):
        self._check(self._api.GeoKernel3D_SaveProject(
            self._handle, str(Path(path).resolve()).encode("utf-8")))

    def project_display(self):
        height = ctypes.c_float()
        imagery = ctypes.c_int()
        self._check(self._api.GeoKernel3D_GetProjectDisplay(
            self._handle, ctypes.byref(height), ctypes.byref(imagery)))
        return height.value, bool(imagery.value)
