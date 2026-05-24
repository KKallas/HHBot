"""OpenCV rendering of the scene to a BGR frame.

The world is mm-native. This module owns the only mm→px conversion: a
single scale `MM_TO_PX` applied at draw time. The output frame stacks a
top-down view above a Z-axis side strip; both panels are scaled from the
same world units.

Each robot's TCP carries a small ArUco marker (DICT_5X5_50) so a downstream
CV pipeline watching the live stream can verify the simulator's reported
TCP coordinate matches what's visible in the image — coordinate-frame
ground truth in-band with the video.
"""

from __future__ import annotations

import itertools
import math

import cv2
import numpy as np

from .scene import (
    FIELD_H_MM,
    FIELD_W_MM,
    ROBOT_BASE_SIDE_MM,
    Scene,
)
from .scene import ROBOT_COLORS


# ----- display configuration -----
# 16:9 top-down only; the Z side strip moved out of the video stream so the
# camera view stays clean. Live Z values are exposed via /state and shown in
# the test page's State (JSON) panel.
MM_TO_PX = 1.0                    # 1 mm = 1 px on the rendered canvas
TOPDOWN_H_PX = int(FIELD_H_MM * MM_TO_PX)
TOPDOWN_W_PX = int(FIELD_W_MM * MM_TO_PX)
CANVAS_W_PX = TOPDOWN_W_PX
CANVAS_H_PX = TOPDOWN_H_PX

# ----- grid + dim labels -----
GRID_MAJOR_MM = 100
GRID_MINOR_MM = 50
AXIS_LABEL_EVERY_MM = 100

# ----- robot drawing -----
ARM_WIDTH_MM = 30                 # arm rectangle thickness
TCP_RADIUS_MM = 6
TCP_MARKER_SIZE_MM = 30           # ArUco marker on TCP (mm side)
TAG_MARKER_SIZE_MM = 16           # AtomS3R display is 0.85" diag ≈ 15 mm square

# ----- ArUco dictionaries -----
# Tags and robots use different dictionaries so a CV pipeline can tell them
# apart at a glance without ID overlap juggling.
_TAG_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
_ROBOT_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)

# Robot TCP marker IDs (one per robot, stable)
_ROBOT_MARKER_IDS = {1: 0, 2: 1}


# Monotonic frame counter rendered in the HUD as a heartbeat.
_frame_counter = itertools.count()


# ----- marker bitmap cache -----
_marker_cache: dict[tuple[str, int, int], np.ndarray] = {}


def _marker_bgr(dict_key: str, dictionary, marker_id: int, side_px: int) -> np.ndarray:
    """Generate (or fetch) an ArUco marker bitmap at the given pixel size."""
    key = (dict_key, marker_id, side_px)
    cached = _marker_cache.get(key)
    if cached is not None:
        return cached
    gen_px = max(side_px, 200)
    img = cv2.aruco.generateImageMarker(dictionary, marker_id, gen_px)
    img = cv2.resize(img, (side_px, side_px), interpolation=cv2.INTER_NEAREST)
    bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    _marker_cache[key] = bgr
    return bgr


def _blit_marker(frame: np.ndarray, cx: int, cy: int, side_px: int,
                 dict_key: str, dictionary, marker_id: int) -> None:
    m = _marker_bgr(dict_key, dictionary, marker_id, side_px)
    h, w = m.shape[:2]
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = x0 + w, y0 + h
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    mx0, my0 = fx0 - x0, fy0 - y0
    mx1, my1 = mx0 + (fx1 - fx0), my0 + (fy1 - fy0)
    frame[fy0:fy1, fx0:fx1] = m[my0:my1, mx0:mx1]


def _blit_rotated_marker(frame: np.ndarray, cx: int, cy: int, side_px: int,
                         dict_key: str, dictionary, marker_id: int,
                         angle_deg: float) -> None:
    """Rotate the marker around its center and composite onto `frame` so the
    out-of-original pixels stay transparent (don't overwrite scene with black).

    A real ArUco detector will read both the ID and the rotation back out, so
    this also lets a CV pipeline recover the robot's wrist (J4) angle.
    """
    m = _marker_bgr(dict_key, dictionary, marker_id, side_px)
    cos_a = abs(math.cos(math.radians(angle_deg)))
    sin_a = abs(math.sin(math.radians(angle_deg)))
    out_size = int(math.ceil(side_px * (cos_a + sin_a)))
    center = (side_px / 2.0, side_px / 2.0)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    # Translate so the rotated bbox fits in the larger output canvas
    M[0, 2] += (out_size - side_px) / 2.0
    M[1, 2] += (out_size - side_px) / 2.0

    rotated = cv2.warpAffine(
        m, M, (out_size, out_size),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0),
    )
    mask = cv2.warpAffine(
        np.full((side_px, side_px), 255, dtype=np.uint8),
        M, (out_size, out_size),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )

    x0, y0 = cx - out_size // 2, cy - out_size // 2
    x1, y1 = x0 + out_size, y0 + out_size
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    mx0, my0 = fx0 - x0, fy0 - y0
    mx1, my1 = mx0 + (fx1 - fx0), my0 + (fy1 - fy0)

    roi = frame[fy0:fy1, fx0:fx1]
    rot_roi = rotated[my0:my1, mx0:mx1]
    mask_roi = mask[my0:my1, mx0:mx1]
    mask_3 = cv2.cvtColor(mask_roi, cv2.COLOR_GRAY2BGR)
    frame[fy0:fy1, fx0:fx1] = np.where(mask_3 > 0, rot_roi, roi)


