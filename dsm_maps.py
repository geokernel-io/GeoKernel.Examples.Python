"""Native GeoKernel 2D map with the overlay calls the DSM-to-DTM examples use.

geokernel 1.5.40 does not yet wrap SetOverlayPoint, RemoveOverlayShape and AddTextShape,
which the 1.5.40 runtime exports; NativeMap calls them through ctypes.
"""
from __future__ import annotations

import ctypes as ct

from geokernel import Viewer


class NativeMap(Viewer):
    """geokernel.Viewer plus three calls exported by the 1.5.40 runtime but not yet wrapped.

    Overlay points move without re-rendering the map (hover cursor); text shapes are
    labels that follow a world point (A/B tags) and are removed by clear_shapes().
    """

    def _native(self, name: str, arguments: list):
        function = getattr(self._dll.viewer, name)
        function.argtypes, function.restype = arguments, ct.c_bool
        return function

    def set_overlay_point(self, key: str, x: float, y: float, style: dict) -> bool:
        function = self._native("GeoKernelViewer_SetOverlayPoint",
                                [ct.c_void_p, ct.c_wchar_p, ct.c_double, ct.c_double, ct.c_wchar_p])
        return bool(function(self._handle, key, float(x), float(y), self._json_text(style)))

    def remove_overlay_shape(self, key: str) -> bool:
        return bool(self._native("GeoKernelViewer_RemoveOverlayShape", [ct.c_void_p, ct.c_wchar_p])(self._handle, key))

    def add_text_shape(self, x: float, y: float, text: str, style: dict) -> bool:
        function = self._native("GeoKernelViewer_AddTextShape",
                                [ct.c_void_p, ct.c_double, ct.c_double, ct.c_wchar_p, ct.c_wchar_p])
        return bool(function(self._handle, float(x), float(y), text, self._json_text(style)))
