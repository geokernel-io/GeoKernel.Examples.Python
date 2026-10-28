"""Job-owned vector display previews using only the GDAL bundled with the SDK."""
from __future__ import annotations

import ctypes as ct
import threading
from pathlib import Path

from geokernel.dll import find_bin_dir, load_library
from geoai_support import check_cancel


def prepare_vector_preview(source: Path, cancel: threading.Event) -> Path:
    """Keep the authoritative GeoPackage untouched; convert a display-only copy."""
    check_cancel(cancel)
    output = source.with_name("viewer-preview.geojson")
    gdal = load_library(find_bin_dir() / "gdal.dll")
    pointer = ct.c_void_p
    arguments = ct.POINTER(ct.c_char_p)
    callback_type = ct.CFUNCTYPE(ct.c_int, ct.c_double, ct.c_char_p, pointer)
    signatures = {
        "GDALAllRegister": ([], None),
        "GDALOpenEx": ([ct.c_char_p, ct.c_uint, arguments, arguments, arguments], pointer),
        "GDALClose": ([pointer], None),
        "GDALVectorTranslateOptionsNew": ([arguments, pointer], pointer),
        "GDALVectorTranslateOptionsFree": ([pointer], None),
        "GDALVectorTranslateOptionsSetProgress": ([pointer, callback_type, pointer], None),
        "GDALVectorTranslate": ([ct.c_char_p, pointer, ct.c_int, ct.POINTER(pointer), pointer, ct.POINTER(ct.c_int)], pointer),
    }
    for name, (args, result) in signatures.items():
        function = getattr(gdal, name)
        function.argtypes, function.restype = args, result
    gdal.GDALAllRegister()
    dataset = gdal.GDALOpenEx(str(source).encode("utf-8"), 4, None, None, None)
    if not dataset:
        raise RuntimeError("Cannot open result polygons for display.")
    options = translated = None
    completed = False
    progress = callback_type(lambda *_: 0 if cancel.is_set() else 1)
    argv = (ct.c_char_p * 7)(b"-f", b"GeoJSON", b"-t_srs", b"EPSG:4326", b"-dim", b"XY", None)
    try:
        options = gdal.GDALVectorTranslateOptionsNew(argv, None)
        if not options:
            raise RuntimeError("Cannot initialize polygon display conversion.")
        gdal.GDALVectorTranslateOptionsSetProgress(options, progress, None)
        inputs = (pointer * 1)(dataset)
        usage_error = ct.c_int()
        translated = gdal.GDALVectorTranslate(str(output).encode("utf-8"), None, 1, inputs, options, ct.byref(usage_error))
        check_cancel(cancel)
        if not translated or usage_error.value:
            raise RuntimeError("Cannot prepare result polygon preview.")
        completed = True
    finally:
        if translated:
            gdal.GDALClose(translated)
        if options:
            gdal.GDALVectorTranslateOptionsFree(options)
        gdal.GDALClose(dataset)
        if not completed:
            output.unlink(missing_ok=True)
    check_cancel(cancel)
    return output


def apply_vector_opacity(viewer, index: int, percent: int, *, fill_color: str = "#ef5350",
                         fill_alpha: int = 110, line_rgb: str = "ffdd55", line_width: float = 1.0) -> None:
    """Set brush/outline alpha explicitly for vector backends, including zero."""
    opacity = max(0, min(100, percent)) / 100
    viewer.set_layer_style(index, dict(
        fillColor=fill_color, fillOpacity=round(fill_alpha * opacity),
        lineColor=f"#{round(255 * opacity):02x}{line_rgb}", lineWidth=line_width,
    ))
    viewer.set_layer_opacity(index, 1.0)
    viewer.refresh_layers()
