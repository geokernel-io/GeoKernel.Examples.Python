# DSM to DTM — live AI versus classical (Python)

Python port of the Qt `DsmToDtmAI` example: run the experimental **pix_grad** model through
**GeoKernel.AI**, run the native classical filter independently on the same DSM, and
compare the newly generated heights. Three linked native GeoKernel **2D maps** keep the
original DSM on the left. Neither method receives the reference or the other method's
terrain estimate. Uses published **geokernel 1.5.40** and PySide6; inference goes through
the SDK's raster inference C ABI (`geokernel.ai.AI`), rasters through the SDK's GDAL
runtime (no NumPy, rasterio, ONNX Runtime or system GDAL). Support code is in
`dsm_ai.py`, the classical algorithm in `dsm_terrain.py`, the window in
`dsm_to_dtm_ai.py`.

Requires Windows x64, Python 3.11+ and a valid GeoKernel license. Same environment as
the other DSM examples:

```powershell
py -3.11 -m venv .venv-dsm
.\.venv-dsm\Scripts\python.exe -m pip install -r requirements-dsm-to-dtm.txt
.\.venv-dsm\Scripts\python.exe dsm_to_dtm_ai.py
```

Options: `--data-dir <directory>` (cache root for terrain, support and model files),
`--model-archive <zip>` / `--model-url <https-url>` (the exact pinned model ZIP),
`--sample-archive <zip>` / `--sample-url <https-url>` (the pinned Zurich v2 support ZIP,
not the 1 km source). All hash pins still apply.

## Workflow

1. Startup verifies the Zurich v2 support ZIP ([pins](dsm_to_dtm-sample-assets.json)) for
   the matching PROJ database, then downloads **the original full 1 km DSM and reference**
   directly from swisstopo (2000 × 2000 at 0.5 m, EPSG:2056; sizes and SHA-256 in
   [dsm_to_dtm_ai-terrain-assets.json](dsm_to_dtm_ai-terrain-assets.json)).
2. The model package is then acquired and its archive plus every package file checked
   against [dsm_to_dtm_ai-model-assets.json](dsm_to_dtm_ai-model-assets.json). **Use model
   ZIP** supplies the same pinned package locally; it does not accept arbitrary weights.
3. Choose tile overlap (default **64 px**, 0–128), CPU threads (default 4) and a classical
   preset, then **Run AI + classical**. The classical result is computed first, then an
   independent GeoKernel.AI inference from the same source DSM. The status bar shows the
   phases and AI tile counts.
4. Compare **terrain relief**, **removed heights** (one fixed 0–20 m scale) or **signed
   reference errors** (one fixed −2 to +2 m scale). Both terrain maps share identical
   lighting. Display limits never clip the numeric scores. Gray is NoData.
5. **Full input** scores all common valid pixels. **Shared comparison crop** zooms to the
   250 × 250 m window of the earlier Zurich examples (column 200 / row 800, 500 × 500
   cells); everything outside it is dimmed. Both methods still process all 4 million cells.
6. Pan/zoom is linked. With Pan active, click a cell to read original, classical, AI and
   reference heights; a marker shows it on every map. Display, scope and viewport changes
   never rerun inference.
7. Changing processing settings keeps the last comparison visible and marks it as needing
   a new run. **Cancel** keeps the completed comparison.
8. **Open DSM GeoTIFF** loads a custom source (its comparison crop is the central 60% in
   each axis) and clears the reference and estimates. **Open reference** attaches an
   exactly aligned evaluation-only raster without rerunning inference.
9. **Save comparison folder** stages every file plus `comparison.json` in the chosen parent
   and renames the staging folder to a new `dsm-dtm-ai-<UTC time>-<id>` folder only when
   everything is complete. Existing files are never overwritten.

