"""ASCII level loading, region materials and solid-tile queries."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


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
