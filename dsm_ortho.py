"""DSM + orthophoto to DTM support: three independent terrain estimates from the same full DSM.

1. the native classical filter (`dsm_terrain.estimate`, DSM only);
2. the experimental pix_grad model (DSM only);
3. the experimental rgb_grad_fm model (DSM plus an exactly aligned RGB orthophoto).

Both models run through GeoKernel.AI's raster inference C ABI. No method sees another's result
or the evaluation reference. The input sample and both model packages are SHA-256 verified
against pinned manifests. All functions may run on a worker thread.
"""
from __future__ import annotations

import ctypes as ct
import math
from array import array
from dataclasses import dataclass, field, replace
from pathlib import Path

import dsm_ai as da
import dsm_support as ds
import dsm_terrain as dt

ROOT_DIR = Path(__file__).resolve().parent
SAMPLE_ASSETS = ROOT_DIR / "dsm_ortho_to_dtm-sample-assets.json"
MODEL_ASSETS = (ROOT_DIR / "dsm_ortho_to_dtm-pix-model-assets.json", ROOT_DIR / "dsm_ortho_to_dtm-rgb-model-assets.json")
METHODS = ("classical", "pix_grad", "rgb_grad_fm")
MODEL_IDS = ("davpergan-dtm-dsm-gan-pix-grad", "davpergan-dtm-dsm-gan-rgb-grad-fm")
MODEL_SHA256 = ("e400e27f6afc75bcf4e1a61432ee9557529683903996dd953d3e8e3fcbe90eb6",
                "5042d5abac64d6b1764265924c9910807e3a5efee7e1b9517fc9d86bf4d0e3a3")
AGENT = "GeoKernel-DsmOrthoToDtm-Python/1.0"


def prepare_model(index: int, root: Path, archive: str | None, url: str | None, cancel, progress) -> Path:
    """Verified pix_grad (0) or rgb_grad_fm (1) package folder."""
    assets = ds.read_json(MODEL_ASSETS[index])
    return da.prepare_model(assets, root, archive, url or assets["url"], cancel,
                            lambda value, text: progress(value, f"{METHODS[index + 1]}: {text}"),
                            MODEL_IDS[index], MODEL_SHA256[index], AGENT)


# ----- orthophoto ---------------------------------------------------------------------------------
@dataclass
class Ortho:
    path: str
    sha256: str
    bands: list          # three bytes objects, row-major
    context: list        # the same bands with RGB-only context fill for invalid RGB cells
    filled: int = 0


def _bind():
    lib = ds._gdal().lib
    p, i, d = ct.c_void_p, ct.c_int, ct.c_double
    for name, args, result in (("GDALGetRasterDataType", [p], i), ("GDALGetRasterColorInterpretation", [p], i),
                               ("GDALGetRasterScale", [p, ct.POINTER(i)], d), ("GDALGetRasterOffset", [p, ct.POINTER(i)], d),
                               ("GDALGetMaskBand", [p], p)):
        function = getattr(lib, name)
        function.argtypes, function.restype = args, result
    return lib


