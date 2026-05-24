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
# 16:9 framing with the robot bodies pinned to the left and right edges:
# bases 500 mm apart, body side 200 mm → body-outer to body-outer = 700 mm.
# Height = 700 * 9/16 = 393.75, rounded to 394 mm.
FIELD_W_MM = 700
FIELD_H_MM = 394

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
# (base separation = reach + body_radius = 400 + 100 = 500 mm) AND so each
# body's outer face is flush with the frame edge.
ROBOT_HOMES_MM = {
    1: (100.0, 197.0),       # left — body spans x = 0..200, frame-left flush
    2: (600.0, 197.0),       # right — body spans x = 500..700, frame-right flush
}

# Start posture: arms partly extended toward the opponent so the field looks
# alive on a fresh boot and the marker rotation is immediately visible.
HOME_EXTEND_FRAC = 0.30      # TCP starts 30% of reach toward the opposing robot
ROBOT_FACING_X = {           # +1 if this robot faces right, -1 if left
    1: +1,
    2: -1,
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
    # Auto-pick sequence state. /pick locks X/Y, descends to Z_marker, tries to
    # attach a tag, then ascends back to Z_safe. /move cancels the sequence.
    pick_phase: Optional[str] = None     # None | "descending" | "ascending"
    pick_lock_x: float = 0.0
    pick_lock_y: float = 0.0


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


# ----- receptacle -----
# Half the robot base side, placed on the robot's *left when facing opponent*,
# inside the area the other robot's reach can't touch (so the opponent can't
# steal/sabotage). Bottom-left origin + width/height in mm. See issue #5.
RECEPTACLE_W_MM = 100.0
RECEPTACLE_H_MM = 80.0

RECEPTACLE_POS_MM = {
    # R1 faces +X; its left = -Y (above the body) — top-left quadrant
    1: (50.0, 8.0),
    # R2 faces -X; its left = +Y (below the body) — bottom-right quadrant
    2: (550.0, 306.0),
}


@dataclass
class Receptacle:
    """Per-robot scoring zone. count = number of tags delivered;
    value = sum of their point values; collected = (tag_id, value) audit log."""
    robot_id: int
    x: float                 # top-left X in mm
    y: float                 # top-left Y in mm
    w: float
    h: float
    count: int = 0
    value: int = 0
    collected: list = None   # initialised in __post_init__

    def __post_init__(self):
        if self.collected is None:
            self.collected = []

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


class Scene:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.robots: dict[int, Robot] = {}
        self.tags: dict[int, Tag] = {}
        self.receptacles: dict[int, Receptacle] = {}
        self.game = Game()
        self._next_tag_id = 1
        self._next_aruco_id = 0
        self._reset_robots()
        self._reset_receptacles()

    # ----- mutations -----

    def _reset_robots(self) -> None:
        """Robots face each other with TCP extended HOME_EXTEND_FRAC of reach
        toward the opponent; Z starts at Z_safe."""
        self.robots.clear()
        for rid, (bx, by) in ROBOT_HOMES_MM.items():
            extend = ROBOT_FACING_X[rid] * HOME_EXTEND_FRAC * ROBOT_REACH_MM
            tcp_x = bx + extend
            self.robots[rid] = Robot(
                id=rid,
                base_x=bx, base_y=by,
                reach_r=ROBOT_REACH_MM,
                x=tcp_x, y=by, z=Z_SAFE_MM,
                target_x=tcp_x, target_y=by, target_z=Z_SAFE_MM,
                color=ROBOT_COLORS[rid],
            )

    def _reset_receptacles(self) -> None:
        self.receptacles.clear()
        for rid, (x, y) in RECEPTACLE_POS_MM.items():
            self.receptacles[rid] = Receptacle(
                robot_id=rid, x=x, y=y, w=RECEPTACLE_W_MM, h=RECEPTACLE_H_MM,
            )

    def reset(self) -> None:
        self._reset_robots()
        self._reset_receptacles()
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
        to the reach boundary; Z is clamped to [ROBOT_MIN_Z, ROBOT_MAX_Z].
        Cancels any in-progress /pick sequence."""
        r = self.robots[robot_id]
        r.pick_phase = None
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

    def _try_attach(self, r: Robot) -> Optional[int]:
        """Attach the nearest free tag if TCP is within XY+Z tolerance. No
        motion; just the attach check. Returns tag id now held, or None."""
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
            self.tags[best_id].carried_by = r.id
            r.holding = best_id
        return best_id

    def pick(self, robot_id: int, descend: bool = True) -> dict:
        """Start a pickup. With descend=True (default): lock X/Y, drop to
        Z_marker, attach, ascend back to Z_safe — the full sequence runs in
        step(). With descend=False: attach in place at current Z (the v1
        behaviour, useful when the player is already scripting the descent).

        Returns a status dict; clients poll /state for the sequence to finish.
        """
        r = self.robots[robot_id]
        if r.holding is not None:
            return {"action": "already_holding", "holding": r.holding,
                    "phase": r.pick_phase}
        if r.pick_phase is not None:
            return {"action": "already_picking", "holding": None,
                    "phase": r.pick_phase}
        if not descend:
            attached = self._try_attach(r)
            return {"action": "attached" if attached else "no_tag_in_range",
                    "holding": attached, "phase": None}
        # Lock the planar target so /move from elsewhere doesn't drift the
        # robot during descent; sequence transitions in step().
        r.pick_lock_x = r.x
        r.pick_lock_y = r.y
        r.target_x = r.x
        r.target_y = r.y
        r.target_z = Z_MARKER_MM
        r.pick_phase = "descending"
        return {"action": "started", "holding": None, "phase": "descending"}

    def drop(self, robot_id: int) -> dict:
        """Release the held tag. If TCP X/Y is inside this robot's receptacle,
        the tag is *scored* — removed from the field, added to the receptacle's
        running count + value. Otherwise it falls to the field at TCP X/Y with
        Z reset to Z_marker.
        Returns a status dict with the tag id and the action taken."""
        r = self.robots[robot_id]
        if r.holding is None:
            return {"action": "no_tag", "tag_id": None}
        tid = r.holding
        t = self.tags[tid]
        rec = self.receptacles.get(robot_id)

        if rec is not None and rec.contains(r.x, r.y):
            value = t.value
            rec.collected.append({"tag_id": tid, "value": value})
            rec.count += 1
            rec.value += value
            del self.tags[tid]
            r.holding = None
            return {
                "action": "scored", "tag_id": tid, "value": value,
                "receptacle": {"count": rec.count, "value": rec.value},
            }

        t.carried_by = None
        t.x = r.x
        t.y = r.y
        t.z = Z_MARKER_MM
        r.holding = None
        return {"action": "dropped", "tag_id": tid}

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

            # Pick sequence state machine — descending → attach → ascending → done
            if r.pick_phase == "descending":
                if (abs(r.z - Z_MARKER_MM) < 0.5
                        and abs(r.x - r.pick_lock_x) < 0.5
                        and abs(r.y - r.pick_lock_y) < 0.5):
                    self._try_attach(r)
                    # Always ascend, even if no tag was in range — predictable
                    # posture: TCP ends at Z_safe whether or not pickup succeeded.
                    r.target_z = Z_SAFE_MM
                    r.pick_phase = "ascending"
            elif r.pick_phase == "ascending":
                if abs(r.z - Z_SAFE_MM) < 0.5:
                    r.pick_phase = None

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
                    "pick_phase": r.pick_phase,
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
            "receptacles": [
                {
                    "robot_id": r.robot_id,
                    "x": r.x, "y": r.y, "w": r.w, "h": r.h,
                    "count": r.count, "value": r.value,
                }
                for r in self.receptacles.values()
            ],
        }
