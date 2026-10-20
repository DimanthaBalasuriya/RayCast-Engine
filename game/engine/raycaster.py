"""Vectorized DDA wall rays and perspective-correct floor/ceiling casting."""

from __future__ import annotations

import math

import numpy as np

from config import FOV_DEG
from engine.atlas import Atlas
from engine.level import Level
from engine.player import Player


def _camera(player: Player, width: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ca, sa = math.cos(player.angle), math.sin(player.angle)
    plane = math.tan(math.radians(FOV_DEG) / 2)
    camera_x = 2 * (np.arange(width, dtype=np.float32) + 0.5) / width - 1
    return ca + (-sa * plane) * camera_x, sa + (ca * plane) * camera_x, camera_x


def cast_walls(level: Level, atlas: Atlas, player: Player, width: int, height: int, horizon: float) -> tuple[np.ndarray, ...]:
    """Cast all columns together; only the DDA step count uses a Python loop."""
    unit = level.tile_world_size
    px, py = player.x / unit, player.y / unit
    dx, dy, _ = _camera(player, width)
    mx = np.full(width, math.floor(px), dtype=np.int32)
    my = np.full(width, math.floor(py), dtype=np.int32)
    delta_x = np.abs(1 / np.where(np.abs(dx) < 1e-8, 1e-8, dx))
    delta_y = np.abs(1 / np.where(np.abs(dy) < 1e-8, 1e-8, dy))
    step_x = np.where(dx < 0, -1, 1)
    step_y = np.where(dy < 0, -1, 1)
    side_x = np.where(dx < 0, px - mx, mx + 1 - px) * delta_x
    side_y = np.where(dy < 0, py - my, my + 1 - py) * delta_y
    active = np.ones(width, dtype=bool)
    side = np.zeros(width, dtype=np.int8)
    for _ in range(level.width + level.height + 4):
        if not np.any(active):
            break
        advance_x = active & (side_x < side_y)
        advance_y = active & ~advance_x
        mx[advance_x] += step_x[advance_x]
        my[advance_y] += step_y[advance_y]
        side_x[advance_x] += delta_x[advance_x]
        side_y[advance_y] += delta_y[advance_y]
        side[advance_x] = 0
        side[advance_y] = 1
        cx = np.clip(mx, 0, level.width - 1)
        cy = np.clip(my, 0, level.height - 1)
        active &= ~level.solid[cy, cx]
    # DDA distances are along the camera plane rays and already perpendicular.
    depth = np.maximum(np.where(side == 0, side_x - delta_x, side_y - delta_y), 0.03)
    hit_x = px + depth * dx
    hit_y = py + depth * dy
    u = np.where(side == 0, hit_y, hit_x) % 1
    u = np.where(((side == 0) & (dx > 0)) | ((side == 1) & (dy < 0)), 1 - u, u)
    tex_x = np.minimum((u * atlas.tile_size).astype(np.int32), atlas.tile_size - 1)
    wall_ids = level.wall_at(mx, my)
    wall_height = height / depth
    top = horizon - wall_height * 0.5
    bottom = horizon + wall_height * 0.5
    rows = np.arange(height, dtype=np.float32)[:, None]
    wall_mask = (rows >= top[None, :]) & (rows < bottom[None, :])
    tex_y = (((rows - top[None, :]) / wall_height[None, :]) * atlas.tile_size).astype(np.int32)
    tex_y = np.clip(tex_y, 0, atlas.tile_size - 1)
    color = atlas.lookup(np.broadcast_to(wall_ids, (height, width)),
                         np.broadcast_to(tex_x, (height, width)), tex_y)
    # Sample the open side of a wall rather than its solid tile in the lightmap.
    nx = np.where(side == 0, -step_x, 0).astype(np.float32)
    ny = np.where(side == 1, -step_y, 0).astype(np.float32)
    sample_x = (hit_x + nx * 0.18) * unit
    sample_y = (hit_y + ny * 0.18) * unit
    face = np.where(side == 0, np.where(nx > 0, 2, 3), np.where(ny > 0, 4, 5)).astype(np.uint8)
    return color, wall_mask, depth * unit, sample_x, sample_y, face


def cast_planes(level: Level, atlas: Atlas, player: Player, width: int, height: int, horizon: float) -> tuple[np.ndarray, ...]:
    """Project every plane pixel from its row distance and ray direction."""
    dx, dy, _ = _camera(player, width)
    rows = np.arange(height, dtype=np.float32) + 0.5
    offset = rows - horizon
    floor = offset > 0
    # The floor and ceiling are half a tile above/below the camera.
    distance = (height * 0.5 * level.tile_world_size) / np.maximum(np.abs(offset), 0.5)
    wx = player.x + distance[:, None] * dx[None, :]
    wy = player.y + distance[:, None] * dy[None, :]
    tile_x = np.clip(np.floor(wx / level.tile_world_size).astype(np.int32), 0, level.width - 1)
    tile_y = np.clip(np.floor(wy / level.tile_world_size).astype(np.int32), 0, level.height - 1)
    ids = np.where(floor[:, None], level.floors[tile_y, tile_x], level.ceilings[tile_y, tile_x])
    tx = np.floor((wx / level.tile_world_size % 1) * atlas.tile_size).astype(np.int32)
    ty = np.floor((wy / level.tile_world_size % 1) * atlas.tile_size).astype(np.int32)
    color = atlas.lookup(ids, tx, ty)
    face = np.where(floor[:, None], 0, 1).astype(np.uint8)
    return color, wx, wy, np.broadcast_to(face, (height, width)), np.broadcast_to(distance[:, None], (height, width))