| File | Content |
| --- | --- |
| `classical-dtm.tif`, `ai-dtm.tif` | Full-grid Float32 terrain heights |
| `ai-raw.tif` | SDK blended heights before the final upper-bound check |
| `classical-removed.tif`, `ai-removed.tif` | Full-grid DSM minus final terrain |
| `classical-qa.tif` | Classical QA bits 1 NoData, 2 interpolated, 4 hull fallback, 8 edge band, 16 clamped |
| `comparison-dsm.tif`, `comparison-classical.tif`, `comparison-ai.tif` | Exact comparison-crop cells |
| `comparison-reference.tif` | Optional matching evaluation crop |
| `comparison.json` | Source/model hashes, parameters, SDK inference provenance, full and crop scores, files, attribution |

## Numeric behaviour and results

The request uses the package's tiling and normalization, `floatBands` output and band 1.
Missing DSM cells are filled for input context only, by four-neighbour propagation from
valid DSM cells; the original mask is restored on output. The graph bounds its output by
the DSM; the example keeps the raw blended raster and applies a final upper bound (its
count is recorded). On large custom inputs the classical working spacing is increased
until the support grid fits 262,144 cells.

On the full Zurich tile every output raster (all 4 million cells, including the six
display maps and the crops) is **identical to the Qt build**, and so are the scores:

| Scope | Method | RMSE (m) | MAE (m) | Bias (m) |
| --- | --- | --- | --- | --- |
| Full input (4,000,000 px) | Classical (Balanced) | 1.300 | 0.517 | 0.400 |
| | AI · pix_grad (overlap 64) | 1.749 | 0.981 | −0.668 |
| Shared crop (250,000 px) | Classical | 1.018 | 0.355 | 0.253 |
| | AI · pix_grad | 0.659 | 0.407 | −0.277 |

121 AI tiles, 33,253 AI upper-bound clamps; classical 161,079 supports. A small custom
input with NoData holes (220 × 190, context fill and edge padding) also matched the Qt
build exactly.

Supported inputs: one north-up metre-height band, projected metre CRS, square pixels,
identity scale/offset, 8 × 8 to 4 million cells, at least 5% valid. The reference must
share the exact grid and an equivalent CRS.

## Differences from the Qt example

- Inference uses the SDK's JSON raster inference C ABI instead of the C++
  `AiRasterInferenceExecutor::requestFromPackage`. That entry point has no separate
  context band, source-mask or padding options, so the example prepares them itself: the
  context-filled DSM is the inference raster, inputs smaller than one tile are edge-padded
  right/bottom (the package's padding mode) and the result is cropped, and the source mask
  is re-applied afterwards. The results are the same as Qt's; `comparison.json` records
  `small_input_edge_padding`, and the SDK provenance describes the raster actually sent.
- The C ABI has no cancellation hook, so **Cancel** and closing the window take effect
  when the running AI pass ends (about 4–8 s for the 1 km tile on 4 CPU threads).
- The model is prepared on the worker thread, not the GUI thread.
- The comparison crop is outlined with a solid line (owned shapes have no dash style) and
  dimmed with four translucent polygons. The probe marker is a native overlay point.
  Views are linked by extent, so maps whose sizes differ by a pixel show a fractionally
  different vertical range.

## Model and attribution

Weights: **David Perez**, [Zenodo 7973800](https://doi.org/10.5281/zenodo.7973800),
**CC BY 4.0**, as the deterministic ONNX adaptation described in the Qt example (ONNX
SHA-256 `e400e27f6afc75bcf4e1a61432ee9557529683903996dd953d3e8e3fcbe90eb6`). One Float32
NCHW 256 × 256 DSM-only input; per-tile min/max normalization is inside the graph.
Training region Brussels/UrbIS; generalization to this input is unverified.

Terrain: **Federal Office of Topography swisstopo**, swissSURFACE3D Raster (2018) and
swissALTI3D (2019), LN02 heights, no vertical datum conversion. Fixed development scene,
**not a held-out benchmark**. The model can smooth real terrain, introduce bias and leave
tile artifacts; a smaller RMSE in one crop does not establish superiority elsewhere.
