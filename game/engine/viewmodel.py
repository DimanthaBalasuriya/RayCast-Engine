"""Manifest-driven first-person weapon sprite composited after world lighting."""

from __future__ import annotations

import math

import numpy as np
import pygame

import config
from engine.camera import Camera
from engine.lighting import Lighting
from engine.player import Player
from engine.weapons import Weapons


class Viewmodel:
    def __init__(self, weapons: Weapons, player: Player, lighting: Lighting):
        self.weapons, self.player, self.lighting = weapons, player, lighting
        self.sheet = pygame.image.load(str(weapons.image_path)).convert_alpha()
        self.frames: dict[tuple[str, str, int], pygame.Surface] = {}
        for name, item in weapons.items.items():
            for state, entries in item.definition["frames"].items():
                for index, entry in enumerate(entries if isinstance(entries, list) else [entries]):
                    self.frames[(name, state, index)] = self.sheet.subsurface(pygame.Rect(entry["rect"])).copy()
        self.recoil_offset = 0.0
        self.walk_phase = 0.0
        self.last_draw_rect: pygame.Rect | None = None

    def draw(self, screen: pygame.Surface, camera: Camera, dt: float) -> None:
        """Draw a lit, swaying weapon at internal pixel resolution."""
        if not config.SHOW_VIEWMODEL or not self.player.alive:
            return
        item = self.weapons.current
        state = self.weapons.state
        if state == "FIRING":
            pose = "fire"
        elif state == "RELOADING":
            pose = "reload"
        elif state.startswith("SWITCHING"):
            pose = "switch"
        elif state == "COOLDOWN" and item.definition["fire_mode"] == "pump":
            pose = "pump"
        else:
            pose = "idle"
        if pose not in item.definition["frames"]:
            pose = "idle"
        entries = item.definition["frames"].get(pose, item.definition["frames"]["idle"])
        count = len(entries) if isinstance(entries, list) else 1
        index = int((self.weapons.timer * config.VIEWMODEL_ANIM_FPS) % count) if count > 1 else 0
        frame = self.frames[(item.name, pose, index)].copy()
        if self.weapons.flash_left <= 0:
            sample = self.lighting.sample(np.array(camera.x), np.array(camera.y), np.array(0))
            ambient = np.asarray(self.lighting.level.meta["ambient"])
            tint = np.clip(ambient + sample, 0.30, 1.0)
            frame.fill(tuple((tint * 255).astype(int)), special_flags=pygame.BLEND_RGB_MULT)
        size = int(screen.get_height() * config.VIEWMODEL_HEIGHT_FRACTION)
        width = max(1, int(size * frame.get_width() / frame.get_height()))
        image = pygame.transform.scale(frame, (width, size))
        speed = math.hypot(self.player.vx, self.player.vy)
        # Turn input changes only the camera. Raw mouse pixels previously shifted
        # the gun without shifting the crosshair, unlike keyboard turning.
        self.walk_phase += speed * dt * config.HEAD_BOB_FREQUENCY
        sway = math.sin(self.walk_phase) * speed * config.VIEWMODEL_SWAY
        x = (screen.get_width() - width) // 2 + int(sway * screen.get_width())
        self.recoil_offset += (self.weapons.recoil - self.recoil_offset) * (1 - math.exp(-dt * config.RECOIL_RECOVERY))
        y = screen.get_height() - size + int(self.player.crouch_t * size * config.VIEWMODEL_CROUCH_DROP)
        y -= int(self.recoil_offset * size * config.VIEWMODEL_RECOIL_LIFT)
        y -= int(self.player.z * size * config.VIEWMODEL_JUMP_LIFT)
        if state.startswith("SWITCHING"):
            fraction = self.weapons.timer / max(item.definition["switch_time"] * 0.5, 1e-6)
            y += int(size * (1 - fraction if state == "SWITCHING_OUT" else fraction))
        screen.blit(image, (x, y))
        self.last_draw_rect = pygame.Rect(x, y, width, size)
