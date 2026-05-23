"""OpenCV rendering of the scene to a BGR frame."""

from __future__ import annotations

import itertools

import cv2
import numpy as np

from .scene import FIELD_H, FIELD_W, Scene

# Monotonic frame counter rendered in the HUD as a heartbeat — so anyone
# viewing the stream can tell instantly whether frames are being decoded or
# the player is stuck on a stale image.
_frame_counter = itertools.count()


# ArUco dictionary used for every tag. Generated markers are cached so the
# render loop stays cheap even with many tags on the field.
_ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
_MARKER_PX = 60                    # final on-canvas size
_MARKER_GEN_PX = 200               # generation resolution before resize

_marker_cache: dict[int, np.ndarray] = {}


def _marker_bgr(aruco_id: int) -> np.ndarray:
    cached = _marker_cache.get(aruco_id)
    if cached is not None:
        return cached
    img = cv2.aruco.generateImageMarker(_ARUCO_DICT, aruco_id, _MARKER_GEN_PX)
    img = cv2.resize(img, (_MARKER_PX, _MARKER_PX), interpolation=cv2.INTER_NEAREST)
    bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    _marker_cache[aruco_id] = bgr
    return bgr


def _blit_marker(frame: np.ndarray, cx: int, cy: int, aruco_id: int) -> None:
    m = _marker_bgr(aruco_id)
    h, w = m.shape[:2]
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = x0 + w, y0 + h
    # Clip against frame bounds so partially off-canvas markers don't crash
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(FIELD_W, x1), min(FIELD_H, y1)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    mx0, my0 = fx0 - x0, fy0 - y0
    mx1, my1 = mx0 + (fx1 - fx0), my0 + (fy1 - fy0)
    frame[fy0:fy1, fx0:fx1] = m[my0:my1, mx0:mx1]


def render_frame(scene: Scene) -> np.ndarray:
    frame = np.full((FIELD_H, FIELD_W, 3), (40, 80, 40), dtype=np.uint8)  # dark green field

    # Reach circles: filled at low alpha, then a crisp outline
    overlay = frame.copy()
    for r in scene.robots.values():
        cv2.circle(
            overlay,
            (int(r.reach_x), int(r.reach_y)),
            int(r.reach_r),
            r.color,
            thickness=-1,
            lineType=cv2.LINE_AA,
        )
    cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, dst=frame)
    for r in scene.robots.values():
        cv2.circle(
            frame,
            (int(r.reach_x), int(r.reach_y)),
            int(r.reach_r),
            r.color,
            thickness=2,
            lineType=cv2.LINE_AA,
        )

    # Tags as real ArUco bitmaps so future CV can detect them off the stream
    for t in scene.tags.values():
        _blit_marker(frame, int(t.x), int(t.y), t.aruco_id)
        cv2.putText(
            frame,
            str(t.value),
            (int(t.x) + 32, int(t.y) - 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
            (255, 255, 255), 2, cv2.LINE_AA,
        )

    # Robots: ghost line to target, head circle, id label
    for r in scene.robots.values():
        cv2.line(
            frame,
            (int(r.x), int(r.y)),
            (int(r.target_x), int(r.target_y)),
            r.color, 1, cv2.LINE_AA,
        )
        cv2.circle(frame, (int(r.x), int(r.y)), 22, r.color, -1, cv2.LINE_AA)
        cv2.circle(frame, (int(r.x), int(r.y)), 22, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(
            frame,
            f"R{r.id}",
            (int(r.x) - 12, int(r.y) + 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
            (255, 255, 255), 2, cv2.LINE_AA,
        )

    # HUD: timer (center) + frame counter (top-right heartbeat)
    t = scene.game.time_left
    label = f"{t:5.1f}s" + ("" if scene.game.running else "  (paused)")
    cv2.putText(
        frame, label,
        (FIELD_W // 2 - 90, 40),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0,
        (255, 255, 255), 2, cv2.LINE_AA,
    )
    cv2.putText(
        frame, f"f{next(_frame_counter):06d}",
        (FIELD_W - 160, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
        (200, 200, 200), 1, cv2.LINE_AA,
    )

    return frame
