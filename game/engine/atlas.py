"""Manifest-driven RGB texture lookup."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pygame


class Atlas:
    """Map level tile IDs to texture arrays without assuming atlas positions."""

    def __init__(self, manifest_path: Path):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.tile_size = int(data["tile_size"])
        self.default_floor = int(data["default_floor"])
        self.default_ceiling = int(data["default_ceiling"])
        surface = pygame.image.load(str(manifest_path.parent / data["image"]))
        pixels = pygame.surfarray.array3d(surface).transpose(1, 0, 2)
        checker = np.zeros((self.tile_size, self.tile_size, 3), dtype=np.uint8)
        yy, xx = np.mgrid[:self.tile_size, :self.tile_size]
        checker[(xx // 8 + yy // 8) % 2 == 0] = (255, 0, 255)
        max_id = max([255, *(int(key) for key in data["tiles"])])
        self.textures = np.repeat(checker[None], max_id + 1, axis=0)
        self.available: set[int] = set()
        self.warned: set[int] = set()
        for key, item in data["tiles"].items():
            tile_id = int(key)
            x, y = int(item["col"]) * self.tile_size, int(item["row"]) * self.tile_size
            if x + self.tile_size > pixels.shape[1] or y + self.tile_size > pixels.shape[0]:
                raise ValueError(f"Atlas tile {tile_id} is outside the image")
            self.textures[tile_id] = pixels[y:y + self.tile_size, x:x + self.tile_size]
            self.available.add(tile_id)
        self.id_lut = np.zeros(max_id + 1, dtype=np.int16)
        self.id_lut[list(self.available)] = list(self.available)

    def checked_id(self, tile_id: int) -> int:
        """Return a safe lookup ID and warn once when a texture is absent."""
        if tile_id not in self.available:
            if tile_id not in self.warned:
                logging.warning("Missing atlas tile id %s; using checker texture", tile_id)
                self.warned.add(tile_id)
            return 0
        return tile_id

    def validate_ids(self, ids: np.ndarray) -> None:
        """Warn for all tile IDs referenced by a level."""
        for tile_id in np.unique(ids):
            self.checked_id(int(tile_id))

    def lookup(self, ids: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Fetch many texture pixels in one NumPy operation."""
        safe = self.id_lut[np.clip(ids, 0, len(self.id_lut) - 1)]
        return self.textures[safe, y % self.tile_size, x % self.tile_size]