def _mm(v: float) -> int:
    """World mm → top-down pixel."""
    return int(round(v * MM_TO_PX))


# ----- top-down panel -----

def _draw_grid(panel: np.ndarray) -> None:
    """Light minor lines every 50 mm; brighter major lines every 100 mm."""
    minor = (52, 64, 52)
    major = (90, 110, 90)
    # Minor (skip those that coincide with major)
    for x in range(0, FIELD_W_MM + 1, GRID_MINOR_MM):
        if x % GRID_MAJOR_MM == 0:
            continue
        px = _mm(x)
        cv2.line(panel, (px, 0), (px, TOPDOWN_H_PX), minor, 1, cv2.LINE_AA)
    for y in range(0, FIELD_H_MM + 1, GRID_MINOR_MM):
        if y % GRID_MAJOR_MM == 0:
            continue
        py = _mm(y)
        cv2.line(panel, (0, py), (TOPDOWN_W_PX, py), minor, 1, cv2.LINE_AA)
    # Major
    for x in range(0, FIELD_W_MM + 1, GRID_MAJOR_MM):
        px = _mm(x)
        cv2.line(panel, (px, 0), (px, TOPDOWN_H_PX), major, 1, cv2.LINE_AA)
    for y in range(0, FIELD_H_MM + 1, GRID_MAJOR_MM):
        py = _mm(y)
        cv2.line(panel, (0, py), (TOPDOWN_W_PX, py), major, 1, cv2.LINE_AA)


