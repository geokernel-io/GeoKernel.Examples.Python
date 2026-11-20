"""Live AI / classical DSM-to-DTM comparison support.

The experimental pix_grad model runs through GeoKernel.AI's raster inference C ABI
(`GeoKernelAI_RunRasterInference`, wrapped by `geokernel.ai.AI`); the classical estimate
is `dsm_terrain.estimate`. Both receive the same full source DSM and nothing else: the
reference is evaluation-only and neither method sees the other's result. Model package,
full 1 km Zurich tile and the projection support sample are acquired and SHA-256 verified
against pinned manifests. All functions may run on a worker thread.
"""
from __future__ import annotations

import datetime
import math
import os
import shutil
import tempfile
import threading
import uuid
from array import array
from dataclasses import dataclass, field, replace
from pathlib import Path

import dsm_support as ds
import dsm_terrain as dt

ROOT_DIR = Path(__file__).resolve().parent
MODEL_ASSETS = ROOT_DIR / "dsm_to_dtm_ai-model-assets.json"
TERRAIN_ASSETS = ROOT_DIR / "dsm_to_dtm_ai-terrain-assets.json"
MODEL_ID = "davpergan-dtm-dsm-gan-pix-grad"
MODEL_SHA256 = "e400e27f6afc75bcf4e1a61432ee9557529683903996dd953d3e8e3fcbe90eb6"
AGENT = "GeoKernel-DsmToDtmAI-Python/1.0"
MODEL_HINT = "Use the exact model ZIP or retry its public URL."
MAX_SUPPORT_CELLS = 262144


# ----- acquisition --------------------------------------------------------------------------------
def prepare_terrain(assets: dict, root: Path, cancel: threading.Event, progress: ds.Progress) -> Path:
    """Download (when needed) and verify the full 1 km DSM and reference by size and SHA-256."""
    folder = Path(root) / assets["cache"]
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("dsm", "reference"):
        asset = assets["sources"][name]
        path = folder / asset["file"]
        if ds.hash_file(path) != asset["sha256"]:
            ds._download(asset["url"], path, cancel, lambda value, _: progress(value, f"Full 1 km {name}: downloading..."),
                         AGENT, "Retry when the swisstopo download is reachable.")
        ds.check_cancel(cancel)
        if path.stat().st_size != asset["bytes"] or ds.hash_file(path) != asset["sha256"]:
            raise RuntimeError("Full terrain source failed size/SHA-256 verification.")
    return folder


def prepare_model(assets: dict, root: Path, local_archive: str | None, url: str, cancel: threading.Event,
                  progress: ds.Progress, model_id: str = MODEL_ID, model_sha256: str = MODEL_SHA256,
                  agent: str = AGENT) -> Path:
    """Verified pinned model package folder (archive and every package file hash-checked)."""
    folder = ds.prepare_sample(assets, root, local_archive, url, cancel, progress, agent, MODEL_HINT)
    ds.check_cancel(cancel)
    from geokernel.ai import AI

    inspection = AI().inspect_model_package(folder)
    manifest = inspection.get("manifest") or {}
    if not inspection.get("valid") or manifest.get("id") != model_id or inspection.get("modelSha256") != model_sha256:
        raise RuntimeError("Unexpected model package. " + " ".join(inspection.get("validationErrors") or []))
    return folder


# ----- AI inference -------------------------------------------------------------------------------
@dataclass
class AiHeight:
    raw: array
    dtm: array
    provenance: dict = field(default_factory=dict)
    tiles: int = 0
    context_filled: int = 0
    clamped: int = 0
    padded: bool = False


def _same_crs(a: str, b: str) -> bool:
    lib = ds._gdal().lib
    left, right = lib.OSRNewSpatialReference(None), lib.OSRNewSpatialReference(None)
    try:
        return (lib.OSRSetFromUserInput(left, a.encode("utf-8")) == 0
                and lib.OSRSetFromUserInput(right, b.encode("utf-8")) == 0 and bool(lib.OSRIsSame(left, right)))
    finally:
        lib.OSRDestroySpatialReference(left)
        lib.OSRDestroySpatialReference(right)


