# SAM3 segmentation — Python / PySide6

Meta SAM3 text and interactive point/box segmentation on the fixed buildings raster.

## SDK and setup

Uses the published **geokernel 1.5.39** PyPI package and its bundled native runtime. Windows x64, Python 3.10+ and the matching PySide6 6.11.0 are required. No sibling SDK repository or native build is needed.

```powershell
python -m pip install -r requirements-geoai.txt
python sam3_segmentation_inference.py
```

The SDK is imported from the installed package. Models and sample data are downloaded by the example when needed. `GEOKERNEL_BIN` is available only as an explicit compatible-runtime override; it is not pointed at a sibling checkout automatically.


## Workflow

Startup displays only the RGB source. Generate draft prepares only the selected model profile and starts background inference. Text mode scans the source with a concept such as `building`; the score threshold defaults to 0.50. Text mode ignores map points and boxes.

Select Point / box segmentation to use the tracker. Choose Positive point, Negative point or Box: click two corners. Positive points are green, negative points red, and boxes yellow. A box surrounds one object; it does not scan an area for every building. A positive point or a completed box is required. Clear prompts removes selections. A maximum of 64 point/box tokens is supported (a box consumes two).

The map is WGS84. Prompt removal and draft discard explicitly restore WGS84 and retain the current view extent, because native layer removal can otherwise adopt the source raster CRS. The worker transforms points and all four box corners to the original raster CRS using SDK GDAL, traditional GIS axis order. The original raster is not resampled. Tracker mask quality selection is separate from the text score threshold.

The worker prepares a temporary WGS84 GeoJSON display copy of the result polygons before enabling draft review. The original GeoPackage and raster stay unchanged for export; the display copy shares the job workspace and is removed on discard or close.

Review the orange draft polygons. Accept draft enables Save Shapefile and Save accepted GeoTIFF, each with a destination dialog. GeoTIFF pixels contain instance IDs, not semantic classes or confidence. Discard removes the temporary result and allows another run. Results are never restored at startup. Choose a new export destination; existing datasets are not overwritten.

The transparency slider becomes more opaque to the right and applies alpha directly to the draft fill and outline. Downloads, hash verification, extraction, export and cleanup use a worker; native inference runs asynchronously. Cancel is cooperative and may wait for model loading/current inference. Closing cancels work and waits asynchronously for renderer/job cleanup.

Models are multi-GB FP32 bundles: text about 3.09 GB, tracker about 1.70 GB. Only the selected profile is downloaded and cached. Both use the specialized `sam3-package.json` manifest, SHA-256 verification and native bundle validation. Existing shared example caches are reused. Only inputs are cached; inference outputs remain session-only until explicitly saved.

Auto currently uses CPU. CUDA requires a compatible GPU ONNX Runtime, CUDA/cuDNN deployment and sufficient GPU memory. Set GEOKERNEL_BIN to that deployment; choosing CUDA does not install GPU dependencies. Explicit CUDA failures are reported without silent CPU fallback.

Retain the SAM License and package notices. See [data sources](sam3_segmentation_inference-data-sources.md) for the exact packages, hashes and imagery caveat. No license keys or application test/CLI modes are embedded.