def _draw_axis_labels(panel: np.ndarray) -> None:
    color = (160, 180, 160)
    font = cv2.FONT_HERSHEY_SIMPLEX
    # X labels along the top edge
    for x in range(0, FIELD_W_MM + 1, AXIS_LABEL_EVERY_MM):
        cv2.putText(panel, f"{x}", (_mm(x) + 3, 12), font, 0.35, color, 1, cv2.LINE_AA)
    # Y labels down the left edge
    for y in range(0, FIELD_H_MM + 1, AXIS_LABEL_EVERY_MM):
        py = _mm(y)
        cv2.putText(panel, f"{y}", (4, py + 10 if y == 0 else py - 3), font, 0.35, color, 1, cv2.LINE_AA)
    # Total dims on outer edges
    cv2.putText(panel, f"{FIELD_W_MM} mm", (TOPDOWN_W_PX // 2 - 40, TOPDOWN_H_PX - 6),
                font, 0.4, (200, 220, 200), 1, cv2.LINE_AA)
    cv2.putText(panel, f"{FIELD_H_MM} mm", (TOPDOWN_W_PX - 70, 18),
                font, 0.4, (200, 220, 200), 1, cv2.LINE_AA)


def _draw_reach_circles(panel: np.ndarray, scene: Scene) -> None:
    overlay = panel.copy()
    for r in scene.robots.values():
        cv2.circle(
            overlay,
            (_mm(r.base_x), _mm(r.base_y)),
            _mm(r.reach_r),
            r.color, thickness=-1, lineType=cv2.LINE_AA,
        )
    cv2.addWeighted(overlay, 0.10, panel, 0.90, 0, dst=panel)
    for r in scene.robots.values():
        cv2.circle(
            panel,
            (_mm(r.base_x), _mm(r.base_y)),
            _mm(r.reach_r),
            r.color, thickness=2, lineType=cv2.LINE_AA,
        )


def _draw_robot(panel: np.ndarray, robot) -> None:
    """Draw the physical robot: base square + arm rectangle + TCP + TCP marker."""
    # 1) Base square footprint
    half = ROBOT_BASE_SIDE_MM / 2.0
    p1 = (_mm(robot.base_x - half), _mm(robot.base_y - half))
    p2 = (_mm(robot.base_x + half), _mm(robot.base_y + half))
    cv2.rectangle(panel, p1, p2, (40, 40, 40), thickness=-1)         # dark fill
    cv2.rectangle(panel, p1, p2, robot.color, thickness=2)            # accent border
    # Label in the top-left corner of the base so the arm rectangle (which
    # always extends from base center outward) never covers it.
    cv2.putText(panel, f"R{robot.id}",
                (_mm(robot.base_x - half) + 8, _mm(robot.base_y - half) + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, robot.color, 2, cv2.LINE_AA)

    # 2) Arm rectangle: from base center to TCP, ARM_WIDTH_MM wide
    bx, by = robot.base_x, robot.base_y
    tx, ty = robot.x, robot.y
    dx, dy = tx - bx, ty - by
    length = (dx * dx + dy * dy) ** 0.5
    if length > 1e-3:
        # Perpendicular unit vector for the width
        ux, uy = -dy / length, dx / length
        w_mm = ARM_WIDTH_MM / 2.0
        corners = np.array([
            [bx + ux * w_mm, by + uy * w_mm],
            [tx + ux * w_mm, ty + uy * w_mm],
            [tx - ux * w_mm, ty - uy * w_mm],
            [bx - ux * w_mm, by - uy * w_mm],
        ], dtype=np.float32)
        pts = np.array([[_mm(x), _mm(y)] for x, y in corners], dtype=np.int32)
        cv2.fillPoly(panel, [pts], (70, 70, 70))
        cv2.polylines(panel, [pts], isClosed=True, color=robot.color,
                      thickness=1, lineType=cv2.LINE_AA)

    # 3) TCP indicator (drawn under the marker)
    cv2.circle(panel, (_mm(tx), _mm(ty)), _mm(TCP_RADIUS_MM),
               robot.color, thickness=-1, lineType=cv2.LINE_AA)

    # 4) ArUco marker on the TCP, rotated so its right side aligns with the
    #    arm direction — mimics a marker physically stuck on a J4-rotating
    #    end-effector, and gives the CV pipeline wrist-angle recovery for free.
    #    cv2 angle convention: positive = counter-clockwise in math sense,
    #    which is visually clockwise when image Y points down. Negating the
    #    atan2 angle makes the marker's local +X point along the arm.
    if length > 1e-3:
        arm_angle_deg = -math.degrees(math.atan2(dy, dx))
    else:
        arm_angle_deg = 0.0
    _blit_rotated_marker(
        panel, _mm(tx), _mm(ty), _mm(TCP_MARKER_SIZE_MM),
        "robot", _ROBOT_DICT, _ROBOT_MARKER_IDS[robot.id],
        arm_angle_deg,
    )


def _draw_tags(panel: np.ndarray, scene: Scene) -> None:
    side_px = _mm(TAG_MARKER_SIZE_MM)
    for t in scene.tags.values():
        _blit_marker(panel, _mm(t.x), _mm(t.y), side_px,
                     "tag", _TAG_DICT, t.aruco_id)
        cv2.putText(panel, str(t.value),
                    (_mm(t.x) + side_px // 2 + 2, _mm(t.y) - side_px // 2 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


def _draw_receptacles(panel: np.ndarray, scene: Scene) -> None:
    """Each robot's scoring zone: tinted fill + colored border + live count
    and total-value label. Drawn under tags so a tag mid-air over the
    receptacle still reads clearly."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    overlay = panel.copy()
    for rec in scene.receptacles.values():
        color = ROBOT_COLORS.get(rec.robot_id, (200, 200, 200))
        p0 = (_mm(rec.x), _mm(rec.y))
        p1 = (_mm(rec.x + rec.w), _mm(rec.y + rec.h))
        cv2.rectangle(overlay, p0, p1, color, thickness=-1)
    cv2.addWeighted(overlay, 0.18, panel, 0.82, 0, dst=panel)

    for rec in scene.receptacles.values():
        color = ROBOT_COLORS.get(rec.robot_id, (200, 200, 200))
        p0 = (_mm(rec.x), _mm(rec.y))
        p1 = (_mm(rec.x + rec.w), _mm(rec.y + rec.h))
        cv2.rectangle(panel, p0, p1, color, thickness=2)
        label = f"R{rec.robot_id} BIN  {rec.count}t / {rec.value}pt"
        cv2.putText(
            panel, label,
            (_mm(rec.x) + 4, _mm(rec.y) + 16),
            font, 0.42, (255, 255, 255), 1, cv2.LINE_AA,
        )


# ----- top-level frame -----

def render_frame(scene: Scene) -> np.ndarray:
    """Render a single 16:9 top-down BGR frame. Z info no longer lives in
    the stream — read it from /state."""
    frame = np.full((CANVAS_H_PX, CANVAS_W_PX, 3), (40, 80, 40), dtype=np.uint8)

    _draw_grid(frame)
    _draw_axis_labels(frame)
    _draw_reach_circles(frame, scene)
    _draw_receptacles(frame, scene)
    _draw_tags(frame, scene)
    for r in scene.robots.values():
        _draw_robot(frame, r)

    # HUD: timer + state tag (center top) + frame heartbeat (top-right)
    t = scene.game.time_left
    state = scene.game.state
    label = f"{t:5.1f}s  ({state})" if state != "running" else f"{t:5.1f}s"
    cv2.putText(frame, label, (CANVAS_W_PX // 2 - 80, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, f"f{next(_frame_counter):06d}",
                (CANVAS_W_PX - 100, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

    return frame
