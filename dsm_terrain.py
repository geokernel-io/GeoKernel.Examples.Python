"""Live classical DSM-to-DTM processing (method native-multiscale-morphological-tin-v1).

Port of the Qt DsmToDtmProcessing filter: block lower envelope with the actual source pixel
of each minimum, reflected-boundary morphological openings at increasing scales with a
slope/relief/roughness height allowance, a TIN through the surviving DSM supports
(GDAL's linear gridding on the native pixel centres), retained source samples, a DSM
upper bound and QA bits. Float32 storage follows the Qt implementation: intermediate grids
are Float32 and the same subtractions are rounded to Float32 before comparisons. The
reference is never an input to `estimate`; it is only used afterwards by `score`.
All functions may run on a worker thread.
"""
from __future__ import annotations

import ctypes as ct
import json
import math
import os
import threading
from array import array
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import dsm_support as ds

NODATA = -9999.0
METHOD = "native-multiscale-morphological-tin-v1"
Progress = Callable[[int, str], None]


def f32(values) -> array:
    """Round a sequence to Float32 (the storage type of the Qt implementation)."""
    return array("f", values)


# ----- GDAL bridge --------------------------------------------------------------------------------
class _Bridge:
    """Extra GDAL/OSR entry points of the SDK runtime used by the processing example."""

    def __init__(self):
        g = ds._gdal()
        self.g, lib = g, g.lib
        p, i, d, s = ct.c_void_p, ct.c_int, ct.c_double, ct.c_char_p
        progress = ct.CFUNCTYPE(ct.c_int, ct.c_double, ct.c_char_p, ct.c_void_p)
        self.progress_type = progress
        declarations = {
            "GDALGetMaskBand": ([p], p),
            "GDALGetRasterScale": ([p, ct.POINTER(i)], d),
            "GDALGetRasterOffset": ([p, ct.POINTER(i)], d),
            "GDALGetRasterUnitType": ([p], s),
            "GDALSetRasterUnitType": ([p, s], i),
            "GDALSetMetadataItem": ([p, s, s, s], i),
            "GDALVersionInfo": ([s], s),
            "OSRIsProjected": ([p], i),
            "OSRGetLinearUnits": ([p, ct.POINTER(s)], d),
            "GDALGridContextCreate": ([i, p, ct.c_uint, ct.POINTER(d), ct.POINTER(d), ct.POINTER(d), i], p),
            "GDALGridContextProcess": ([p, d, d, d, d, ct.c_uint, ct.c_uint, i, p, progress, p], i),
            "GDALGridContextFree": ([p], None),
        }
        for name, (arguments, result) in declarations.items():
            function = getattr(lib, name)
            function.argtypes, function.restype = arguments, result
        self.lib = lib
        version = int(lib.GDALVersionInfo(b"VERSION_NUM") or 0)
        if version < 3060000:
            raise RuntimeError("The gridding bridge requires GDAL 3.6 or newer.")


_BRIDGE: _Bridge | None = None
_BRIDGE_LOCK = threading.Lock()


def bridge() -> _Bridge:
    global _BRIDGE
    with _BRIDGE_LOCK:
        if _BRIDGE is None:
            _BRIDGE = _Bridge()
        return _BRIDGE


# ----- rasters ------------------------------------------------------------------------------------
@dataclass
class Raster:
    path: str
    projection: str
    sha256: str
    width: int
    height: int
    pixel: float
    transform: tuple
    z: array
    valid: bytearray

    def extent(self):
        t = self.transform
        return t[0], t[3] - self.height * self.pixel, t[0] + self.width * self.pixel, t[3]


def _metre_projected(projection: str) -> bool:
    b = bridge()
    lib = b.g.lib
    srs = lib.OSRNewSpatialReference(None)
    try:
        if lib.OSRSetFromUserInput(srs, projection.encode("utf-8")) != 0 or not b.lib.OSRIsProjected(srs):
            return False
        name = ct.c_char_p()
        return abs(b.lib.OSRGetLinearUnits(srs, ct.byref(name)) - 1.0) < 1e-9
    finally:
        lib.OSRDestroySpatialReference(srs)


