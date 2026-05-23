"""HTTP GET routes — simulator v2 control surface.

All coordinates are in millimetres. /move requires z (no v1 back-compat).
/pick succeeds only when TCP is within (pick_xy_tol, pick_z_tol) of an
unheld tag's marker — the player code is responsible for descending to
Z_marker before calling /pick.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from .scene import Scene


def build_router(scene: Scene) -> APIRouter:
    router = APIRouter()

    @router.get("/state")
    async def get_state():
        async with scene.lock:
            return scene.state()

    @router.get("/robot/{robot_id}/move")
    async def move(
        robot_id: int,
        x: float = Query(..., description="Target X in mm"),
        y: float = Query(..., description="Target Y in mm"),
        z: float = Query(..., description="Target Z in mm — required in v2"),
    ):
        if robot_id not in scene.robots:
            raise HTTPException(404, f"Unknown robot {robot_id}")
        async with scene.lock:
            tx, ty, tz = scene.move_robot(robot_id, x, y, z)
        return {"ok": True, "target": {"x": tx, "y": ty, "z": tz}}

    @router.get("/robot/{robot_id}/pick")
    async def pick(robot_id: int):
        if robot_id not in scene.robots:
            raise HTTPException(404, f"Unknown robot {robot_id}")
        async with scene.lock:
            picked = scene.pick(robot_id)
        return {"ok": True, "picked": picked}

    @router.get("/robot/{robot_id}/drop")
    async def drop(robot_id: int):
        if robot_id not in scene.robots:
            raise HTTPException(404, f"Unknown robot {robot_id}")
        async with scene.lock:
            dropped = scene.drop(robot_id)
        return {"ok": True, "dropped": dropped}

    @router.get("/tag/add")
    async def add_tag(
        x: float = Query(..., description="Tag X in mm"),
        y: float = Query(..., description="Tag Y in mm"),
        value: int = 1,
    ):
        async with scene.lock:
            tid = scene.add_tag(x, y, value=value)
        return {"ok": True, "tag_id": tid}

    @router.get("/game/start")
    async def game_start():
        async with scene.lock:
            scene.start_game()
        return {"ok": True}

    @router.get("/game/reset")
    async def game_reset():
        async with scene.lock:
            scene.reset()
        return {"ok": True}

    @router.get("/stream")
    async def stream():
        return RedirectResponse(url="/hls/playlist.m3u8", status_code=302)

    return router
