# HHBot Simulator (v2)

A standalone Python service that renders the HHBot game field in real physical units, streams it as H.264 over HLS, and accepts HTTP GET commands to drive two robot heads in 3D and place ArUco tags. v2 is **mm-native** end-to-end: every coordinate, dimension, speed, and tolerance is in millimetres or mm/s.

> Still milestone-grade: no Dobot TCP API, no game master, no scoring, no collision detection. Just enough to drive a physically meaningful fake field and verify coordinate frames against the live video.

## What's new in v2

- **mm everywhere.** Field, reach, speed, tolerances all in mm. Pixels exist only at the render boundary.
- **Field framed 16:9 with bodies at the edges.** 700 × 394 mm. Bases 500 mm apart; with the 200 mm body, R1's left face and R2's right face sit flush with the frame edges. The reach circles extend beyond the frame and are clipped at the camera boundary — same as a real overhead camera with limited FOV.
- **Robots drawn realistically.** Base square (200 × 200 mm) + arm rectangle from base to TCP (varying length) + TCP indicator + a fixed ArUco marker on the TCP itself.
- **TCP ArUco markers (DICT_5X5_50, IDs 0/1).** A live-stream CV pipeline can detect these and compare the visual position to whatever `/state` reports — built-in coordinate-frame ground truth.
- **3D motion.** Robots have Z; `/move` requires `z`. Straight-line 3D interpolation at 300 mm/s. Pick succeeds only when TCP is within `10 mm` X/Y and `3 mm` Z of an unheld tag's marker.
- **Side-strip Z viz.** A 140 px strip below the top-down shows each robot's TCP altitude, with reference lines at `Z = 0`, `Z_marker = 36.83 mm`, and `Z_safe = 55.25 mm`.
- **Grid + dimensions.** 50 mm minor / 100 mm major gridlines, X/Y labels every 200 mm, overall field dimensions printed on the panel.
- **Receptacles + scoring.** Each robot owns a 100 × 80 mm bin on its *left when facing the opponent*, placed in the opponent's unreachable zone. R1's bin sits top-left at `(50, 8)`; R2's bin sits bottom-right at `(550, 306)`. Calling `/drop` while TCP is inside your own bin *scores* the tag — it leaves the field and the bin's running `count` / `value` increment. Drops outside the bin still land on the field as before.

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
| `GET /robot/{1,2}/pick` | **Full sequence by default**: locks the planar target, descends to `Z_marker`, attaches the nearest in-range tag, ascends back to `Z_safe`. Non-blocking — returns immediately with `phase: "descending"`; poll `/state` and watch `robots[i].pick_phase` go `descending → ascending → null`. Pass `?descend=false` to attach in place (v1 behaviour: TCP must already be at `Z_marker`). Any `/move` cancels an active sequence. |
| `GET /robot/{1,2}/drop` | Release the held tag. If TCP is inside your own receptacle, the tag is **scored** (response `action: "scored"` + new `count` / `value`) and removed from the field. Otherwise it falls to the field at TCP X/Y with Z = `Z_marker`. |
| `GET /tag/add?x=&y=&value=1` | Add an ArUco tag at `(x, y)` mm on the field surface. |
| `GET /game/start` | Begin the 90 s countdown. |
| `GET /game/reset` | Clear tags, home the robots at `Z_safe`, reset the timer. |
| `GET /state` | JSON snapshot with `units: "mm"`, Z constants, robots, tags. |
| `GET /stream` | `302 → /hls/playlist.m3u8`. |
| `GET /` | The built-in test page (primitives only). |

### Pickup sequence

`/pick` is auto-sequenced — one HTTP call performs descend → attach → ascend. A complete pickup looks like:

```python
move(robot=1, x=tag_x, y=tag_y, z=Z_safe)     # fly over the tag
pick(robot=1)                                  # descend, vacuum, ascend (~0.4 s)
# poll /state until robots[0].pick_phase is null and holding != null
move(robot=1, x=box_x, y=box_y, z=Z_safe)     # carry to receptacle
drop(robot=1)                                  # release at current Z
```

In the test page, that's: Move-R1 click on tag → R1 Pick button → wait briefly → Move-R1 click on receptacle → R1 Drop.

If you'd rather drive the descent manually (e.g. for stepwise debugging), call `/pick?descend=false` — that's the v1 attach-only behaviour, and your script is responsible for getting TCP to `Z_marker` first.

## Defaults

- Field: **700 × 394 mm** (16:9; bodies pinned to frame edges)
- Robots: R1 base `(100, 197)` mm · R2 base `(600, 197)` mm · reach 400 mm · base side 200 mm
- Speed: 300 mm/s (3D)
- ArUco: tags use `DICT_4X4_50` (16 mm side, matches the AtomS3R display); robot TCP markers use `DICT_5X5_50` (30 mm side, IDs 0 and 1), rotated with the arm direction
- Render canvas: **700 × 394 px** at 1 mm = 1 px
- HLS: 25 fps, 1 s segments, last 5 retained

### Scoring sequence

```python
move(robot=1, x=tag_x, y=tag_y, z=Z_safe)     # fly over the tag
pick(robot=1)                                  # descend, vacuum, ascend
move(robot=1, x=100, y=48,    z=Z_safe)       # carry to R1's bin centre
drop(robot=1)                                  # action: "scored" — count++
```

`/state` exposes each receptacle's running totals at `receptacles[i].count` and `receptacles[i].value`. The bin labels in the render also update live (`R1 BIN 3t / 12pt`).

## Deliberately out of scope

Real Dobot TCP `:29999` API · 3-Nilsson topology · game master · scoring · featured 10-point tag · head-to-head collision / MG400 alarm-reset · receptacles + weight validation · CV detection on the stream (the TCP markers exist for this future pipeline; v2 doesn't consume the stream).
