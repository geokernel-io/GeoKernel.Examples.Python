# GeoKernel Python Examples

## Tiles3DStreaming (Python)

`tiles_3d_streaming.py` prepares the Sagrada Família DEM, orthophoto, full 3D Tiles
archive and EGM08D595 geoid. The native streamer selects detail as the camera moves.
Controls include a 64–128 MiB geometry budget, start/stop, visibility and focus.
Live counters describe the cache and tile state, not total RAM/VRAM usage.

Vertical exaggeration stays at 1×. Terrain uses the regional geoid correction;
building alignment is approximate. Hiding clears tiles; showing restarts streaming.
Stop retains the currently loaded tiles.

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-tiles-3d-streaming.txt && .venv\Scripts\python.exe tiles_3d_streaming.py
```

## Measurement3D (Python)

`measurement_3d.py` downloads the Sagrada Família DEM and orthophoto automatically.
Enable Add points and click terrain to measure distance or horizontal polygon area.
The native scene displays the measurement line; the panel displays coordinates and
totals. Finish stops capture, Backspace removes the last point, and Esc clears it.

Results use physical ENU metres, independent of vertical exaggeration. 3D length
uses straight segments, not terrain-following length. Area is horizontal plan area,
not terrain surface area. Invalid polygons report an error. Maximum 64 points;
the DEM vertical datum is unverified.

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-measurement-3d.txt && .venv\Scripts\python.exe measurement_3d.py
```

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

Official Python examples for the GeoKernel native GIS SDK.

## Requirements

- Windows 10 or later
- A supported Python 3 version
- A valid GeoKernel license

## Getting Started

Choose an example directory, install its dependencies and run the Python script.

## Resources

