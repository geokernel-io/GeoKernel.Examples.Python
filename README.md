# GeoKernel Python Examples

All examples use the shared `requirements.txt`, pinned to GeoKernel 1.5.35.
Install once in your virtual environment with `python -m pip install -r requirements.txt`.

## GlobeHello (Python)

`globe_hello.py` uses the published **geokernel 1.5.35** package and its PySide6
Globe widget. Like Qt, WinForms and WPF GlobeHello, it starts with a blank globe;
the toolbar independently enables atmosphere, Esri satellite imagery, online DEM
and sunlight. The icon is shared with other examples and the status bar has a
fixed height. Closing the window releases the native Globe.

Requires Windows x64, Python 3.10+ and a Vulkan-capable graphics driver.
Install into a virtual environment; pip downloads the SDK, native runtime and
matching PySide6 automatically. Esri imagery/elevation require internet access.
No synthetic data, local SDK checkout, preparation script or test arguments are used.

```powershell
py -3 -m venv .venv-globe
.\.venv-globe\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-globe\Scripts\pythonw.exe globe_hello.py
```

`pythonw.exe` starts the GUI without a console. Left drag pans; right drag or wheel
zooms; middle drag / Ctrl orbits. Attribution and service errors appear in the
status bar.

## Tiles3DStreaming (Python)

`tiles_3d_streaming.py` prepares the Sagrada Família DEM, orthophoto, full 3D Tiles
archive and EGM08D595 geoid. The native streamer selects detail as the camera moves.
Controls include a 64–128 MiB geometry budget, start/stop, visibility and focus.
Live counters describe the cache and tile state, not total RAM/VRAM usage.

Vertical exaggeration stays at 1×. Terrain uses the regional geoid correction;
building alignment is approximate. Hiding clears tiles; showing restarts streaming.
Stop retains the currently loaded tiles.

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe tiles_3d_streaming.py
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

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe measurement_3d.py
```

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

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
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe roads_on_terrain.py
```

The example uses the published `geokernel==1.5.35` package. No local SDK build is required.

## Buildings3D (Python)

`buildings_3d.py` automatically downloads the Sagrada Família DEM, orthophoto
and building footprints. Buildings are clamped to the terrain. The sample uses
an illustrative default height of 9 metres because these footprints have no
measured heights. Change the height and select **Apply height / Reload sample**.
Visibility, color, opacity and terrain exaggeration are also adjustable.

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe buildings_3d.py
```

The example uses the published `geokernel==1.5.35` package. No local SDK build is required.

## ModelPlacement (Python)

`model_placement.py` automatically downloads the textured Sagrada Família model,
DEM, orthophoto and EGM08D595 geoid grid. Placement controls include longitude,
latitude, above-terrain height, heading, pitch, roll and scale. Select **Apply
placement / Reload** to apply changes. The model and terrain are prepared
before the scene is displayed; no placeholder model is used.

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe model_placement.py
```

The example uses the published `geokernel==1.5.35` package. No local SDK build is required.
Placement is approximate. Model credit and license are retained in the download.

## FeaturePicking (Python)

`feature_picking.py` automatically downloads the Sagrada Família DEM, orthophoto,
roads and building footprints. Click a building or road to inspect its source
attributes. Multiple selection, active selection, zoom to selection, visibility
and vertical exaggeration controls are included. Esc clears the selection.
Building heights are illustrative (9 metres).

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

Build the native target from a fresh CMD window:



Then run the example using the existing Python virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe feature_picking.py
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

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

From **CMD**, using the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe point_cloud.py
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

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

From **CMD**, with the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe terrain_analysis.py
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

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

From **CMD**, with the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe elevation_profile.py
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

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

From **CMD**, with the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe viewshed_analysis.py
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

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

From **CMD**, using the existing virtual environment:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe layer_styling_and_filtering.py
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

Uses the published GeoKernel 1.5.35 package. No local SDK build or DLL override is required.

