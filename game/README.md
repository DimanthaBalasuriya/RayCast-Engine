# Ray — dynamic light raycaster

A textured, explorable 2.5D dungeon built with Python, pygame CE and NumPy. Phase 2 adds acceleration-based movement, jump, crouch, camera height, two weapons, hitscan impacts, shootable lights, bullet holes, health and a HUD to the dynamic lighting demo.

## Install and run

Use Python 3.11 or newer. From this `game` directory:

```powershell
python -m pip install -r requirements.txt
python tools/generate_atlas.py --viewer
python tools/generate_weapons.py
python tools/selftest.py
python main.py
```

The generated atlas and weapon assets are already included. The atlas `--viewer` writes a labeled contact sheet. To measure frame rates without a visible window, run `python main.py --benchmark --frames 50`. Add `--size 640x360` to test a larger internal resolution. `python main.py --window-benchmark --frames 60` measures three simulated window sizes. `python main.py --no-confirm-quit` exits immediately on Esc or a close request for development.

For the measured fast path, optionally install Numba with `python -m pip install numba`. The game runs without it.

## Controls

| Input | Action |
| --- | --- |
| W / S | Forward / back |
| A / D | Strafe |
| Mouse X or left / right arrows | Turn |
| Mouse Y | Look up / down when F5 is on |
| Shift | Run |
| Space | Jump |
| Left Ctrl | Crouch (hold by default) |
| Left mouse button | Fire |
| Right mouse button | Hold to zoom |
| R | Reload |
| 1 / 2, mouse wheel | Select pistol / shotgun |
| Q | Switch to previous weapon |
| H / T | Debug damage / refill all ammunition |
| Enter | Respawn after death |
| F | Flashlight |
| E | Drop a light that fades after five seconds |
| F1 | Debug overlay and minimap |
| F2 | Lighting |
| F3 | Fog |
| F4 | Cycle low, medium, high lighting quality |
| F5 | Vertical look |
| F6 / F7 / F8 | Toggle head bob / viewmodel / HUD |
| C | Recenter vertical look |
| Esc or window close button | Open Quit game? confirmation |
| Dialog: Left / Right / Tab / Shift+Tab | Select Resume or Quit |
| Dialog: Enter / Space | Activate selected choice |
| Dialog: N / Esc / Y | Resume / Resume / Quit |
| F11 or Alt+Enter | Toggle fullscreen |

## Configuration

Edit `config.py` for window, render, FOV, movement, lighting, and HUD settings. `WINDOW_DEFAULT_SIZE` is 1280×800, `MIN_WINDOW_SIZE` is 640×400, `START_MAXIMIZED` is on, `START_FULLSCREEN` is off, and `PAUSE_ON_FOCUS_LOSS` is on. `CONFIRM_QUIT` controls the quit dialog. `RENDER_HEIGHT` stays at 200 while internal width follows the window aspect between `MIN_ASPECT = 1.0` and `MAX_ASPECT = 2.4`; outside that range the view is centered with black bars. `REFERENCE_ASPECT = 4/3`, `FOV_DEG = 66`, and `MAX_HFOV_DEG = 130` define Hor+ FOV. `UI_REFERENCE_HEIGHT`, `UI_SCALE_MIN`, and `UI_SCALE_MAX` control HUD scaling. `RESIZE_DEBOUNCE` is reserved for an optional future resize delay; resizing currently coalesces events once per frame without delaying the picture. `RENDER_MODE` uses fixed height; fixed pixel size is not implemented. `RENDER_SIZE` is only a benchmark override.

`CROUCH_TOGGLE = True` changes Ctrl from hold to toggle. `AUTO_JUMP` defaults to off. `LIGHTING_QUALITY` changes samples per tile and dynamic update cadence: low 2×2 every third frame, medium 4×4 every second frame, high 6×6 every frame.

Vertical look shifts the horizon, wall centers and floor/ceiling row distances. It is a screen-space shear, not true camera pitch; walls distort slightly at extreme angles. F5 turns it off and immediately levels the view.

Jump height at the defaults is `3.1² / (2 × 14) ≈ 0.34` tile. All current walls are full height, so jumping changes the camera and movement feel but cannot clear a wall or land on a crate. `Level.ground_height()` and `Level.can_stand()` are hooks for future height geometry.

