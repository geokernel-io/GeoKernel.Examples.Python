"""Oosterwold building change analysis and review with the published Python SDK.



The native HOTOSM task supplies instance polygons. A second FloatBands pass

supplies matching scores; sigmoid runs after logit blending, so results can

slightly differ from the Qt example's per-tile decoded scores.

"""

# UI event boundaries report native/worker errors without terminating the app.
# ruff: noqa: BLE001
from __future__ import annotations

import copy
import ctypes as ct
import hashlib
import json
import math
import queue
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from geoai_support import HOTOSM, check_cancel, configure_sdk, prepare_asset

configure_sdk()
# SDK runtime selection must happen before importing its native bindings.
# isort: split
from geokernel import AI, AITasks, Viewer, ViewerEventType, ViewerTool
from geokernel.dll import find_bin_dir, load_library
from geokernel.native import SIGNATURES
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# The published Python wrapper omits this existing 1.5.39 C API entry point.
# Register its signature before Viewer construction and use the public raw API.
SIGNATURES.setdefault(
    "GeoKernelViewer_SelectFeatureHit",
    ("bool", ("void_p", "double", "double", "double", "int", "int", "int")),
)
DATA_URL = "https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/almere_oosterwold_change_2016_2025_v1.zip"
DATA_SHA = "ecc35ef2c6bbdd586adc6ecc812ce1c74aee62fbf8e404de1d63b75bf7137a88"
FILES = ("oosterwold_2016-epsg25831-50cm.tif", "oosterwold_2025-epsg25831-50cm.tif")
HASHES = (
    "db723783db4c8738a716fe8b898de2e3099bab9394e335bd489db2412ae0c5c3",
    "7b1b12d8b27cd0714f140415004daf9fd0000495eda31366c7cd4aab218caa82",
)
BOUNDS = (657533.0, 5800382.0, 658557.0, 5801406.0)
DEMO = (657885.0, 5800734.0, 658205.0, 5801054.0)
ATTRIBUTION = "Beeldmateriaal Nederland / PDOK, 2016 & 2025, CC BY 4.0. WMS crop/reprojection rendered at 0.5 m. Model: HOTOSM / Meta DINOv3; retain package licenses."
PROFILES = {
    "Conservative": {
        "area": 50.0,
        "coverage": 0.10,
        "tolerance": 2.0,
        "own": 0.75,
        "other": 0.20,
    },
    "Balanced": {
        "area": 20.0,
        "coverage": 0.20,
        "tolerance": 1.0,
        "own": 0.55,
        "other": 0.35,
    },
}


