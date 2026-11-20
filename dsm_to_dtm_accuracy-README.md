# DSM to DTM — reference accuracy by area (Python)

Python port of the Qt `DsmToDtmAccuracy` example: compare **where classical and AI
terrain estimates differ from the same reference**. Three linked native GeoKernel **2D
maps** keep the original DSM on the left, with classical and AI error maps beside it.
Select an area to compare numeric errors, their distribution and individual source
pixels. Uses published **geokernel 1.5.40** and PySide6; rasters are read and written
with the SDK's GDAL runtime (no NumPy, rasterio or system GDAL). **No inference runs
here.**

Requires Windows x64, Python 3.11+ and a valid GeoKernel license. Same environment as
the other DSM examples:

```powershell
py -3.11 -m venv .venv-dsm
.\.venv-dsm\Scripts\python.exe -m pip install -r requirements-dsm-to-dtm.txt
.\.venv-dsm\Scripts\python.exe dsm_to_dtm_accuracy.py
```

Options: `--data-dir <directory>`, `--sample-archive <exact-v2.zip>`,
`--sample-url <https-mirror>`; all hash pins still apply.

## Workflow

1. Startup reuses the verified Zurich v2 sample ([pins](dsm_to_dtm-sample-assets.json))
   and prepares 19 shared-scale display maps; the status bar shows progress and
   supports cancellation.
2. **Signed reference errors**: blue below the reference, white zero, red above, on the
   same metre scale for both methods. **Absolute reference errors** shows magnitude;
   **Terrain estimates** shows both surfaces with identical hillshade.
3. **Display limit** (1, 2, 5 or 10 m) only sets colour saturation; numeric scores
   never change with colours or zoom.
4. Choose a geographic preset or **Select evaluation area** and drag a box on any map.
   The same source cells are evaluated for both methods; cells outside are dimmed on
   all three maps. **Evaluate current view** uses the visible extent; **Full sample**
   restores the complete area.
5. Read RMSE, MAE, signed bias, P95 absolute error and the share above **Large error >**.
   The sidebar names the lower RMSE and the lower MAE separately; no overall winner is
   inferred. The histogram shows six common absolute-error bins as percentages.
6. With Pan active, click a map pixel to read DSM, reference, classical and AI heights
   and both signed errors; a shared marker shows the cell on every map.
7. **Export area report** writes JSON with the metrics, histogram counts, threshold,
   native pixel window, evaluated cell bounds, source manifest, archive hash and
   attribution, atomically.

## Numeric interpretation

Scores use the Float32 source arrays. An area includes native cell centres inside its
box, clipped to the sample; the dimmed footprint is the union of those 0.5 × 0.5 m
cells. Errors are `estimate − reference`; P95 is the nearest-rank 95th percentile of
absolute errors (`ceil(0.95·N)`); the large-error count uses `abs(error) > threshold`;
histogram bins are `[0, 0.25]`, `(0.25, 0.5]`, `(0.5, 1]`, `(1, 2]`, `(2, 5]`, `(5, ∞)` m.
Pixel inspection reads the containing cell without interpolation.

Full sample (250,000 pixels): classical RMSE 1.006692 / MAE 0.350048 / bias 0.247517 m;
AI RMSE 0.659430 / MAE 0.406952 / bias −0.277471 m — AI has the lower RMSE, classical
the lower MAE. Presets are geographic windows, not land-cover classes.

## Differences from the Qt example

The maps are native windows, so the area and probe use the viewer's own drawing instead
of a Qt painter overlay: four translucent rectangles dim the outside of the area, a
solid outline marks it, and the probe is a native overlay point (`NativeMap` in
`dsm_maps.py` wraps the exported but not yet bound overlay calls). Views are linked by
extent. The viewer has no EPSG:2056 preset; each map adopts its first layer's CRS.

## Data

500 × 500 cells, 250 × 250 m, EPSG:2056, LN02 heights (EPSG:5728), no vertical datum
conversion. Source: **Federal Office of Topography swisstopo** (swissSURFACE3D Raster,
swissALTI3D). AI: David Perez's experimental DSM-only pix_grad adaptation, CC BY 4.0.
Fixed development crop, **not a held-out benchmark**; DSM 2018 / reference 2019.