## Level and assets

`assets/characters/` contains three transparent player pose sheets and ten transparent enemy pose strips generated from the supplied character reference. `assets/characters/manifest.json` lists each file and its intended left-to-right pose order. `assets/characters/animations/` adds a four-frame, five-row animation kit for every character, with row names, suggested FPS, and loop behavior in its own `manifest.json`. Players have idle, walk, run, cover, and fight rows. Enemies have role-specific movement, defense or attack, and death rows. All 260 cells contain artwork. These AI-generated sequences are source assets: small silhouette changes, effects crossing cell edges, and loop seams may need cleanup before production use.

The active player is now the Assault character (`PLAYER_CHARACTER = "assault"`). The HUD animates his idle, walk, run, cover, and fight states while the first-person weapon view remains active. One Alpha Drone appears ahead of the start point. It walks toward the player, attacks at close range, takes weapon damage, dies, and respawns after six seconds for repeated testing. Its billboard is wall-occluded using the renderer's z-buffer. The enemy's red health bar and a red minimap marker help test hits and visibility. The other generated characters remain available as assets for later integration.

`levels/level01.txt` is a 32×32 ASCII grid. `#` uses the legend's default wall; `1` through `8` select wall IDs; `.` and `P` are open; `D` is a solid door texture; spaces are solid void. `level01.json` supplies the player start, tile size, floor and ceiling defaults, rectangular region material overrides, ambient/fog values and light definitions. Region rectangles use `[x0, y0, x1, y1]` with exclusive upper bounds. Point lights accept `pos`, `z`, `color`, `intensity`, `radius`, `flicker`, and optional orbit fields. Named flicker modes are `none`, `torch`, `pulse`, `strobe`, and `broken`.

To replace art, replace `assets/atlas.png` and `assets/atlas.json` together. Keep the tile IDs the level uses, but arrange tiles anywhere in the PNG and update each manifest `col` and `row`. The manifest controls texture size, tile positions, and default floor/ceiling IDs; game code has no atlas coordinate assumptions. Missing IDs draw a magenta/black checker and log one warning per ID. The procedural generator uses a fixed seed and writes deterministic output.

`assets/weapons.json` defines every weapon by name. Each entry has `slot`, `fire_mode` (`semi`, `auto` or `pump`), `rpm`, `damage`, `pellets`, `spread_deg`, `range`, `mag_size`, `start_reserve`, `reload_time`, `switch_time`, recoil and muzzle-light objects, plus `frames` (`idle`, `fire`, `reload`, `switch`, `pump`) with PNG pixel rectangles. Change stats or add another weapon entry with a new slot without changing game code. To replace the placeholder art, replace `assets/weapons.png` and update the rectangles and image name in `weapons.json`. `python tools/generate_weapons.py` regenerates both files deterministically, overwriting replacements.

`level01.json` marks three lights as `shootable: true`: a starting torch and two hall tech lights. Shooting one disables its contribution and emits `light_shot_out`. Weapon firing, impacts, movement, damage and respawn emit synchronous events through `engine/events.py`; no audio is played.

## Rendering and lighting decisions

Wall rays use one vectorized DDA per screen column, perpendicular distances, face-corrected texture U coordinates, and a per-column z-buffer for later sprite support. The floor and ceiling use row-distance projection at every pixel. Texture and light lookups are NumPy array operations; no Python loop visits pixels or columns.

Lighting stores six RGB maps at sub-tile resolution: floor, ceiling, and the four wall normals. Static point lights are baked once. A vectorized tile DDA checks the path from each light to each affected sample, so walls and pillars block direct light. Flickering, moving, flashlight and temporary lights rebuild their affected regions on the selected update cadence. Rendering samples the combined maps bilinearly at visible plane pixels and at each wall hit on the open side of the face. A small bounce term prevents fully black tangent surfaces. The final pass applies ambient light, smooth tone mapping and exponential distance fog.

This lightmap design trades CPU time and three lightmap buffers for directional lighting and occlusion. If Numba is installed, a compiled pixel shader provides the fast path. Numba is optional and is not in `requirements.txt`; without it, the game uses vectorized NumPy shading with identical output and lower FPS. Extremely thin geometry below a tile cannot cast a shadow, and the lower quality modes update moving light less often.