def digest(value) -> str:
    if isinstance(value, Path):
        checksum = hashlib.sha256()
        with value.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                checksum.update(block)
        return checksum.hexdigest()
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class Gdal:
    def __init__(self):
        self.dll = load_library(find_bin_dir() / "gdal.dll")
        p, i, s, d = ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_double
        declarations = {
            "GDALAllRegister": (None, []),
            "GDALOpen": (p, [s, i]),
            "GDALOpenEx": (p, [s, ct.c_uint, p, p, p]),
            "GDALClose": (None, [p]),
            "GDALGetDriverByName": (p, [s]),
            "GDALCreate": (p, [p, s, i, i, i, i, p]),
            "GDALAutoCreateWarpedVRT": (p, [p, s, s, i, d, p]),
            "GDALCreateCopy": (p, [p, s, p, i, p, p, p]),
            "GDALGetRasterXSize": (i, [p]),
            "GDALGetRasterYSize": (i, [p]),
            "GDALGetRasterCount": (i, [p]),
            "GDALGetRasterBand": (p, [p, i]),
            "GDALGetGeoTransform": (i, [p, ct.POINTER(d)]),
            "GDALSetGeoTransform": (i, [p, ct.POINTER(d)]),
            "GDALGetProjectionRef": (s, [p]),
            "GDALSetProjection": (i, [p, s]),
            "GDALRasterIO": (i, [p, i, i, i, i, i, p, i, i, i, i, i]),
            "GDALSetRasterColorInterpretation": (i, [p, i]),
            "GDALDatasetGetLayer": (p, [p, i]),
            "OGR_L_ResetReading": (None, [p]),
            "OGR_L_GetNextFeature": (p, [p]),
            "OGR_F_Destroy": (None, [p]),
            "OGR_F_GetGeometryRef": (p, [p]),
            "OGR_F_GetFieldIndex": (i, [p, s]),
            "OGR_F_GetFieldAsInteger": (i, [p, i]),
            "OGR_G_ExportToJson": (p, [p]),
            "OGR_G_CreateGeometryFromJson": (p, [s]),
            "OGR_G_DestroyGeometry": (None, [p]),
            "OGR_G_Clone": (p, [p]),
            "OGR_G_Area": (d, [p]),
            "OGR_G_IsValid": (i, [p]),
            "OGR_G_Transform": (i, [p, p]),
            "VSIFree": (None, [p]),
            "OSRNewSpatialReference": (p, [s]),
            "OSRImportFromEPSG": (i, [p, i]),
            "OSRSetAxisMappingStrategy": (None, [p, i]),
            "OSRDestroySpatialReference": (None, [p]),
            "OCTNewCoordinateTransformation": (p, [p, p]),
            "OCTDestroyCoordinateTransformation": (None, [p]),
            "OCTTransform": (i, [p, i, ct.POINTER(d), ct.POINTER(d), ct.POINTER(d)]),
            "GDALRasterizeLayers": (i, [p, i, p, i, p, p, p, p, p, p, p]),
        }
        for name, (result, args) in declarations.items():
            fn = getattr(self.dll, name)
            fn.restype = result
            fn.argtypes = args
            setattr(self, name, fn)
        self.GDALAllRegister()

    @staticmethod
    def check(code):
        if code:
            raise RuntimeError("GDAL operation failed.")

    def open(self, path):
        value = self.GDALOpen(str(path).encode(), 0)
        if not value:
            raise RuntimeError(f"Cannot open {path}")
        return value

    def display_raster(self, source, destination):
        """Make a WGS84 display copy; inference keeps the original metre grid."""
        ds = self.open(source)
        warped = output = None
        try:
            warped = self.GDALAutoCreateWarpedVRT(ds, None, b"EPSG:4326", 1, 0, None)
            if not warped:
                raise RuntimeError("Cannot reproject imagery for the map.")
            output = self.GDALCreateCopy(
                self.GDALGetDriverByName(b"GTiff"),
                str(destination).encode(),
                warped,
                0,
                None,
                None,
                None,
            )
            if not output:
                raise RuntimeError("Cannot create the map preview.")
            width, height, transform, _ = self.metadata(output)
            if (
                width < 1
                or height < 1
                or not (-180 <= transform[0] <= 180 and -90 <= transform[3] <= 90)
            ):
                raise ValueError("Map preview was not reprojected to WGS84.")
            return Path(destination)
        finally:
            if output:
                self.GDALClose(output)
            if warped:
                self.GDALClose(warped)
            self.GDALClose(ds)

    def metadata(self, ds):
        gt = (ct.c_double * 6)()
        self.check(self.GDALGetGeoTransform(ds, gt))
        return (
            self.GDALGetRasterXSize(ds),
            self.GDALGetRasterYSize(ds),
            tuple(gt),
            self.GDALGetProjectionRef(ds),
        )

    def read(self, ds, band, dtype=np.float32):
        w, h, _, _ = self.metadata(ds)
        a = np.empty((h, w), dtype=dtype)
        self.check(
            self.GDALRasterIO(
                self.GDALGetRasterBand(ds, band),
                0,
                0,
                0,
                w,
                h,
                a.ctypes.data,
                w,
                h,
                5 if dtype == np.int32 else 6,
                0,
                0,
            )
        )
        return a

    def crop(self, source, bounds, target):
        ds = self.open(source)
        out = None
        try:
            w, h, gt, crs = self.metadata(ds)
            if gt[1] != 0.5 or gt[5] != -0.5 or gt[2] or gt[4] or b"25831" not in crs:
                raise RuntimeError(
                    "Expected the pinned north-up EPSG:25831 0.5m imagery."
                )
            x = max(0, math.floor((bounds[0] - gt[0]) / 0.5))
            y = max(0, math.floor((gt[3] - bounds[3]) / 0.5))
            width = min(w, math.ceil((bounds[2] - gt[0]) / 0.5)) - x
            height = min(h, math.ceil((gt[3] - bounds[1]) / 0.5)) - y
            if min(width, height) <= 0:
                raise ValueError("Analysis area does not intersect the imagery.")
            out = self.GDALCreate(
                self.GDALGetDriverByName(b"GTiff"),
                str(target).encode(),
                width,
                height,
                3,
                6,
                None,
            )
            if not out:
                raise RuntimeError("Cannot create crop.")
            self.check(self.GDALSetProjection(out, crs))
            self.check(
                self.GDALSetGeoTransform(
                    out,
                    (ct.c_double * 6)(
                        gt[0] + x * 0.5, 0.5, 0, gt[3] - y * 0.5, 0, -0.5
                    ),
                )
            )
            for band in range(1, 4):
                a = np.empty((height, width), np.float32)
                self.check(
                    self.GDALRasterIO(
                        self.GDALGetRasterBand(ds, band),
                        0,
                        x,
                        y,
                        width,
                        height,
                        a.ctypes.data,
                        width,
                        height,
                        6,
                        0,
                        0,
                    )
                )
                self.check(
                    self.GDALRasterIO(
                        self.GDALGetRasterBand(out, band),
                        1,
                        0,
                        0,
                        width,
                        height,
                        a.ctypes.data,
                        width,
                        height,
                        6,
                        0,
                        0,
                    )
                )
                self.check(
                    self.GDALSetRasterColorInterpretation(
                        self.GDALGetRasterBand(out, band), band + 2
                    )
                )
        finally:
            if out:
                self.GDALClose(out)
            self.GDALClose(ds)

    def geometry(self, value, source=4326, target=25831):
        geom = self.OGR_G_CreateGeometryFromJson(json.dumps(value).encode())
        if not geom:
            raise ValueError("Invalid geometry JSON.")
        a = b = operation = None
        try:
            if not self.OGR_G_IsValid(geom):
                raise ValueError("Invalid polygon; repair it before approval.")
            if source != target:
                a = self.OSRNewSpatialReference(None)
                b = self.OSRNewSpatialReference(None)
                self.check(self.OSRImportFromEPSG(a, source))
                self.check(self.OSRImportFromEPSG(b, target))
                self.OSRSetAxisMappingStrategy(a, 0)
                self.OSRSetAxisMappingStrategy(b, 0)
                operation = self.OCTNewCoordinateTransformation(a, b)
                if not operation:
                    raise RuntimeError("Cannot transform geometry.")
                self.check(self.OGR_G_Transform(geom, operation))
            area = self.OGR_G_Area(geom)
            ptr = self.OGR_G_ExportToJson(geom)
            if not ptr:
                raise RuntimeError("Cannot serialize geometry.")
            try:
                result = json.loads(ct.string_at(ptr))
            finally:
                self.VSIFree(ptr)
            return result, area
        finally:
            self.OGR_G_DestroyGeometry(geom)
            if operation:
                self.OCTDestroyCoordinateTransformation(operation)
            if a:
                self.OSRDestroySpatialReference(a)
            if b:
                self.OSRDestroySpatialReference(b)

    def polygons_and_labels(self, path, grid):
        w, h, gt, crs = grid
        ds = self.GDALOpenEx(str(path).encode(), 4, None, None, None)
        mem = None
        if not ds:
            raise RuntimeError("Cannot open predicted polygons.")
        try:
            layer = self.GDALDatasetGetLayer(ds, 0)
            if not layer:
                raise RuntimeError("Prediction layer missing.")
            records = []
            while f := self.OGR_L_GetNextFeature(layer):
                try:
                    geom = self.OGR_F_GetGeometryRef(f)
                    if not geom or not self.OGR_G_IsValid(geom):
                        continue
                    field = self.OGR_F_GetFieldIndex(f, b"instance_id")
                    if field < 0:
                        raise RuntimeError("Missing instance_id.")
                    ptr = self.OGR_G_ExportToJson(geom)
                    try:
                        geo = json.loads(ct.string_at(ptr))
                    finally:
                        self.VSIFree(ptr)
                    records.append(
                        (
                            self.OGR_F_GetFieldAsInteger(f, field),
                            geo,
                            self.OGR_G_Area(geom),
                        )
                    )
                finally:
                    self.OGR_F_Destroy(f)
            mem = self.GDALCreate(
                self.GDALGetDriverByName(b"MEM"), b"", w, h, 1, 5, None
            )
            self.check(self.GDALSetProjection(mem, crs))
            self.check(self.GDALSetGeoTransform(mem, (ct.c_double * 6)(*gt)))
            if records:
                self.OGR_L_ResetReading(layer)
                opts = (ct.c_char_p * 2)(b"ATTRIBUTE=instance_id", None)
                self.check(
                    self.GDALRasterizeLayers(
                        mem,
                        1,
                        (ct.c_int * 1)(1),
                        1,
                        (ct.c_void_p * 1)(layer),
                        None,
                        None,
                        None,
                        opts,
                        None,
                        None,
                    )
                )
            return records, self.read(mem, 1, np.int32)
        finally:
            if mem:
                self.GDALClose(mem)
            self.GDALClose(ds)


