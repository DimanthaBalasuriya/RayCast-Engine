# Ray — dynamic light raycaster

A textured, explorable 2.5D dungeon built with Python, pygame CE and NumPy. The demo has colored point lights, occluded torch flicker, a moving light, a soft flashlight cone, fog, and an optional vertically shifted horizon.

## Install and run

Use Python 3.11 or newer. From this `game` directory:

```powershell
python -m pip install -r requirements.txt
python tools/generate_atlas.py --viewer
python main.py
```

The generated `assets/atlas.png` and `assets/atlas.json` are already included. `--viewer` also writes `assets/atlas_viewer.png`, a labeled contact sheet. To measure frame rates without a visible window, run `python main.py --benchmark --frames 50`. Add `--size 640x360` to test a larger internal resolution.

For the measured fast path, optionally install Numba with `python -m pip install numba`. The game runs without it.

## Controls

| Input | Action |
| --- | --- |
| W / S | Forward / back |
| A / D | Strafe |
| Mouse X or left / right arrows | Turn |
| Mouse Y | Look up / down when F5 is on |
| Shift | Run |
| F | Flashlight |
| E | Drop a light that fades after five seconds |
| F1 | Debug overlay and minimap |
| F2 | Lighting |
| F3 | Fog |
| F4 | Cycle low, medium, high lighting quality |
| F5 | Vertical look |
| C | Recenter vertical look |
| Esc | Release captured mouse; press again to quit |
| Click | Recapture mouse |

## Configuration

Edit `config.py` for `RENDER_SIZE`, `WINDOW_SIZE`, FOV, movement speeds, mouse sensitivity, `ENABLE_VERTICAL_LOOK`, `MAX_PITCH`, lightmap quality, falloff curve and flashlight direction lag. The default internal resolution is 320×200 and is scaled to the window with nearest-neighbor pixels. `LIGHTING_QUALITY` changes samples per tile and dynamic update cadence: low 2×2 every third frame, medium 4×4 every second frame, high 6×6 every frame.

Vertical look shifts the horizon, wall centers and floor/ceiling row distances. It is a screen-space shear, not true camera pitch; walls distort slightly at extreme angles. F5 turns it off and immediately levels the view.

## Level and assets

`levels/level01.txt` is a 32×32 ASCII grid. `#` uses the legend's default wall; `1` through `8` select wall IDs; `.` and `P` are open; `D` is a solid door texture; spaces are solid void. `level01.json` supplies the player start, tile size, floor and ceiling defaults, rectangular region material overrides, ambient/fog values and light definitions. Region rectangles use `[x0, y0, x1, y1]` with exclusive upper bounds. Point lights accept `pos`, `z`, `color`, `intensity`, `radius`, `flicker`, and optional orbit fields. Named flicker modes are `none`, `torch`, `pulse`, `strobe`, and `broken`.

To replace art, replace `assets/atlas.png` and `assets/atlas.json` together. Keep the tile IDs the level uses, but arrange tiles anywhere in the PNG and update each manifest `col` and `row`. The manifest controls texture size, tile positions, and default floor/ceiling IDs; game code has no atlas coordinate assumptions. Missing IDs draw a magenta/black checker and log one warning per ID. The procedural generator uses a fixed seed and writes deterministic output.

## Rendering and lighting decisions

Wall rays use one vectorized DDA per screen column, perpendicular distances, face-corrected texture U coordinates, and a per-column z-buffer for later sprite support. The floor and ceiling use row-distance projection at every pixel. Texture and light lookups are NumPy array operations; no Python loop visits pixels or columns.

Lighting stores six RGB maps at sub-tile resolution: floor, ceiling, and the four wall normals. Static point lights are baked once. A vectorized tile DDA checks the path from each light to each affected sample, so walls and pillars block direct light. Flickering, moving, flashlight and temporary lights rebuild their affected regions on the selected update cadence. Rendering samples the combined maps bilinearly at visible plane pixels and at each wall hit on the open side of the face. A small bounce term prevents fully black tangent surfaces. The final pass applies ambient light, smooth tone mapping and exponential distance fog.

This lightmap design trades CPU time and three lightmap buffers for directional lighting and occlusion. If Numba is installed, a compiled pixel shader provides the fast path. Numba is optional and is not in `requirements.txt`; without it, the game uses vectorized NumPy shading with identical output and lower FPS. Extremely thin geometry below a tile cannot cast a shadow, and the lower quality modes update moving light less often.

## Measured performance

Headless sequential benchmark on this workspace's Python 3.14.7 / pygame CE 2.5.8 / optional Numba 0.68.0 environment, after warmup. Results depend on CPU and display settings:

| Stage | 320×200, 60 frames | 640×360, 40 frames |
| --- | ---: | ---: |
| M3 walls and floor/ceiling pass, lighting off | 127.6 FPS | 35.4 FPS |
| M5 baked static lighting | 107.1 FPS | 30.9 FPS |
| M6 dynamic lights and flashlight | 77.2 FPS | 27.5 FPS |
| M7 vertical look on | 77.3 FPS | 25.7 FPS |

The 320×200 target is met here. The 640×360 dynamic-light case remains below the requested 30 FPS target on this host. These headless numbers do not include window scaling, overlay or display synchronization; use the live F1 overlay for your machine. Vertical look uses only a horizon offset and should have similar cost to level view; the difference in this short sample reflects run-to-run variation.
