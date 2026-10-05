"""GUI-thread bridge to the SDK terrain mesh analysis display modes."""

import ctypes

from terrain_viewer import TerrainViewer


class TerrainAnalysisViewer(TerrainViewer):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent, library=library)
        try:
            function = self._api.GeoKernel3D_SetTerrainDisplayMode
        except AttributeError as error:
            raise RuntimeError("Required Viewer3D API is missing. Install GeoKernel 1.5.32 or newer.") from error
        function.restype = ctypes.c_int
        function.argtypes = [ctypes.c_void_p, ctypes.c_int]

    def set_display_mode(self, mode):
        if mode not in (0, 1, 2):
            raise ValueError("Display mode must be relief, slope or aspect.")
        if self._handle:
            self._check(self._api.GeoKernel3D_SetTerrainDisplayMode(self._handle, mode))
