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
from engine.weapon_art import WeaponArt


class Viewmodel:
    def __init__(self, weapons: Weapons, player: Player, lighting: Lighting,
                 art: WeaponArt | None = None):
        self.weapons, self.player, self.lighting = weapons, player, lighting
        self.art = art or WeaponArt(weapons.manifest)
        self.recoil_offset = 0.0
        self.walk_phase = 0.0
        self.ads_blend = 0.0
        self.last_draw_rect: pygame.Rect | None = None
        self.last_pose: str | None = None
        self.last_frame_index = 0

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
        count = self.art.count(item.name, pose)
        if pose == "fire":
            total = min(self.weapons.cooldown, float(item.definition["muzzle_light"]["duration"]))
        elif pose == "reload":
            total = float(item.definition["reload_time"])
        elif pose == "switch":
            total = float(item.definition["switch_time"]) * 0.5
        elif pose == "pump":
            shot_interval = 60.0 / float(item.definition["rpm"])
            fire_window = min(shot_interval * config.WEAPON_FIRE_FRAME_FRACTION,
                              float(item.definition["muzzle_light"]["duration"]))
            total = max(0.0, shot_interval - fire_window)
        else:
            total = 0.0
        frame_time = float(item.definition.get("frame_time", {}).get(pose,
                           total / count if total else 1 / config.VIEWMODEL_ANIM_FPS))
        elapsed = max(0.0, total - self.weapons.timer)
        index = min(count - 1, int(elapsed / max(frame_time, 1e-6)))
        if state == "SWITCHING_OUT":
            index = count - 1 - index
        self.last_pose, self.last_frame_index = pose, index
        base, offset = self.art.frame(item.name, pose, index)
        frame = base.copy()
        aiming = camera.zoom if state not in ("RELOADING", "SWITCHING_OUT", "SWITCHING_IN") else 0.0
        self.ads_blend += (aiming - self.ads_blend) * (1 - math.exp(-dt * config.ZOOM_SPEED))
        ads_blend = max(0.0, min(1.0, self.ads_blend))
        tint = None
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
        hip_sight = item.definition.get("hip_sight", [base.get_width() // 2, 16])
        scale = size / base.get_height()
        cx, cy = screen.get_width() // 2, screen.get_height() // 2
        x = cx - round(hip_sight[0] * scale) + round(offset[0] * scale) + int(sway * screen.get_width() * (1 - ads_blend))
        self.recoil_offset += (self.weapons.recoil - self.recoil_offset) * (1 - math.exp(-dt * config.RECOIL_RECOVERY))
        y = cy + round(item.definition.get("hip_sight_drop", 12) * scale) - round(hip_sight[1] * scale) + round(offset[1] * scale) + int(self.player.crouch_t * size * config.VIEWMODEL_CROUCH_DROP)
        y -= int(self.recoil_offset * size * config.VIEWMODEL_RECOIL_LIFT)
        y -= int(self.player.z * size * config.VIEWMODEL_JUMP_LIFT)
        if state.startswith("SWITCHING"):
            fraction = self.weapons.timer / max(item.definition["switch_time"] * 0.5, 1e-6)
            y += int(size * (1 - fraction if state == "SWITCHING_OUT" else fraction))
        if ads_blend < 1:
            image.set_alpha(round(255 * (1 - ads_blend)))
            screen.blit(image, (x, y))
        if ads_blend > 0:
            ads = self.art.ads(item.name).copy()
            if tint is not None:
                ads.fill(tuple((tint * 255).astype(int)), special_flags=pygame.BLEND_RGB_MULT)
            ads_scale = float(item.definition.get("ads_scale", 1.0)) * scale
            ads_size = (max(1, round(ads.get_width() * ads_scale)),
                        max(1, round(ads.get_height() * ads_scale)))
            ads_image = pygame.transform.scale(ads, ads_size)
            ads_image.set_alpha(round(255 * ads_blend))
            sight = item.definition.get("ads_sight", [ads.get_width() // 2, ads.get_height() // 3])
            ads_x = cx - round(sight[0] * ads_scale)
            ads_y = cy - round(sight[1] * ads_scale)
            ads_y -= int(self.recoil_offset * size * config.VIEWMODEL_RECOIL_LIFT)
            screen.blit(ads_image, (ads_x, ads_y))
        if self.weapons.flash_left > 0:
            flash = self.art.flash(item.name, int(self.weapons.flash_left * 60) % 2)
            flash_size = max(1, round(flash.get_height() * scale))
            flash_image = pygame.transform.scale(flash, (max(1, round(flash.get_width() * scale)), flash_size))
            dx, dy = item.definition.get("muzzle_offset", [0, -base.get_height() * 0.75])
            flash_x = cx + round(dx * scale * (1 - ads_blend))
            flash_y = screen.get_height() + round(dy * scale)
            flash_y = round(flash_y * (1 - ads_blend) + cy * ads_blend)
            screen.blit(flash_image, (flash_x - flash_image.get_width() // 2,
                                      flash_y - flash_size // 2))
        self.last_draw_rect = pygame.Rect(x, y, width, size)