Run from CMD:

```cmd
cd /d "D:\projects\GeoKernel.Examples.Python" && .venv\Scripts\python.exe -m pip install -r requirements.txt && .venv\Scripts\python.exe project_save_load.py
```

## GlobeTerrainNavigation (Python)

`globe_terrain_navigation.py` matches the Qt, WinForms and WPF terrain/navigation
examples. Opens above Sagrada Familia, Barcelona, with real Esri satellite
imagery, DEM, atmosphere and sunlight enabled. The four features can be toggled
independently. Navigation includes zoom in/out, rotate left/right, tilt up/down,
top view, north alignment and Overview to restore the starting camera.

Uses the published `geokernel==1.5.35` package and its pinned PySide6 runtime.
Windows x64, a Vulkan-capable graphics driver and a valid license are required.
The SDK installs automatically with pip; imagery and elevation stream on demand
and require internet access. No synthetic data or local SDK checkout is used.

From PowerShell in this repository (reuse `.venv-globe` if already created):

```powershell
py -3 -m venv .venv-globe
.\.venv-globe\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-globe\Scripts\pythonw.exe globe_terrain_navigation.py
```

Left drag pans, right drag or the wheel zooms, and middle drag / Ctrl + left drag
orbits. Includes the shared application icon, fixed 24-pixel status bar and native
resource cleanup on close. No application command-line options or test modes.

## GlobeVectorStyling (Python)

'globe_vector_styling.py' displays real Sagrada Familia building footprints over
Esri imagery, with atmosphere and the same starting camera as Qt, WinForms and
WPF. It downloads the sample automatically on first launch and reuses the shared
data/sagrada_familia_buildings cache.

Controls include Fill, Labels, attribute categories (or Uniform), label field,
opacity, base color, Zoom to buildings and Esri on/off. Click a building to see
its attributes; hover the status bar to read long values. Polygons rejected by
SDK fill validation remain outline-only and are counted in the status bar.

Uses published geokernel==1.5.35 and its pinned PySide6 runtime. Requires Windows
x64, a Vulkan-capable graphics driver and a valid license. Internet is needed for
the first sample download and satellite imagery.

From PowerShell (reuse .venv-globe if already created):

~~~powershell
py -3 -m venv .venv-globe
.\.venv-globe\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-globe\Scripts\pythonw.exe globe_vector_styling.py
~~~

Includes the application icon, fixed 24-pixel status bar and native cleanup on
close. SDK load/style jobs run asynchronously. No application command-line
options or test modes.

## GlobeBuildings (Python)

`globe_buildings.py` downloads and displays real Sagrada Familia building
footprints over Esri imagery, with atmosphere and the same camera as the Qt,
WinForms and WPF examples. The sample is cached in `data/sagrada_familia_buildings`.

Click Extrude to build 3D buildings or return to footprints. Display height defaults
to 18 metres; it is illustrative, not measured. Turn extrusion off before changing
height. The example uses the reference sphere without DEM. Controls remain disabled
until geometry generation and GPU upload finish. Includes Zoom to buildings,
Atmosphere and Esri toggles, the application icon and a fixed 24-pixel status bar.

Uses published `geokernel==1.5.35` and its pinned PySide6 runtime. Requires Windows
x64, a Vulkan-capable graphics driver and a valid license. Internet is required for
the first sample download and satellite imagery. Reuse `.venv-globe` if it exists:

```powershell
py -3 -m venv .venv-globe
.\.venv-globe\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-globe\Scripts\pythonw.exe globe_buildings.py
```

No application command-line options or test modes. Closing the window releases
the native globe, including when an extrusion job is still running.

## GlobeModelPlacement (Python)

`globe_model_placement.py` automatically downloads the real Sagrada Familia model,
verifies its archive SHA-256 checksum and caches the complete glTF, buffers and
textures in `data/sagrada_familia_3d_model`. The published `geokernel==1.5.35`
package and its pinned PySide6 runtime are installed with pip.

