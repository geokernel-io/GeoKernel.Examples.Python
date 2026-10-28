"""Worker-only source display preparation using the SDK-shipped GDAL (no rasterio dependency)."""
from __future__ import annotations

import ctypes as ct
import math
import threading
import uuid
from pathlib import Path

from geokernel.dll import find_bin_dir, load_library
from geoai_support import check_cancel


def prepare_flood_rgb(source: Path, cache: Path, cancel: threading.Event) -> Path:
    return _prepare_rgb(source, cache, cancel, fields=False)


def prepare_fields_rgb(source: Path, cache: Path, cancel: threading.Event) -> Path:
    return _prepare_rgb(source, cache, cancel, fields=True)


def prepare_super_resolution_rgb(source: Path, cache: Path, cancel: threading.Event) -> Path:
    return _prepare_rgb(source, cache, cancel, fields=True, super_resolution=True)


def _prepare_rgb(source: Path, cache: Path, cancel: threading.Event, *, fields: bool,
                 super_resolution: bool = False) -> Path:
    output = cache / ("sen2sr-source-rgb-python-v1.tif" if super_resolution else
                      "prue-source-rgb-python-v1.tif" if fields else "prithvi-source-rgb-python-v1.tif")
    if output.is_file():
        check_cancel(cancel)
        return output
    temporary = cache / f"{uuid.uuid4()}.tif"
    try:
        _create_rgb(source, temporary, cancel, fields=fields, super_resolution=super_resolution)
        check_cancel(cancel)
        try:
            temporary.rename(output)
        except OSError:
            if not output.is_file():
                raise
        return output
    finally:
        temporary.unlink(missing_ok=True)


def _create_rgb(source: Path, output: Path, cancel: threading.Event, *, fields: bool,
                super_resolution: bool = False) -> None:
    gdal = load_library(find_bin_dir() / "gdal.dll")
    pointer, integer, text = ct.c_void_p, ct.c_int, ct.c_char_p
    declarations = {
        "GDALAllRegister": ([], None),
        "GDALOpen": ([text, integer], pointer),
        "GDALClose": ([pointer], None),
        "GDALGetRasterXSize": ([pointer], integer),
        "GDALGetRasterYSize": ([pointer], integer),
        "GDALGetRasterCount": ([pointer], integer),
        "GDALGetRasterBand": ([pointer, integer], pointer),
        "GDALGetRasterNoDataValue": ([pointer, ct.POINTER(integer)], ct.c_double),
        "GDALRasterIO": ([pointer, integer, integer, integer, integer, integer, pointer,
                          integer, integer, integer, integer, integer], integer),
        "GDALGetGeoTransform": ([pointer, ct.POINTER(ct.c_double)], integer),
        "GDALSetGeoTransform": ([pointer, ct.POINTER(ct.c_double)], integer),
        "GDALGetProjectionRef": ([pointer], text),
        "GDALSetProjection": ([pointer, text], integer),
        "GDALGetDriverByName": ([text], pointer),
        "GDALCreate": ([pointer, text, integer, integer, integer, integer, pointer], pointer),
        "GDALSetRasterColorInterpretation": ([pointer, integer], integer),
    }
    for name, (arguments, result) in declarations.items():
        function = getattr(gdal, name)
        function.argtypes, function.restype = arguments, result

    def checked(code):
        if code != 0:
            raise RuntimeError("GDAL could not prepare the source RGB display.")

    gdal.GDALAllRegister()
    dataset = gdal.GDALOpen(str(source).encode("utf-8"), 0)
    if not dataset:
        raise RuntimeError("Cannot open the spectral source raster.")
    destination = None
    try:
        width, height = gdal.GDALGetRasterXSize(dataset), gdal.GDALGetRasterYSize(dataset)
        if width <= 0 or height <= 0 or width * height > 16_000_000:
            raise RuntimeError("Unsupported source preview dimensions.")
        count = gdal.GDALGetRasterCount(dataset)
        if super_resolution and count not in (4, 8):
            raise RuntimeError("SEN2SR needs RGBN input.")
        if fields and not super_resolution and count != 8:
            raise RuntimeError("PRUE needs an aligned two-period eight-band stack.")
        if not fields and count not in (6, 13):
            raise RuntimeError("Prithvi needs a 13-band chip or six selected spectral bands.")
        bands = [1, 2, 3, 4] if super_resolution else list(range(1, 9)) if fields else [2, 3, 4, 9, 12, 13] if count == 13 else [1, 2, 3, 4, 5, 6]
        pixels = width * height
        valid = bytearray([1]) * pixels
        channels = [None, None, None]
        for index, number in enumerate(bands):
            check_cancel(cancel)
            band = gdal.GDALGetRasterBand(dataset, number)
            values = (ct.c_float * pixels)()
            checked(gdal.GDALRasterIO(band, 0, 0, 0, width, height, values, width, height, 6, 0, 0))
            has_nodata = integer()
            nodata = gdal.GDALGetRasterNoDataValue(band, ct.byref(has_nodata))
            for i, value in enumerate(values):
                valid[i] &= math.isfinite(value) and value >= 0 and (not has_nodata.value or value != nodata)
            if index < 3:
                channels[index if fields else 2 - index] = values
        transform = (ct.c_double * 6)()
        checked(gdal.GDALGetGeoTransform(dataset, transform))
        projection = gdal.GDALGetProjectionRef(dataset)
        destination = gdal.GDALCreate(gdal.GDALGetDriverByName(b"GTiff"), str(output).encode("utf-8"),
                                      width, height, 4, 1, None)
        if not destination:
            raise RuntimeError("Cannot create the RGB display raster.")
        checked(gdal.GDALSetGeoTransform(destination, transform))
        checked(gdal.GDALSetProjection(destination, projection))
        for channel in range(4):
            check_cancel(cancel)
            data = (ct.c_ubyte * pixels)()
            if channel == 3:
                for i in range(pixels):
                    data[i] = 255 if valid[i] else 0
            else:
                values = channels[channel]
                ordered = sorted(value for i, value in enumerate(values) if valid[i])
                if not ordered:
                    raise RuntimeError("No valid source pixels for RGB display.")
                low, high = ordered[int((len(ordered) - 1) * .02)], ordered[int((len(ordered) - 1) * .98)]
                scale = 255 / max(high - low, 1)
                for i, value in enumerate(values):
                    if valid[i]:
                        data[i] = int(max(0, min(255, (value - low) * scale)))
            band = gdal.GDALGetRasterBand(destination, channel + 1)
            checked(gdal.GDALRasterIO(band, 1, 0, 0, width, height, data, width, height, 1, 0, 0))
            checked(gdal.GDALSetRasterColorInterpretation(band, channel + 3))
    finally:
        if destination:
            gdal.GDALClose(destination)
        gdal.GDALClose(dataset)
