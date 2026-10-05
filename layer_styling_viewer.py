"""GUI-thread adapter for the SDK's vector styling and filtering API."""
import ctypes
import json

from feature_picking_viewer import FeaturePickingViewer


class LayerStylingViewer(FeaturePickingViewer):
    def __init__(self, parent=None, *, library=None):
        super().__init__(parent, library=library)
        signatures = {
            "GetLayerStyling": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)],
            "UpdateLayerStyling": [ctypes.c_void_p, ctypes.c_char_p],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self._api, "GeoKernel3D_" + name)
            except AttributeError as error:
                raise RuntimeError("Required Viewer3D API is missing. Install GeoKernel 1.5.32 or newer.") from error
            function.restype = ctypes.c_int
            function.argtypes = arguments

    def layers(self):
        value = ctypes.c_char_p()
        self._check(self._api.GeoKernel3D_GetLayerStyling(self._handle, ctypes.byref(value)))
        if value.value is None:
            raise RuntimeError("SDK returned no layer snapshot.")
        return json.loads(value.value.decode("utf-8"))

    def update_style(self, action, layer_id="", **values):
        command = json.dumps({"action": action, "id": layer_id, **values},
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._check(self._api.GeoKernel3D_UpdateLayerStyling(self._handle, command))