def infer_ai(dsm: dt.Raster, model: Path, overlap: int, threads: int, folder: Path, cancel: threading.Event,
             progress: ds.Progress) -> AiHeight:
    """pix_grad over the full DSM with the package's tiling; the reference is not involved.

    Missing DSM cells are filled for input context only (four-neighbour DSM support), and
    inputs smaller than one tile are edge-padded right/bottom, the package's padding mode,
    before the raster reaches the SDK. The source mask is restored and the final DTM is
    bounded above by the DSM; the blended raw output is retained.
    """
    manifest = ds.read_json(Path(model) / "geokernel-model.json")
    if manifest.get("modelSha256") != MODEL_SHA256:
        raise RuntimeError("This example requires the pinned pix_grad adaptation.")
    tile_w, tile_h = int(manifest["tiling"]["width"]), int(manifest["tiling"]["height"])
    w, h = dsm.width, dsm.height
    out = AiHeight(array("f"), array("f"))
    out.context_filled = len(dsm.valid) - sum(dsm.valid)
    pw, ph = max(w, tile_w), max(h, tile_h)
    out.padded = (pw, ph) != (w, h)
    source = Path(dsm.path)
    if out.context_filled or out.padded:
        z = dsm.z
        if out.context_filled:
            progress(38, "Filling missing DSM context from DSM support only...")
            nearest = dt.support_map(dsm.valid, w, h, cancel)
            z = array("f", (z[i] if dsm.valid[i] else z[nearest[i]] for i in range(w * h)))
        if out.padded:
            padded = array("f")
            for y in range(ph):
                row = z[min(y, h - 1) * w:(min(y, h - 1) + 1) * w]
                padded.extend(row)
                padded.extend(array("f", [row[-1]]) * (pw - w))
            z = padded
        source = dt.write_raster(replace(dsm, width=pw, height=ph), Path(folder) / "dsm-context.tif", z, 6)
    ds.check_cancel(cancel)
    from geokernel.ai import AI

    provenance = manifest.get("provenance") or {}
    output = Path(folder) / "ai-inference.tif"
    request = {
        "modelPackagePath": str(model), "rasterPath": str(source), "outputPath": str(output),
        "outputMode": "floatBands", "bands": [1], "provider": "cpu", "intraOpThreads": int(threads),
        "interOpThreads": 1, "tiling": {"overlapX": int(overlap), "overlapY": int(overlap)},
        "modelRevision": provenance.get("revision") or provenance.get("sourceUrl") or "",
    }

    def tiles(p):
        progress(40 + int(p["percent"] * 0.4), f"AI tiles {p['completedTiles']} / {p['totalTiles']} · {p['message']}")

    result = AI().run_raster_inference(request, tiles)
    ds.check_cancel(cancel)
    if (result.get("cancelled") or result.get("width") != pw or result.get("height") != ph
            or result.get("bandCount") != 1 or result.get("dataType") != "Float32"):
        raise RuntimeError("AI result dimensions or numeric type do not match the source.")
    if (tuple(float(v) for v in result.get("geoTransform") or ()) != tuple(dsm.transform)
            or not _same_crs(dsm.projection, result.get("projectionWkt") or "")):
        raise RuntimeError("AI inference changed the source grid or CRS.")
    values = ds.read_raster(output).bands[0]
    if out.padded:
        values = array("f", (v for y in range(h) for v in values[y * pw:y * pw + w]))
    raw, final = array("f", values), array("f", values)
    for i in range(w * h):
        if not dsm.valid[i]:
            raw[i] = final[i] = dt.NODATA
            continue
        if not math.isfinite(raw[i]):
            raise RuntimeError("AI returned a nonfinite valid-source height.")
        if final[i] > dsm.z[i]:
            final[i] = dsm.z[i]
            out.clamped += 1
    out.raw, out.dtm = raw, final
    out.provenance = result.get("provenance") or {}
    out.tiles = int(result.get("processedTiles") or 0)
    return out


# ----- comparison ---------------------------------------------------------------------------------
@dataclass
class Scene:
    dsm: dt.Raster
    reference: dt.Raster | None
    original: Path
    manifest: dict = field(default_factory=dict)


@dataclass
class Removal:
    """The fields of dt.Terrain the display helpers read, for the AI estimate."""
    dtm: array
    removed: array
    quality: bytearray = field(default_factory=bytearray)


@dataclass
class Comparison:
    classical: dt.Terrain
    ai: AiHeight
    overlap: int
    threads: int
    model: Path
    model_manifest: dict
    folder: Path
    maps: list = field(default_factory=lambda: [[None] * 3, [None] * 3])
    full: list = field(default_factory=lambda: [dt.Score(), dt.Score()])
    crop: list = field(default_factory=lambda: [dt.Score(), dt.Score()])
    files: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)


def effective_parameters(dsm: dt.Raster, parameters: dt.Parameters) -> dt.Parameters:
    """Keep the selected settings but coarsen the working grid until it fits the support-cell cap."""
    p = replace(parameters)

    def cells(size):
        return math.ceil(size / max(1.0, math.floor(p.working / dsm.pixel + 0.5)))

    while cells(dsm.width) * cells(dsm.height) > MAX_SUPPORT_CELLS:
        p.working += dsm.pixel
    return p


