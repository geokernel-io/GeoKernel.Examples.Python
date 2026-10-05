"""Main-thread bridge to the SDK's vector selection API."""

import ctypes
import json
from pathlib import Path

from terrain_viewer import TerrainViewer


class FeaturePickingViewer(TerrainViewer):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent, library=library)
        self.enable_imagery_api()
        self.enable_roads_api()
        self.enable_buildings_api()
        signatures = {
            "LoadFeaturesOnTerrain": [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
                                      ctypes.c_char_p, ctypes.c_char_p, ctypes.c_float, ctypes.c_int],
            "GetFeatureSelection": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)],
            "SetMultipleSelection": [ctypes.c_void_p, ctypes.c_int],
            "ActivateSelection": [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64],
            "ClearSelection": [ctypes.c_void_p],
            "FocusSelection": [ctypes.c_void_p],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Required Viewer3D API is missing. Install GeoKernel 1.5.32 or newer.") from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    def load_features(self, dem, imagery, roads, buildings, resolution=512):
        self.initialize()
        paths = [str(Path(p).resolve()).encode("utf-8") for p in (dem, imagery, roads, buildings)]
        self._check(self._api.GeoKernel3D_LoadFeaturesOnTerrain(self._handle, *paths, 9.0, resolution))

    def selection(self):
        value = ctypes.c_char_p()
        self._check(self._api.GeoKernel3D_GetFeatureSelection(self._handle, ctypes.byref(value)))
        if value.value is None:
            raise RuntimeError("SDK returned no selection snapshot.")
        # Copy and decode before the SDK's next selection read. IDs stay strings.
        return json.loads(value.value.decode("utf-8"))

    def multiple_selection(self, enabled):
        self._check(self._api.GeoKernel3D_SetMultipleSelection(self._handle, int(enabled)))

    def activate_selection(self, revision, index):
        return self._check(self._api.GeoKernel3D_ActivateSelection(
            self._handle, int(revision), int(index))) == 1

    def clear_selection(self):
        self._check(self._api.GeoKernel3D_ClearSelection(self._handle))

    def focus_selection(self):
        self._check(self._api.GeoKernel3D_FocusSelection(self._handle))
