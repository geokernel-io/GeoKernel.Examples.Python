"""Shared support for the DSM-to-DTM examples.

Verified sample acquisition (pinned ZIP and per-file SHA-256), process-local PROJ/GDAL
configuration and numeric raster IO through the GDAL runtime shipped with the SDK.
No NumPy or rasterio dependency; all functions may run on a worker thread.
"""
from __future__ import annotations

import ctypes as ct
import hashlib
import json
import math
import os
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from geokernel.dll import find_bin_dir, load_library

ROOT_DIR = Path(__file__).resolve().parent
Progress = Callable[[int, str], None]


class Cancelled(RuntimeError):
    def __init__(self):
        super().__init__("Operation cancelled.")


def check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise Cancelled()


def read_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid JSON: {path}")
    return value


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def valid_sample(folder: Path, assets: dict) -> bool:
    files = assets.get("files") or {}
    return bool(files) and all(hash_file(folder / name) == expected for name, expected in files.items())


SAMPLE_HINT = "The sample ZIP must be uploaded to the SampleData v1 release. Use Retry after upload."


def _download(url: str, destination: Path, cancel: threading.Event, progress: Progress, agent: str,
              hint: str = SAMPLE_HINT, label: str = "Downloading sample data...") -> None:
    if not url.lower().startswith("https://"):
        raise RuntimeError("Sample URL must use HTTPS.")
    partial = destination.with_name(destination.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as file:
            status = getattr(response, "status", 200)
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                check_cancel(cancel)
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                file.write(chunk)
                done += len(chunk)
                progress(int(100 * done / total) if total else 0, label)
        partial.replace(destination)
    except Cancelled:
        partial.unlink(missing_ok=True)
        raise
    except Exception as error:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Sample download failed: {error}\n{url}\n{hint}") from error


def prepare_sample(assets: dict, root: Path, local_archive: str | None, url: str,
                   cancel: threading.Event, progress: Progress,
                   agent: str = "GeoKernel-DsmToDtm-Python/1.0", hint: str = SAMPLE_HINT) -> Path:
    """Return a verified sample folder; download/extract only when the cache is invalid."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    folder = root / assets["cache"]
    progress(0, "Checking cached sample files...")
    if valid_sample(folder, assets):
        return folder

    archive = Path(local_archive) if local_archive else root / assets["archive"]
    expected = assets["sha256"]
    if not local_archive and hash_file(archive) != expected:
        _download(url, archive, cancel, progress, agent, hint)
    check_cancel(cancel)
    if hash_file(archive) != expected:
        raise RuntimeError("Sample ZIP SHA-256 mismatch. The existing data was retained.")

    staging = Path(tempfile.mkdtemp(prefix=".extract-", dir=root))
    try:
        progress(0, "Extracting verified sample ZIP...")
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                check_cancel(cancel)
                target = (staging / member.filename).resolve()
                if staging.resolve() not in target.parents and target != staging.resolve():
                    raise RuntimeError("Sample ZIP contains an unsafe path.")
                source.extract(member, staging)
        if not valid_sample(staging, assets):
            raise RuntimeError("Extracted sample files failed SHA-256 verification.")
        if folder.exists():
            folder.rename(folder.with_name(f"{folder.name}.invalid-{int(time.time() * 1000)}"))
        staging.rename(folder)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return folder


def configure_runtime(sample_folder: Path | None = None) -> None:
    """Prefer SDK-local proj-data, then the verified sample database; process-local only."""
    bin_dir = find_bin_dir()
    gdal_data = bin_dir / "gdal-data"
    if gdal_data.is_dir():
        os.environ["GDAL_DATA"] = str(gdal_data)
    if sample_folder is None:
        return
    sdk_proj = bin_dir / "proj-data"
    proj = sdk_proj if (sdk_proj / "proj.db").is_file() else Path(sample_folder) / "proj-data"
    if not (proj / "proj.db").is_file():
        raise RuntimeError("Sample projection database is missing.")
    os.environ["PROJ_DATA"] = str(proj)
    os.environ["PROJ_LIB"] = str(proj)
    os.environ["PROJ_NETWORK"] = "OFF"
    _gdal().set_proj_path(proj)


class _Gdal:
    def __init__(self):
        self.lib = load_library(find_bin_dir() / "gdal.dll")
        p, i, s, d = ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_double
        declarations = {
            "GDALAllRegister": ([], None),
            "GDALOpen": ([s, i], p),
            "GDALClose": ([p], None),
            "GDALGetRasterXSize": ([p], i),
            "GDALGetRasterYSize": ([p], i),
            "GDALGetRasterCount": ([p], i),
            "GDALGetRasterBand": ([p, i], p),
            "GDALGetRasterNoDataValue": ([p, ct.POINTER(i)], d),
            "GDALSetRasterNoDataValue": ([p, d], i),
            "GDALRasterIO": ([p, i, i, i, i, i, p, i, i, i, i, i], i),
            "GDALGetGeoTransform": ([p, ct.POINTER(d)], i),
            "GDALSetGeoTransform": ([p, ct.POINTER(d)], i),
            "GDALGetProjectionRef": ([p], s),
            "GDALSetProjection": ([p, s], i),
            "GDALGetDriverByName": ([s], p),
            "GDALCreate": ([p, s, i, i, i, i, p], p),
            "CPLGetLastErrorMsg": ([], s),
            "OSRNewSpatialReference": ([s], p),
            "OSRDestroySpatialReference": ([p], None),
            "OSRImportFromEPSG": ([p, i], i),
            "OSRSetFromUserInput": ([p, s], i),
            "OSRIsSame": ([p, p], i),
            "OSRSetPROJSearchPaths": ([ct.POINTER(s)], None),
        }
        for name, (arguments, result) in declarations.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = arguments, result
        self.lib.GDALAllRegister()
        self.lock = threading.Lock()

    def error(self, message: str) -> RuntimeError:
        detail = self.lib.CPLGetLastErrorMsg()
        detail = detail.decode("utf-8", "replace") if detail else ""
        return RuntimeError(f"{message} {detail}".strip())

    def set_proj_path(self, folder: Path) -> None:
        paths = (ct.c_char_p * 2)(str(folder).encode("utf-8"), None)
        self.lib.OSRSetPROJSearchPaths(paths)


_GDAL: _Gdal | None = None
_GDAL_LOCK = threading.Lock()


def _gdal() -> _Gdal:
    global _GDAL
    with _GDAL_LOCK:
        if _GDAL is None:
            _GDAL = _Gdal()
        return _GDAL


@dataclass
class Raster:
    width: int
    height: int
    transform: tuple[float, ...]
    projection: str
    nodata: float | None
    bands: list[array] = field(default_factory=list)


def read_raster(path: Path, bands: list[int] | None = None) -> Raster:
    """Read whole bands as Float32 values with GDAL's own geotransform (corner based)."""
    g = _gdal()
    lib = g.lib
    dataset = lib.GDALOpen(str(path).encode("utf-8"), 0)
    if not dataset:
        raise g.error(f"Cannot open raster {path}.")
    try:
        width, height = lib.GDALGetRasterXSize(dataset), lib.GDALGetRasterYSize(dataset)
        if width <= 0 or height <= 0 or width * height > 64_000_000:
            raise RuntimeError(f"Unsupported raster dimensions in {path}.")
        transform = (ct.c_double * 6)()
        if lib.GDALGetGeoTransform(dataset, transform) != 0:
            raise RuntimeError(f"Raster has no world transform: {path}.")
        projection = (lib.GDALGetProjectionRef(dataset) or b"").decode("utf-8")
        numbers = bands or list(range(1, lib.GDALGetRasterCount(dataset) + 1))
        result = Raster(width, height, tuple(transform), projection, None)
        for number in numbers:
            band = lib.GDALGetRasterBand(dataset, number)
            if not band:
                raise RuntimeError(f"Missing band {number} in {path}.")
            values = array("f", bytes(4 * width * height))
            buffer = (ct.c_float * len(values)).from_buffer(values)
            if lib.GDALRasterIO(band, 0, 0, 0, width, height, buffer, width, height, 6, 0, 0) != 0:
                raise g.error(f"Could not read numeric values from {path}.")
            has_nodata = ct.c_int()
            nodata = lib.GDALGetRasterNoDataValue(band, ct.byref(has_nodata))
            if number == numbers[0] and has_nodata.value:
                result.nodata = nodata
            del buffer
            result.bands.append(values)
        return result
    finally:
        lib.GDALClose(dataset)


def same_crs(projection: str, epsg: int) -> bool:
    lib = _gdal().lib
    left, right = lib.OSRNewSpatialReference(None), lib.OSRNewSpatialReference(None)
    try:
        return (lib.OSRSetFromUserInput(left, projection.encode("utf-8")) == 0
                and lib.OSRImportFromEPSG(right, epsg) == 0
                and bool(lib.OSRIsSame(left, right)))
    finally:
        lib.OSRDestroySpatialReference(left)
        lib.OSRDestroySpatialReference(right)


def write_float_geotiff(path: Path, width: int, height: int, transform, projection: str,
                        bands: list[array], nodata: float | None = -9999.0) -> Path:
    g = _gdal()
    lib = g.lib
    driver = lib.GDALGetDriverByName(b"GTiff")
    dataset = lib.GDALCreate(driver, str(path).encode("utf-8"), width, height, len(bands), 6, None)
    if not dataset:
        raise g.error(f"Cannot create GeoTIFF {path}.")
    try:
        values = (ct.c_double * 6)(*transform)
        if lib.GDALSetGeoTransform(dataset, values) != 0 or lib.GDALSetProjection(dataset, projection.encode("utf-8")) != 0:
            raise g.error("Cannot write GeoTIFF georeferencing.")
        for index, data in enumerate(bands, 1):
            if len(data) != width * height:
                raise RuntimeError("GeoTIFF band size mismatch.")
            band = lib.GDALGetRasterBand(dataset, index)
            if nodata is not None:
                lib.GDALSetRasterNoDataValue(band, nodata)
            source = data if isinstance(data, array) and data.typecode == "f" else array("f", data)
            buffer = (ct.c_float * len(source)).from_buffer(source)
            code = lib.GDALRasterIO(band, 1, 0, 0, width, height, buffer, width, height, 6, 0, 0)
            del buffer
            if code != 0:
                raise g.error("Cannot write GeoTIFF values.")
    finally:
        lib.GDALClose(dataset)
    return Path(path)


# The DSM-to-DTM sample shared by all six examples.
ZURICH_V2 = ROOT_DIR / "dsm_to_dtm-sample-assets.json"
SAMPLE_NAMES = ("dsm.tif", "dtm_classical.tif", "dtm_ai.tif", "dtm_reference.tif")


@dataclass
class Grids:
    folder: Path
    width: int
    height: int
    transform: tuple[float, ...]
    projection: str
    manifest: dict
    profile_row: int
    z: list[array]


def read_grids(folder: Path, cancel: threading.Event) -> Grids:
    """Read the four pinned 500 x 500, 0.5 m EPSG:2056 height rasters and validate them."""
    folder = Path(folder)
    manifest = read_json(folder / "source-manifest.json")
    profile_row = int(manifest.get("profile", {}).get("row", -1))
    grids: Grids | None = None
    z: list[array] = []
    for index, name in enumerate(SAMPLE_NAMES):
        check_cancel(cancel)
        raster = read_raster(folder / name, [1])
        if not same_crs(raster.projection, 2056):
            raise RuntimeError("The sample height CRS is not equivalent to EPSG:2056.")
        t = raster.transform
        if not (raster.width == 500 and raster.height == 500 and t[1] == .5 and t[5] == -.5 and t[2] == 0 and t[4] == 0):
            raise RuntimeError(
                f"The sample requires the pinned 500 x 500, 0.5 m grid. Found {raster.width} x {raster.height}; "
                f"pixel {t[1]}, {t[5]}; rotation {t[4]}, {t[2]}.")
        if index == 0:
            grids = Grids(folder, raster.width, raster.height, t, raster.projection, manifest, profile_row, z)
        elif raster.projection != grids.projection or t != grids.transform:
            raise RuntimeError("Height rasters do not share exactly the same CRS and grid.")
        values = raster.bands[0]
        nodata = raster.nodata
        for value in values:
            if not math.isfinite(value) or (nodata is not None and value == nodata):
                raise RuntimeError("This prepared comparison requires valid heights in all four rasters.")
        z.append(values)
    if not 0 <= profile_row < grids.height:
        raise RuntimeError("Invalid sample profile row.")
    return grids


# ----- interactive profile helpers (DsmToDtmProfile) ------------------------------------------
SURFACE_NAMES = ("Original DSM", "Classical DTM", "AI DTM", "Reference DTM")


def write_rgb_bands(path: Path, width: int, height: int, transform, projection: str,
                    bands: tuple[bytes, bytes, bytes]) -> Path:
    """Write a Byte RGB GeoTIFF (display only). Byte RGB bypasses the viewer's statistical
    stretch of non-Byte imagery, so colours keep their shared, precomputed scale."""
    g = _gdal()
    lib = g.lib
    if any(len(band) != width * height for band in bands):
        raise RuntimeError("Display image size mismatch.")
    driver = lib.GDALGetDriverByName(b"GTiff")
    dataset = lib.GDALCreate(driver, str(path).encode("utf-8"), width, height, 3, 1, None)
    if not dataset:
        raise g.error(f"Cannot create GeoTIFF {path}.")
    try:
        values = (ct.c_double * 6)(*transform)
        if lib.GDALSetGeoTransform(dataset, values) != 0 or lib.GDALSetProjection(dataset, projection.encode("utf-8")) != 0:
            raise g.error("Cannot write GeoTIFF georeferencing.")
        for index, data in enumerate(bands, 1):
            source = bytearray(data)
            buffer = (ct.c_ubyte * len(source)).from_buffer(source)
            code = lib.GDALRasterIO(lib.GDALGetRasterBand(dataset, index), 1, 0, 0, width, height, buffer,
                                    width, height, 1, 0, 0)
            del buffer
            if code != 0:
                raise g.error("Cannot write GeoTIFF values.")
    finally:
        lib.GDALClose(dataset)
    return Path(path)


def write_rgb_geotiff(path: Path, width: int, height: int, transform, projection: str, gray: bytes) -> Path:
    """Write one 8-bit gray image as identical R, G and B bands (display relief only)."""
    return write_rgb_bands(path, width, height, transform, projection, (gray, gray, gray))


def relief(grids: Grids, band: int, cancel: threading.Event) -> bytes:
    """Hillshade with one fixed light (azimuth 315°, altitude 40°) and contrast for all maps.

    No per-map normalization: identical heights give identical gray values in every relief.
    """
    w, h, z = grids.width, grids.height, grids.z[band]
    azimuth, altitude = math.radians(315), math.radians(40)
    lx, ly, lz = math.sin(azimuth) * math.cos(altitude), math.cos(azimuth) * math.cos(altitude), math.sin(altitude)
    out = bytearray(w * h)
    sqrt = math.sqrt
    for y in range(h):
        check_cancel(cancel)
        top, bottom = max(0, y - 1), min(h - 1, y + 1)
        sy = 1 / ((bottom - top) * .5)
        row, above, below = z[y * w:(y + 1) * w], z[top * w:(top + 1) * w], z[bottom * w:(bottom + 1) * w]
        left, right = row[:1] + row[:-1], row[1:] + row[-1:]
        offset = y * w
        for x in range(w):
            sx = 1.0 if 0 < x < w - 1 else 2.0
            dx, dy = (right[x] - left[x]) * sx, (above[x] - below[x]) * sy
            light = (-dx * lx - dy * ly + lz) / sqrt(dx * dx + dy * dy + 1)
            value = int(255 * (.25 + .75 * (light if light > 0 else 0)) + .5)  # round half up, as Qt
            out[offset + x] = 255 if value > 255 else value
    return bytes(out)


def sample_height(grids: Grids, band: int, x: float, y: float) -> float | None:
    """Bilinear height at a world point between pixel centres; None outside (no extrapolation)."""
    t = grids.transform
    col = (x - t[0]) / t[1] - .5
    row = (y - t[3]) / t[5] - .5
    if (not math.isfinite(col) or not math.isfinite(row) or col < -1e-7 or row < -1e-7
            or col > grids.width - 1 + 1e-7 or row > grids.height - 1 + 1e-7):
        return None
    cx, cy = min(max(col, 0.0), grids.width - 1.0), min(max(row, 0.0), grids.height - 1.0)
    ix, iy = min(int(cx), grids.width - 2), min(int(cy), grids.height - 2)
    u, v = cx - ix, cy - iy
    z, w = grids.z[band], grids.width
    i = iy * w + ix
    return ((1 - v) * ((1 - u) * z[i] + u * z[i + 1])
            + v * ((1 - u) * z[i + w] + u * z[i + w + 1]))


@dataclass
class ProfileSample:
    x: float
    y: float
    distance: float
    heights: tuple[float, float, float, float]


@dataclass
class Profile:
    start: tuple[float, float]
    end: tuple[float, float]
    length: float
    spacing: float
    samples: list[ProfileSample]
    rmse: tuple[float, float]
    mae: tuple[float, float]


def make_profile(grids: Grids, a: tuple[float, float], b: tuple[float, float], requested: float) -> Profile:
    """Equal-spaced samples, ceil(length / requested) + 1 of them (at most 4096)."""
    if sample_height(grids, 0, *a) is None or sample_height(grids, 0, *b) is None:
        raise ValueError("Choose both endpoints inside the raster pixel centres.")
    if not (math.isfinite(requested) and .5 <= requested <= 10):
        raise ValueError("Profile spacing must be between 0.5 and 10 metres.")
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length < .5:
        raise ValueError("Choose endpoints at least 0.5 m apart.")
    intervals = min(max(math.ceil(length / requested), 1), 4095)
    samples, sq, ab = [], [0.0, 0.0], [0.0, 0.0]
    for i in range(intervals + 1):
        t = i / intervals
        x, y = a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t
        heights = tuple(sample_height(grids, band, x, y) for band in range(4))
        if any(value is None for value in heights):
            raise ValueError("The transect crosses unavailable raster data.")
        for method in range(2):
            error = heights[method + 1] - heights[3]
            sq[method] += error * error
            ab[method] += abs(error)
        samples.append(ProfileSample(x, y, length * t, heights))
    n = len(samples)
    return Profile(a, b, length, length / intervals, samples,
                   (math.sqrt(sq[0] / n), math.sqrt(sq[1] / n)), (ab[0] / n, ab[1] / n))


def example_endpoints(grids: Grids) -> tuple[tuple[float, float], tuple[float, float]]:
    """The fixed building transect of the first example: row `profile.row`, west half."""
    t = grids.transform
    y = t[3] + (grids.profile_row + .5) * t[5]
    return (t[0] + .25, y), (t[0] + (grids.width - .5) * .5, y)


CSV_HEADER = ("distance_m,easting_epsg2056_m,northing_epsg2056_m,dsm_ln02_m,classical_ln02_m,"
              "ai_ln02_m,reference_ln02_m,classical_error_m,ai_error_m\n")


def _atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def export_profile(path: Path, profile: Profile, grids: Grids, archive_sha256: str) -> None:
    """Write the numeric CSV, then `<name>.csv.metadata.json`; each file atomically."""
    lines = [CSV_HEADER]
    for s in profile.samples:
        h = s.heights
        values = (s.distance, s.x, s.y, *h, h[1] - h[3], h[2] - h[3])
        lines.append(",".join(f"{value:.6f}" for value in values) + "\n")
    _atomic_write(path, "".join(lines).encode("utf-8"))
    metadata = {
        "sample_archive_sha256": archive_sha256,
        "source": grids.manifest,
        "sampling": "Bilinear numeric heights, projected metric distances",
        "line_length_m": profile.length,
        "sample_spacing_m": profile.spacing,
        "sample_count": len(profile.samples),
        "source_attribution": "Federal Office of Topography swisstopo; AI: David Perez, pix_grad adaptation",
    }
    try:
        _atomic_write(Path(str(path) + ".metadata.json"), json.dumps(metadata, indent=4).encode("utf-8"))
    except OSError as error:
        raise RuntimeError(f"CSV saved; cannot save metadata sidecar: {error}") from error


# ----- reference accuracy helpers (DsmToDtmAccuracy) --------------------------------------------
DISPLAY_LIMITS = (1.0, 2.0, 5.0, 10.0)
ERROR_BIN_EDGES = (0.25, 0.5, 1.0, 2.0, 5.0)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = int(hex_color.lstrip("#"), 16)
    return value >> 16, (value >> 8) & 0xFF, value & 0xFF


_NEUTRAL, _BELOW, _ABOVE = _rgb("#fafafa"), _rgb("#2464b5"), _rgb("#c93645")
_ORANGE, _RED = _rgb("#f4a340"), _rgb("#b22f35")


def _mix(a, b, t):
    # Round half away from zero, as Qt's lround (a channel can step downwards, so use floor/ceil by sign).
    out = []
    for x, y in zip(a, b):
        v = x + (y - x) * t
        out.append(int(math.floor(v + 0.5)) if v >= 0 else int(math.ceil(v - 0.5)))
    return tuple(out)


def error_color(error: float, absolute: bool, limit: float) -> tuple[int, int, int]:
    """Shared display scale: signed blue-white-red or absolute white-orange-red, saturating at `limit`."""
    t = min(abs(error) / limit, 1.0)
    if not absolute:
        return _mix(_NEUTRAL, _BELOW if error < 0 else _ABOVE, t)
    return _mix(_NEUTRAL, _ORANGE, t * 2) if t < 0.5 else _mix(_ORANGE, _RED, (t - 0.5) * 2)


def error_bands(grids: Grids, method: int, absolute: bool, limit: float, cancel: threading.Event):
    """R, G, B bytes of one error display map (estimate - reference)."""
    estimate, reference, w = grids.z[method], grids.z[3], grids.width
    n = len(reference)
    r, g, b = bytearray(n), bytearray(n), bytearray(n)
    color = error_color
    for y in range(grids.height):
        check_cancel(cancel)
        for i in range(y * w, (y + 1) * w):
            r[i], g[i], b[i] = color(estimate[i] - reference[i], absolute, limit)
    return bytes(r), bytes(g), bytes(b)


def pixel_window(grids: Grids, area: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """Native cells whose centres lie in the area: (left, top, width, height), clipped to the grid."""
    x_min, y_min, x_max, y_max = area
    if not all(math.isfinite(v) for v in area) or x_max <= x_min or y_max <= y_min:
        raise ValueError("Choose a nonempty finite study area.")
    t = grids.transform
    dx, dy, x0, y0 = t[1], -t[5], t[0], t[3]

    def clip(value, maximum):
        return int(min(max(value, 0.0), float(maximum)))

    left = clip(math.ceil((x_min - x0) / dx - 0.5), grids.width)
    right = clip(math.floor((x_max - x0) / dx - 0.5) + 1, grids.width)
    top = clip(math.ceil((y0 - y_max) / dy - 0.5), grids.height)
    bottom = clip(math.floor((y0 - y_min) / dy - 0.5) + 1, grids.height)
    if right <= left or bottom <= top:
        raise ValueError("The selected area contains no source pixel centres.")
    return left, top, right - left, bottom - top


def window_extent(grids: Grids, window) -> tuple[float, float, float, float]:
    """World bounds of the union of the window's cells."""
    left, top, width, height = window
    t = grids.transform
    return t[0] + left * t[1], t[3] + (top + height) * t[5], t[0] + (left + width) * t[1], t[3] + top * t[5]


def preset_area(grids: Grids, index: int) -> tuple[float, float, float, float]:
    """Geographic windows: full sample, central, northern and southern blocks (not land-cover classes)."""
    x, y, size = grids.transform[0], grids.transform[3], grids.width * 0.5
    return ((x, y - size, x + size, y),
            (x + size * 0.2, y - size * 0.8, x + size * 0.8, y - size * 0.2),
            (x, y - size * 0.35, x + size, y),
            (x, y - size, x + size, y - size * 0.65))[index]


@dataclass
class Metric:
    count: int
    rmse: float
    mae: float
    bias: float
    p95: float
    above: int
    bins: list[int]

    def json(self) -> dict:
        return {"pixels": self.count, "rmse_m": self.rmse, "mae_m": self.mae, "bias_m": self.bias,
                "p95_absolute_m": self.p95, "above_threshold_pixels": self.above,
                "above_threshold_percent": 100.0 * self.above / self.count if self.count else 0.0,
                "absolute_error_histogram": list(self.bins)}


def measure(grids: Grids, window, threshold: float) -> tuple[Metric, Metric]:
    """RMSE, MAE, bias, nearest-rank P95 of |error|, count above threshold and six-bin histogram."""
    import bisect

    if not (math.isfinite(threshold) and threshold > 0):
        raise ValueError("Error threshold must be positive.")
    left, top, width, height = window
    if width <= 0 or height <= 0 or left < 0 or top < 0 or left + width > grids.width or top + height > grids.height:
        raise ValueError("Invalid source pixel window.")
    reference, w = grids.z[3], grids.width
    result = []
    for method in (1, 2):
        estimate = grids.z[method]
        squared = absolute_sum = signed = 0.0
        above = 0
        bins = [0] * 6
        errors = []
        for y in range(top, top + height):
            start = y * w + left
            for i in range(start, start + width):
                error = estimate[i] - reference[i]
                magnitude = abs(error)
                squared += error * error
                absolute_sum += magnitude
                signed += error
                if magnitude > threshold:
                    above += 1
                bins[bisect.bisect_left(ERROR_BIN_EDGES, magnitude)] += 1
                errors.append(magnitude)
        n = len(errors)
        errors.sort()
        result.append(Metric(n, math.sqrt(squared / n), absolute_sum / n, signed / n,
                             errors[math.ceil(0.95 * n) - 1], above, bins))
    return result[0], result[1]


def export_accuracy_report(path: Path, grids: Grids, window, area_name: str, threshold: float,
                           metrics: tuple[Metric, Metric], archive_sha256: str) -> None:
    """Selected-area metrics and provenance as JSON, written atomically."""
    left, top, width, height = window
    report = {
        "schema_version": 1,
        "sample_archive_sha256": archive_sha256,
        "source_manifest": grids.manifest,
        "area_name": area_name,
        "source_pixel_window": {"column": left, "row": top, "width": width, "height": height},
        "evaluated_cell_bounds_epsg2056": list(window_extent(grids, window)),
        "pixel_footprint_m2": metrics[0].count * 0.25,
        "large_error_threshold_m": threshold,
        "p95_definition": "Nearest-rank empirical 95th percentile of absolute reference errors",
        "histogram_bin_edges_m": list(ERROR_BIN_EDGES),
        "classical": metrics[0].json(),
        "ai_pix_grad": metrics[1].json(),
        "reference_used_for_inference": False,
        "metric_scope": "Shared native pixel centres in this selected area; fixed development scene; "
                        "not held-out generalization accuracy",
        "attribution": "Federal Office of Topography swisstopo; AI: David Perez, pix_grad adaptation",
    }
    _atomic_write(path, json.dumps(report, indent=4).encode("utf-8"))