def comparison_window(scene: Scene) -> tuple[int, int, int, int]:
    """Column, row, width, height: the shared Zurich crop, or the central 60% of a custom DSM."""
    d = scene.dsm
    if scene.manifest.get("standard_full_tile"):
        return 200, 800, 500, 500
    left, top = d.width // 5, d.height // 5
    return left, top, d.width - 2 * left, d.height - 2 * top


def area_score(dsm: dt.Raster, z, reference: dt.Raster | None, rect) -> dt.Score:
    s = dt.Score()
    if reference is None:
        return s
    x0, y0, w, h = rect
    squared = absolute = signed = 0.0
    for y in range(y0, y0 + h):
        for i in range(y * dsm.width + x0, y * dsm.width + x0 + w):
            if dsm.valid[i] and reference.valid[i]:
                e = z[i] - reference.z[i]
                s.count += 1
                squared += e * e
                absolute += abs(e)
                signed += e
    if s.count:
        s.rmse, s.mae, s.bias = math.sqrt(squared / s.count), absolute / s.count, signed / s.count
    return s


def cut_raster(source: dt.Raster, rect) -> dt.Raster:
    x0, y0, w, h = rect
    t = source.transform
    return replace(source, width=w, height=h,
                   transform=(t[0] + x0 * source.pixel, t[1], t[2], t[3] - y0 * source.pixel, t[4], t[5]),
                   z=cut_values(source.z, source.width, rect),
                   valid=bytearray(v for y in range(y0, y0 + h) for v in source.valid[y * source.width + x0:y * source.width + x0 + w]))


def cut_values(values, width: int, rect) -> array:
    x0, y0, w, h = rect
    out = array("f")
    for y in range(y0, y0 + h):
        out.extend(values[y * width + x0:y * width + x0 + w])
    return out


def crop_extent(scene: Scene) -> tuple[float, float, float, float]:
    x0, y0, w, h = comparison_window(scene)
    t, p = scene.dsm.transform, scene.dsm.pixel
    left, top = t[0] + x0 * p, t[3] - y0 * p
    return left, top - h * p, left + w * p, top


def evaluate(scene: Scene, result: Comparison, model_assets: dict) -> None:
    d = scene.dsm
    rect = comparison_window(scene)
    for method, heights in enumerate((result.classical.dtm, result.ai.dtm)):
        result.full[method] = dt.score(d, heights, scene.reference)
        result.crop[method] = area_score(d, heights, scene.reference, rect)
    ref = scene.reference
    result.report = {
        "schema_version": 1,
        "method": "pix_grad_live_and_independent_native_classical",
        "source_dsm": d.path,
        "source_sha256": d.sha256,
        "reference": ref.path if ref else None,
        "reference_sha256": ref.sha256 if ref else None,
        "reference_used_for_processing": False,
        "classical_uses_ai": False,
        "ai_uses_classical": False,
        "model_archive_sha256": model_assets.get("sha256"),
        "model_sha256": result.model_manifest.get("modelSha256"),
        "model_manifest": result.model_manifest,
        "sdk_inference": result.ai.provenance,
        "ai": {"overlap_pixels": result.overlap, "cpu_threads": result.threads, "processed_tiles": result.ai.tiles,
               "context_filled_source_pixels": result.ai.context_filled,
               "context_fill": "four-neighbour DSM-only support propagation",
               "small_input_edge_padding": result.ai.padded,
               "upper_bound_clamped_pixels": result.ai.clamped, "raw_output_retained": True},
        "classical": {"method": dt.METHOD, "parameters": result.classical.parameters.json(),
                      "summary": result.classical.summary},
        "grid": {"width": d.width, "height": d.height, "transform": list(d.transform), "crs_wkt": d.projection},
        "evaluation": {
            "full": {"classical": result.full[0].json(), "ai": result.full[1].json()},
            "comparison_crop": {"pixel_window": dict(zip(("column", "row", "width", "height"), rect)),
                                "classical": result.crop[0].json(), "ai": result.crop[1].json()}},
        "source_manifest": scene.manifest,
        "output_files": {name: name for name in result.files},
        "attribution": "Terrain sample: Federal Office of Topography swisstopo. Model weights: David Perez, Zenodo "
                       "7973800, CC BY 4.0; deterministic ONNX adaptation.",
        "limits": "Experimental regional model; fixed development scene, not held-out benchmark. Metre heights, no "
                  "vertical datum conversion. Source filename years differ.",
    }


