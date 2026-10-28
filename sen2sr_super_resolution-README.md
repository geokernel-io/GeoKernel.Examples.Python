# SEN2SR super resolution — Python / PySide6

ESAOpenSR SEN2SRLite RGBN 4× super resolution on the fixed Sentinel-2 / FTW sample.

## SDK and setup

Uses the published **geokernel 1.5.39** PyPI package and its bundled native runtime. Windows x64, Python 3.10+ and the matching PySide6 6.11.0 are required. No sibling SDK repository or native build is needed.

```powershell
python -m pip install -r requirements-geoai.txt
python sen2sr_super_resolution.py
```

The SDK is imported from the installed package. Models and sample data are downloaded by the example when needed. `GEOKERNEL_BIN` is available only as an explicit compatible-runtime override; it is not pointed at a sibling checkout automatically.


## Workflow

Startup downloads/verifies the pinned sample and shows only a cached RGB source display. Run prepares the fixed model and starts native background inference. No predictions are loaded at startup or saved automatically.

The original 578 × 379 eight-band TIFF is preserved. Inference uses its first period: B4/B3/B2/B8 (RGB + NIR), L2A DN with BOA correction/normalization embedded in the package. The result is 2312 × 1516 with four Float32 reflectance bands, computed over 28 overlapping tiles. The reference matches the native/Qt output pixel-for-pixel; this verifies reproducibility, not accuracy.

Once complete, the viewer loads native source/enhanced RGB comparison previews with the same contrast stretch. A bottom detail panel opens automatically: the same central 96 × 96 source-pixel region is displayed beside its actual 384 × 384 enhanced output. Both panels use the shared source-derived contrast; the original crop is enlarged bilinearly for an equal-size comparison. View > 4× detail comparison can reopen the panel. The panel is read on a worker with SDK GDAL and its image buffers are cleared on rerun. The first result is shown fully opaque (100% enhanced) by default. Zoom in to compare edge detail: the full-extent view resamples both rasters into the same display area. Move the slider left to see the source and right to see the enhanced image; the label identifies original, enhanced or blend. The slider is enabled only when a completed result is available. The current map extent is preserved on result load and rerun. Previews are display-only; the scientific output remains four-band Float32.

Save GeoTIFF opens the destination dialog and retains RGB + NIR, the source CRS/footprint, and AI provenance metadata. The affine pixel/rotation terms are divided by four while origin is preserved. Band 4 is NIR, not alpha. Float reflectance is not display-clipped. Choose a new destination; existing datasets are not overwritten. There is no Shapefile output.

Outputs are estimates on a finer grid, not new sensor measurements. Validate any measurement or downstream analysis separately. The model does not turn 10 m sensor measurements into acquired 2.5 m data.

Downloads, hashes, extraction, initial RGB preparation, export and release run on a worker. Viewer operations stay on the Qt thread; native inference runs asynchronously. Cancel is cooperative. Rerun removes both job-owned comparison previews and restores the persistent source display before releasing the previous workspace. Close waits asynchronously for task/renderer cleanup.

Inputs and derived source displays are cached at `%LOCALAPPDATA%/GeoKernel/Examples/GeoAI` or `GEOKERNEL_EXAMPLES_DATA_DIR`; inference results remain temporary until explicitly exported. The RGB helper uses SDK GDAL via ctypes, with no rasterio/PyTorch dependency. The input is a raw TIFF, downloaded directly without ZIP extraction.

Auto currently selects CPU. Explicit CUDA needs compatible GPU ONNX Runtime and CUDA/cuDNN files in the selected native deployment; the example does not install them or silently fall back. The task rejects unsupported/invalid spectral inputs and limits scientific output memory to 512 MiB.

Retain package CC0-1.0 and inherited Apache-2.0 notices. See [data sources](sen2sr_super_resolution-data-sources.md) for exact URLs, SHA-256 hashes and attribution. No application CLI/test modes or license keys are embedded.
