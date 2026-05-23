# HHBot Simulator (Milestone 1)

A standalone Python service that renders a top-down HHBot field, streams it as H.264 over HLS, and accepts HTTP GET commands to drive two robot heads and place ArUco tags.

This is milestone 1 — deliberately *not* the full architecture in the top-level README. No Dobot TCP API, no game master, no scoring, no collision detection. Just enough to drive a fake field and see something on a video stream.

## Requirements
- Python 3.11+
- `ffmpeg` on PATH (macOS: `brew install ffmpeg`)

## Run
From the HHBot repo root:

```bash
python -m venv simulator/.venv && source simulator/.venv/bin/activate
pip install -r simulator/requirements.txt
python -m simulator.main
```

Open <http://127.0.0.1:7700>. The test page has a video player, a mode toolbar (Move R1 / Move R2 / Add Tag), pick/drop buttons, and Game Start/Reset. Click on the video to fire the current mode's command at those canvas coordinates.

CLI flags: `--host` (default `127.0.0.1`), `--port` (default `7700`). Env fallbacks: `SIMULATOR_HOST`, `SIMULATOR_PORT`. The default port matches Nilsson's "project server" convention so it can be wired up as the project descriptor (see `.nilsson/config.json` at the HHBot repo root).

## HTTP API

| Endpoint | Effect |
|---|---|
| `GET /robot/{1,2}/move?x=&y=` | Move robot head toward `(x, y)`. Targets outside the robot's reach circle are clamped to its boundary. |
| `GET /robot/{1,2}/pick` | Vacuum-grab the nearest free tag within 50 px. Idempotent. |
| `GET /robot/{1,2}/drop` | Release the held tag at the current head position. |
| `GET /tag/add?x=&y=&value=1` | Add an ArUco tag at `(x, y)`. `value` defaults to 1. |
| `GET /game/start` | Begin the 90 s countdown. |
| `GET /game/reset` | Clear tags, home the robots, reset the timer. |
| `GET /state` | JSON snapshot of the whole scene. |
| `GET /stream` | `302 → /hls/playlist.m3u8`. |
| `GET /` | The built-in test page. |

## Defaults
- Field: 1280 × 720
- Robots: R1 home `(320, 360)`, R2 home `(960, 360)`, reach radius 400 (overlap ~50% across the middle)
- Robot speed: 300 px/s · pick radius: 50 px · round: 90 s
- ArUco dictionary: `DICT_4X4_50` · marker size: 60 px on canvas
- HLS: 25 fps, 1 s segments, last 5 retained (~3–5 s glass-to-glass latency)

## Layout

```
simulator/
├── main.py        # FastAPI app, render loop, lifespan
├── scene.py       # State model + mutations
├── render.py      # OpenCV drawing
├── stream.py      # ffmpeg HLS pipeline
├── api.py         # HTTP GET routes
├── static/        # Test page (index.html, app.css, app.js)
└── hls/           # ffmpeg output (gitignored)
```

## Deliberately out of scope
Real Dobot TCP :29999 API · 3-Nilsson topology · game master · scoring · featured 10-point tag · head-to-head collision detection / MG400 alarm-reset sequence · receptacles and weight validation · CV detection consuming the stream.
