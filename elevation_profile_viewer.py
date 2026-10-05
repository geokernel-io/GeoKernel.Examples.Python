"""Main-thread bridge to the native terrain profile API."""

import ctypes
import json

from terrain_viewer import TerrainViewer


class ElevationProfileViewer(TerrainViewer):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent, library=library)
        self.enable_imagery_api()
        signatures = {
            "SetProfileMode": [ctypes.c_void_p, ctypes.c_int, ctypes.c_double],
            "EditProfile": [ctypes.c_void_p, ctypes.c_int],
            "GetProfile": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Required Viewer3D API is missing. Install GeoKernel 1.5.32 or newer.") from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    def profile_mode(self, capture, spacing):
        self._check(self._api.GeoKernel3D_SetProfileMode(self._handle, int(capture), float(spacing)))

    def edit_profile(self, undo):
        self._check(self._api.GeoKernel3D_EditProfile(self._handle, int(undo)))

    def profile(self):
        value = ctypes.c_char_p()
        self._check(self._api.GeoKernel3D_GetProfile(self._handle, ctypes.byref(value)))
        if value.value is None:
            raise RuntimeError("SDK returned no profile snapshot.")
        # Copy the borrowed native string before the next profile call.
        return json.loads(value.value.decode("utf-8"))
