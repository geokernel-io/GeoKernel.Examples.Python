"""GUI-thread bindings for the native terrain viewshed and overlay API."""
import ctypes
import json

from terrain_viewer import TerrainViewer


class ViewshedViewer(TerrainViewer):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent, library=library)
        self.enable_imagery_api()
        signatures = {
            "ConfigureViewshed": [ctypes.c_void_p, ctypes.c_double, ctypes.c_double,
                                  ctypes.c_double, ctypes.c_double, ctypes.c_int],
            "SetViewshedCapture": [ctypes.c_void_p, ctypes.c_int],
            "ViewshedAction": [ctypes.c_void_p, ctypes.c_int],
            "SetViewshedOverlay": [ctypes.c_void_p, ctypes.c_int],
            "GetViewshed": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Required Viewer3D API is missing. Install GeoKernel 1.5.32 or newer.") from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    def configure(self, eye, target, radius, spacing, width):
        self._check(self._api.GeoKernel3D_ConfigureViewshed(
            self._handle, eye, target, radius, spacing, width))

    def capture(self, enabled):
        self._check(self._api.GeoKernel3D_SetViewshedCapture(self._handle, int(enabled)))

    def overlay(self, visible):
        self._check(self._api.GeoKernel3D_SetViewshedOverlay(self._handle, int(visible)))

    def action(self, action):
        """0: calculate/resume, 1: pause, 2: clear observer and result."""
        self._check(self._api.GeoKernel3D_ViewshedAction(self._handle, action))

    def viewshed(self):
        value = ctypes.c_char_p()
        self._check(self._api.GeoKernel3D_GetViewshed(self._handle, ctypes.byref(value)))
        if value.value is None:
            raise RuntimeError("SDK returned no viewshed snapshot.")
        return json.loads(value.value.decode("utf-8"))
