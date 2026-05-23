"""Scene state: robots, tags, game timer.

Single source of truth for the simulator's world. Mutations go through
the methods here; the render loop reads state under the same asyncio
lock so frames never observe a half-applied update.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Optional


FIELD_W = 1280
FIELD_H = 720

ROBOT_SPEED = 300.0        # px / s
PICK_RADIUS = 50.0         # px
ROUND_SECONDS = 90.0
REACH_RADIUS = 400.0

# Robot homes placed so the two reach circles overlap ~50% across the middle
# (centers 640 px apart, radii 400 → overlap zone roughly 160 px wide each side
# of midline, i.e. half of each robot's reach is shared).
ROBOT_HOMES = {
    1: (320.0, 360.0),     # left
    2: (960.0, 360.0),     # right
}
ROBOT_COLORS = {
    1: (255, 140, 0),      # BGR: blue
    2: (0, 140, 255),      # BGR: orange
}


@dataclass
class Robot:
    id: int
    home_x: float
    home_y: float
    reach_x: float
    reach_y: float
    reach_r: float
    x: float
    y: float
    target_x: float
    target_y: float
    holding: Optional[int] = None     # tag id, or None
    color: tuple = (255, 255, 255)


@dataclass
class Tag:
    id: int
    aruco_id: int
    x: float
    y: float
    value: int = 1
    carried_by: Optional[int] = None  # robot id, or None


@dataclass
class Game:
    running: bool = False
    time_left: float = ROUND_SECONDS
    duration: float = ROUND_SECONDS


class Scene:
    """In-memory world state. All mutations go through the methods below."""

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
        self.robots.clear()
        for rid, (hx, hy) in ROBOT_HOMES.items():
            self.robots[rid] = Robot(
                id=rid,
                home_x=hx, home_y=hy,
                reach_x=hx, reach_y=hy,
                reach_r=REACH_RADIUS,
                x=hx, y=hy,
                target_x=hx, target_y=hy,
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

    def move_robot(self, robot_id: int, x: float, y: float) -> tuple[float, float]:
        """Set the robot's target. Targets outside its reach circle are
        clamped to the nearest point on the reach boundary."""
        r = self.robots[robot_id]
        dx = x - r.reach_x
        dy = y - r.reach_y
        d = math.hypot(dx, dy)
        if d > r.reach_r and d > 0:
            scale = r.reach_r / d
            x = r.reach_x + dx * scale
            y = r.reach_y + dy * scale
        r.target_x = float(x)
        r.target_y = float(y)
        return (r.target_x, r.target_y)

    def pick(self, robot_id: int) -> Optional[int]:
        """Attach the nearest free tag within PICK_RADIUS. Returns the tag id
        now held by this robot, or None if nothing was in range."""
        r = self.robots[robot_id]
        if r.holding is not None:
            return r.holding
        best_id: Optional[int] = None
        best_d = PICK_RADIUS
        for tid, t in self.tags.items():
            if t.carried_by is not None:
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
        self.tags[tid].carried_by = None
        self.tags[tid].x = r.x
        self.tags[tid].y = r.y
        r.holding = None
        return tid

    # ----- per-frame step -----

    def step(self, dt: float) -> None:
        # Move each robot toward its target at constant speed
        for r in self.robots.values():
            dx = r.target_x - r.x
            dy = r.target_y - r.y
            d = math.hypot(dx, dy)
            if d > 1e-3:
                step = min(d, ROBOT_SPEED * dt)
                r.x += dx / d * step
                r.y += dy / d * step
        # Carried tags follow their holder
        for t in self.tags.values():
            if t.carried_by is not None:
                r = self.robots[t.carried_by]
                t.x = r.x
                t.y = r.y
        # Game timer
        if self.game.running:
            self.game.time_left -= dt
            if self.game.time_left <= 0:
                self.game.time_left = 0
                self.game.running = False

    def state(self) -> dict:
        return {
            "field": {"w": FIELD_W, "h": FIELD_H},
            "game": {
                "running": self.game.running,
                "time_left": round(self.game.time_left, 2),
                "duration": self.game.duration,
            },
            "robots": [
                {
                    "id": r.id,
                    "x": round(r.x, 1), "y": round(r.y, 1),
                    "target_x": round(r.target_x, 1),
                    "target_y": round(r.target_y, 1),
                    "reach": {"x": r.reach_x, "y": r.reach_y, "r": r.reach_r},
                    "holding": r.holding,
                }
                for r in self.robots.values()
            ],
            "tags": [
                {
                    "id": t.id, "aruco_id": t.aruco_id,
                    "x": round(t.x, 1), "y": round(t.y, 1),
                    "value": t.value, "carried_by": t.carried_by,
                }
                for t in self.tags.values()
            ],
        }