def read_ortho(dsm: dt.Raster, path: Path, cancel) -> Ortho:
    """Three RGB-ordered Byte bands on the DSM's exact grid that cover every valid DSM cell."""
    ds.check_cancel(cancel)
    lib = _bind()
    dataset = lib.GDALOpen(str(path).encode("utf-8"), 0)
    if not dataset:
        raise RuntimeError("Cannot open RGB orthophoto.")
    n = dsm.width * dsm.height
    bands, valid = [], bytearray(b"\x01" * n)
    try:
        if lib.GDALGetRasterCount(dataset) != 3:
            raise ValueError("Orthophoto must contain exactly three RGB Byte bands.")
        t = (ct.c_double * 6)()
        has_transform = lib.GDALGetGeoTransform(dataset, t) == 0
        projection = (lib.GDALGetProjectionRef(dataset) or b"").decode("utf-8")
        if not (da._same_crs(dsm.projection, projection) and has_transform and lib.GDALGetRasterXSize(dataset) == dsm.width
                and lib.GDALGetRasterYSize(dataset) == dsm.height and tuple(t) == tuple(dsm.transform)):
            raise ValueError("RGB and DSM must have the same dimensions, exact affine grid and equivalent CRS. "
                             "Align them before loading.")
        for channel in range(3):
            ds.check_cancel(cancel)
            band = lib.GDALGetRasterBand(dataset, channel + 1)
            if lib.GDALGetRasterDataType(band) != 1 or lib.GDALGetRasterColorInterpretation(band) != channel + 3:
                raise ValueError("Use RGB-ordered Byte bands; no implicit spectral or color conversion is performed.")
            present = ct.c_int()
            scale = lib.GDALGetRasterScale(band, ct.byref(present))
            if present.value and abs(scale - 1) >= 1e-12:
                raise ValueError("Apply RGB scale before loading.")
            offset = lib.GDALGetRasterOffset(band, ct.byref(present))
            if present.value and abs(offset) >= 1e-12:
                raise ValueError("Apply RGB offset before loading.")
            pixels, mask = bytearray(n), bytearray(n)
            for target, source in ((pixels, band), (mask, lib.GDALGetMaskBand(band))):
                buffer = (ct.c_ubyte * n).from_buffer(target)
                code = lib.GDALRasterIO(source, 0, 0, 0, dsm.width, dsm.height, buffer, dsm.width, dsm.height, 1, 0, 0)
                del buffer
                if code != 0:
                    raise RuntimeError("Cannot read RGB pixels or validity.")
            bands.append(bytes(pixels))
            valid = bytearray(1 if a and b else 0 for a, b in zip(valid, mask))
    finally:
        lib.GDALClose(dataset)
    if any(dsm.valid[i] and not valid[i] for i in range(n)):
        raise ValueError("RGB does not cover every valid DSM pixel. Crop or prepare common source coverage explicitly.")
    filled = n - sum(valid)
    context = bands
    if filled:
        nearest = dt.support_map(valid, dsm.width, dsm.height, cancel)
        context = [bytes(b[i] if valid[i] else b[nearest[i]] for i in range(n)) for b in bands]
    ds.check_cancel(cancel)
    return Ortho(str(Path(path).resolve()), ds.hash_file(Path(path)), bands, context, filled)


# ----- inference ----------------------------------------------------------------------------------
def write_stack(raster: dt.Raster, path: Path, bands: list) -> Path:
    """A Float32 GeoTIFF of several bands on the raster's grid (the model input stack)."""
    ds.write_float_geotiff(path, raster.width, raster.height, raster.transform, raster.projection, bands, None)
    return Path(path)


def infer(dsm: dt.Raster, model: Path, rgb: Ortho | None, overlap: int, threads: int, folder: Path, cancel,
          progress: ds.Progress) -> da.AiHeight:
    """pix_grad (DSM) or rgb_grad_fm (DSM, R, G, B) over the full grid; the reference is not involved.

    Missing DSM cells are filled for input context from DSM support only (RGB was context-filled
    from RGB support only). The channels are stacked in the model's order into one Float32 raster,
    edge-padded right/bottom when smaller than one tile, and the source mask is restored after.
    """
    index = 1 if rgb is not None else 0
    manifest = ds.read_json(Path(model) / "geokernel-model.json")
    if manifest.get("modelSha256") != MODEL_SHA256[index]:
        raise RuntimeError("Unexpected AI checkpoint for the declared input profile.")
    tile_w, tile_h = int(manifest["tiling"]["width"]), int(manifest["tiling"]["height"])
    w, h = dsm.width, dsm.height
    out = da.AiHeight(array("f"), array("f"))
    out.context_filled = len(dsm.valid) - sum(dsm.valid)
    pw, ph = max(w, tile_w), max(h, tile_h)
    out.padded = (pw, ph) != (w, h)
    z = dsm.z
    if out.context_filled:
        nearest = dt.support_map(dsm.valid, w, h, cancel)
        z = array("f", (z[i] if dsm.valid[i] else z[nearest[i]] for i in range(w * h)))
    channels = [z] + ([array("f", iter(b)) for b in rgb.context] if rgb is not None else [])
    source = Path(dsm.path)
    if out.padded:
        def grow(values):
            grown = array("f")
            for y in range(ph):
                row = values[min(y, h - 1) * w:(min(y, h - 1) + 1) * w]
                grown.extend(row)
                grown.extend(array("f", [row[-1]]) * (pw - w))
            return grown
        channels = [grow(c) for c in channels]
    if out.context_filled or out.padded or rgb is not None:
        source = write_stack(replace(dsm, width=pw, height=ph), Path(folder) / f"{METHODS[index + 1]}-input.tif", channels)
    ds.check_cancel(cancel)
    from geokernel.ai import AI

    provenance = manifest.get("provenance") or {}
    output = Path(folder) / f"{METHODS[index + 1]}-inference.tif"
    result = AI().run_raster_inference({
        "modelPackagePath": str(model), "rasterPath": str(source), "outputPath": str(output),
        "outputMode": "floatBands", "bands": list(range(1, len(channels) + 1)), "provider": "cpu",
        "intraOpThreads": int(threads), "interOpThreads": 1, "tiling": {"overlapX": int(overlap), "overlapY": int(overlap)},
        "modelRevision": provenance.get("revision") or provenance.get("sourceUrl") or "",
    }, lambda p: progress(p["percent"], f"tiles {p['completedTiles']} / {p['totalTiles']} · {p['message']}"))
    ds.check_cancel(cancel)
    if (result.get("cancelled") or result.get("width") != pw or result.get("height") != ph
            or result.get("bandCount") != 1 or result.get("dataType") != "Float32"):
        raise RuntimeError("AI result does not match the source grid/type.")
    if (tuple(float(v) for v in result.get("geoTransform") or ()) != tuple(dsm.transform)
            or not da._same_crs(dsm.projection, result.get("projectionWkt") or "")):
        raise RuntimeError("AI result changed the CRS or affine grid.")
    values = ds.read_raster(output).bands[0]
    if out.padded:
        values = array("f", (v for y in range(h) for v in values[y * pw:y * pw + w]))
    raw, final = array("f", values), array("f", values)
    for i in range(w * h):
        if not dsm.valid[i]:
            raw[i] = final[i] = dt.NODATA
            continue
        if not math.isfinite(raw[i]) or raw[i] == dt.NODATA:
            raise RuntimeError("AI returned an invalid height on a valid DSM pixel.")
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
    rgb: Ortho
    reference: dt.Raster | None
    original: Path
    manifest: dict = field(default_factory=dict)


