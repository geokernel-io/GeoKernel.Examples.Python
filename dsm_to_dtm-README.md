# DSM to DTM — ground beneath buildings (Python)

Python port of the Qt `DsmToDtm` example. An original DSM stays visible beside a
prepared terrain estimate in two linked **native GeoKernel 3D** viewers. Uses
published **geokernel 1.5.40** and PySide6. Numeric rasters are read and written
with the GDAL runtime shipped in the SDK; NumPy, rasterio and system GDAL are not
required. No model weights or AI service are needed: **no inference runs here**.

Requires Windows x64, Python 3.11+ (matching PySide6 6.11), Vulkan and a valid
GeoKernel license. From this repository:

```powershell
py -3.11 -m venv .venv-dsm
.\.venv-dsm\Scripts\python.exe -m pip install -r requirements-dsm-to-dtm.txt
.\.venv-dsm\Scripts\python.exe dsm_to_dtm.py
```

## Workflow

1. Startup downloads the fixed sample ZIP from the `GeoKernel.SampleData` **v1
   release**. The ZIP and every extracted file are SHA-256 checked against
   [dsm_to_dtm-sample-assets.json](dsm_to_dtm-sample-assets.json). A complete valid
   cache under `data/zurich-dsm-to-dtm-v2` works offline.
2. The left view always shows the **original DSM: roofs, trees and ground**. The
   right initially shows the **classical DTM at 100%**. Pan, orbit or zoom either
   view; the other follows.
3. Select **Classical / morphological-TIN** or **AI / DSM-only pix_grad**. Both are
   independent prepared estimates from the same original DSM.
4. Move the surface slider and release. **0% is exactly the original DSM; 100% is
   exactly the selected prepared DTM.** Intermediate values interpolate numeric
   heights, `(1-t)*DSM+t*DTM`, written to a temporary Float32 GeoTIFF and rebuilt
   as native terrain. Keyboard changes use a short debounce.
5. The profile chart samples all four original rasters on the fixed building
   transect. Gray: DSM; teal: classical; purple: AI; dashed orange: reference DTM.
6. Vertical exaggeration applies to both views (default 1×).
7. Cancel keeps the previous complete views and restores the last committed
   selection. Closing during preparation cancels first, then releases both viewers.

The reference DTM is used only for the profile and the stored crop scores; it
never enters estimation or interpolation. Temporary GeoTIFFs are deleted on exit.

## Differences from the Qt example

The published Viewer3D C API has no exact ENU camera mapping and no analysis-line
overlay, so this port:

- copies render-space cameras directly between the two viewers. Both scenes use
  the same grid and grid-centre origin, so the cameras correspond to within 1e-5;
- shows the fixed transect only in the profile chart, without the two-endpoint 3D
  guide line;
- shows an indeterminate progress bar while Viewer3D prepares terrain, because the
  C API does not report native load progress.

## Options

```powershell
.\.venv-dsm\Scripts\python.exe dsm_to_dtm.py --sample-archive D:\data\zurich_dsm_to_dtm_v2.zip
.\.venv-dsm\Scripts\python.exe dsm_to_dtm.py --sample-url https://mirror.example/zurich_dsm_to_dtm_v2.zip
.\.venv-dsm\Scripts\python.exe dsm_to_dtm.py --data-dir D:\cache\geokernel
```

All hash pins still apply to a local archive or mirror.

## Data

All rasters share 500 × 500 pixels at 0.5 m, EPSG:2056, heights in the
source-declared LN02 reference (EPSG:5728), metres; there is no vertical datum
conversion. Crop reference errors (250,000 shared pixels): classical RMSE 1.01 m /
MAE 0.35 m, AI RMSE 0.66 m / MAE 0.41 m. These are scores for this fixed crop, not a
held-out benchmark.

Data: **Federal Office of Topography swisstopo**, swissSURFACE3D Raster and
swissALTI3D ([OGD terms](https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices)).
AI: David Perez's [pix_grad checkpoint](https://doi.org/10.5281/zenodo.7973800),
CC BY 4.0. The archive contains derived output only, no weights.
