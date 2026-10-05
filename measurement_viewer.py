"""Main-thread bridge to the native physical-ENU measurement API."""

import ctypes
import json

from terrain_viewer import TerrainViewer


class MeasurementViewer(TerrainViewer):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent, library=library)
        self.enable_imagery_api()
        signatures = {
            "SetMeasurementMode": [ctypes.c_void_p, ctypes.c_int, ctypes.c_int],
            "EditMeasurement": [ctypes.c_void_p, ctypes.c_int],
            "GetMeasurement": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Required Viewer3D API is missing. Install GeoKernel 1.5.32 or newer.") from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    def measurement_mode(self, area, capture):
        self._check(self._api.GeoKernel3D_SetMeasurementMode(self._handle, int(area), int(capture)))

    def edit_measurement(self, undo):
        self._check(self._api.GeoKernel3D_EditMeasurement(self._handle, int(undo)))

    def measurement(self):
        value = ctypes.c_char_p()
        self._check(self._api.GeoKernel3D_GetMeasurement(self._handle, ctypes.byref(value)))
        if value.value is None:
            raise RuntimeError("SDK returned no measurement snapshot.")
        # Copy the borrowed native string before the next measurement call.
        return json.loads(value.value.decode("utf-8"))
