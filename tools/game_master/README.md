# tools/game_master

One-click match-control tools for the HHBot game master Nilsson. Each is a self-contained Python script that calls the simulator's HTTP API; they share `_http.py` for URL resolution and request handling.

## The tools

| Script | Effect |
|---|---|
| `start_game.py` | `GET /game/start` — fresh start from idle/ended, resume from paused |
| `pause_game.py` | `GET /game/pause` — freeze timer; no-op unless running |
| `end_game.py` | `GET /game/end` — stop timer, keep field + scores for archival |
| `set_tag.py x y [--value V]` | `GET /tag/add?x=&y=&value=` — add one tag at world `(x, y)` mm |
| `set_game.py` | `/game/reset` + adds 6 regular + 1 featured 10-pt tag in a balanced layout |

All scripts auto-resolve the simulator URL from `.nilsson/run_local.json` (whatever Nilsson's `run_local` workflow recorded). Override with `--url`.

## Run standalone

From the HHBot repo root:

```bash
python tools/game_master/set_game.py        # reset + place starting layout
python tools/game_master/start_game.py      # begin the 90 s countdown
python tools/game_master/set_tag.py 350 250 --value 5
python tools/game_master/pause_game.py      # freeze
python tools/game_master/start_game.py      # resume
python tools/game_master/end_game.py        # stop, keep score visible
```

## Install into Nilsson

Nilsson's tool scanner only watches `Nilsson/tools/`. Symlink the group in:

```bash
ln -s ../../tools/game_master Nilsson/tools/game_master
```

(Or copy the directory if you'd rather not symlink.) The Nilsson watcher picks them up within ~2 poll cycles. Each tool appears in the Tools tab as a one-click button.

## Layout placed by `set_game.py`

```
        100        200        300        400        500        600
   ┌────────────────────────────────────────────────────────────┐
   │ ┌────┐                                                     │ <- y= 8..88   R1 bin
   │ │ R1 │  ·                                                  │
   │ │BIN │       (250,100,1)              (500,100,1)          │
   │ └────┘                                                     │
   │ ┌────┐         (350,150,1)                                 │
   │ │ R1 │              (450,200,1)                            │
   │ │body│      ◆ (350,197,10) featured                        │
   │ └────┘         (300,280,1)  (400,300,1)                    │
   │                                              ┌────┐        │
   │                                              │ R2 │        │
   │                                              │body│        │
   │                                              └────┘        │
   │                                              ┌────┐        │ <- y=306..386 R2 bin
   │                                              │ R2 │        │
   │                                              │BIN │        │
   │                                              └────┘        │
   └────────────────────────────────────────────────────────────┘
```

All seven points are within both reach circles (≤ 400 mm from each base), and none falls inside either receptacle footprint.