- [GeoKernel Website](https://geokernel.io)
- [Documentation](https://docs.geokernel.io)
- [Sample Data](https://github.com/geokernel-io/GeoKernel.SampleData)

## Support

For questions, contact [admin@geokernel.io](mailto:admin@geokernel.io).

## RoadsOnTerrain (Python)

`roads_on_terrain.py` automatically downloads the Sagrada Família terrain,
orthophoto and road shapefile. It includes road visibility, color and opacity,
terrain mesh resolution, vertical exaggeration and camera reset controls.

Run from CMD:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-roads-on-terrain.txt && .venv\Scripts\python.exe roads_on_terrain.py
```

The example uses the published `geokernel==1.5.32` package. No local SDK build is required.

## Buildings3D (Python)

`buildings_3d.py` automatically downloads the Sagrada Família DEM, orthophoto
and building footprints. Buildings are clamped to the terrain. The sample uses
an illustrative default height of 9 metres because these footprints have no
measured heights. Change the height and select **Apply height / Reload sample**.
Visibility, color, opacity and terrain exaggeration are also adjustable.

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-buildings-3d.txt && .venv\Scripts\python.exe buildings_3d.py
```

The example uses the published `geokernel==1.5.32` package. No local SDK build is required.

## ModelPlacement (Python)

`model_placement.py` automatically downloads the textured Sagrada Família model,
DEM, orthophoto and EGM08D595 geoid grid. Placement controls include longitude,
latitude, above-terrain height, heading, pitch, roll and scale. Select **Apply
placement / Reload** to apply changes. The model and terrain are prepared
before the scene is displayed; no placeholder model is used.

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-model-placement.txt && .venv\Scripts\python.exe model_placement.py
```

The example uses the published `geokernel==1.5.32` package. No local SDK build is required.
Placement is approximate. Model credit and license are retained in the download.

## FeaturePicking (Python)

`feature_picking.py` automatically downloads the Sagrada Família DEM, orthophoto,
roads and building footprints. Click a building or road to inspect its source
attributes. Multiple selection, active selection, zoom to selection, visibility
and vertical exaggeration controls are included. Esc clears the selection.
Building heights are illustrative (9 metres).

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

Build the native target from a fresh CMD window:



Then run the example using the existing Python virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-feature-picking.txt && .venv\Scripts\python.exe feature_picking.py
```

## PointCloudViewer (Python)

`point_cloud.py` automatically downloads and opens the EuroSDR P4 40 × 40 m
LAZ sample. It uses the same native reader and model-preview window as the Qt,
WinForms and WPF examples. Select RGB or height colours, choose a display sample
limit of 50,000 / 100,000 / 250,000 points, cancel loading or reset the camera.
The source count, display count, source Z range and RGB availability are shown.

The preview is locally normalized. Source coordinates remain EPSG:32630; heights
are provisional. Source data is not modified. Point size is fixed at one pixel.
Downloads use the shared sample-data helper and cache. During download/extraction,
the window stays open until the helper returns; native reading can be cancelled.

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

From **CMD**, using the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-point-cloud.txt && .venv\Scripts\python.exe point_cloud.py
```

## TerrainAnalysis (Python)

`terrain_analysis.py` automatically downloads and opens the Sagrada Família
DEM, using the same native relief, slope and aspect modes as Qt and .NET.
Includes matching legends, 256/512/1024 mesh resolution, vertical exaggeration,
cancellation and camera reset.

Slope/aspect describe loaded mesh faces before exaggeration, not an exported
analysis raster. Mesh resolution affects results. Aspect is clockwise from north
in local ENU, with eight sectors spanning ±22.5° and a flat class below 0.01°.
Heights are metres with an unverified vertical reference.

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

From **CMD**, with the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-terrain-analysis.txt && .venv\Scripts\python.exe terrain_analysis.py
```

## ElevationProfile (Python)

`elevation_profile.py` automatically downloads and opens the Sagrada Família DEM
and orthophoto. Click terrain to draw a route; a resizable chart below the map
shows elevation against horizontal distance. Finish, undo or clear the route,
and adjust sample spacing from 1 to 100 metres.

Uses the same native profile calculation as Qt and .NET: 32 samples per timer
tick, up to 64 route points and 4096 samples. Results describe the loaded terrain
mesh in its unverified source vertical datum. Missing samples remain gaps;
display exaggeration does not affect measurements.

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

From **CMD**, with the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-elevation-profile.txt && .venv\Scripts\python.exe elevation_profile.py
```

## ViewshedAnalysis (Python)

`viewshed_analysis.py` automatically downloads and opens the Sagrada Família DEM
and orthophoto. Select an observer on terrain and adjust eye/target heights,
radius, ray spacing and grid resolution. Results appear in a north-up grid and
as a 55%-opacity overlay on the 3D terrain. Includes pause/resume, clear, imagery
and overlay visibility, and vertical exaggeration.

Uses the same native viewshed and triangle-clipped overlay as Qt and .NET.
Analysis samples the loaded 512-sample terrain mesh; buildings, vegetation and
refraction are excluded. Small obstacles between samples may be missed. Vertical
datum is unverified; exaggeration changes only the view.

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

From **CMD**, with the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-viewshed-analysis.txt && .venv\Scripts\python.exe viewshed_analysis.py
```

## LayerStylingAndFiltering (Python)

`layer_styling_and_filtering.py` automatically downloads and opens the Sagrada
Família DEM, orthophoto, roads and buildings using the existing sample cache.
Each vector layer keeps its visibility, opacity, uniform/source color, attribute
theme and case-insensitive literal substring filter. Includes up to 200 example
values per field, matching counts, zoom to visible matches and reset.

Filtering and styling use the same native ViewerController as Qt and .NET.
Filters search all records and affect drawing and selection. Matching counts
include records with no drawable geometry. Changes are session-only; reloading
replaces the scene. Building heights are illustrative (9 m), and the DEM vertical
datum is unverified.

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

From **CMD**, using the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-layer-styling-and-filtering.txt && .venv\Scripts\python.exe layer_styling_and_filtering.py
```

## ProjectSaveLoad (Python)

`project_save_load.py` automatically loads the Sagrada Família DEM, orthophoto,
roads and buildings using the shared sample cache. Provides Open, Save, Save as,
Ctrl+S and Ctrl+Shift+S alongside layer styling and filtering.

Uses the same native .gk3d reader/writer as Qt and .NET. Projects persist local
source references, camera, height scale, visibility, opacity, colors, themes and
filters. Pending filter text is applied before saving. Projects do not embed
datasets; keep source files accessible. Open/reload replaces the current scene.
Cancelled or failed preparation retains the previous scene. Advanced model,
point-cloud, globe, 3D Tiles, analysis, time-series and geoid-conversion projects
are outside this sample's scope.

Uses the published GeoKernel 1.5.32 package. No local SDK build or DLL override is required.

Run from CMD:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements-project-save-load.txt && .venv\Scripts\python.exe project_save_load.py
```