```powershell
py -3 -m venv .venv-globe
.\.venv-globe\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-globe\Scripts\pythonw.exe globe_model_placement.py
```

Reuse `.venv-globe` if it already exists. Requires Windows x64, Python 3.11 or newer,
a Vulkan-capable graphics driver, a valid license and internet for initial downloads
and satellite imagery.

Starts with Esri imagery, atmosphere and the Qt example's approximate placement:
longitude 2.1744, latitude 41.4036, ellipsoidal anchor height 14.089 m, without DEM.
Model credit: PeeJaa. Controls include Zoom to model, Rotate 30 degrees, Scale
(0.01–10), Anchor height (-100–10000 m), Apply, Remove, Restore, Atmosphere and Esri.
Change scale/height and click Apply. Restore reloads the cached model using its
last accepted placement. Controls remain disabled during asynchronous geometry
work and GPU upload. Includes the application icon, fixed 24-pixel status bar,
native cleanup on close, and no application command-line options or test modes.

Known SDK 1.5.35 limitation: heading 30 degrees with scale 1.5 is rejected with
`Model is too small for scene precision.` Scale 2 succeeds. The example displays
the error and restores accepted input values while retaining the previous model.
This native precision limitation requires a separate SDK fix/release.

## GlobeRasterServices (Python)

`globe_raster_services.py` opens real Sagrada Familia orthophoto and DEM with Esri
imagery and atmosphere. Both local layers are enabled automatically, with elevation
exaggeration 1x. DEM color shading is disabled so it does not cover the orthophoto.
There is no service-selection toolbar or synthetic data.

```powershell
py -3 -m venv .venv-globe
.\.venv-globe\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-globe\Scripts\pythonw.exe globe_raster_services.py
```

Reuse `.venv-globe` if it exists. Uses published `geokernel==1.5.35` and its pinned
PySide6 runtime. Requires Windows x64, Python 3.11+, a Vulkan-capable graphics
driver and a valid license. Internet is needed for initial downloads and imagery.

First launch downloads the real raster archives, verifies SHA-256 checksums and
extracts them into `data/sagrada_familia_ortophoto` and `data/sagrada_familia_terrain`.
Completion markers are written only after successful extraction. Subsequent launches
reuse the local cache. Native loading uses asynchronous jobs. Includes the shared
application icon, fixed 24-pixel status bar, error reporting, native cleanup on close
and no application command-line arguments or test modes.

## GlobeTerrainAnalysis (Python)

`globe_terrain_analysis.py` opens Barcelona with real DEM, Esri imagery and atmosphere.
The terrain archive downloads automatically, is SHA-256 verified and cached in
`data/sagrada_familia_terrain`. DEM color shading is disabled; elevation remains 1x.

```powershell
py -3 -m venv .venv-globe
.\.venv-globe\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-globe\Scripts\pythonw.exe globe_terrain_analysis.py
```

Reuse `.venv-globe` if present. Uses published `geokernel==1.5.35`. Requires Windows
x64, Python 3.11+, a Vulkan-capable GPU, valid license and internet for downloads/imagery.

Select a tool and click the terrain: Line of sight takes observer/target points
within 10 km (both 1.7 m above ground); Viewshed takes one observer (350 m radius,
15 m spacing); Slope / aspect takes one point; Measure takes start/end points.
The LOS map line marks the ground path, not the elevated sight ray. Analysis is
terrain-only: buildings are excluded. Missing samples are reported, not assumed
visible. If terrain residency changes, wait for loading to settle and select again.

Further clicks start a new selection. Clear/Esc cancels; Barcelona restores the
camera. The scrollable results panel stays 170 pixels high and the status bar stays
24 pixels high. Includes the application icon and cleanup during pending analysis.
No application CLI arguments, synthetic data or test modes are included.