def prepare(cancel, progress):
    before = prepare_asset(DATA_URL, DATA_SHA, FILES[0], cancel, progress)
    paths = [before, before.with_name(FILES[1])]
    for p, expected in zip(paths, HASHES):
        if digest(p) != expected:
            raise RuntimeError(f"Imagery SHA-256 mismatch: {p.name}")
    manifest = prepare_asset(
        HOTOSM.model_url, HOTOSM.model_sha, "geokernel-model.json", cancel, progress
    )
    return paths, manifest.parent


def dilate(mask, radius):
    h, w = mask.shape
    a = np.zeros_like(mask)
    b = np.zeros_like(mask)
    for dx in range(-radius, radius + 1):
        if abs(dx) < w:
            a[:, max(0, dx) : min(w, w + dx)] |= mask[:, max(0, -dx) : min(w, w - dx)]
    for dy in range(-radius, radius + 1):
        if abs(dy) < h:
            b[max(0, dy) : min(h, h + dy), :] |= a[max(0, -dy) : min(h, h - dy), :]
    return b


def analyze(paths, model, bounds, policy, threshold, provider, cancel, progress):
    started = time.monotonic()
    g = Gdal()
    dates = []
    with tempfile.TemporaryDirectory(prefix="geokernel-change-") as work:
        tasks = AITasks()
        ai = AI()
        for index, (year, path) in enumerate(zip((2016, 2025), paths)):
            check_cancel(cancel)
            crop = Path(work) / f"{year}.tif"
            g.crop(path, bounds, crop)
            task = tasks.start(
                {
                    "task": "hotosm-buildings",
                    "modelPackagePath": str(model),
                    "rasterPath": str(crop),
                    "threshold": threshold,
                    "provider": provider,
                    "intraOpThreads": 2,
                }
            )
            try:
                while True:
                    if cancel.is_set():
                        task.cancel()
                    status = task.status()
                    progress(
                        index * 45 + int(status["percent"] * 0.3),
                        f"{year}: {status['message']}",
                    )
                    if status["state"] == "failed":
                        raise RuntimeError(status.get("error", "Inference failed."))
                    if status["state"] == "cancelled":
                        check_cancel(cancel)
                    if status["state"] == "completed":
                        break
                    time.sleep(0.05)
                check_cancel(cancel)
                native = task.result()
                ds = g.open(crop)
                try:
                    grid = g.metadata(ds)
                finally:
                    g.GDALClose(ds)
                polygons, labels = g.polygons_and_labels(native["vectorPath"], grid)
                # Public FloatBands ABI has no cancellation callback. Cancellation
                # is checked before/after this pass; closing waits for the worker.
                raw = Path(work) / f"{year}-scores.tif"
                progress(index * 45 + 31, f"{year}: matching scores…")
                ai.run_raster_inference(
                    {
                        "modelPackagePath": str(model),
                        "rasterPath": str(crop),
                        "outputMode": "floatBands",
                        "outputPath": str(raw),
                        "bands": [1, 2, 3],
                        "provider": provider,
                        "intraOpThreads": 2,
                        "interOpThreads": 1,
                    }
                )
                check_cancel(cancel)
                ds = g.open(raw)
                try:
                    if g.metadata(ds) != grid:
                        raise ValueError("Score and label grids differ.")
                    logits = g.read(ds, 1)
                finally:
                    g.GDALClose(ds)
                if not np.isfinite(logits).all():
                    raise ValueError("Nonfinite building logits.")
                scores = 1 / (1 + np.exp(-np.clip(logits, -80, 80)))
                dates.append(
                    {
                        "native": native,
                        "polygons": polygons,
                        "labels": labels,
                        "scores": scores,
                        "grid": grid,
                    }
                )
            finally:
                task.close()
        if dates[0]["grid"] != dates[1]["grid"]:
            raise ValueError("Date grids differ.")
        features = []
        edge_count = 0
        matched = 0
        for idx, kind in ((1, "new"), (0, "removed")):
            check_cancel(cancel)
            own = dates[idx]
            other = dates[1 - idx]
            labels = own["labels"]
            flat = labels.ravel()
            coverage = dilate(
                other["scores"] >= 0.25, math.ceil(policy["tolerance"] / 0.5)
            )
            counts = np.bincount(flat)
            n = len(counts)
            covered = np.bincount(flat, weights=coverage.ravel(), minlength=n)
            own_scores = np.bincount(flat, weights=own["scores"].ravel(), minlength=n)
            other_scores = np.bincount(
                flat, weights=other["scores"].ravel(), minlength=n
            )
            edge = set(
                np.concatenate(
                    (labels[0], labels[-1], labels[:, 0], labels[:, -1])
                ).tolist()
            ) - {0}
            edge_count += len(edge)
            seen = set()
            for label, geometry, area in own["polygons"]:
                if (
                    label in edge
                    or counts[label] * 0.25 < policy["area"]
                    or area < policy["area"]
                ):
                    continue
                mean = own_scores[label] / counts[label]
                opposite = other_scores[label] / counts[label]
                overlap = covered[label] / counts[label]
                if (
                    mean < policy["own"]
                    or opposite > policy["other"]
                    or overlap >= policy["coverage"]
                ):
                    if label not in seen:
                        matched += 1
                        seen.add(label)
                    continue
                geographic, _ = g.geometry(geometry, 25831, 4326)
                identifier = f"{kind}-{len(features) + 1:04d}"
                features.append(
                    {
                        "type": "Feature",
                        "id": identifier,
                        "geometry": geographic,
                        "properties": {
                            "candidate_id": identifier,
                            "change_type": kind,
                            "review_status": "pending",
                            "review_note": "",
                            "reviewed_by": "",
                            "area_m2": area,
                            "source_instance_id": label,
                            "building_score": mean,
                            "other_date_score": opposite,
                            "other_date_coverage": overlap,
                            "before_year": 2016,
                            "after_year": 2025,
                        },
                    }
                )
        elapsed = time.monotonic() - started
        provenance = {
            "dataset_url": DATA_URL,
            "dataset_archive_sha256": DATA_SHA,
            "before_sha256": HASHES[0],
            "after_sha256": HASHES[1],
            "before_year": 2016,
            "after_year": 2025,
            "source_crs": "EPSG:25831",
            "model_id": "hotosm-dinov3s-buildings",
            "model_archive_sha256": HOTOSM.model_sha,
            "model_sha256": digest(model / "model.onnx"),
            "threshold": threshold,
            "filters": policy,
            "weak_building_threshold": 0.25,
            "provider": dates[0]["native"]["provider"],
            "analysis_geotransform": list(dates[0]["grid"][2]),
            "analysis_width": dates[0]["grid"][0],
            "analysis_height": dates[0]["grid"][1],
            "elapsed_seconds": elapsed,
            "attribution": ATTRIBUTION,
            "imagery_license": "https://creativecommons.org/licenses/by/4.0/",
            "method": "Native HOTOSM instances plus second FloatBands score pass; sigmoid after logit blending. Same filter policy as Qt; not bit-identical to per-tile decoded scoring. Predictions require review.",
        }
        progress(100, "Complete")
        return {
            "type": "FeatureCollection",
            "features": features,
            "geokernel_provenance": provenance,
            "stats": {
                "before": dates[0]["native"]["instances"],
                "after": dates[1]["native"]["instances"],
                "edge": edge_count,
                "matched": matched,
                "elapsed": elapsed,
            },
        }