def read_raster(path: Path, cancel: threading.Event) -> Raster:
    """Single-band north-up metre heights in a projected metre CRS, with an explicit validity mask."""
    ds.check_cancel(cancel)
    b = bridge()
    lib, blib = b.g.lib, b.lib
    dataset = lib.GDALOpen(str(path).encode("utf-8"), 0)
    if not dataset:
        raise b.g.error("Cannot open height raster.")
    try:
        if lib.GDALGetRasterCount(dataset) != 1:
            raise ValueError("Use a single-band height raster.")
        band = lib.GDALGetRasterBand(dataset, 1)
        present = ct.c_int()
        scale = blib.GDALGetRasterScale(band, ct.byref(present))
        if present.value and abs(scale - 1) >= 1e-12:
            raise ValueError("Apply raster scale to metre heights before opening.")
        offset = blib.GDALGetRasterOffset(band, ct.byref(present))
        if present.value and abs(offset) >= 1e-12:
            raise ValueError("Apply raster offset before opening.")
        units = (blib.GDALGetRasterUnitType(band) or b"").decode("utf-8", "replace").lower()
        if units not in ("", "m", "metre", "meter", "metres", "meters"):
            raise ValueError("Height units must be metres. Unspecified units are assumed to be metres.")
        width, height = lib.GDALGetRasterXSize(dataset), lib.GDALGetRasterYSize(dataset)
        t = (ct.c_double * 6)()
        has_transform = lib.GDALGetGeoTransform(dataset, t) == 0
        projection = (lib.GDALGetProjectionRef(dataset) or b"").decode("utf-8")
        if not _metre_projected(projection):
            raise ValueError("Use a projected CRS with metre XY units.")
        if not (has_transform and t[2] == 0 and t[4] == 0 and t[1] > 0 and abs(t[1] + t[5]) < 1e-9):
            raise ValueError("Use a north-up raster with square pixels.")
        if not (width >= 8 and height >= 8 and width * height <= 4_000_000):
            raise ValueError("This interactive example supports 8 x 8 to 4 million source cells.")
        n = width * height
        z = array("f", bytes(4 * n))
        buffer = (ct.c_float * n).from_buffer(z)
        if lib.GDALRasterIO(band, 0, 0, 0, width, height, buffer, width, height, 6, 0, 0) != 0:
            del buffer
            raise b.g.error("Cannot read complete heights.")
        del buffer
        has_nodata = ct.c_int()
        nodata = lib.GDALGetRasterNoDataValue(band, ct.byref(has_nodata))
        mask = bytearray(n)
        mask_buffer = (ct.c_ubyte * n).from_buffer(mask)
        code = lib.GDALRasterIO(blib.GDALGetMaskBand(band), 0, 0, 0, width, height, mask_buffer, width, height, 1, 0, 0)
        del mask_buffer
        if code != 0:
            raise b.g.error("Cannot read source validity pixels.")
    finally:
        lib.GDALClose(dataset)
    no_value = float(array("f", [nodata])[0]) if has_nodata.value else None
    isfinite = math.isfinite
    valid = bytearray(1 if mask[i] and isfinite(v) and v != no_value else 0 for i, v in enumerate(z))
    count = sum(valid)
    if count < 4 or count < n * 0.05:
        raise ValueError("Insufficient valid source coverage.")
    ds.check_cancel(cancel)
    return Raster(str(Path(path).resolve()), projection, ds.hash_file(Path(path)), width, height, t[1],
                  (t[0], t[1], 0.0, t[3], 0.0, t[5]), z, valid)


def validate_reference(dsm: Raster, reference: Raster) -> None:
    lib = ds._gdal().lib
    a, b = lib.OSRNewSpatialReference(None), lib.OSRNewSpatialReference(None)
    try:
        same = (lib.OSRSetFromUserInput(a, dsm.projection.encode("utf-8")) == 0
                and lib.OSRSetFromUserInput(b, reference.projection.encode("utf-8")) == 0 and lib.OSRIsSame(a, b))
    finally:
        lib.OSRDestroySpatialReference(a)
        lib.OSRDestroySpatialReference(b)
    if not (same and dsm.width == reference.width and dsm.height == reference.height
            and dsm.transform == reference.transform):
        raise ValueError("Reference must share the DSM's exact dimensions, grid and equivalent CRS; no implicit resampling.")


