"""Scene state: robots, tags, game timer — all in millimetres.

The world is mm-native: every coordinate, dimension, speed, and tolerance is
mm or mm/s. Pixels exist only at the render boundary. The render module
multiplies by a scale to produce a display image, but the API and state
never see pixels.

Single source of truth for the simulator. Mutations go through the methods
here; the render loop reads state under the same asyncio lock so frames
never observe a half-applied update.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Optional


# ----- field -----
FIELD_W_MM = 1300
FIELD_H_MM = 800

# ----- tag stack (from docs/tag-hardware.md) -----
Z_BATTERY_TOP_MM = 23.93        # top of Atomic Battery Base
Z_ATOMS3R_TOP_MM = 12.9         # AtomS3R height (display on top face)
Z_MARKER_MM = Z_BATTERY_TOP_MM + Z_ATOMS3R_TOP_MM   # 36.83 mm — marker face Z
Z_TOOL_MM = 50.0                # vacuum length below the robot flange
Z_SAFE_MM = 1.5 * Z_MARKER_MM   # 55.245 mm — safe traverse height

# ----- robot -----
ROBOT_REACH_MM = 400.0           # MG400 horizontal reach radius
ROBOT_BASE_SIDE_MM = 200.0       # 200x200 mm footprint
ROBOT_SPEED_MM_S = 300.0         # planar / 3D speed
ROBOT_MAX_Z_MM = 150.0           # ceiling above field
ROBOT_MIN_Z_MM = 0.0             # can't go below field surface

# ----- pick -----
PICK_XY_TOL_MM = 10.0            # X/Y tolerance for /pick
PICK_Z_TOL_MM = 3.0              # Z tolerance for /pick (TCP must be near marker)

# ----- game -----
ROUND_SECONDS = 90.0

# Robot bases placed so each reach circle just touches the other robot's body
# (base separation = reach + body_radius = 400 + 100 = 500 mm).
ROBOT_HOMES_MM = {
    1: (250.0, 400.0),       # left
    2: (750.0, 400.0),       # right
}
ROBOT_COLORS = {
    1: (255, 140, 0),        # BGR: blue
    2: (0, 140, 255),        # BGR: orange
}


@dataclass
class Robot:
    id: int
    base_x: float
    base_y: float
    reach_r: float
    x: float                 # TCP world x in mm
    y: float                 # TCP world y in mm
    z: float                 # TCP world z in mm (height above field)
    target_x: float
    target_y: float
    target_z: float
    holding: Optional[int] = None
    color: tuple = (255, 255, 255)


@dataclass
class Tag:
    id: int
    aruco_id: int
    x: float
    y: float
    z: float = Z_MARKER_MM   # marker face Z
    value: int = 1
    carried_by: Optional[int] = None


@dataclass
class Game:
    running: bool = False
    time_left: float = ROUND_SECONDS
    duration: float = ROUND_SECONDS


class Scene:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.robots: dict[int, Robot] = {}
        self.tags: dict[int, Tag] = {}
        self.game = Game()
        self._next_tag_id = 1
        self._next_aruco_id = 0
        self._reset_robots()

    # ----- mutations -----

    def _reset_robots(self) -> None:
        """Robots idle at home X/Y, Z = Z_safe (traverse altitude)."""
        self.robots.clear()
        for rid, (bx, by) in ROBOT_HOMES_MM.items():
            self.robots[rid] = Robot(
                id=rid,
                base_x=bx, base_y=by,
                reach_r=ROBOT_REACH_MM,
                x=bx, y=by, z=Z_SAFE_MM,
                target_x=bx, target_y=by, target_z=Z_SAFE_MM,
                color=ROBOT_COLORS[rid],
            )

    def reset(self) -> None:
        self._reset_robots()
        self.tags.clear()
        self._next_tag_id = 1
        self._next_aruco_id = 0
        self.game = Game()

    def start_game(self) -> None:
        if not self.game.running:
            self.game.running = True
            self.game.time_left = self.game.duration

    def add_tag(
        self,
        x: float,
        y: float,
        value: int = 1,
        aruco_id: Optional[int] = None,
    ) -> int:
        if aruco_id is None:
            aruco_id = self._next_aruco_id
            self._next_aruco_id = (self._next_aruco_id + 1) % 50  # DICT_4X4_50
        tag_id = self._next_tag_id
        self._next_tag_id += 1
        self.tags[tag_id] = Tag(
            id=tag_id, aruco_id=aruco_id,
            x=float(x), y=float(y), value=int(value),
        )
        return tag_id

    def move_robot(self, robot_id: int, x: float, y: float, z: float) -> tuple[float, float, float]:
        """Set the robot's 3D target. X/Y outside the reach disk are clamped
        to the reach boundary; Z is clamped to [ROBOT_MIN_Z, ROBOT_MAX_Z]."""
        r = self.robots[robot_id]
        # Clamp X/Y to reach disk
        dx = x - r.base_x
        dy = y - r.base_y
        d = math.hypot(dx, dy)
        if d > r.reach_r and d > 0:
            scale = r.reach_r / d
            x = r.base_x + dx * scale
            y = r.base_y + dy * scale
        # Clamp Z
        z = max(ROBOT_MIN_Z_MM, min(ROBOT_MAX_Z_MM, z))
        r.target_x = float(x)
        r.target_y = float(y)
        r.target_z = float(z)
        return (r.target_x, r.target_y, r.target_z)

    def pick(self, robot_id: int) -> Optional[int]:
        """Attach the nearest free tag if TCP is within XY and Z tolerance of
        its marker. Returns the tag id now held, or None if not in range."""
        r = self.robots[robot_id]
        if r.holding is not None:
            return r.holding
        best_id: Optional[int] = None
        best_d = PICK_XY_TOL_MM
        for tid, t in self.tags.items():
            if t.carried_by is not None:
                continue
            if abs(r.z - t.z) > PICK_Z_TOL_MM:
                continue
            d = math.hypot(t.x - r.x, t.y - r.y)
            if d < best_d:
                best_d = d
                best_id = tid
        if best_id is not None:
            self.tags[best_id].carried_by = robot_id
            r.holding = best_id
        return best_id

    def drop(self, robot_id: int) -> Optional[int]:
        r = self.robots[robot_id]
        if r.holding is None:
            return None
        tid = r.holding
        t = self.tags[tid]
        t.carried_by = None
        # Tag drops to the field surface at the TCP's X/Y (Z resets to marker face)
        t.x = r.x
        t.y = r.y
        t.z = Z_MARKER_MM
        r.holding = None
        return tid

    # ----- per-frame step -----

    def step(self, dt: float) -> None:
        # 3D straight-line motion at constant speed toward target
        for r in self.robots.values():
            dx = r.target_x - r.x
            dy = r.target_y - r.y
            dz = r.target_z - r.z
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d > 1e-3:
                step = min(d, ROBOT_SPEED_MM_S * dt)
                r.x += dx / d * step
                r.y += dy / d * step
                r.z += dz / d * step
        # Carried tags follow holder TCP exactly
        for t in self.tags.values():
            if t.carried_by is not None:
                r = self.robots[t.carried_by]
                t.x = r.x
                t.y = r.y
                t.z = r.z
        # Game timer
        if self.game.running:
            self.game.time_left -= dt
            if self.game.time_left <= 0:
                self.game.time_left = 0
                self.game.running = False

    def state(self) -> dict:
        return {
            "units": "mm",
            "field": {"w": FIELD_W_MM, "h": FIELD_H_MM},
            "z": {
                "marker": round(Z_MARKER_MM, 2),
                "tool": Z_TOOL_MM,
                "safe": round(Z_SAFE_MM, 2),
                "min": ROBOT_MIN_Z_MM,
                "max": ROBOT_MAX_Z_MM,
            },
            "pick": {"xy_tol": PICK_XY_TOL_MM, "z_tol": PICK_Z_TOL_MM},
            "game": {
                "running": self.game.running,
                "time_left": round(self.game.time_left, 2),
                "duration": self.game.duration,
            },
            "robots": [
                {
                    "id": r.id,
                    "x": round(r.x, 2), "y": round(r.y, 2), "z": round(r.z, 2),
                    "target_x": round(r.target_x, 2),
                    "target_y": round(r.target_y, 2),
                    "target_z": round(r.target_z, 2),
                    "base": {"x": r.base_x, "y": r.base_y, "side": ROBOT_BASE_SIDE_MM},
                    "reach": r.reach_r,
                    "tool_z": Z_TOOL_MM,
                    "holding": r.holding,
                }
                for r in self.robots.values()
            ],
            "tags": [
                {
                    "id": t.id, "aruco_id": t.aruco_id,
                    "x": round(t.x, 2), "y": round(t.y, 2), "z": round(t.z, 2),
                    "value": t.value, "carried_by": t.carried_by,
                }
                for t in self.tags.values()
            ],
        }
