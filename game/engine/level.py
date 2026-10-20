"""ASCII level loading, region materials and solid-tile queries."""

from __future__ import annotations

import json
from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Hit:
    tile: tuple[int, int]
    face: str
    distance: float
    point: tuple[float, float]
    u: float
    normal: tuple[int, int]
    surface: int


class Level:
    """Immutable tile grids and metadata loaded from a text/JSON pair."""

    def __init__(self, text_path: Path):
        self.meta = json.loads(text_path.with_suffix(".json").read_text(encoding="utf-8"))
        lines = text_path.read_text(encoding="utf-8").splitlines()
        self.height = len(lines)
        self.width = max(map(len, lines))
        self.tile_world_size = float(self.meta.get("tile_world_size", 1.0))
        self.walls = np.zeros((self.height, self.width), dtype=np.int16)
        self.solid = np.ones((self.height, self.width), dtype=bool)
        legend = self.meta.get("legend", {})
        for y, line in enumerate(lines):
            for x, char in enumerate(line.ljust(self.width)):
                if char in (".", "P"):
                    self.solid[y, x] = False
                elif char == "D":
                    self.walls[y, x] = 7
                elif char.isdigit() and char != "0":
                    self.walls[y, x] = int(char)
                elif char == "#":
                    self.walls[y, x] = int(legend.get("#", 1))
                else:
                    self.walls[y, x] = int(legend.get("void", 2))
        self.floors = np.full_like(self.walls, int(self.meta["floor_map_default"]))
        self.ceilings = np.full_like(self.walls, int(self.meta["ceiling_map_default"]))
        for region in self.meta.get("regions", []):
            x0, y0, x1, y1 = region["rect"]
            self.floors[y0:y1, x0:x1] = int(region["floor"])
            self.ceilings[y0:y1, x0:x1] = int(region["ceiling"])
        self.player_start = self.meta["player"]
        px, py = float(self.player_start["x"]), float(self.player_start["y"])
        if self.is_solid(px, py):
            raise ValueError("Player starts inside a solid tile")

    def is_solid(self, x: float, y: float) -> bool:
        """Treat out-of-bounds coordinates as solid."""
        tx, ty = int(np.floor(x / self.tile_world_size)), int(np.floor(y / self.tile_world_size))
        return tx < 0 or ty < 0 or tx >= self.width or ty >= self.height or bool(self.solid[ty, tx])

    def wall_at(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Return wall IDs for in-bounds integer tile coordinates."""
        return self.walls[np.clip(y, 0, self.height - 1), np.clip(x, 0, self.width - 1)]

    def ground_height(self, x: float, y: float) -> float:
        """Current level has one flat floor; retained for later height geometry."""
        return 0.0

    def can_stand(self, x: float, y: float) -> bool:
        """All current ceilings have full height."""
        return True

    def grid_raycast(self, origin: tuple[float, float], direction: tuple[float, float],
                     max_dist: float) -> Hit | None:
        """Cast a scalar DDA through the same solid grid used by wall/light rays."""
        unit = self.tile_world_size
        ox, oy = origin[0] / unit, origin[1] / unit
        dx, dy = direction
        mx, my = math.floor(ox), math.floor(oy)
        sx, sy = (-1 if dx < 0 else 1), (-1 if dy < 0 else 1)
        delta_x = abs(1 / dx) if abs(dx) > 1e-9 else math.inf
        delta_y = abs(1 / dy) if abs(dy) > 1e-9 else math.inf
        side_x = (ox - mx if dx < 0 else mx + 1 - ox) * delta_x
        side_y = (oy - my if dy < 0 else my + 1 - oy) * delta_y
        for _ in range(self.width + self.height + 2):
            if side_x < side_y:
                distance = side_x * unit
                mx += sx
                side_x += delta_x
                face, normal = ("W", (-1, 0)) if sx > 0 else ("E", (1, 0))
            else:
                distance = side_y * unit
                my += sy
                side_y += delta_y
                face, normal = ("N", (0, -1)) if sy > 0 else ("S", (0, 1))
            if distance > max_dist:
                return None
            if not (0 <= mx < self.width and 0 <= my < self.height):
                return None
            if self.solid[my, mx]:
                hx, hy = origin[0] + dx * distance, origin[1] + dy * distance
                raw_u = (hy / unit if normal[0] else hx / unit) % 1
                u = (1 - raw_u) % 1 if (normal[0] < 0 or normal[1] > 0) else raw_u
                return Hit((mx, my), face, distance, (hx, hy), u, normal, int(self.walls[my, mx]))
        return None