def write_raster(raster: Raster, path: Path, data, kind: int) -> Path:
    """Float32 (kind 6, NoData -9999, metre units) or Byte QA (kind 1, NoData 1) GeoTIFF on the source grid."""
    b = bridge()
    lib, blib = b.g.lib, b.lib
    options = (ct.c_char_p * 3)(b"COMPRESS=DEFLATE", b"TILED=YES", None)
    dataset = lib.GDALCreate(lib.GDALGetDriverByName(b"GTiff"), str(path).encode("utf-8"), raster.width,
                             raster.height, 1, kind, ct.cast(options, ct.c_void_p))
    if not dataset:
        raise b.g.error(f"Cannot create GeoTIFF: {path}")
    try:
        if (lib.GDALSetGeoTransform(dataset, (ct.c_double * 6)(*raster.transform)) != 0
                or lib.GDALSetProjection(dataset, raster.projection.encode("utf-8")) != 0):
            raise b.g.error("Cannot write raster coordinates.")
        blib.GDALSetMetadataItem(dataset, b"GEOKERNEL_TERRAIN_METHOD", METHOD.encode(), None)
        band = lib.GDALGetRasterBand(dataset, 1)
        lib.GDALSetRasterNoDataValue(band, 1.0 if kind == 1 else NODATA)
        if kind == 6:
            blib.GDALSetRasterUnitType(band, b"metre")
        source = bytearray(data) if kind == 1 else array("f", data)
        buffer = ((ct.c_ubyte if kind == 1 else ct.c_float) * len(source)).from_buffer(source)
        code = lib.GDALRasterIO(band, 1, 0, 0, raster.width, raster.height, buffer, raster.width, raster.height, kind, 0, 0)
        del buffer
        if code != 0:
            raise b.g.error("Cannot write raster pixels.")
    finally:
        lib.GDALClose(dataset)
    return Path(path)


# ----- filter building blocks ---------------------------------------------------------------------
@dataclass
class Parameters:
    working: float = 2.0
    window: float = 64.0
    threshold: float = 0.4
    slope: float = 0.12
    terrain: float = 0.5
    retain: float = 0.35

    def json(self) -> dict:
        return {"requested_working_m": self.working, "maximum_window_m": self.window,
                "base_threshold_m": self.threshold, "slope_allowance": self.slope,
                "terrain_slope_factor": self.terrain, "retain_tolerance_m": self.retain,
                "roughness_scale_m": 0.6, "maximum_base_threshold_m": 3.0}


PRESETS = (Parameters(), Parameters(1, 80, 0.25, 0.08, 0.25, 0.2), Parameters(2, 48, 0.6, 0.16, 0.8, 0.4))


def reflect(index: int, count: int) -> int:
    while index < 0 or index >= count:
        index = -index - 1 if index < 0 else 2 * count - index - 1
    return index


def extremes(values: array, width: int, height: int, radius: int, minimum: bool, cancel) -> array:
    """Separable sliding minimum/maximum over (2r+1)² with reflected boundaries (monotonic deque)."""
    def one_pass(source, target, vertical):
        lines, length = (width, height) if vertical else (height, width)
        stride, step = (1, width) if vertical else (width, 1)
        for line in range(lines):
            ds.check_cancel(cancel)
            base = line * stride
            queue = deque()
            for k in range(-radius, length + radius):
                at = reflect(k, length)
                value = source[base + at * step]
                if minimum:
                    while queue and queue[-1][1] >= value:
                        queue.pop()
                else:
                    while queue and queue[-1][1] <= value:
                        queue.pop()
                queue.append((k, value))
                while queue[0][0] < k - radius * 2:
                    queue.popleft()
                destination = k - radius
                if destination >= 0:
                    target[base + destination * step] = queue[0][1]

    horizontal, output = array("f", values), array("f", values)
    one_pass(values, horizontal, False)
    one_pass(horizontal, output, True)
    return output


