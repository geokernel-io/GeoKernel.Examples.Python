# Building change review — Python

Oosterwold 2016 → 2025, with synchronized native GeoKernel maps, building change
candidates, vertex editing, review decisions and approved-only GeoJSON export.
Uses published **geokernel 1.5.39**, PySide6 and NumPy. GDAL/ONNX come from the SDK;
system GDAL and a sibling SDK checkout are not required.

Requires Windows x64, Python 3.11+ (matching PySide6 6.11), a supported graphics
driver and a valid GeoKernel license. From this repository:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-building-change.txt
.\.venv\Scripts\python.exe building_change_review.py
```

Use `pythonw.exe` instead of `python.exe` to hide the console.

## Workflow

Startup downloads/verifies both images and the model; initially only imagery is
displayed. The worker prepares WGS84 display copies because the published viewer
does not reproject these ETRS89 rasters while drawing. Inference and metric areas
always use the original EPSG:25831 images. Display layers are checked against the
map coordinates before reporting Ready. A preparation failure shows its error
and **Retry loading** retries without restarting the app.

Choose **Demo area (fixed)** (320 m square), **Current view**, or
**Full dataset** (1024 m square), then **Run analysis**. Default CPU inference uses
threshold 0.4371. Settings, including the custom filter parameters, are collapsed.

Select candidates in the table. Green denotes additions, red removals and gray
rejections. Orange marks the selected location on both dates; the reference on
the 2016 image does not assert that a building existed there. Use **Edit vertices**
in the right map, with undo/redo in the active edit session. Polygon rings are
retained; multipart geometry is not flattened for editing.

Browsing uses the native selection overlay and retains image/candidate layers
and table items. **Edit vertices** opens an editable layer only for that candidate;
selecting another candidate ends the edit session and returns the map to Pan.
Review styles update the existing candidate layer. Geometry changes are published
when leaving the edit or reviewing it. The example registers the existing
`GeoKernelViewer_SelectFeatureHit` C API signature for the published Python
1.5.39 wrapper's raw API; SDK files are unchanged.

**Approve**, **Reject**, and **Pending** record reviewer and note. Editing resets
approval and recalculates area. **Export GeoJSON** writes only approved geometry;
an approval hash guards against subsequent edits. WGS84 geometry, metric area,
years, scores, parameters and data/model hashes accompany exported candidates.
Decisions remain in memory until export; a new analysis replaces them after confirmation.

Cancel retains the previous result. Instance inference cancels cooperatively;
the score inference pass must finish before cancellation/close completes.
Closing awaits workers and map readers before deleting temporary session files.
Native map events are queued before extent synchronization to avoid callback reentry.

## Filtering and Qt comparison

Native `hotosm-buildings` inference supplies instance polygons for each date.
The public 1.5.39 API does not expose its decoded score raster, so an additional
`FloatBands` inference per date supplies matching evidence. This port applies
sigmoid after logit blending; Qt decodes before tile blending. Filter defaults
match, but predictions are not bit-identical and runtime is higher.

| Filter | Minimum area | Other-date coverage below | Tolerance | Own mean at least | Other mean at most |
|---|---:|---:|---:|---:|---:|
| Conservative | 50 m² | 0.10 | 2 m | 0.75 | 0.20 |
| Balanced | 20 m² | 0.20 | 1 m | 0.55 | 0.35 |

Coverage uses other-date scores ≥ 0.25 buffered by the tolerance; border-touching
instances are excluded. Analysis and area use EPSG:25831; maps/export use WGS84.
CPU functional verification produced 0/68 instances and 42 additions in the
fixed demo. Full-dataset inference also exercised existing-building matching
(29/471 instances). Counts are not accuracy: reference change labels are absent.

## Pinned inputs and attribution

[Imagery ZIP](https://github.com/geokernel-io/GeoKernel.SampleData/releases/download/v1/almere_oosterwold_change_2016_2025_v1.zip)
contains the two `oosterwold_YEAR-epsg25831-50cm.tif` images, README, attribution
and source manifest. Each is 2048 × 2048 RGB Byte on the same 0.5 m grid.
Bounds: `657533,5800382,658557,5801406`; fixed demo:
`657885,5800734,658205,5801054` (EPSG:25831).

Imagery: Beeldmateriaal Nederland / PDOK,
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/),
[provider attribution](https://www.beeldmateriaal.nl/dataroom).
These are WMS JPEG renders of 0.25 m annual layers on a 0.5 m grid, converted
without additional pixel loss to GeoTIFF. Years identify annual layers, not
verified local capture dates; shadows and registration can create false changes.

[Model package](https://pub-00d214f25f754884b22349c19ac37bbf.r2.dev/geokernel-models/hotosm-dinov3s-buildings-geokernel-onnx-v1.zip):
HOTOSM / DINOv3-S. Retain HOTOSM attribution, model/dataset cards, CC BY 4.0 and
the separate Meta DINOv3 license and applicable terms.

| Object | SHA-256 |
|---|---|
| Imagery ZIP | `ecc35ef2c6bbdd586adc6ecc812ce1c74aee62fbf8e404de1d63b75bf7137a88` |
| 2016 image | `db723783db4c8738a716fe8b898de2e3099bab9394e335bd489db2412ae0c5c3` |
| 2025 image | `7b1b12d8b27cd0714f140415004daf9fd0000495eda31366c7cd4aab218caa82` |
| Model ZIP | `3a6cd11e013f81b46b3db700feddef2d98319780285b8320e1200573684b24bb` |
| model.onnx | `9a28e28403accc06c70a3104aedb31eca50401ed23c8ba4314b26357c25e9043` |

The shared cache is `%LOCALAPPDATA%\GeoKernel\Examples\GeoAI`, indexed by archive
hash. Override with `GEOKERNEL_EXAMPLES_DATA_DIR`. Inputs are verified and source
images remain unchanged. `building_change_review.py` contains the analysis, export, UI and worker lifecycle
in one example file. It uses the repository's shared `geoai_support.py` helpers.
