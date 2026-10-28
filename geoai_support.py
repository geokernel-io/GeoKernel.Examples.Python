"""Shared runtime and immutable-input preparation for the new GeoAI examples."""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import threading
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class Cancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class GeoAiProfile:
    task: str
    title: str
    run_label: str
    model_url: str
    model_sha: str
    data_url: str
    data_sha: str
    raster_name: str
    display_name: str
    description: str
    legend: str
    credits: str
    buildings: bool = False
    threshold_label: str = "Building threshold"
    export_name: str = ""
    archived_data: bool = True


DYNAMIC_WORLD = GeoAiProfile(
    task="dynamic-world", title="Google Dynamic World — land cover",
    run_label="Run land-cover classification",
    model_url="https://pub-00d214f25f754884b22349c19ac37bbf.r2.dev/geokernel-models/google-dynamicworld-geokernel-onnx-v1.zip",
    model_sha="326bb2899cdea6e620a02f5e16fd330ec848e0a5b76f72f576038d7bc1e0aa63",
    data_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/spain_sentinel2_l1c.zip",
    data_sha="07811e9600882c526185268c5b280134e5715c95042754e414d6736fa5647839",
    raster_name="dynamicworld_spain_sentinel2_l1c.tif", display_name="dynamicworld_spain_rgb.tif",
    description="Spain / Alicante · Sentinel-2 L1C · 512 × 512 · 10 m\nNo predictions are loaded at startup.",
    legend="Water · Trees · Grass · Flooded vegetation · Crops · Shrub and scrub · Built · Bare · Snow and ice",
    credits="Contains modified Copernicus Sentinel data 2019.\nModel: Google / National Geographic / WRI.\nApache-2.0; retain downloaded notices.",
)

HOTOSM = GeoAiProfile(
    task="hotosm-buildings", title="HOTOSM DINOv3-S — building footprints",
    run_label="Run building segmentation inference",
    model_url="https://pub-00d214f25f754884b22349c19ac37bbf.r2.dev/geokernel-models/hotosm-dinov3s-buildings-geokernel-onnx-v1.zip",
    model_sha="3a6cd11e013f81b46b3db700feddef2d98319780285b8320e1200573684b24bb",
    data_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/buildings.zip",
    data_sha="f7cb0554b54c8e8bf31d576c38f988a8902382ad2ec3db3de6de05f5dbfb6f2b",
    raster_name="buildings.tif", display_name="buildings.tif",
    description="Buildings RGB sample · original raster resolution\nNo predictions are loaded at startup.",
    legend="Building footprints",
    credits="Model: HOTOSM / Meta DINOv3.\nCC-BY-4.0 + separate DINOv3 License; retain notices.\nImagery source/license not verified.",
    buildings=True,
)


GEOAI_USA = GeoAiProfile(
    task="geoai-usa-buildings", title="GeoAI USA — Mask R-CNN building footprints",
    run_label="Run building segmentation inference",
    model_url="https://pub-00d214f25f754884b22349c19ac37bbf.r2.dev/geokernel-models/giswqs-geoai-usa-maskrcnn-resnet50-fpn-geokernel-onnx-v1.zip",
    model_sha="055097781e125083201421c37c70d36336f2f968b69b1aa09350578d2c87ca32",
    data_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/buildings.zip",
    data_sha="f7cb0554b54c8e8bf31d576c38f988a8902382ad2ec3db3de6de05f5dbfb6f2b",
    raster_name="buildings.tif", display_name="buildings.tif",
    description="Buildings RGB sample · USA-trained aerial checkpoint\nNo predictions are loaded at startup.",
    legend="Building footprints",
    credits="Model: giswqs/geoai — Mask R-CNN ResNet50 FPN.\nMIT model declaration; retain package notices.\nImagery source/license not verified.",
    buildings=True, threshold_label="Confidence threshold",
)


PRITHVI = GeoAiProfile(
    task="prithvi-flood", title="IBM/NASA Prithvi EO 2.0 — flood analysis",
    run_label="Run flood analysis",
    model_url="https://pub-00d214f25f754884b22349c19ac37bbf.r2.dev/geokernel-models/ibm-nasa-prithvi-eo2-300m-tl-sen1floods11-geokernel-onnx-v1.zip",
    model_sha="34711ae55d48fe265b19c18551aef4b4aa84045a07bffb407161570b19429c13",
    data_url="https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/flood_analysis.zip",
    data_sha="059e9a84bed08ea5da76941432e6e8409bd1352661ff72f750e47df5f740c38f",
    raster_name="India_900498_S2Hand.tif", display_name="",
    description="India · Sentinel-2 L1C · 512 × 512\nRGB display uses B4/B3/B2; inference uses six spectral bands.\nNo predictions are loaded at startup.",
    legend="Non-water · Water / flood",
    credits="Model: IBM / NASA Prithvi EO 2.0; Apache-2.0.\nImagery: Copernicus / Sen1Floods11 (Cloud to Street).\nRetain package/source notices.",
    export_name="flood-extent.shp",
)


