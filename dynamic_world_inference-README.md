# Dynamic World — Python / PySide6

Nine-class land-cover classification on the fixed Spain Sentinel-2 L1C raster.

## SDK and setup

Uses the published **geokernel 1.5.39** PyPI package and its bundled native runtime. Windows x64, Python 3.10+ and the matching PySide6 6.11.0 are required. No sibling SDK repository or native build is needed.

```powershell
python -m pip install -r requirements-geoai.txt
python dynamic_world_inference.py
```

The SDK is imported from the installed package. Models and sample data are downloaded by the example when needed. `GEOKERNEL_BIN` is available only as an explicit compatible-runtime override; it is not pointed at a sibling checkout automatically.


## Workflow

Startup downloads/caches only the original RGB source and its spectral input. No predictions are restored.
Click Run land-cover classification to prepare the fixed model and start native background inference.
The reference produces 1400 class polygons. This is a reproducibility count, not an accuracy score.

The output transparency slider becomes more opaque to the right. Save Shapefile opens the file dialog;
choose a new destination, since the native exporter does not replace an existing Shapefile dataset.
Cancel is cooperative. During close the viewer's result layers are detached before the AI job is released.
The window stays in its event loop while background cleanup finishes.

Input/model downloads, hashing, extraction, export and task release use a worker. Polling and viewer operations stay on the Qt thread.
The native job owns inference. Input files are SHA-256 verified and cached at `%LOCALAPPDATA%/GeoKernel/Examples/GeoAI`,
shared with the .NET examples, or `GEOKERNEL_EXAMPLES_DATA_DIR` if configured. Only inputs are cached; results are session-only.

Auto currently selects CPU. CUDA requires matching GPU ONNX Runtime and CUDA/cuDNN files in the selected native deployment.
The example does not install GPU dependencies or silently fall back from an explicit CUDA selection.

Scientific input is the original nine-band L1C DN stack, with normalization embedded in the ONNX model.
The separate RGB display is not used as inference input. Water class 0 is valid; NoData is excluded.
Model/imagery attribution and hashes are in [dynamic_world_inference-data-sources.md](dynamic_world_inference-data-sources.md).
No license keys or command-line validation modes are included.