@dataclass
class Comparison:
    classical: dt.Terrain
    ai: list                 # [pix_grad, rgb_grad_fm] AiHeight
    overlap: int
    threads: int
    model_manifests: list
    maps: list = field(default_factory=lambda: [[None] * 3 for _ in range(3)])
    full: list = field(default_factory=lambda: [dt.Score() for _ in range(3)])
    crop: list = field(default_factory=lambda: [dt.Score() for _ in range(3)])
    files: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)

    def heights(self, method: int):
        return self.ai[method - 1].dtm if method else self.classical.dtm


def evaluate(scene: Scene, result: Comparison, archive_sha256: list) -> None:
    d, ref = scene.dsm, scene.reference
    rect = da.comparison_window(scene)
    full, crop, models = {}, {}, {}
    for method in range(3):
        result.full[method] = dt.score(d, result.heights(method), ref)
        result.crop[method] = da.area_score(d, result.heights(method), ref, rect)
        full[METHODS[method]] = result.full[method].json()
        crop[METHODS[method]] = result.crop[method].json()
    crop["pixel_window"] = dict(zip(("column", "row", "width", "height"), rect))
    for model in range(2):
        a = result.ai[model]
        models[METHODS[model + 1]] = {"archive_sha256": archive_sha256[model], "manifest": result.model_manifests[model],
                                      "sdk_inference": a.provenance, "context_filled_dsm_pixels": a.context_filled,
                                      "small_input_edge_padding": a.padded, "upper_bound_clamped_pixels": a.clamped}
    result.report = {
        "schema_version": 1,
        "experiment": "independent classical / DSM-only pix_grad / DSM+RGB rgb_grad_fm",
        "source_dsm": d.path,
        "source_dsm_sha256": d.sha256,
        "source_rgb": scene.rgb.path,
        "source_rgb_sha256": scene.rgb.sha256,
        "rgb_context_filled_pixels": scene.rgb.filled,
        "reference": ref.path if ref else None,
        "reference_sha256": ref.sha256 if ref else None,
        "reference_used_for_processing": False,
        "methods_feed_each_other": False,
        "model_input_order": "pix_grad: DSM; rgb_grad_fm: DSM, R, G, B",
        "ai_options": {"overlap_pixels": result.overlap, "cpu_threads": result.threads, "tile_pixels": 256},
        "models": models,
        "classical": {"method": dt.METHOD, "parameters": result.classical.parameters.json(), "summary": result.classical.summary},
        "grid": {"width": d.width, "height": d.height, "transform": list(d.transform), "crs_wkt": d.projection},
        "evaluation": {"full": full, "comparison_crop": crop},
        "source_manifest": scene.manifest,
        "output_files": {name: name for name in result.files},
        "attribution": "Federal Office of Topography swisstopo. AI weights: David Perez, Zenodo 7973800 / 7973886, CC BY 4.0; "
                       "independent deterministic ONNX adaptations.",
        "interpretation": "Different pretrained checkpoints/training objectives; observed differences do not isolate the causal "
                          "contribution of RGB. Fixed development scene, not a held-out benchmark. Survey years and training GSD "
                          "differ or remain unverified.",
    }