def update_geometry(feature, geometry):
    if digest(feature["geometry"]) == digest(geometry):
        return False
    _, area = Gdal().geometry(geometry)
    feature["geometry"] = geometry
    feature["properties"].update(
        review_status="pending",
        reviewed_by="",
        review_note="Geometry edited; review again.",
        area_m2=area,
    )
    feature.pop("approved_geometry_sha256", None)
    return True


def review(feature, decision, actor, note):
    if decision not in ("approved", "rejected", "pending") or not actor.strip():
        raise ValueError("Enter a reviewer and a valid decision.")
    if decision == "approved":
        _, area = Gdal().geometry(feature["geometry"])
        feature["properties"]["area_m2"] = area
        feature["approved_geometry_sha256"] = digest(feature["geometry"])
    else:
        feature.pop("approved_geometry_sha256", None)
    feature["properties"].update(
        review_status=decision, reviewed_by=actor.strip(), review_note=note.strip()
    )


def export(result, target):
    approved = []
    for feature in result["features"]:
        if feature["properties"]["review_status"] != "approved":
            continue
        if feature.get("approved_geometry_sha256") != digest(feature["geometry"]):
            raise ValueError("Geometry changed; approve again.")
        Gdal().geometry(feature["geometry"])
        approved.append(
            {k: v for k, v in feature.items() if k != "approved_geometry_sha256"}
        )
    if not approved:
        raise ValueError("Approve at least one candidate.")
    value = {
        "type": "FeatureCollection",
        "features": approved,
        "geokernel_provenance": result["geokernel_provenance"],
    }
    target = Path(target)
    temporary = target.with_name(target.name + ".part")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf8")
    temporary.replace(target)


def coordinates(geometry):
    def walk(value):
        if value and isinstance(value[0], (float, int)):
            yield value
        else:
            for child in value:
                yield from walk(child)

    return list(walk(geometry["coordinates"]))


def envelope(geometry):
    points = coordinates(geometry)
    return (
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    )


def rectangle(bounds):
    a, b, c, d = bounds
    return {
        "type": "Polygon",
        "coordinates": [[[a, b], [c, b], [c, d], [a, d], [a, b]]],
    }


