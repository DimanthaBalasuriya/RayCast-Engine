"""Fixed-capacity wall bullet holes projected with wall texture coordinates."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

import config
from engine.level import Hit


@dataclass
class Decal:
    tile: tuple[int, int]
    face: str
    u: float
    v: float
    size: float
    created: float


FACE_CODES = {"E": 2, "W": 3, "S": 4, "N": 5}


class Decals:
    def __init__(self) -> None:
        self.items: deque[Decal] = deque(maxlen=config.MAX_DECALS)

    def add(self, hit: Hit, height: float, now: float) -> None:
        """Place a hole at a world-space height on one exact wall face."""
        self.items.append(Decal(hit.tile, hit.face, hit.u, height, config.DECAL_SIZE, now))

    def apply(self, walls: np.ndarray, wall_mask: np.ndarray, mx: np.ndarray, my: np.ndarray,
              face: np.ndarray, u: np.ndarray, top: np.ndarray,
              wall_height: np.ndarray, now: float) -> np.ndarray:
        """Blend capped decals before light and fog, vectorized over affected pixels."""
        if config.DECAL_LIFETIME > 0:
            self.items = deque((item for item in self.items
                                if now - item.created < config.DECAL_LIFETIME),
                               maxlen=config.MAX_DECALS)
        if not self.items:
            return walls
        output = walls.copy()
        screen_y = np.arange(walls.shape[0], dtype=np.float32)[:, None]
        for decal in self.items:
            columns = (mx == decal.tile[0]) & (my == decal.tile[1]) & (face == FACE_CODES[decal.face])
            du = np.minimum(np.abs(u - decal.u), 1 - np.abs(u - decal.u))
            columns &= du < decal.size
            if not columns.any():
                continue
            selected = np.flatnonzero(columns)
            # World V uses 0 at floor, so the hole remains fixed as top/height move.
            world_v = 1 - (screen_y - top[selected][None, :]) / wall_height[selected][None, :]
            normalized = np.sqrt((du[selected][None, :] / decal.size) ** 2
                                 + ((world_v - decal.v) / decal.size) ** 2)
            mask = (normalized < 1) & wall_mask[:, selected]
            age = 1 if config.DECAL_LIFETIME == 0 else max(0, 1 - (now - decal.created) / config.DECAL_LIFETIME)
            dark = np.where(normalized < 0.45, 0.13, 0.46)
            # Two short diagonal soot cracks outside the central puncture.
            signed_u = u[selected][None, :] - decal.u
            signed_v = world_v - decal.v
            cracks = ((np.abs(signed_v - signed_u * 0.65) < decal.size * 0.08)
                      | (np.abs(signed_v + signed_u * 0.5) < decal.size * 0.06))
            dark = np.where(cracks & (normalized > 0.4), 0.28, dark)
            dark = 1 - (1 - dark) * age
            patch = output[:, selected].astype(np.float32)
            patch = np.where(mask[..., None], patch * dark[..., None], patch)
            output[:, selected] = patch.astype(np.uint8)
        return output