def display_maps(d: dt.Raster, terrain, reference: dt.Raster | None, folder: Path, method: int, cancel,
                 progress: ds.Progress, base: int = 86) -> list[Path]:
    """Terrain relief, removed height (0-20 m) and signed reference error (-2..+2 m) RGB GeoTIFFs."""
    paths = []
    for mode in range(3):
        progress(base + method * 4 + mode, f"Preparing {'AI' if method else 'classical'} display...")
        bands = (dt.relief_bands(d, terrain.dtm, cancel) if mode == 0
                 else dt.diagnostic_bands(d, terrain, 0 if mode == 1 else 2, reference, cancel))
        paths.append(ds.write_rgb_bands(Path(folder) / f"view-{method}-{mode}.tif", d.width, d.height, d.transform,
                                        d.projection, bands))
    return paths


def compare(scene: Scene, model: Path, parameters: dt.Parameters, overlap: int, threads: int, folder: Path,
            model_assets: dict, cancel: threading.Event, progress: ds.Progress) -> Comparison:
    """Classical first, then an independent AI inference from the same full source DSM."""
    d = scene.dsm
    classical = dt.estimate(d, parameters, cancel, lambda p, text: progress(int(p * 0.35), "Classical: " + text))
    ai = infer_ai(d, model, overlap, threads, folder, cancel, progress)
    result = Comparison(classical, ai, overlap, threads, Path(model),
                        ds.read_json(Path(model) / "geokernel-model.json"), Path(folder))

    def numeric(name, values, kind=6):
        ds.check_cancel(cancel)
        result.files[name] = dt.write_raster(d, Path(folder) / name, values, kind)

    progress(82, "Writing native-resolution numeric results...")
    numeric("classical-dtm.tif", classical.dtm)
    numeric("ai-dtm.tif", ai.dtm)
    numeric("ai-raw.tif", ai.raw)
    numeric("classical-removed.tif", classical.removed)
    removal = Removal(ai.dtm, array("f", (max(0.0, d.z[i] - ai.dtm[i]) if d.valid[i] else dt.NODATA
                                          for i in range(d.width * d.height))))
    numeric("ai-removed.tif", removal.removed)
    numeric("classical-qa.tif", classical.quality, 1)
    for method, terrain in enumerate((classical, removal)):
        result.maps[method] = display_maps(d, terrain, scene.reference, folder, method, cancel, progress)
    progress(96, "Preparing the shared comparison crop and scores...")
    rect = comparison_window(scene)
    cropped = cut_raster(d, rect)

    def crop(name, values):
        result.files[name] = dt.write_raster(cropped, Path(folder) / name, cut_values(values, d.width, rect), 6)

    crop("comparison-dsm.tif", d.z)
    crop("comparison-classical.tif", classical.dtm)
    crop("comparison-ai.tif", ai.dtm)
    if scene.reference is not None:
        crop("comparison-reference.tif", scene.reference.z)
    evaluate(scene, result, model_assets)
    ds.check_cancel(cancel)
    return result


def attach_reference(scene: Scene, result: Comparison, folder: Path, model_assets: dict, cancel,
                     progress: ds.Progress) -> Comparison:
    """New error maps, crop file and scores for a new evaluation reference; heights unchanged."""
    out = replace(result, maps=[list(result.maps[0]), list(result.maps[1])], files=dict(result.files),
                  full=list(result.full), crop=list(result.crop))
    d = scene.dsm
    for method, heights in enumerate((result.classical.dtm, result.ai.dtm)):
        progress(40 + method * 20, "Preparing reference error maps...")
        bands = dt.diagnostic_bands(d, Removal(heights, array("f")), 2, scene.reference, cancel)
        out.maps[method][2] = ds.write_rgb_bands(Path(folder) / f"reference-{method}.tif", d.width, d.height,
                                                 d.transform, d.projection, bands)
    rect = comparison_window(scene)
    out.files["comparison-reference.tif"] = dt.write_raster(
        cut_raster(d, rect), Path(folder) / "comparison-reference.tif", cut_values(scene.reference.z, d.width, rect), 6)
    evaluate(scene, out, model_assets)
    return out


def export_bundle(result, base: Path, cancel: threading.Event, progress: ds.Progress,
                  name: str = "dsm-dtm-ai", staging_prefix: str = ".dsm-dtm-export-") -> Path:
    """Stage every file plus comparison.json beside the target, then rename into a new unique folder."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = Path(base) / f"{name}-{stamp}-{uuid.uuid4().hex[:6]}"
    staging = Path(tempfile.mkdtemp(prefix=staging_prefix, dir=base))
    try:
        for index, (name, source) in enumerate(result.files.items(), 1):
            ds.check_cancel(cancel)
            progress(index * 90 // len(result.files), f"Saving {name}")
            dt.atomic_copy(source, staging / name, cancel)
        report = dict(result.report, output_files={name: name for name in result.files})
        dt.write_json(staging / "comparison.json", report)
        ds.check_cancel(cancel)
        if target.exists():
            raise RuntimeError("Cannot commit result directory: it already exists.")
        os.rename(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target
