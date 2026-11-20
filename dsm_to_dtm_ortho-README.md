# DSM + orthophoto to DTM — three independent methods (Python)

Python port of the Qt `DsmOrthoToDtm` example. Compare three newly computed terrain estimates
on **the same full DSM**: the native classical filter (DSM only), the experimental
**pix_grad** model (DSM only) and the experimental **rgb_grad_fm** model (DSM plus an aligned
RGB orthophoto). Four linked native GeoKernel **2D maps** keep the input context on the left,
switchable between the real orthophoto and the DSM relief. The reference is evaluation-only;
the methods do not feed each other. Uses published **geokernel 1.5.40** and PySide6; inference
goes through the SDK's raster inference C ABI (`geokernel.ai.AI`), rasters through the SDK's
GDAL runtime. Support code is in `dsm_ortho.py` (with shared pieces of `dsm_ai.py`), the
classical filter in `dsm_terrain.py`, the window in `dsm_to_dtm_ortho.py`.

```powershell
py -3.11 -m venv .venv-dsm
.\.venv-dsm\Scripts\python.exe -m pip install -r requirements-dsm-to-dtm.txt
.\.venv-dsm\Scripts\python.exe dsm_to_dtm_ortho.py
```

Options: `--data-dir <directory>`, `--sample-archive <zip>` / `--sample-url <https-url>` (the
pinned DSM + orthophoto ZIP), `--pix-model-archive`, `--rgb-model-archive`, `--pix-model-url`,
`--rgb-model-url` (the pinned model ZIPs). All archive and file hashes stay enforced.

## Data and models

The input ZIP `zurich_dsm_ortho_to_dtm_v1.zip` (GeoKernel.SampleData v1 release, pins in
[dsm_ortho_to_dtm-sample-assets.json](dsm_ortho_to_dtm-sample-assets.json)) holds the full
1 km `dsm.tif`, the aligned SWISSIMAGE `ortho_rgb.tif` (three Byte bands), the evaluation
`reference.tif`, the source manifest, notices and the matching PROJ database: 2000 × 2000
cells, 0.5 m, EPSG:2056. Models: pix_grad (Zenodo 7973800) and rgb_grad_fm (Zenodo 7973886),
both by David Perez, CC BY 4.0, as deterministic ONNX adaptations
([pix](dsm_ortho_to_dtm-pix-model-assets.json), [rgb](dsm_ortho_to_dtm-rgb-model-assets.json)).
pix_grad receives **DSM**; rgb_grad_fm receives exactly **DSM, R, G, B**.

## Workflow

1. Startup verifies/downloads the input ZIP, then both model packages (every file checked).
   The model buttons supply the same pinned ZIPs locally.
2. Choose AI overlap (64 px, 0–128), CPU threads (4) and the classical preset, then **Run all
   three methods**. Classical runs first, then pix_grad, then rgb_grad_fm (256 × 256 tiles).
3. The three estimates share one hillshade; switch them together to removed heights (0–20 m)
   or signed reference errors (−2 to +2 m). **Input context** shows the orthophoto or the DSM.
4. The default **Shared comparison crop** (column 200 / row 800, 500 × 500 cells) dims the
   rest of each map; **Full input** scores the complete valid overlap. Both are saved.
5. Pan/zoom is linked; click a cell to read RGB bytes, DSM, all three estimates and reference.
6. **Open aligned DSM + RGB** loads custom sources (crop = central 60%); **Open reference**
   attaches an aligned evaluation surface without regenerating any heights.
7. **Save comparison folder** stages the three `<method>-dtm.tif` / `-removed.tif`, both
   `<AI>-raw.tif`, `classical-qa.tif`, the `comparison-*.tif` crops (heights and RGB) and
   `comparison.json`, then renames the folder to `dsm-ortho-dtm-<UTC time>-<id>`.

Custom RGB must be three RGB-ordered Byte bands on the DSM's exact grid and cover every valid
DSM cell; RGB gaps outside valid DSM are context-filled from RGB support only, DSM gaps from
DSM support only. The source files are never edited.

## Results

On the Zurich sample every output raster (heights, raw AI, QA, nine display maps, crops) is
**identical to the Qt build**, and so are the scores:

| Method | Crop RMSE / MAE / bias (m) | Full input RMSE / MAE / bias (m) |
| --- | --- | --- |
| Classical (Balanced) | 1.018 / 0.355 / 0.253 | 1.300 / 0.517 / 0.400 |
| pix_grad (overlap 64) | 0.659 / 0.407 / −0.277 | 1.749 / 0.981 / −0.668 |
| rgb_grad_fm (overlap 64) | 0.663 / 0.399 / −0.249 | 1.615 / 0.877 / −0.561 |

A small custom input with DSM and RGB gaps (220 × 190, context fills and edge padding) also
matched the Qt build exactly. Different checkpoints and training objectives mean this does
not isolate the causal contribution of RGB; it is a fixed development scene.

## Differences from the Qt example

- Inference uses the SDK's JSON raster inference C ABI instead of the C++ `requestFromPackage`.
  It takes one raster and a band list, with no separate source bands, mask or padding options,
  so the example stacks the model channels (context-filled DSM, then R, G, B) into one Float32
  raster in the model's order, edge-pads inputs smaller than one tile and crops the result, and
  re-applies the source mask. The SDK reads every band as Float32, so the model input and the
  results are the same as Qt's; the SDK provenance describes the stacked raster.
- The C ABI has no cancellation hook: **Cancel** and closing take effect when the running AI
  pass ends (each model takes several seconds on the 1 km tile).
- Models are prepared on the worker thread. The crop is outlined with a solid line and dimmed
  with four translucent polygons; the probe marker is a native overlay point; views are linked
  by extent.