The camera supplies eye height to wall, floor and ceiling casting. A shot uses the same wall grid and face/U convention as rendering. Decals store tile, face and wall coordinates, then project with each frame's wall top and height, so they stay fixed while the camera moves. The gun is tinted from the lightmap and drawn after world lighting at internal resolution; HUD text is drawn after upscale.

## Decisions

- Phase 2 supersedes phase 1's no-weapons scope and makes head bob on by default. The F6 toggle can disable it.
- The shotgun uses a full-magazine reload. The optional rifle and particles are omitted.
- The scalar hitscan and batched light rays both use the level's solid grid and DDA rules. The lighting path retains its vectorized traversal because calling scalar `grid_raycast()` for every lightmap sample would miss the performance target.
- Vertical aim uses the shared vertical projection scale `proj = (render_height / 2) / tan(vfov / 2)` for walls, planes and hitscan. Sheared vertical look is still approximate at extreme angles.
- The window starts maximized with pygame CE 2.5.8's public `pygame.Window.from_display_module().maximize()` API. If unavailable, it starts in a resizable desktop-sized window with an 80-pixel margin. Native maximize and restore are handled by pygame window events.
- Mouse and arrow turning now affect the camera equally. Raw mouse movement no longer shifts the gun sprite independently of the centered crosshair; walking sway remains.
- The window addendum replaces the former Esc mouse-release/quit behavior with a modal confirmation. Its stated projection formula and 66° reference FOV slightly change the old `H / distance` image scale; the shared perspective formula takes precedence for correct proportions across aspect ratios.
- The Assault sheet is used as an animated HUD identity because the game remains first person. The existing weapon viewmodel continues to show the held weapon. The Alpha Drone is the single combat test enemy; it uses the existing damageable and z-buffer hooks without introducing a full enemy system.

## Measured performance

Headless sequential benchmark on this workspace's Python 3.14.7 / pygame CE 2.5.8 / optional Numba 0.68.0 environment, after warmup. Results depend on CPU and display settings:

| Stage | 320×200, 60 frames | 640×360, 40 frames |
| --- | ---: | ---: |
| M3 walls and floor/ceiling pass, lighting off | 127.6 FPS | 35.4 FPS |
| M5 baked static lighting | 107.1 FPS | 30.9 FPS |
| M6 dynamic lights and flashlight | 77.2 FPS | 27.5 FPS |
| M7 vertical look on | 77.3 FPS | 25.7 FPS |

The phase 1 numbers above are retained as a baseline. Phase 2's headless benchmark uses eight level lights, repeated pistol shots, muzzle and impact lights, decals, a viewmodel, and at P7 window upscale and HUD. Measured after warmup on this host:

| Stage | 320×200, look off / on | 640×360, look off / on |
| --- | ---: | ---: |
| P2 camera height | 79.0 / 79.4 FPS | 24.0 / 24.2 FPS |
| P5 hitscan and impacts | 73.6 / 74.6 FPS | 23.9 / 23.5 FPS |
| P7 full view and HUD | 63.9 / 64.1 FPS | 22.5 / 22.7 FPS |

The 320×200 60 FPS target is met with optional Numba on this host. The 640×360 30 FPS target is not met. Without Numba, the vectorized NumPy fallback remains functional but is slower. Live performance also depends on display scaling, synchronization and the debug overlay.

With the adaptive renderer, `--window-benchmark --frames 60` measured 71.2 FPS at 1280×800 (320×200 internal), 58.2 FPS at 1920×1080 (356×200 internal), and 46.6 FPS at 2560×1440 (356×200 internal), using eight level lights on this host. These are simulated window sizes with a software output surface, not live fullscreen measurements. Internal height stays fixed, but wider views require more ray columns and larger windows cost more CPU time to upscale and draw the HUD. The 60 FPS target was met at 1280×800, but not at the two larger tested sizes.

After adding the Assault HUD portrait and one Alpha Drone billboard, a sequential 60-frame window benchmark on this host measured 70.6 FPS at 1280×800, 64.6 FPS at 1920×1080, and 64.0 FPS at 2560×1440. The drone render stage cost about 0.36 ms in an isolated 320×200 frame. These headless figures vary between runs and do not predict live fullscreen FPS exactly.