def gaussian(values: array, width: int, height: int, sigma: float, cancel) -> array:
    radius = int(math.ceil(3 * sigma))
    kernel = [math.exp(-0.5 * k * k / (sigma * sigma)) for k in range(-radius, radius + 1)]
    total = 0.0
    for v in kernel:
        total += v
    kernel = [v / total for v in kernel]
    temporary, output = array("f", values), array("f", values)
    for y in range(height):
        ds.check_cancel(cancel)
        row = y * width
        for x in range(width):
            value = 0.0
            for k in range(-radius, radius + 1):
                value += values[row + reflect(x + k, width)] * kernel[k + radius]
            temporary[row + x] = value
    for y in range(height):
        ds.check_cancel(cancel)
        for x in range(width):
            value = 0.0
            for k in range(-radius, radius + 1):
                value += temporary[reflect(y + k, height) * width + x] * kernel[k + radius]
            output[y * width + x] = value
    return output


def gradient(z: array, width: int, height: int, pixel: float) -> array:
    """Central-difference slope magnitude; height differences are Float32 as in the Qt code."""
    dx_raw, dy_raw, dx_span, dy_span = [], [], [], []
    for y in range(height):
        t, b = max(0, y - 1), min(height - 1, y + 1)
        for x in range(width):
            l, r = max(0, x - 1), min(width - 1, x + 1)
            dx_raw.append(z[y * width + r] - z[y * width + l])
            dy_raw.append(z[b * width + x] - z[t * width + x])
            dx_span.append((r - l) * pixel)
            dy_span.append((b - t) * pixel)
    dx, dy = f32(dx_raw), f32(dy_raw)
    return f32(math.hypot(dx[i] / dx_span[i], dy[i] / dy_span[i]) for i in range(width * height))


def support_map(valid, width: int, height: int, cancel) -> list[int]:
    """Four-neighbour propagation of the nearest support index (fills holes and hull fallbacks)."""
    nearest = [-1] * len(valid)
    queue = [i for i, v in enumerate(valid) if v]
    if not queue:
        raise RuntimeError("No support cells.")
    for i in queue:
        nearest[i] = i
    head = 0
    while head < len(queue):
        if head % 4096 == 0:
            ds.check_cancel(cancel)
        i = queue[head]
        head += 1
        x, y = i % width, i // width
        for n in (i - 1 if x else -1, i + 1 if x + 1 < width else -1, i - width if y else -1,
                  i + width if y + 1 < height else -1):
            if n >= 0 and nearest[n] < 0:
                nearest[n] = nearest[i]
                queue.append(n)
    return nearest


def triangulate(raster: Raster, x: list, y: list, z: list, cancel: threading.Event, progress: Progress) -> array:
    """GDAL linear (Delaunay TIN) gridding of the supports at every native pixel centre."""
    b = bridge()

    class LinearOptions(ct.Structure):  # GDALGridLinearOptions, versioned by size since GDAL 3.6
        _fields_ = [("size", ct.c_size_t), ("radius", ct.c_double), ("nodata", ct.c_double)]

    options = LinearOptions(ct.sizeof(LinearOptions), 0.0, NODATA)
    count = len(z)
    xs, ys, zs = ((ct.c_double * count)(*v) for v in (x, y, z))
    ds.check_cancel(cancel)
    progress(62, f"Triangulating {count} ground supports...")
    context = b.lib.GDALGridContextCreate(10, ct.byref(options), count, xs, ys, zs, 1)
    ds.check_cancel(cancel)
    if not context:
        raise RuntimeError("GDAL could not triangulate ground supports; check candidate distribution and SDK Qhull support.")
    try:
        def tick(fraction, _message, _user):
            progress(65 + int(fraction * 16), "Interpolating native source pixel centres...")
            return 0 if cancel.is_set() else 1

        callback = b.progress_type(tick)
        result = array("f", bytes(4 * raster.width * raster.height))
        buffer = (ct.c_float * len(result)).from_buffer(result)
        # Local x = column metres, y = row metres; output GeoTIFFs keep the real CRS.
        status = b.lib.GDALGridContextProcess(context, 0.0, raster.width * raster.pixel, 0.0,
                                              raster.height * raster.pixel, raster.width, raster.height, 6,
                                              ct.cast(buffer, ct.c_void_p), callback, None)
        del buffer
    finally:
        b.lib.GDALGridContextFree(context)
    ds.check_cancel(cancel)
    if status != 0:
        raise RuntimeError("TIN interpolation failed.")
    return result


