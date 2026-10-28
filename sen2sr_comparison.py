"""Read matching source/result detail windows with the SDK-bundled GDAL."""
from __future__ import annotations

import ctypes as ct
import threading
from pathlib import Path

from geokernel.dll import find_bin_dir, load_library
from geoai_support import check_cancel


def read_detail(source: Path, enhanced: Path, cancel: threading.Event) -> dict:
    gdal = load_library(find_bin_dir() / "gdal.dll")
    pointer, integer = ct.c_void_p, ct.c_int
    signatures = {
        "GDALAllRegister": ([], None),
        "GDALOpen": ([ct.c_char_p, integer], pointer),
        "GDALClose": ([pointer], None),
        "GDALGetRasterXSize": ([pointer], integer),
        "GDALGetRasterYSize": ([pointer], integer),
        "GDALGetRasterCount": ([pointer], integer),
        "GDALGetRasterBand": ([pointer, integer], pointer),
        "GDALRasterIO": ([pointer, integer, integer, integer, integer, integer,
                          pointer, integer, integer, integer, integer, integer], integer),
    }
    for name, (args, result) in signatures.items():
        function = getattr(gdal, name)
        function.argtypes, function.restype = args, result
    check_cancel(cancel)
    gdal.GDALAllRegister()
    original = gdal.GDALOpen(str(source).encode("utf-8"), 0)
    output = None
    try:
        output = gdal.GDALOpen(str(enhanced).encode("utf-8"), 0)
        if not original or not output:
            raise RuntimeError("Cannot open the source/enhanced comparison images.")
        width, height = gdal.GDALGetRasterXSize(original), gdal.GDALGetRasterYSize(original)
        if (width < 1 or height < 1 or gdal.GDALGetRasterCount(original) < 3 or
                gdal.GDALGetRasterCount(output) < 3 or
                gdal.GDALGetRasterXSize(output) != width * 4 or
                gdal.GDALGetRasterYSize(output) != height * 4):
            raise RuntimeError("Comparison images must share a source footprint at 1× and 4× resolution.")
        size = min(96, width, height)
        x, y = (width - size) // 2, (height - size) // 2

        def read_rgb(dataset, left, top, edge):
            rgb = bytearray(edge * edge * 3)
            for channel in range(3):
                check_cancel(cancel)
                plane = (ct.c_ubyte * (edge * edge))()
                band = gdal.GDALGetRasterBand(dataset, channel + 1)
                if gdal.GDALRasterIO(band, 0, left, top, edge, edge, plane, edge, edge, 1, 0, 0):
                    raise RuntimeError("Cannot read comparison detail pixels.")
                rgb[channel::3] = bytes(plane)
            return bytes(rgb)

        return dict(source=read_rgb(original, x, y, size),
                    enhanced=read_rgb(output, x * 4, y * 4, size * 4),
                    source_size=size, enhanced_size=size * 4, source_x=x, source_y=y)
    finally:
        if output:
            gdal.GDALClose(output)
        if original:
            gdal.GDALClose(original)
