# GeoAI USA building footprints — Python / PySide6

GeoAI USA Mask R-CNN ResNet50 FPN on the single fixed buildings.tif sample. Confidence threshold defaults to **0.50**; the mask threshold is fixed at 0.50.

## SDK and setup

Uses the published **geokernel 1.5.39** PyPI package and its bundled native runtime. Windows x64, Python 3.10+ and the matching PySide6 6.11.0 are required. No sibling SDK repository or native build is needed.

```powershell
python -m pip install -r requirements-geoai.txt
python geoai_usa_building_footprints.py
```

The SDK is imported from the installed package. Models and sample data are downloaded by the example when needed. `GEOKERNEL_BIN` is available only as an explicit compatible-runtime override; it is not pointed at a sibling checkout automatically.


## Workflow

Startup downloads/caches the original buildings RGB raster only. No saved predictions are restored.
Click Run building segmentation inference to prepare the fixed model and create footprints.
Only execution provider and confidence threshold are configurable; model/input/download paths remain fixed.

The result is drawn as red filled polygons with yellow boundaries. A worker converts the job-owned GeoPackage into a temporary WGS84 GeoJSON for display, with explicit fill/outline alpha for the opacity slider. The authoritative GeoPackage and its original CRS remain unchanged for Shapefile export. The display copy is removed when the job is released. The transparency slider becomes more opaque to the right.
Save Shapefile opens the file dialog. Choose a new destination; existing Shapefile datasets are not overwritten by the task exporter.
The native instance_id attribute becomes instance_i under Shapefile's ten-character field-name limit.
No instance-label TIFF, persistent prediction cache or separate prepare/download button is exposed.

Inference runs in the native task. Input preparation, hashing/extraction, export and job release use a worker.
Cancel is cooperative and may wait for the current native processing boundary.
The GUI keeps processing events while rendering and background work finish.
Re-running and closing detach the result layer and wait for render completion before releasing the temporary workspace.

## Data and model

The original 2503 × 1126 RGB raster and CRS are preserved, with no demo downsampling.
The CPU reference at threshold 0.50 produces **746 instances / 857 polygon parts**, using associated boxes/scores/classes/masks, overlap merging
and the same native pipeline as Qt/.NET. Disconnected parts can share an instance ID. Counts are a reproducibility reference, not an accuracy score.
Predictions are not ground truth, and touching/missed buildings can remain.

Inputs/model ZIPs are SHA-256 verified and cached at `%LOCALAPPDATA%/GeoKernel/Examples/GeoAI`,
shared with the .NET/Dynamic World examples, or `GEOKERNEL_EXAMPLES_DATA_DIR` if configured.
Only immutable inputs are cached; predictions remain temporary until explicit export.
Auto currently selects CPU. Explicit CUDA needs matching GPU ONNX Runtime and CUDA/cuDNN files in the native deployment;
selecting CUDA does not install support or silently fall back to CPU.

See [geoai_usa_building_footprints-data-sources.md](geoai_usa_building_footprints-data-sources.md) and downloaded package notices.
Preserve the MIT model declaration, PyTorch/torchvision licenses, attribution and conversion notices. Imagery source/license is not verified; SDK licensing is separate.
No license keys or command-line test modes are embedded.

This checkpoint is trained on USA aerial RGB imagery; accuracy outside that domain has not been established. Model-card licensing does not resolve undocumented training/imagery rights.
