"""Main-thread ctypes bridge to the native camera-driven tiles streamer."""

import ctypes
import json
from pathlib import Path

from terrain_viewer import TerrainViewer


class TilesViewer(TerrainViewer):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent, library=library)
        self.enable_imagery_api()
        signatures = {
            "LoadTilesTerrain": [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
                                 ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int],
            "StartTiles": [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int],
            "StopTiles": [ctypes.c_void_p, ctypes.c_int],
            "FocusTiles": [ctypes.c_void_p],
            "GetTilesState": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Required Viewer3D API is missing. Install GeoKernel 1.5.32 or newer.") from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    @staticmethod
    def encoded(path):
        return str(Path(path).resolve()).encode("utf-8")

    def load_tiles_terrain(self, dem, imagery, geoid, tiles):
        self.initialize()
        self.set_height_scale(1)
        paths = [self.encoded(p) for p in (dem, imagery, geoid, tiles)]
        self._check(self._api.GeoKernel3D_LoadTilesTerrain(self._handle, *paths, 512))

    def start_tiles(self, source, budget):
        self._check(self._api.GeoKernel3D_StartTiles(self._handle, self.encoded(source), budget))

    def stop_tiles(self, clear=False):
        self._check(self._api.GeoKernel3D_StopTiles(self._handle, int(clear)))

    def focus_tiles(self):
        self._check(self._api.GeoKernel3D_FocusTiles(self._handle))

    def tiles_state(self):
        value = ctypes.c_char_p()
        self._check(self._api.GeoKernel3D_GetTilesState(self._handle, ctypes.byref(value)))
        if value.value is None:
            raise RuntimeError("SDK returned no tiles state.")
        return json.loads(value.value.decode("utf-8"))
