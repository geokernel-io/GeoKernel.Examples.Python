# DSM to DTM — interactive elevation profile (Python)

Python port of the Qt `DsmToDtmProfile` example. Draw your own **A → B transect** on
two linked native GeoKernel **2D maps** and compare the original DSM, classical DTM,
AI DTM and provider reference heights on one chart. Uses published **geokernel
1.5.40** and PySide6. Numeric rasters are read and the display reliefs written with
the GDAL runtime shipped in the SDK; NumPy, rasterio and system GDAL are not required.
**No inference runs here.**

Requires Windows x64, Python 3.11+ (matching PySide6 6.11) and a valid GeoKernel
license. From this repository (the same environment as `dsm_to_dtm.py`):

```powershell
py -3.11 -m venv .venv-dsm
.\.venv-dsm\Scripts\python.exe -m pip install -r requirements-dsm-to-dtm.txt
.\.venv-dsm\Scripts\python.exe dsm_to_dtm_profile.py
```

## Workflow

1. Startup reuses the pinned **Zurich v2 ZIP** of the first example: the archive and
   every extracted file are SHA-256 checked against
   [dsm_to_dtm-sample-assets.json](dsm_to_dtm-sample-assets.json). A valid cache under
   `data/zurich-dsm-to-dtm-v2` works offline. The four numeric height rasters are read
   and validated (500 × 500, 0.5 m, EPSG:2056).
2. The left map is always the original DSM. Choose **Classical / AI / Reference** for
   the right map. Both maps share position and scale; pan or zoom either one.
3. The fixed transect of the first example loads initially. Choose **Draw transect**,
   click **A**, then **B** on either map; the line appears on both maps and the chart
   updates. Dragging still pans. Toggling Draw off cancels an unfinished line and keeps
   the previous profile. Clicks outside the valid pixel centres are rejected; endpoints
   must be at least 0.5 m apart.
4. The chart shows **gray DSM, teal classical, purple AI and dashed orange reference**
   on one source-height scale. **Compare errors against reference** plots
   classical − reference and AI − reference around zero.
5. Hover over the chart to mark the sample on both maps and read its distance,
   coordinates and all four heights. **Sample spacing** (0.5–10 m) resamples the same
   line. **Clear** removes the transect; **Example** restores the fixed one.
6. **Export profile CSV** writes distance, EPSG:2056 easting/northing, all four heights
   and the classical/AI signed errors, then `<name>.csv.metadata.json` with the source
   manifest, archive hash, attribution and sampling. Each file is written atomically; a
   metadata failure is reported after the CSV is saved.
7. Cancel stops preparation; closing during loading cancels and waits for the worker
   before the maps are released. Reliefs live in a temporary folder deleted on exit.

## Numeric interpretation

Profiles sample the **Float32 height arrays**, never display pixels: bilinear
interpolation between pixel centres, no extrapolation and no vertical datum
conversion. Distances are Euclidean EPSG:2056 metres. The sample count is
`ceil(length / spacing) + 1` (at most 4096) with the actual equal spacing shown. The
RMSE/MAE card describes **this line's samples only**, not the whole scene.

Both maps use the same hillshade (azimuth 315°, altitude 40°, fixed contrast, no
per-map normalization), written as 8-bit RGB GeoTIFFs for display only.

## Differences from the Qt example

The published Python binding embeds each map as a native window, so the transect is
drawn with the viewer's own shapes rather than a Qt painter overlay: the line and the
A/B markers are owned shapes and labels, the hover sample is a native overlay point.
`SetOverlayPoint`, `RemoveOverlayShape` and `AddTextShape` are exported by the 1.5.40
runtime but not yet wrapped by geokernel 1.5.40, so `ProfileMap` (a `geokernel.Viewer`
subclass in the script) calls them through ctypes. Navigation uses the toolbar's Pan,
Zoom box, Zoom in/out and Full extent; the viewer has no EPSG:2056 preset, so each map
adopts the CRS of its first relief layer.

## Options

```powershell
.\.venv-dsm\Scripts\python.exe dsm_to_dtm_profile.py --sample-archive D:\data\zurich_dsm_to_dtm_v2.zip
.\.venv-dsm\Scripts\python.exe dsm_to_dtm_profile.py --sample-url https://mirror.example/zurich_dsm_to_dtm_v2.zip
.\.venv-dsm\Scripts\python.exe dsm_to_dtm_profile.py --data-dir D:\cache\geokernel
```

All hash pins still apply.

## Data and attribution

500 × 500 pixels, 250 × 250 m, EPSG:2056, source-declared LN02 heights (EPSG:5728) in
metres. Source: **Federal Office of Topography swisstopo** (swissSURFACE3D Raster,
swissALTI3D, [OGD terms](https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices)).
AI: David Perez's experimental DSM-only [pix_grad](https://doi.org/10.5281/zenodo.7973800),
CC BY 4.0; the archive contains derived output only. DSM/reference source years are
2018/2019; this is a fixed development scene and line errors are descriptive
comparisons, not a held-out benchmark.