def removal(d: dt.Raster, dtm) -> da.Removal:
    return da.Removal(dtm, array("f", (max(0.0, d.z[i] - dtm[i]) if d.valid[i] else dt.NODATA for i in range(d.width * d.height))))


def compare(scene: Scene, models: list, parameters: dt.Parameters, overlap: int, threads: int, folder: Path,
            archive_sha256: list, cancel, progress: ds.Progress) -> Comparison:
    """Classical, then pix_grad, then rgb_grad_fm, each from the same full source grid."""
    d, folder = scene.dsm, Path(folder)
    manifests = [ds.read_json(Path(m) / "geokernel-model.json") for m in models]
    classical = dt.estimate(d, parameters, cancel, lambda p, text: progress(int(p * 0.24), "Classical: " + text))
    ai = []
    for model in range(2):
        ai.append(infer(d, Path(models[model]), scene.rgb if model else None, overlap, threads, folder, cancel,
                        lambda p, text, m=model: progress(25 + m * 29 + int(p * 0.28), f"{METHODS[m + 1]}: {text}")))
    result = Comparison(classical, ai, overlap, threads, manifests)

    def numeric(name, values, kind=6):
        ds.check_cancel(cancel)
        result.files[name] = dt.write_raster(d, folder / name, values, kind)

    for method in range(3):
        progress(84 + method * 3, f"Preparing {METHODS[method]} outputs...")
        display = removal(d, result.heights(method))
        numeric(f"{METHODS[method]}-dtm.tif", display.dtm)
        numeric(f"{METHODS[method]}-removed.tif", display.removed)
        if method:
            numeric(f"{METHODS[method]}-raw.tif", ai[method - 1].raw)
        for mode in range(3):
            bands = (dt.relief_bands(d, display.dtm, cancel) if mode == 0
                     else dt.diagnostic_bands(d, display, 0 if mode == 1 else 2, scene.reference, cancel))
            result.maps[method][mode] = ds.write_rgb_bands(folder / f"view-{method}-{mode}.tif", d.width, d.height,
                                                           d.transform, d.projection, bands)
    numeric("classical-qa.tif", classical.quality, 1)
    progress(96, "Writing identical source-pixel comparison crops...")
    rect = da.comparison_window(scene)
    cropped = da.cut_raster(d, rect)

    def crop(name, values):
        result.files[name] = dt.write_raster(cropped, folder / name, da.cut_values(values, d.width, rect), 6)

    crop("comparison-dsm.tif", d.z)
    for method in range(3):
        crop(f"comparison-{METHODS[method]}.tif", result.heights(method))
    if scene.reference is not None:
        crop("comparison-reference.tif", scene.reference.z)
    x0, y0, w, h = rect
    rgb_crop = [bytes(b[(y0 + y) * d.width + x0 + x] for y in range(h) for x in range(w)) for b in scene.rgb.bands]
    result.files["comparison-rgb.tif"] = ds.write_rgb_bands(folder / "comparison-rgb.tif", w, h, cropped.transform,
                                                            d.projection, rgb_crop)
    evaluate(scene, result, archive_sha256)
    ds.check_cancel(cancel)
    return result


def attach_reference(scene: Scene, result: Comparison, folder: Path, archive_sha256: list, cancel, progress) -> Comparison:
    """New error maps, crop file and scores for a new evaluation reference; heights unchanged."""
    out = replace(result, maps=[list(m) for m in result.maps], files=dict(result.files), full=list(result.full),
                  crop=list(result.crop))
    d = scene.dsm
    for method in range(3):
        progress(30 + method * 20, "Preparing reference error maps...")
        bands = dt.diagnostic_bands(d, da.Removal(result.heights(method), array("f")), 2, scene.reference, cancel)
        out.maps[method][2] = ds.write_rgb_bands(Path(folder) / f"reference-{method}.tif", d.width, d.height,
                                                 d.transform, d.projection, bands)
    rect = da.comparison_window(scene)
    out.files["comparison-reference.tif"] = dt.write_raster(
        da.cut_raster(d, rect), Path(folder) / "comparison-reference.tif", da.cut_values(scene.reference.z, d.width, rect), 6)
    evaluate(scene, out, archive_sha256)
    return out


def export_bundle(result: Comparison, base: Path, cancel, progress) -> Path:
    return da.export_bundle(result, base, cancel, progress, "dsm-ortho-dtm", ".dsm-ortho-export-")
