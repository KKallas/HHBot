# HHBot Simulator (v2)

A standalone Python service that renders the HHBot game field in real physical units, streams it as H.264 over HLS, and accepts HTTP GET commands to drive two robot heads in 3D and place ArUco tags. v2 is **mm-native** end-to-end: every coordinate, dimension, speed, and tolerance is in millimetres or mm/s.

> Still milestone-grade: no Dobot TCP API, no game master, no scoring, no collision detection. Just enough to drive a physically meaningful fake field and verify coordinate frames against the live video.

## What's new in v2

- **mm everywhere.** Field, reach, speed, tolerances all in mm. Pixels exist only at the render boundary.
- **Field sized to the working envelope.** 1300 × 800 mm — the bounding box of both robots' reach circles, with bases 500 mm apart so each reach just touches the other robot's body.
- **Robots drawn realistically.** Base square (200 × 200 mm) + arm rectangle from base to TCP (varying length) + TCP indicator + a fixed ArUco marker on the TCP itself.
- **TCP ArUco markers (DICT_5X5_50, IDs 0/1).** A live-stream CV pipeline can detect these and compare the visual position to whatever `/state` reports — built-in coordinate-frame ground truth.
- **3D motion.** Robots have Z; `/move` requires `z`. Straight-line 3D interpolation at 300 mm/s. Pick succeeds only when TCP is within `10 mm` X/Y and `3 mm` Z of an unheld tag's marker.
- **Side-strip Z viz.** A 140 px strip below the top-down shows each robot's TCP altitude, with reference lines at `Z = 0`, `Z_marker = 36.83 mm`, and `Z_safe = 55.25 mm`.
- **Grid + dimensions.** 50 mm minor / 100 mm major gridlines, X/Y labels every 200 mm, overall field dimensions printed on the panel.

## Z reference table

| Symbol | Value | Source |
|---|---|---|
| `Z_marker` | **36.83 mm** | Atomic Battery Base 23.93 + AtomS3R 12.9 = top of the tag stack (marker face) |
| `Z_tool` | **50 mm** | Vacuum end-effector length below the robot flange |
| `Z_safe` | **55.25 mm** | `1.5 × Z_marker` — default traverse height; robots idle here |
| `pick_xy_tol` | 10 mm | TCP must be within this X/Y radius of the tag |
| `pick_z_tol` | 3 mm | TCP must be within this Z distance of the tag's marker |

## Requirements

- Python 3.11+
- `ffmpeg` on PATH (macOS: `brew install ffmpeg`)
- `opencv-contrib-python` (for `cv2.aruco`)

## Run

From the HHBot repo root:

```bash
python -m venv simulator/.venv && source simulator/.venv/bin/activate
pip install -r simulator/requirements.txt
python -m simulator.main
```

Open <http://127.0.0.1:7700>. CLI flags: `--host` (default `0.0.0.0`), `--port` (default `7700`). Env fallbacks: `SIMULATOR_HOST`, `SIMULATOR_PORT`.

## HTTP API

| Endpoint | Effect |
|---|---|
| `GET /robot/{1,2}/move?x=&y=&z=` | Move TCP toward `(x, y, z)` in mm. **`z` is required.** X/Y outside the reach disk clamp to the reach boundary; Z clamps to `[0, 150]`. |
| `GET /robot/{1,2}/pick` | Attach the nearest free tag if TCP is within (`pick_xy_tol`, `pick_z_tol`) of its marker. Player code is responsible for descending to `Z_marker` before calling this. |
| `GET /robot/{1,2}/drop` | Release the held tag at the current TCP X/Y; tag Z resets to `Z_marker`. |
| `GET /tag/add?x=&y=&value=1` | Add an ArUco tag at `(x, y)` mm on the field surface. |
| `GET /game/start` | Begin the 90 s countdown. |
| `GET /game/reset` | Clear tags, home the robots at `Z_safe`, reset the timer. |
| `GET /state` | JSON snapshot with `units: "mm"`, Z constants, robots, tags. |
| `GET /stream` | `302 → /hls/playlist.m3u8`. |
| `GET /` | The built-in test page (primitives only). |

### Pickup sequence (player-side)

The simulator only exposes primitives. A pickup is a script the player writes, e.g.:

```python
move(robot=1, x=tag_x, y=tag_y, z=Z_safe)     # fly over
move(robot=1, x=tag_x, y=tag_y, z=Z_marker)   # descend onto marker
pick(robot=1)                                  # vacuum
move(robot=1, x=tag_x, y=tag_y, z=Z_safe)     # ascend
move(robot=1, x=box_x, y=box_y, z=Z_safe)     # carry to receptacle
drop(robot=1)
```

The test page itself only fires the planar primitive (Move at `Z_safe`); you exercise full descent cycles via `curl` or a Python script.

## Defaults

- Field: **1300 × 800 mm**
- Robots: R1 base `(250, 400)` mm · R2 base `(750, 400)` mm · reach 400 mm · base side 200 mm
- Speed: 300 mm/s (3D)
- ArUco: tags use `DICT_4X4_50` (30 mm side); robot TCP markers use `DICT_5X5_50` (30 mm side, IDs 0 and 1)
- Render canvas: **1300 × 940 px** (top-down 1300 × 800 + side strip 1300 × 140) at 1 mm = 1 px
- HLS: 25 fps, 1 s segments, last 5 retained

## Deliberately out of scope

Real Dobot TCP `:29999` API · 3-Nilsson topology · game master · scoring · featured 10-point tag · head-to-head collision / MG400 alarm-reset · receptacles + weight validation · CV detection on the stream (the TCP markers exist for this future pipeline; v2 doesn't consume the stream).