class Bridge(QObject):
    event = Signal(int, object)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Building change review — Python")
        self.resize(1460, 860)
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("GeoKernelAppIcon.ico"))))
        self.viewers = [Viewer(), Viewer()]
        self.applied = [None, None]
        self.render_busy = [False, False]
        self.bridge = Bridge(self)
        # Native extent events can arrive while the viewer holds its render lock.
        # Read/synchronize the other view only after that callback returns.
        self.bridge.event.connect(self._event, Qt.ConnectionType.QueuedConnection)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.finish = None
        self.cancel_event = threading.Event()
        self.messages = queue.SimpleQueue()
        self.result = None
        self.paths = None
        self.model = None
        self.displays = None
        self.sources_ready = False
        self.workspace = tempfile.TemporaryDirectory(prefix="geokernel-change-view-")
        self.revision = 0
        self.published_result = None
        self.candidates_dirty = False
        self.candidate_styles = [None, None]
        self.selected = -1
        self.changing = False
        self.closing = False
        self.close_allowed = False
        self.detached = False
        self.overlay_visible = True
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        for side, viewer in enumerate(self.viewers):
            pane = QWidget()
            column = QVBoxLayout(pane)
            column.setContentsMargins(0, 0, 0, 0)
            label = QLabel("2016 — BEFORE" if side == 0 else "2025 — AFTER")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            column.addWidget(label)
            column.addWidget(viewer.qt_widget(auto_close=False), 1)
            split.addWidget(pane)
            viewer.set_coordinate_system_preset("wgs84")
            viewer.set_tool(ViewerTool.PAN)
            viewer.set_event_callback(
                lambda event, side=side: self.bridge.event.emit(side, event)
            )
        layout.addWidget(split, 1)
        panel = QWidget()
        controls = QVBoxLayout(panel)
        controls.setSpacing(8)
        controls.addWidget(QLabel("<b>Oosterwold</b> · 2016 → 2025"))
        self.scope = QComboBox()
        self.scope.addItems(["Demo area (fixed)", "Current view", "Full dataset"])
        self.profile = QComboBox()
        self.profile.addItems(["Conservative", "Balanced", "Custom"])
        form = QFormLayout()
        form.addRow("Area", self.scope)
        form.addRow("Filter", self.profile)
        controls.addLayout(form)
        toggle = QToolButton()
        toggle.setText("Settings")
        toggle.setCheckable(True)
        controls.addWidget(toggle)
        advanced = QWidget()
        settings = QFormLayout(advanced)
        settings.setContentsMargins(0, 0, 0, 0)
        self.provider = QComboBox()
        self.provider.addItems(["CPU", "CUDA"])
        settings.addRow("Provider", self.provider)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.05, 0.95)
        self.threshold.setDecimals(4)
        self.threshold.setValue(0.4371)
        settings.addRow("Building threshold", self.threshold)
        self.parameters = {}
        for name, label, low, high, value in [
            ("area", "Min. area (m²)", 1, 1000, 50),
            ("tolerance", "Tolerance (m)", 0, 5, 2),
            ("coverage", "Other-date coverage <", 0.01, 0.95, 0.1),
            ("own", "Own-date score ≥", 0, 1, 0.75),
            ("other", "Other-date score ≤", 0, 1, 0.2),
        ]:
            box = QDoubleSpinBox()
            box.setRange(low, high)
            box.setDecimals(2)
            box.setValue(value)
            settings.addRow(label, box)
            self.parameters[name] = box
            box.valueChanged.connect(lambda _: self.profile.setCurrentIndex(2))
        controls.addWidget(advanced)
        advanced.hide()
        toggle.toggled.connect(advanced.setVisible)
        self.profile.activated.connect(self._preset)
        row = QHBoxLayout()
        self.run_button = QPushButton("Run analysis")
        self.cancel_button = QPushButton("Cancel")
        self.run_button.clicked.connect(self.run)
        self.cancel_button.clicked.connect(self.cancel_event.set)
        row.addWidget(self.run_button, 1)
        row.addWidget(self.cancel_button)
        controls.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setFormat("Ready")
        controls.addWidget(self.progress)
        self.summary = QLabel("Preparing imagery…")
        self.summary.setWordWrap(True)
        controls.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Candidate", "Type", "m²", "Review"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setStretchLastSection(False)
        for column, width in ((1, 60), (2, 65), (3, 85)):
            self.table.setColumnWidth(column, width)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setMinimumHeight(220)
        controls.addWidget(self.table, 1)
        self.table.itemSelectionChanged.connect(self._select)
        self.table.cellDoubleClicked.connect(lambda *_: self.locate())
        self.actor = QLineEdit("demo-reviewer")
        self.note = QLineEdit()
        self.actor.setMaxLength(100)
        self.note.setMaxLength(512)
        form = QFormLayout()
        form.addRow("Reviewer", self.actor)
        form.addRow("Note", self.note)
        controls.addLayout(form)
        row = QHBoxLayout()
        self.decisions = []
        for text, status in [
            ("Approve", "approved"),
            ("Reject", "rejected"),
            ("Pending", "pending"),
        ]:
            button = QPushButton(text)
            button.clicked.connect(lambda _, status=status: self.decide(status))
            self.decisions.append(button)
            row.addWidget(button)
        controls.addLayout(row)
        row = QHBoxLayout()
        self.locate_button = QPushButton("Locate")
        self.locate_button.clicked.connect(self.locate)
        self.save_button = QPushButton("Export GeoJSON")
        self.save_button.clicked.connect(self.save)
        row.addWidget(self.locate_button)
        row.addWidget(self.save_button)
        controls.addLayout(row)
        self.overlays = QCheckBox("Overlays")
        self.overlays.setChecked(True)
        self.overlays.toggled.connect(self._toggle_overlays)
        controls.addWidget(self.overlays)
        credits = QLabel(
            "<a href='https://www.beeldmateriaal.nl/dataroom'>Beeldmateriaal / PDOK</a> · CC BY 4.0"
        )
        credits.setOpenExternalLinks(True)
        credits.setWordWrap(True)
        credits.setToolTip(ATTRIBUTION)
        controls.addWidget(credits)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(panel)
        scroll.setMinimumWidth(370)
        scroll.setMaximumWidth(410)
        layout.addWidget(scroll)
        self.setCentralWidget(central)
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        for label, fn in [
            ("Zoom in", self.viewers[0].zoom_in),
            ("Zoom out", self.viewers[0].zoom_out),
            ("Demo area", lambda: self.focus(DEMO)),
            ("Full extent", lambda: self.focus(BOUNDS)),
            ("Pan", lambda: self._use_tool(ViewerTool.PAN)),
            (
                "Edit vertices",
                lambda: self._use_tool(ViewerTool.EDIT_VERTICES),
            ),
            ("Undo", lambda: self._undo(False)),
            ("Redo", lambda: self._undo(True)),
        ]:
            action = QAction(label, self)
            action.triggered.connect(fn)
            toolbar.addAction(action)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(80)
        self._controls()
        QTimer.singleShot(
            0,
            lambda: self._submit(self._prepare_inputs, self._prepared),
        )

    def _preset(self, index):
        if index < 2:
            for name, value in PROFILES[self.profile.itemText(index)].items():
                self.parameters[name].setValue(value)
            self.profile.setCurrentIndex(index)

    def _progress(self, percent, message):
        self.messages.put((percent, message))

    def _submit(self, work, finish):
        self.cancel_event.clear()
        self.finish = finish
        self.future = self.pool.submit(work)
        self._controls()

    def _controls(self):
        busy = self.future is not None or self.closing
        self.run_button.setText(
            "Run analysis"
            if self.sources_ready
            else "Preparing…"
            if busy
            else "Retry loading"
        )
        for widget in (
            self.scope,
            self.profile,
            self.run_button,
            self.provider,
            self.threshold,
            self.table,
            *self.parameters.values(),
        ):
            widget.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        for button in (*self.decisions, self.locate_button):
            button.setEnabled(
                not busy and self.result is not None and self.selected >= 0
            )
        self.save_button.setEnabled(
            not busy
            and bool(self.result)
            and any(
                f["properties"]["review_status"] == "approved"
                for f in self.result["features"]
            )
        )

    def _prepare_inputs(self):
        paths, model = prepare(self.cancel_event, self._progress)
        gdal = Gdal()
        displays = []
        for index, path in enumerate(paths):
            check_cancel(self.cancel_event)
            self._progress(0, f"Preparing {2016 if index == 0 else 2025} map preview…")
            displays.append(
                gdal.display_raster(
                    path, Path(self.workspace.name) / f"display-{index}.tif"
                )
            )
        check_cancel(self.cancel_event)
        return paths, model, displays

    def _prepared(self, value):
        paths, model, displays = value
        try:
            for viewer, path in zip(self.viewers, displays):
                viewer.clear_layers()
                viewer.set_coordinate_system_preset("wgs84")
                viewer.add_layer(path)
                extent = viewer.layer_projected_extent(0)
                if extent is None or not (
                    -180 <= extent.x_min <= 180 and -90 <= extent.y_min <= 90
                ):
                    raise ValueError("Imagery and map coordinate systems differ.")
                viewer.set_layer_name(0, "Imagery")
            self.focus(DEMO)
        except Exception:
            for viewer in self.viewers:
                viewer.clear_layers()
            raise
        self.paths, self.model, self.displays = paths, model, displays
        self.sources_ready = True
        self.summary.setText("Run analysis to find candidates.")
        self.statusBar().showMessage("Ready")

    def focus(self, bounds):
        geometry, _ = Gdal().geometry(rectangle(bounds), 25831, 4326)
        bounds = envelope(geometry)
        for side, viewer in enumerate(self.viewers):
            viewer.set_view_extent(bounds)
            self.applied[side] = viewer.get_view_extent()

    def _event(self, side, event):
        if event.event_type == ViewerEventType.BUSY_CHANGED:
            self.render_busy[side] = bool(event.int_value)
        if (
            event.event_type == ViewerEventType.VISIBLE_EXTENT_CHANGED
            and not self.closing
        ):
            value = self.viewers[side].get_view_extent()
            if value is None or value == self.applied[side]:
                return
            self.applied[side] = value
            other = 1 - side
            self.viewers[other].set_view_extent(value)
            self.applied[other] = self.viewers[other].get_view_extent()

    def run(self):
        if self.future or self.closing:
            return
        if not self.sources_ready:
            self._submit(self._prepare_inputs, self._prepared)
            return
        try:
            self.capture()
        except Exception as e:
            QMessageBox.warning(self, "Geometry", str(e))
            return
        if (
            self.result
            and QMessageBox.question(
                self,
                "Run analysis",
                "Replace this session’s candidates and review decisions?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        bounds = DEMO if self.scope.currentIndex() == 0 else BOUNDS
        if self.scope.currentIndex() == 1:
            e = self.viewers[0].get_view_extent()
            geometry, _ = Gdal().geometry(
                rectangle((e.x_min, e.y_min, e.x_max, e.y_max))
            )
            bounds = envelope(geometry)
        policy = {name: box.value() for name, box in self.parameters.items()}
        threshold = self.threshold.value()
        provider = self.provider.currentText().lower()
        self._submit(
            lambda: analyze(
                self.paths,
                self.model,
                bounds,
                policy,
                threshold,
                provider,
                self.cancel_event,
                self._progress,
            ),
            self._completed,
        )

    def _completed(self, result):
        self._end_edit()
        self.result = result
        self.selected = 0 if result["features"] else -1
        self.changing = True
        try:
            self.table.setRowCount(len(result["features"]))
            self.table.clearSelection()
            if self.selected >= 0:
                self.table.selectRow(self.selected)
        finally:
            self.changing = False
        self.note.setText(
            result["features"][0]["properties"]["review_note"]
            if self.selected >= 0
            else ""
        )
        self.refresh()
        self._redraw()

    def refresh(self):
        if self.result:
            self.changing = True
            try:
                features = self.result["features"]
                for row, feature in enumerate(features):
                    p = feature["properties"]
                    for col, value in enumerate(
                        [
                            feature["id"],
                            p["change_type"],
                            f"{p['area_m2']:.1f}",
                            p["review_status"],
                        ]
                    ):
                        item = self.table.item(row, col)
                        if item is None:
                            self.table.setItem(row, col, QTableWidgetItem(value))
                        elif item.text() != value:
                            item.setText(value)
            finally:
                self.changing = False
            self.summary.setText(
                f"{sum(f['properties']['change_type'] == 'new' for f in features)} new · {sum(f['properties']['change_type'] == 'removed' for f in features)} removed\n{sum(f['properties']['review_status'] == 'approved' for f in features)} approved · {sum(f['properties']['review_status'] == 'pending' for f in features)} pending"
            )
        self._controls()

    def _write(self, features):
        self.revision += 1
        path = Path(self.workspace.name) / f"overlay-{self.revision}.geojson"
        path.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}),
            encoding="utf8",
        )
        return path

    @staticmethod
    def _layer_index(viewer, name):
        info = viewer.layer_info_by_name(name)
        return info.get("index", -1) if info.get("isValid") else -1

    def _redraw(self):
        if not self.overlay_visible:
            return
        if self.published_result is not self.result or self.candidates_dirty:
            self._end_edit()
        self._ensure_candidates()
        self._update_selection()

    def _ensure_candidates(self):
        if self.published_result is self.result and not self.candidates_dirty:
            return
        for side, viewer in enumerate(self.viewers):
            for name in ("Candidates", "Selection targets"):
                while viewer.remove_layer_by_name(name):
                    pass
            self.candidate_styles[side] = None
            if not self.result:
                continue
            targets = copy.deepcopy(self.result["features"])
            if side == 0:
                for feature in targets:
                    feature["geometry"] = rectangle(envelope(feature["geometry"]))
            if targets:
                viewer.add_layer(self._write(targets))
                viewer.set_layer_name(0, "Selection targets")
                viewer.set_layer_style(
                    0,
                    {
                        "fillOpacity": 0,
                        "lineColor": "#00000000",
                        "lineWidth": 0,
                        "selectedLineColor": "#ef9b00",
                        "selectedLineWidth": 2,
                    },
                )
            kind = "removed" if side == 0 else "new"
            features = [
                f
                for f in self.result["features"]
                if f["properties"]["change_type"] == kind
            ]
            if features:
                viewer.add_layer(self._write(features))
                viewer.set_layer_name(0, "Candidates")
        self.published_result = self.result
        self.candidates_dirty = False
        self._apply_candidate_styles()

    def _apply_candidate_styles(self):
        if not self.result:
            return
        for side, viewer in enumerate(self.viewers):
            index = self._layer_index(viewer, "Candidates")
            if index < 0:
                continue
            kind, color = ("removed", "#ee554f") if side == 0 else ("new", "#20bf73")
            rules = []
            for feature in self.result["features"]:
                p = feature["properties"]
                if p["change_type"] != kind or p["review_status"] == "pending":
                    continue
                style = (
                    {
                        "fillColor": color,
                        "lineColor": color,
                        "fillOpacity": 90,
                        "lineWidth": 3,
                    }
                    if p["review_status"] == "approved"
                    else {
                        "fillColor": "#82909f",
                        "lineColor": "#82909f",
                        "fillOpacity": 10,
                        "lineWidth": 1,
                    }
                )
                rules.append(
                    {
                        "field": "candidate_id",
                        "operator": "equals",
                        "value": feature["id"],
                        "style": style,
                    }
                )
            renderer = {
                "type": "ruleBased",
                "defaultStyle": {
                    "fillColor": color,
                    "lineColor": color,
                    "fillOpacity": 35,
                    "lineWidth": 2,
                },
                "rules": rules,
            }
            if renderer != self.candidate_styles[side]:
                if not viewer.set_layer_symbol_renderer(index, renderer):
                    raise RuntimeError("Cannot style candidates.")
                self.candidate_styles[side] = renderer

    @staticmethod
    def _highlight(viewer, layer, geometry, candidate_id=None):
        if layer < 0:
            raise RuntimeError("Selection references are unavailable.")
        a, b, c, d = envelope(geometry)
        hit = next(
            (
                hit
                for hit in viewer.hit_test_features_in_extent(a, b, c, d)
                if hit["layerIndex"] == layer
                and (
                    candidate_id is None
                    or hit.get("attributes", {}).get("candidate_id") == candidate_id
                )
            ),
            None,
        )
        if hit is None:
            raise RuntimeError("Cannot find selected candidate.")
        # An extent centre can lie outside a concave roof. The ID still identifies
        # the exact feature; the tolerance makes it reachable from that centre.
        if not viewer.native.call(
            "GeoKernelViewer_SelectFeatureHit",
            (a + c) / 2,
            (b + d) / 2,
            max(c - a, d - b, 1e-9) * 2,
            layer,
            hit["shapeId"],
            hit["featureId"],
        ):
            raise RuntimeError("Cannot highlight selected candidate.")

    def _update_selection(self):
        for side, viewer in enumerate(self.viewers):
            if not self.overlay_visible or not self.result or self.selected < 0:
                viewer.clear_selected_features()
                continue
            for name in ("Candidates", "Selection targets", "Selection"):
                info = viewer.layer_info_by_name(name)
                if info.get("isValid") and not info.get("visible"):
                    viewer.set_layer_visible(info["index"], True)
            feature = self.result["features"][self.selected]
            geometry = (
                feature["geometry"]
                if side
                else rectangle(envelope(feature["geometry"]))
            )
            editor = self._layer_index(viewer, "Selection") if side else -1
            target = (
                editor
                if editor >= 0
                else self._layer_index(viewer, "Selection targets")
            )
            self._highlight(
                viewer, target, geometry, None if editor >= 0 else feature["id"]
            )

    def _end_edit(self):
        viewer = self.viewers[1]
        if self._layer_index(viewer, "Selection") >= 0:
            viewer.clear_selected_features()
            viewer.remove_layer_by_name("Selection")
            viewer.set_tool(ViewerTool.PAN)

    def _use_tool(self, tool):
        try:
            if tool == ViewerTool.EDIT_VERTICES:
                if not self.overlay_visible or not self.result or self.selected < 0:
                    raise ValueError("Select a visible candidate before editing.")
                viewer = self.viewers[1]
                if self._layer_index(viewer, "Selection") < 0:
                    geometry = self.result["features"][self.selected]["geometry"]
                    if geometry["type"] != "Polygon":
                        raise ValueError(
                            "Multipart geometry is preserved but cannot be edited here."
                        )
                    viewer.clear_selected_features()
                    index = viewer.add_polygon_layer(
                        "Selection",
                        geometry["coordinates"],
                        {
                            "fillOpacity": 0,
                            "lineColor": "#ef9b00",
                            "lineWidth": 2,
                            "selectedLineColor": "#ef9b00",
                            "selectedLineWidth": 2,
                        },
                    )
                    if (
                        index < 0
                        or not viewer.begin_edit_layer(index)
                        or not viewer.set_active_edit_layer_index(index)
                    ):
                        raise RuntimeError("Cannot edit selected candidate.")
                    self._highlight(viewer, index, geometry)
            self.viewers[1].set_tool(tool)
        except Exception as e:
            self.statusBar().showMessage(str(e))

    def capture(self):
        if not self.result or self.selected < 0 or not self.overlay_visible:
            return False
        viewer = self.viewers[1]
        index = self._layer_index(viewer, "Selection")
        if index < 0 or not viewer.is_layer_editing(index):
            return False
        value = json.loads(viewer.write_layer_last_shape_geojson(index))
        feature = self.result["features"][self.selected]
        previous_status = feature["properties"]["review_status"]
        changed = update_geometry(feature, value.get("geometry", value))
        if changed:
            self.candidates_dirty = True
            if previous_status != "pending":
                self._apply_candidate_styles()
        return changed

    def _toggle_overlays(self, value):
        previous = self.overlay_visible
        try:
            self.capture()
            self.overlay_visible = value
            if value:
                self._redraw()
            else:
                for viewer in self.viewers:
                    viewer.clear_selected_features()
                    for name in ("Selection", "Selection targets", "Candidates"):
                        index = self._layer_index(viewer, name)
                        if index >= 0:
                            viewer.set_layer_visible(index, False)
        except Exception as e:
            self.overlay_visible = previous
            self.overlays.blockSignals(True)
            self.overlays.setChecked(previous)
            self.overlays.blockSignals(False)
            self.statusBar().showMessage(str(e))

    def _select(self):
        if self.changing or not self.result or self.future or self.closing:
            return
        index = self.table.currentRow()
        if index < 0 or index == self.selected:
            return
        previous = self.selected
        try:
            self.capture()
            self._end_edit()
            self.selected = index
            if self.overlay_visible:
                self._ensure_candidates()
                self._update_selection()
        except Exception as e:
            self.selected = previous
            self.changing = True
            try:
                if previous >= 0:
                    self.table.selectRow(previous)
            finally:
                self.changing = False
            self.statusBar().showMessage(str(e))
            return
        self.note.setText(self.result["features"][index]["properties"]["review_note"])
        self.refresh()

    def locate(self):
        if not self.result or self.selected < 0:
            return
        a, b, c, d = envelope(self.result["features"][self.selected]["geometry"])
        dx = max(0.00015, (c - a) * 0.5)
        dy = max(0.00015, (d - b) * 0.5)
        self.viewers[0].set_view_extent((a - dx, b - dy, c + dx, d + dy))

    def _undo(self, redo):
        viewer = self.viewers[1]
        index = self._layer_index(viewer, "Selection")
        if self.result and self.overlay_visible and index >= 0:
            (viewer.redo_edit_layer if redo else viewer.undo_edit_layer)(index)
            if self.capture():
                self.refresh()

    def decide(self, status):
        try:
            self.capture()
            feature = self.result["features"][self.selected]
            previous_status = feature["properties"]["review_status"]
            review(feature, status, self.actor.text(), self.note.text())
            if self.candidates_dirty:
                self._redraw()
            elif previous_status != status:
                self._apply_candidate_styles()
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Review", str(e))

    def save(self):
        try:
            self.capture()
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export approved candidates",
                "building_changes.geojson",
                "GeoJSON (*.geojson)",
            )
            if path:
                export(self.result, path)
        except Exception as e:
            QMessageBox.warning(self, "Export", str(e))

    def _poll(self):
        while not self.messages.empty():
            percent, message = self.messages.get()
            self.progress.setValue(percent)
            self.progress.setFormat("%p%")
            self.statusBar().showMessage(message)
        if self.future and self.future.done():
            future, self.future = self.future, None
            try:
                result = future.result()
                if not self.closing:
                    self.finish(result)
            except Exception as e:
                if not self.closing:
                    self.statusBar().showMessage(str(e))
                    if not self.sources_ready:
                        self.summary.setText(f"Could not load imagery: {e}")
            self._controls()
        if self.closing and not self.future:
            if not self.detached:
                for viewer in self.viewers:
                    viewer.clear_layers()
                self.detached = True
                self.close_after = time.monotonic() + 0.2
                return
            if any(self.render_busy) or time.monotonic() < self.close_after:
                return
            self.timer.stop()
            for viewer in self.viewers:
                viewer.set_event_callback(None)
                viewer.close()
            self.pool.shutdown(wait=False)
            self.workspace.cleanup()
            self.close_allowed = True
            self.close()
            return
        if self.result and not self.future:
            try:
                if self.capture():
                    # Preserve the native edit session and its undo history.
                    self.refresh()
            except Exception as e:
                self.statusBar().showMessage(str(e))

    def closeEvent(self, event):
        if self.close_allowed:
            event.accept()
        else:
            event.ignore()
            self.closing = True
            self.cancel_event.set()
            self._controls()


def main():
    app = QApplication(sys.argv)
    try:
        window = Window()
        window.show()
        app.processEvents()
        for viewer in window.viewers:
            viewer.show()
        return app.exec()
    except Exception as e:
        QMessageBox.critical(None, "Building change review", str(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
