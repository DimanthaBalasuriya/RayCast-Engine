"""Depth-tested enemy billboard drawn with vectorized column masking."""

from __future__ import annotations

import math

import numpy as np
import pygame

import config
from engine.camera import Camera
from engine.character_art import CharacterArt
from engine.enemy import Enemy
from engine.lighting import Lighting


def draw_enemy(screen: pygame.Surface, camera: Camera, z_buffer: np.ndarray,
               enemy: Enemy, art: CharacterArt, lighting: Lighting) -> None:
    dx, dy = enemy.x - camera.x, enemy.y - camera.y
    ca, sa = math.cos(camera.angle), math.sin(camera.angle)
    depth = dx * ca + dy * sa
    if depth <= 0.15:
        return
    lateral = -dx * sa + dy * ca
    plane = math.tan(math.radians(camera.fov) / 2)
    width, height = screen.get_size()
    center_x = width * (0.5 + lateral / (2 * depth * plane))
    projection = camera.projection if camera.projection > 0 else height
    sprite_height = min(height * 3, max(1, round(projection * config.TEST_ENEMY_WORLD_HEIGHT / depth)))
    frame = art.frame(enemy.animation, enemy.animation_time)
    sprite_width = max(1, round(sprite_height * frame.get_width() / frame.get_height()))
    left = round(center_x - sprite_width / 2)
    if left >= width or left + sprite_width <= 0:
        return
    horizon = height * 0.5 + camera.pitch
    bottom = horizon + camera.eye_z * projection / depth
    top = round(bottom - sprite_height)
    source = frame.copy()
    sample = lighting.sample(np.array(enemy.x), np.array(enemy.y), np.array(0))
    ambient = np.asarray(lighting.level.meta["ambient"])
    tint = np.clip(ambient + sample, 0.65, 1.0)
    source.fill(tuple((tint * 255).astype(int)), special_flags=pygame.BLEND_RGB_MULT)
    if enemy.hit_flash > 0:
        source.fill((255, 115, 115), special_flags=pygame.BLEND_RGB_ADD)
    sprite = pygame.transform.scale(source, (sprite_width, sprite_height))
    xs = np.arange(left, left + sprite_width)
    onscreen = (xs >= 0) & (xs < width)
    visible = np.zeros(sprite_width, dtype=bool)
    visible[onscreen] = depth < z_buffer[xs[onscreen]] - 0.03
    if not np.any(visible):
        return
    if not np.all(visible):
        alpha = pygame.surfarray.pixels_alpha(sprite)
        alpha[~visible, :] = 0
        del alpha
    screen.blit(sprite, (left, top))
    if enemy.alive and visible[min(sprite_width - 1, max(0, round(center_x) - left))]:
        bar_w = max(12, min(50, sprite_width // 2))
        bar = pygame.Rect(round(center_x - bar_w / 2), top - 6, bar_w, 3)
        if bar.bottom >= 0:
            pygame.draw.rect(screen, (40, 25, 26), bar)
            fill = bar.copy()
            fill.width = round(bar.width * enemy.health / config.TEST_ENEMY_HEALTH)
            pygame.draw.rect(screen, (236, 69, 64), fill)