PRUE = GeoAiProfile(
    task="prue-fields", title="Fields of The World / PRUE — field boundaries",
    run_label="Run field boundary segmentation",
    model_url="https://pub-00d214f25f754884b22349c19ac37bbf.r2.dev/geokernel-models/fieldsoftheworld-prue-efficientnet-b5-ccby-geokernel-onnx-v2.zip",
    model_sha="0035f723ae5753eb861e056bbb38b60605617485c9700cc16d3317856374da44",
    data_url="https://raw.githubusercontent.com/fieldsoftheworld/ftw-baselines/779b809813b301de7fb9f00f0c5db07086b23227/tests/data-files/inference-img.tif",
    data_sha="da482e7987b36898bd9f8381e7c7fe95c05dfc5ccbba19a58eb65e544d1af750",
    raster_name="inference-img.tif", display_name="",
    description="FTW Sentinel-2 sample · 578 × 379 · two periods, eight bands\nNo predictions are loaded at startup.",
    legend="Background · Field interior · Field boundary",
    credits="Model: FTW / PRUE EfficientNet-B5 CC-BY.\nWeights: CC-BY-4.0; upstream code: MIT.\nImagery: Sentinel-2 / FTW test sample; retain source notices.",
    export_name="field-interiors.shp", archived_data=False,
)


@dataclass(frozen=True)
class PreparedRaster:
    raster: Path
    display: Path


def asset_cache(sha256: str) -> Path:
    base = Path(os.environ.get("GEOKERNEL_EXAMPLES_DATA_DIR") or
                str(Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "GeoKernel/Examples/GeoAI"))
    return base / sha256


def configure_sdk() -> None:
    from importlib import metadata, util

    try:
        version = metadata.version("geokernel")
    except metadata.PackageNotFoundError:
        raise RuntimeError("Install the published SDK: python -m pip install -r requirements-geoai.txt") from None
    if version != "1.5.39":
        raise RuntimeError(f"GeoAI examples require geokernel 1.5.39; installed: {version}. Install requirements-geoai.txt.")
    spec = util.find_spec("geokernel")
    if spec is None or spec.origin is None:
        raise RuntimeError("The installed GeoKernel package could not be located.")
    # Default to this installed wheel's runtime, never a sibling source checkout.
    os.environ.setdefault("GEOKERNEL_BIN", str(Path(spec.origin).parent / "bin"))


def check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise Cancelled("Cancelled.")


def _sha256(path: Path, cancel: threading.Event) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            check_cancel(cancel)
            digest.update(block)
    check_cancel(cancel)
    return digest.hexdigest()


def prepare_asset(url: str, sha256: str, required: str, cancel: threading.Event,
                  progress: Callable[[int, str], None], *, archive: bool = True) -> Path:
    """Run on a worker. Cache inputs only; predictions stay in the native job."""
    root = asset_cache(sha256)
    root.mkdir(parents=True, exist_ok=True)
    download = root / ("download.zip" if archive else required)
    if not download.is_file() or _sha256(download, cancel) != sha256:
        partial = root / f"{uuid.uuid4()}.part"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "GeoKernel-GeoAI-Examples"})
            with urllib.request.urlopen(request, timeout=30) as response, partial.open("xb") as target:
                total = int(response.headers.get("Content-Length", 0))
                received = 0
                while block := response.read(256 * 1024):
                    check_cancel(cancel)
                    target.write(block)
                    received += len(block)
                    progress(int(received * 100 / total) if total else 0,
                             f"Downloading {url.rsplit('/', 1)[-1]} — {received / 1048576:.1f} MB")
            if _sha256(partial, cancel) != sha256:
                raise RuntimeError("Download SHA-256 mismatch. Please retry.")
            partial.replace(download)
        finally:
            partial.unlink(missing_ok=True)
    if not archive:
        return download
    content = root / "content"
    if not content.is_dir():
        staging = root / f"extract-{uuid.uuid4()}"
        try:
            staging.mkdir()
            with zipfile.ZipFile(download) as source:
                for member in source.infolist():
                    check_cancel(cancel)
                    destination = (staging / member.filename).resolve()
                    if not destination.is_relative_to(staging.resolve()):
                        raise RuntimeError("Unsafe path in model/sample archive.")
                    progress(0, f"Extracting {member.filename}…")
                    source.extract(member, staging)
            check_cancel(cancel)
            try:
                staging.rename(content)
            except OSError:
                if not content.is_dir():
                    raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    matches = list(content.rglob(required))
    if len(matches) != 1 or not matches[0].is_file():
        raise RuntimeError(f"Expected one {required} in the package; found {len(matches)}.")
    return matches[0]