@dataclass
class Terrain:
    parameters: Parameters
    working: float
    seconds: float
    supports: int
    dtm: array
    removed: array
    quality: bytearray
    summary: dict = field(default_factory=dict)


def estimate(dsm: Raster, p: Parameters, cancel: threading.Event, progress: Progress) -> Terrain:
    import time

    started = time.perf_counter()
    factor = max(1, int(math.floor(p.working / dsm.pixel + 0.5)))
    working = factor * dsm.pixel
    if p.window < 2 * working:
        raise ValueError("Maximum window must span at least two working cells.")
    width, height = (dsm.width + factor - 1) // factor, (dsm.height + factor - 1) // factor
    if not (width >= 3 and height >= 3 and width * height <= 262144):
        raise ValueError("Working grid must have at least 3 x 3 and at most 262144 cells. Adjust working resolution.")
    count = width * height
    low = [math.inf] * count
    minima = [-1] * count
    valid = bytearray(count)
    z, sv, sw = dsm.z, dsm.valid, dsm.width
    for y in range(dsm.height):
        ds.check_cancel(cancel)
        row = (y // factor) * width
        for x in range(sw):
            source = y * sw + x
            if sv[source]:
                cell = row + x // factor
                if z[source] < low[cell]:
                    low[cell] = z[source]
                    minima[cell] = source
                    valid[cell] = 1
    fill = support_map(valid, width, height, cancel)
    low = f32(low[i] if valid[i] else low[fill[i]] for i in range(count))
    candidates = bytearray(valid)

    def radius_for(window):
        return max(1, int(math.floor(window / working + 0.5)) // 2)

    def opening(values, radius):
        return extremes(extremes(values, width, height, radius, True, cancel), width, height, radius, False, cancel)

    progress(15, "Estimating DSM-derived slope and roughness...")
    envelope = opening(low, radius_for(p.window))
    terrain_slope = gaussian(gradient(envelope, width, height, working), width, height, 1, cancel)
    smoothed = gaussian(low, width, height, 1, cancel)
    local_slope = extremes(gradient(smoothed, width, height, working), width, height, 2, False, cancel)
    difference = f32(low[i] - smoothed[i] for i in range(count))
    variance = gaussian(f32(d * d for d in difference), width, height, 2, cancel)
    roughness = f32(math.sqrt(max(0.0, v)) for v in variance)
    weights = [1.0 / (1.0 + math.pow(r / 0.6, 4)) for r in roughness]
    windows = []
    window = max(working * 2.0, 4.0)
    while window < p.window:
        windows.append(window)
        window *= 2.0
    windows.append(p.window)
    for step, window in enumerate(windows):
        progress(20 + int(35.0 * step / len(windows)), f"Ground candidates: {window:g} m window")
        opened = opening(low, radius_for(window))
        slope = extremes(terrain_slope, width, height, radius_for(window), False, cancel)
        above = f32(low[i] - opened[i] for i in range(count))
        base = min(3.0, p.threshold + p.slope * window)
        for i in range(count):
            if candidates[i]:
                threshold = base + p.terrain * window * min(slope[i], local_slope[i]) * weights[i]
                candidates[i] = 1 if above[i] <= threshold else 0
    xs, ys, zs = [], [], []
    for i in range(count):
        if candidates[i]:
            source = minima[i]
            xs.append((source % sw + 0.5) * dsm.pixel)
            ys.append((source // sw + 0.5) * dsm.pixel)
            zs.append(z[source])
    if len(zs) < 4:
        raise ValueError("Not enough ground supports; relax parameters.")
    nearest = support_map(candidates, width, height, cancel)
    dtm = triangulate(dsm, xs, ys, zs, cancel, progress)
    n = len(z)
    removed, quality = array("f", bytes(4 * n)), bytearray(n)
    retained = fallback = clamped = border_count = 0
    border = int(math.ceil(p.window * 0.5 / dsm.pixel))
    retain = p.retain
    for row in range(dsm.height):
        ds.check_cancel(cancel)
        cell_row = (row // factor) * width
        edge_row = row < border or row >= dsm.height - border
        for col in range(sw):
            i = row * sw + col
            if not sv[i]:
                dtm[i] = removed[i] = NODATA
                quality[i] = 1
                continue
            cell = cell_row + col // factor
            qa = 0
            if dtm[i] == NODATA or not math.isfinite(dtm[i]):
                dtm[i] = low[nearest[cell]]
                qa |= 4
                fallback += 1
            if candidates[cell] and abs(array("f", [z[i] - dtm[i]])[0]) <= retain:
                dtm[i] = z[i]
                retained += 1
            else:
                qa |= 2
            if dtm[i] > z[i]:
                dtm[i] = z[i]
                qa |= 16
                clamped += 1
            if edge_row or col < border or col >= sw - border:
                qa |= 8
                border_count += 1
            removed[i] = max(0.0, z[i] - dtm[i])
            quality[i] = qa
    seconds = time.perf_counter() - started
    summary = {"method": METHOD, "effective_working_m": working, "support_points": len(zs),
               "retained_source_pixels": retained, "outside_hull_fallback_pixels": fallback,
               "upper_bound_clamped_pixels": clamped, "edge_sensitive_pixels": border_count,
               "edge_band_m": p.window * 0.5, "compute_seconds": seconds}
    progress(84, "Preparing numeric GeoTIFFs and display maps...")
    return Terrain(p, working, seconds, len(zs), dtm, removed, quality, summary)


# ----- display, scores and report -----------------------------------------------------------------
NODATA_GRAY = (0x75, 0x81, 0x8C)


def relief_bands(raster: Raster, z, cancel) -> tuple[bytes, bytes, bytes]:
    """Hillshade (azimuth 315°, altitude 40°) on true pixel spacing; NoData gray."""
    w, h, valid, pixel = raster.width, raster.height, raster.valid, raster.pixel
    az, alt = math.radians(315), math.radians(40)
    lx, ly, lz = math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt)
    r, g, b = bytearray(w * h), bytearray(w * h), bytearray(w * h)
    for y in range(h):
        ds.check_cancel(cancel)
        t, bt = max(0, y - 1), min(h - 1, y + 1)
        for x in range(w):
            i = y * w + x
            if not valid[i]:
                r[i], g[i], b[i] = NODATA_GRAY
                continue
            here = z[i]
            l, rr = max(0, x - 1), min(w - 1, x + 1)

            def at(xx, yy):
                k = yy * w + xx
                return z[k] if valid[k] else here

            dx = (at(rr, y) - at(l, y)) / ((rr - l) * pixel)
            dy = (at(x, t) - at(x, bt)) / ((bt - t) * pixel)
            light = (-dx * lx - dy * ly + lz) / math.sqrt(dx * dx + dy * dy + 1.0)
            gray = min(255, max(0, int(math.floor(255 * (0.25 + 0.75 * max(0.0, light)) + 0.5))))
            r[i] = g[i] = b[i] = gray
    return bytes(r), bytes(g), bytes(b)


def _blend(a, b, t):
    t = min(max(t, 0.0), 1.0)
    return tuple(int(math.floor(x + (y - x) * t + 0.5)) for x, y in zip(a, b))


_WHITE, _RED, _BLUE, _ERR_RED = ds._rgb("#fafafa"), ds._rgb("#bc3e31"), ds._rgb("#2464b5"), ds._rgb("#c93645")
_QA_COLORS = {"fallback": ds._rgb("#a743a6"), "edge": ds._rgb("#e8ad49"), "interp": ds._rgb("#edf3f5"),
              "retained": ds._rgb("#15969b")}


def diagnostic_bands(dsm: Raster, terrain: Terrain, mode: int, reference: Raster | None, cancel):
    """0 removed height (0-20 m), 1 support/edge quality, 2 signed reference error (-2..+2 m)."""
    n = dsm.width * dsm.height
    r, g, b = bytearray(n), bytearray(n), bytearray(n)
    for y in range(dsm.height):
        ds.check_cancel(cancel)
        for i in range(y * dsm.width, (y + 1) * dsm.width):
            color = NODATA_GRAY
            if dsm.valid[i]:
                if mode == 0:
                    color = _blend(_WHITE, _RED, terrain.removed[i] / 20.0)
                elif mode == 1:
                    qa = terrain.quality[i]
                    color = _QA_COLORS["fallback" if qa & 4 else "edge" if qa & 8 else "interp" if qa & 2 else "retained"]
                elif reference is not None and reference.valid[i]:
                    error = terrain.dtm[i] - reference.z[i]
                    color = _blend(_WHITE, _BLUE, -error / 2.0) if error < 0 else _blend(_WHITE, _ERR_RED, error / 2.0)
            r[i], g[i], b[i] = color
    return bytes(r), bytes(g), bytes(b)


@dataclass
class Score:
    count: int = 0
    rmse: float = 0.0
    mae: float = 0.0
    bias: float = 0.0

    def json(self) -> dict:
        has = self.count > 0
        return {"pixels": self.count, "rmse_m": self.rmse if has else None, "mae_m": self.mae if has else None,
                "bias_m": self.bias if has else None}


def score(dsm: Raster, result, reference: Raster | None, border: int = 0) -> Score:
    s = Score()
    if reference is None:
        return s
    squared = absolute = signed = 0.0
    for y in range(border, dsm.height - border):
        for i in range(y * dsm.width + border, (y + 1) * dsm.width - border):
            if dsm.valid[i] and reference.valid[i]:
                e = result[i] - reference.z[i]
                s.count += 1
                squared += e * e
                absolute += abs(e)
                signed += e
    if s.count:
        s.rmse, s.mae, s.bias = math.sqrt(squared / s.count), absolute / s.count, signed / s.count
    return s


def report_for(dsm: Raster, reference: Raster | None, manifest: dict, terrain: Terrain, all_score: Score,
               interior: Score) -> dict:
    return {
        "schema_version": 1,
        "method": METHOD,
        "parameters": terrain.parameters.json(),
        "summary": terrain.summary,
        "source_dsm": dsm.path,
        "source_sha256": dsm.sha256,
        "reference": reference.path if reference else None,
        "reference_sha256": reference.sha256 if reference else None,
        "reference_used_for_processing": False,
        "grid": {"width": dsm.width, "height": dsm.height, "geotransform": list(dsm.transform), "crs_wkt": dsm.projection},
        "source_manifest": manifest,
        "all_valid_reference_error": all_score.json(),
        "interior_reference_error": interior.json(),
        "edge_band_definition": "Half the requested maximum window, rounded up to source cells",
        "quality_bits": {"1": "Source NoData", "2": "Interpolated (not explicitly retained source sample)",
                         "4": "Outside TIN hull: grid-support fallback", "8": "Edge-sensitive band",
                         "16": "Prediction clamped to DSM"},
        "height_units": "metre; unspecified source units assumed metres; no vertical datum conversion",
        "processing_scope": "This input raster only. Supply surrounding DSM context and crop afterward to reduce boundary effects.",
    }


def atomic_copy(source: Path, target: Path, cancel: threading.Event) -> None:
    target = Path(target)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with open(source, "rb") as reader, open(temporary, "wb") as writer:
            while True:
                ds.check_cancel(cancel)
                block = reader.read(1024 * 1024)
                if not block:
                    break
                writer.write(block)
            writer.flush()
            os.fsync(writer.fileno())
        ds.check_cancel(cancel)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json(path: Path, value: dict) -> None:
    ds._atomic_write(Path(path), json.dumps(value, indent=4).encode("utf-8"))


def same_file(a: str | Path, b: str | Path) -> bool:
    def canonical(p):
        p = Path(p)
        return os.path.normcase(str(p.resolve() if p.exists() else p.absolute()))
    return canonical(a) == canonical(b)

