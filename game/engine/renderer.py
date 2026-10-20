"""Compose the raycaster, lightmap, fog and final pixel surface."""

from __future__ import annotations

import time

import numpy as np
import pygame

from engine.atlas import Atlas
from engine.level import Level
from engine.lighting import Lighting
from engine.player import Player
from engine.raycaster import cast_planes, cast_walls
from engine.shading import FAST_SHADING, shade_frame


class Renderer:
    """Own the internal-resolution surface and expose measured render stages."""

    def __init__(self, level: Level, atlas: Atlas, lighting: Lighting, size: tuple[int, int]):
        self.level, self.atlas, self.lighting = level, atlas, lighting
        self.width, self.height = size
        self.surface = pygame.Surface(size)
        self.timings: dict[str, float] = {}

    def render(self, player: Player, lighting_on: bool = True, fog_on: bool = True) -> pygame.Surface:
        """Draw one frame; no Python loop visits individual pixels or columns."""
        horizon = self.height * 0.5 + player.pitch
        t0 = time.perf_counter()
        planes, wx, wy, face, distance = cast_planes(
            self.level, self.atlas, player, self.width, self.height, horizon)
        t1 = time.perf_counter()
        walls, wall_mask, z_buffer, wall_x, wall_y, wall_face = cast_walls(
            self.level, self.atlas, player, self.width, self.height, horizon)
        t2 = time.perf_counter()
        self.z_buffer = z_buffer
        if FAST_SHADING:
            ambient = np.asarray(self.level.meta["ambient"], dtype=np.float32)
            fog = np.asarray(self.level.meta["fog"]["color"], dtype=np.float32)
            rgb_yx = shade_frame(
                planes, walls, wall_mask, wx, wy, face, wall_x, wall_y, wall_face,
                distance, z_buffer, self.lighting.combined_map, ambient, fog,
                float(self.level.meta["fog"]["density"]),
                self.lighting.subdivision / self.level.tile_world_size, lighting_on, fog_on)
            t3 = time.perf_counter()
            rgb = np.ascontiguousarray(rgb_yx.transpose(1, 0, 2))
            pygame.surfarray.blit_array(self.surface, rgb)
            t4 = time.perf_counter()
            self.timings = {
                "planes": (t1 - t0) * 1000, "raycast": (t2 - t1) * 1000,
                "lighting": (t3 - t2) * 1000, "pixels": (t4 - t3) * 1000,
                "lightmap": self.lighting.update_ms,
            }
            return self.surface
        color = np.where(wall_mask[..., None], walls, planes).astype(np.float32) / 255
        if lighting_on:
            plane_visible = ~wall_mask
            illumination = np.zeros((self.height, self.width, 3), dtype=np.float32)
            illumination[plane_visible] = self.lighting.sample(
                wx[plane_visible], wy[plane_visible], face[plane_visible])
            wall_light = self.lighting.sample(wall_x, wall_y, wall_face)
            illumination = np.where(wall_mask[..., None], wall_light[None, :, :], illumination)
            ambient = np.asarray(self.level.meta["ambient"], dtype=np.float32)
            linear = color * (ambient + illumination)
            color = 1 - np.exp(-linear * 1.35)  # soft highlight rolloff
        if fog_on:
            d = np.where(wall_mask, z_buffer[None, :], distance)
            density = float(self.level.meta["fog"]["density"])
            amount = 1 - np.exp(-np.minimum(d, 200) * density)
            fog = np.asarray(self.level.meta["fog"]["color"], dtype=np.float32)
            color = color * (1 - amount[..., None]) + fog * amount[..., None]
        t3 = time.perf_counter()
        rgb = np.ascontiguousarray(np.clip(color * 255, 0, 255).astype(np.uint8).transpose(1, 0, 2))
        pygame.surfarray.blit_array(self.surface, rgb)
        t4 = time.perf_counter()
        self.timings = {
            "planes": (t1 - t0) * 1000, "raycast": (t2 - t1) * 1000,
            "lighting": (t3 - t2) * 1000, "pixels": (t4 - t3) * 1000,
            "lightmap": self.lighting.update_ms,
        }
        return self.surface
