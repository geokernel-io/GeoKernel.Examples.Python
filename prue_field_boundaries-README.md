# PRUE field boundaries — Python / PySide6

Fields of The World / PRUE EfficientNet-B5 CC-BY field segmentation on the pinned Sentinel-2 sample.

## SDK and setup

Uses the published **geokernel 1.5.39** PyPI package and its bundled native runtime. Windows x64, Python 3.10+ and the matching PySide6 6.11.0 are required. No sibling SDK repository or native build is needed.

```powershell
python -m pip install -r requirements-geoai.txt
python prue_field_boundaries.py
```

The SDK is imported from the installed package. Models and sample data are downloaded by the example when needed. `GEOKERNEL_BIN` is available only as an explicit compatible-runtime override; it is not pointed at a sibling checkout automatically.


## Workflow

Startup shows only the source image; no predictions are loaded. Run downloads/verifies the fixed model and starts native background inference. Results remain session-only. The reference produces 259 field-interior polygons over two tiles; this count is a reproducibility check, not an accuracy score.

All eight Float32 bands remain at their original 578 × 379 resolution: B4_B/B3_B/B2_B/B8_B followed by B4_A/B3_A/B2_A/B8_A. Normalization is embedded in ONNX. The raw TIFF is downloaded directly from a pinned upstream commit and SHA-256 verified; it is not a ZIP.

A worker creates a separate first-period RGB display with a 2–98% channel stretch, source CRS/affine and validity from all eight bands. It uses the SDK GDAL through ctypes, without rasterio or PyTorch dependencies. The scientific source is unchanged.

The preview shows background 0, field interior 1 and boundary 2; invalid class -1 is transparent. Save Shapefile opens a destination dialog and exports only class-1 interiors. Choose a new destination; existing Shapefile datasets are not overwritten. These are estimated agricultural field divisions, not legal/cadastral parcels.

Move the transparency slider right for a more opaque result. Cancel is cooperative. Downloads, display preparation, export and job cleanup run on a worker; viewer operations stay on the Qt thread. Close waits asynchronously for task/renderer cleanup.

Inputs and the derived source display are cached at `%LOCALAPPDATA%/GeoKernel/Examples/GeoAI` or `GEOKERNEL_EXAMPLES_DATA_DIR`. Predictions are temporary and are released after detaching result layers. Auto currently selects CPU; explicit CUDA requires a compatible GPU ONNX Runtime and CUDA/cuDNN deployment.

Model weights use CC-BY-4.0; upstream code uses MIT. Keep the downloaded package notices. See [data sources](prue_field_boundaries-data-sources.md) for URLs, hashes and attribution. No license keys or command-line test modes are included.

PRUE model v2 uses the same CCBY checkpoint at native resolution with 384 × 384 tiles and 128-pixel overlap. It requires SDK 1.5.39. Larger context reduces the rectangular top-left omission in this sample; this is a visual regression check, not a general accuracy benchmark. Model v1 remains available under its original URL.
