# DSM to DTM — live classical processing (Python)

Python port of the Qt `DsmToDtmProcessing` example: **run a classical conversion on the
input DSM**, change parameters, inspect the newly generated terrain and export numeric
GeoTIFFs. Three linked native GeoKernel **2D maps** show the original DSM, the generated
DTM and a selectable diagnostic map. Uses published **geokernel 1.5.40** and PySide6;
rasters are read, gridded and written with the SDK's GDAL runtime (no NumPy, rasterio or
system GDAL). The algorithm is in `dsm_terrain.py`, the window in
`dsm_to_dtm_processing.py`.

Requires Windows x64, Python 3.11+ and a valid GeoKernel license. Same environment as
the other DSM examples:

```powershell
py -3.11 -m venv .venv-dsm
.\.venv-dsm\Scripts\python.exe -m pip install -r requirements-dsm-to-dtm.txt
.\.venv-dsm\Scripts\python.exe dsm_to_dtm_processing.py
```

Options: `--data-dir <directory>`, `--sample-archive <exact-v2.zip>`,
`--sample-url <https-mirror>`; all hash pins still apply.

## Workflow

1. Startup reuses the verified Zurich v2 sample ([pins](dsm_to_dtm-sample-assets.json))
   and shows its original DSM. Nothing is converted until **Run DSM → DTM** is pressed.
2. Choose **Balanced**, **Remove more objects** or **Preserve more relief**, or adjust the
   six parameters, then press **Run**. Processing runs in a worker thread; the status bar
   shows the phase. **Cancel** discards unfinished work and keeps the last completed
   source/result.
3. The middle map shows the new DTM with the same hillshade as the original. Pan/zoom is
   linked across all three maps. With Pan active, click a pixel to read DSM, DTM, removed
   height, QA bits and the optional reference/error; a marker shows the cell on every map.
4. The right map shows **removed height** (DSM − DTM, fixed 0–20 m colours), **support /
   edge quality** or **signed reference error** (fixed −2 to +2 m). Colours never clip
   the numeric results or scores. NoData is gray.
5. Changing parameters keeps the last result and scores on screen, marked as needing a
   new run. The summary and export keep the parameters actually used.
6. **Open DSM GeoTIFF** loads another source and clears the old result and reference.
   **Open reference (optional)** attaches an exactly aligned evaluation raster and
   updates scores without recomputing the DTM.
7. **Save result GeoTIFFs** writes `<name>.tif`, `<name>.removed.tif`, `<name>.qa.tif`
   and `<name>.json`, each atomically. Source and reference paths are rejected as output
   names, and existing companions need a replacement decision.

## Processing method

Method ID `native-multiscale-morphological-tin-v1`, the same steps as the Qt example:
a block-minimum lower envelope that keeps each minimum's real source position;
reflected-boundary morphological openings at doubling window sizes with a capped
base/slope allowance plus a DSM-derived terrain-slope allowance (reduced in rough areas);
GDAL linear TIN gridding at the source pixel centres; a grid-support fallback outside the
hull; retention of source samples within the keep tolerance; and clamping to the DSM. The
reference is never an input to processing; it is only used afterward for scores.

Intermediate grids use Float32 like the C++ code, so on the Zurich sample the Python
result is **identical to the Qt build**: Balanced gives 10485 supports, 2582 hull-fallback
pixels, and the same DTM, removed-height and QA rasters on all 250,000 cells. Scores: all
cells RMSE 0.863 / MAE 0.324 / bias 0.200 m; interior (138,384 px, outside the 32 m edge
band) RMSE 0.532 / MAE 0.220 / bias 0.098 m.

| Control | Meaning |
| --- | --- |
| Working grid | Requested support-cell spacing, rounded to an integer source-pixel factor. |
| Max. window | Largest opening scale; larger objects need larger surrounding support. |
| Base threshold | Initial allowed height above the morphological lower envelope. |
| Slope allowance | Extra base allowance per metre of window, capped at 3 m with the base term. |
| Relief allowance | Weight of the DSM-derived terrain-slope term. |
| Keep tolerance | Maximum difference for retaining original samples in candidate cells. |

## Output and quality

Heights are Float32 metres with NoData −9999; the QA raster is Byte with NoData 1. The
JSON holds the parameters, effective working grid, source hashes and CRS, support
statistics, both scores and provenance. Each file is written atomically; there is no
transaction across the four files, so a failure reports any files already committed.

QA bits: 1 source NoData, 2 interpolated, 4 outside the TIN hull (fallback), 8 edge band
(half the maximum window), 16 clamped to the DSM. The QA display prioritises fallback
purple, edge orange, interpolated pale and retained teal; the raster keeps all bits.

## Supported inputs and limitations

Single-band north-up GeoTIFF with square pixels in a projected metre CRS; heights in
metres. 8 × 8 to 4 million source cells with at least 5% valid; the working grid must be
3 × 3 to 262,144 cells and the maximum window at least two working cells. The optional
reference must match the grid and CRS exactly. GDAL's TIN construction cannot be
interrupted; cancellation is checked before and after it.

## Differences from the Qt example

The probe marker is a native overlay point (`NativeMap` in `dsm_maps.py`) instead of a Qt
painter overlay. Views are linked by extent, so maps whose heights differ by a pixel show
a fractionally different vertical range. The viewer has no EPSG:2056 preset; each map
adopts its first layer's CRS.

## Data

500 × 500 cells, 0.5 m, EPSG:2056, LN02 heights (EPSG:5728), no vertical datum
conversion. Source: **Federal Office of Topography swisstopo** (swissSURFACE3D Raster,
swissALTI3D). Fixed development crop, **not a held-out benchmark**. The prepared
classical/AI rasters in the sample are not used here.
