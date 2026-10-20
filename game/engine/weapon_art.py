"""Weapon atlas access with per-item concept-art fallbacks."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pygame


LOG = logging.getLogger(__name__)


class WeaponArt:
    def __init__(self, manifest: Path):
        self.manifest = manifest
        data = json.loads(manifest.read_text(encoding="utf-8"))
        fallback_path = manifest.parent / data.get("fallback_image", "weapons_concept.png")
        fallback_manifest = manifest.parent / data.get("fallback_manifest", "weapons_concept.json")
        self.legacy = json.loads(fallback_manifest.read_text(encoding="utf-8"))["weapons"]
        self.fallback = pygame.image.load(str(fallback_path)).convert_alpha()
        self._warnings: set[str] = set()
        image_path = manifest.parent / data.get("image", "weapons.png")
        try:
            self.sheet = pygame.image.load(str(image_path)).convert_alpha()
        except (FileNotFoundError, pygame.error):
            self.sheet = None
            self._warn(f"image {image_path.name}")
        self.definitions = data.get("weapons", {})
        self._cache: dict[tuple[str, str, int], tuple[pygame.Surface, tuple[int, int]]] = {}

    def _warn(self, item: str) -> None:
        if item not in self._warnings:
            self._warnings.add(item)
            LOG.warning("Missing weapon art: %s; using concept fallback", item)

    @staticmethod
    def _extract(sheet: pygame.Surface | None, entry: dict | None) -> pygame.Surface | None:
        if sheet is None or not isinstance(entry, dict):
            return None
        try:
            rect = pygame.Rect(entry["rect"])
            if rect.width <= 0 or rect.height <= 0 or not sheet.get_rect().contains(rect):
                return None
            image = sheet.subsurface(rect).copy()
            return image if pygame.mask.from_surface(image).count() else None
        except (KeyError, TypeError, ValueError, pygame.error):
            return None

    @staticmethod
    def _entries(definition: dict, state: str) -> list[dict]:
        value = definition.get("frames", {}).get(state, [])
        return value if isinstance(value, list) else [value]

    def count(self, name: str, state: str) -> int:
        return max(1, len(self._entries(self.definitions.get(name, self.legacy.get(name, {})), state)))

    def frame(self, name: str, state: str, index: int) -> tuple[pygame.Surface, tuple[int, int]]:
        key = name, state, index
        if key in self._cache:
            return self._cache[key]
        definition = self.definitions.get(name, {})
        entries = self._entries(definition, state)
        entry = entries[index] if 0 <= index < len(entries) else None
        image = self._extract(self.sheet, entry)
        if image is None:
            self._warn(f"{name}/{state}/{index + 1}")
            old = self.legacy.get(name, self.legacy["pistol"])
            old_entries = self._entries(old, state) or self._entries(old, "idle")
            image = self._extract(self.fallback, old_entries[min(index, len(old_entries) - 1)])
            if image is None:
                image = pygame.Surface((96, 96), pygame.SRCALPHA)
        offset = tuple(entry.get("offset", [0, 0])) if isinstance(entry, dict) else (0, 0)
        self._cache[key] = image, offset
        return self._cache[key]

    def icon(self, name: str) -> pygame.Surface:
        key = name, "hud_icon", 0
        if key not in self._cache:
            image = self._extract(self.sheet, self.definitions.get(name, {}).get("hud_icon"))
            if image is None:
                self._warn(f"{name}/hud_icon")
                old = self.legacy.get(name, self.legacy["pistol"])
                image = self._extract(self.fallback, old.get("hud_icon"))
                if image is None:
                    image = pygame.transform.smoothscale(self.frame(name, "idle", 0)[0], (32, 16))
            self._cache[key] = image, (0, 0)
        return self._cache[key][0]

    def ads(self, name: str) -> pygame.Surface:
        key = name, "ads", 0
        if key not in self._cache:
            image = self._extract(self.sheet, self.definitions.get(name, {}).get("ads"))
            if image is None:
                self._warn(f"{name}/ads")
                old = self.legacy.get(name, self.legacy["pistol"])
                image = self._extract(self.fallback, old.get("ads"))
                if image is None:
                    image = self.frame(name, "idle", 0)[0]
            self._cache[key] = image, (0, 0)
        return self._cache[key][0]

    def flash(self, name: str, index: int) -> pygame.Surface:
        key = name, "muzzle_flash", index
        if key not in self._cache:
            entries = self.definitions.get(name, {}).get("muzzle_flash", [])
            image = self._extract(self.sheet, entries[index] if index < len(entries) else None)
            if image is None:
                self._warn(f"{name}/muzzle_flash/{index + 1}")
                old_entries = self.legacy.get(name, self.legacy["pistol"]).get("muzzle_flash", [])
                image = self._extract(self.fallback, old_entries[index % len(old_entries)] if old_entries else None)
                if image is None:
                    image = pygame.Surface((32, 32), pygame.SRCALPHA)
                    pygame.draw.polygon(image, (255, 219, 92, 240), [(0, 16), (12, 11), (16, 0),
                                        (20, 11), (31, 16), (20, 21), (16, 31), (12, 21)])
            self._cache[key] = image, (0, 0)
        return self._cache[key][0]
