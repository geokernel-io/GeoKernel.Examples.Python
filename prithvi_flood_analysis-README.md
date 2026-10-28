# Prithvi flood analysis — Python / PySide6

IBM/NASA Prithvi EO 2.0 300M-TL Sen1Floods11 water/flood mapping on the fixed India Sentinel-2 raster.

## SDK and setup

Uses the published **geokernel 1.5.39** PyPI package and its bundled native runtime. Windows x64, Python 3.10+ and the matching PySide6 6.11.0 are required. No sibling SDK repository or native build is needed.

```powershell
python -m pip install -r requirements-geoai.txt
python prithvi_flood_analysis.py
```

The SDK is imported from the installed package. Models and sample data are downloaded by the example when needed. `GEOKERNEL_BIN` is available only as an explicit compatible-runtime override; it is not pointed at a sibling checkout automatically.


## Workflow

Startup downloads/caches only the original RGB source and its spectral input. No predictions are restored.
Click Run flood analysis to prepare the fixed model and start native background inference.
The reference produces 57 connected water/flood polygons. This is a reproducibility count, not an accuracy score.

The output transparency slider becomes more opaque to the right. Save Shapefile opens the file dialog;
choose a new destination, since the native exporter does not replace an existing Shapefile dataset.
Cancel is cooperative. During close the viewer's result layers are detached before the AI job is released.
The window stays in its event loop while background cleanup finishes.

Input/model downloads, hashing, extraction, export and task release use a worker. Polling and viewer operations stay on the Qt thread.
The native job owns inference. Input files are SHA-256 verified and cached at `%LOCALAPPDATA%/GeoKernel/Examples/GeoAI`,
shared with the .NET examples, or `GEOKERNEL_EXAMPLES_DATA_DIR` if configured. Only inputs are cached; results are session-only.

Auto currently selects CPU. CUDA requires matching GPU ONNX Runtime and CUDA/cuDNN files in the selected native deployment.
The example does not install GPU dependencies or silently fall back from an explicit CUDA selection.

Scientific input is the original 13-band L1C chip. Inference selects B2/B3/B4/B8A/B11/B12; normalization is embedded in ONNX.
The separate RGB display uses B4/B3/B2 with a 2–98% channel stretch, preserving source CRS/affine. It is prepared on a worker
using the SDK-shipped GDAL, without extra rasterio/PyTorch dependencies or modifications to the spectral input.
Only the derived RGB display is cached; prediction files remain temporary.

Class 0 is non-water; class 1 is water/flood; NoData -1 is transparent. The raster preview shows both valid classes,
while Save Shapefile exports only class-1 polygons. The reference is 57 polygons over nine tiles, with 139744 non-water
and 122400 water pixels. A single image cannot distinguish permanent water from newly flooded land.
Model loading has a multi-GB working set, and cancellation may wait for loading or the current tile to finish.
Model/imagery attribution and hashes are in [prithvi_flood_analysis-data-sources.md](prithvi_flood_analysis-data-sources.md).
No license keys or command-line validation modes are included.
