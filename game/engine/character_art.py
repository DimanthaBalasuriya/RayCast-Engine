"""Load the generated character animation grids without modifying source art."""

from __future__ import annotations

import json
from pathlib import Path

import pygame


class CharacterArt:
    def __init__(self, manifest_path: Path, group: str, name: str):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest[group][name]
        sheet = pygame.image.load(str(manifest_path.parent / entry["file"]))
        if pygame.display.get_surface() is not None:
            sheet = sheet.convert_alpha()
        width, height = sheet.get_size()
        columns, rows = int(manifest["columns"]), int(manifest["rows"])
        self.frames: dict[str, list[pygame.Surface]] = {}
        self.settings: dict[str, dict] = {}
        for row, animation in enumerate(entry["animations"]):
            name = animation["name"]
            self.settings[name] = animation
            frames = []
            for column in range(columns):
                x0, x1 = round(column * width / columns), round((column + 1) * width / columns)
                y0, y1 = round(row * height / rows), round((row + 1) * height / rows)
                frames.append(sheet.subsurface(pygame.Rect(x0, y0, x1 - x0, y1 - y0)).copy())
            bounds = pygame.Rect(0, 0, 0, 0)
            for frame in frames:
                visible = frame.get_bounding_rect(min_alpha=8)
                if visible.width and visible.height:
                    bounds = visible if not bounds.width else bounds.union(visible)
            if bounds.width and bounds.height:
                bounds = bounds.clip(pygame.Rect(0, 0, min(frame.get_width() for frame in frames),
                                                  min(frame.get_height() for frame in frames)))
                frames = [frame.subsurface(bounds).copy() for frame in frames]
            self.frames[name] = frames

    def frame(self, animation: str, elapsed: float) -> pygame.Surface:
        """Choose a frame by the manifest FPS, holding the end of one-shot rows."""
        frames = self.frames[animation]
        setting = self.settings[animation]
        number = int(max(0.0, elapsed) * setting["fps"])
        index = number % len(frames) if setting["loop"] else min(number, len(frames) - 1)
        return frames[index]
