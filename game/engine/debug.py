"""Debug text and top-down map drawn after nearest-neighbor upscale."""

from __future__ import annotations

import math
from typing import Any

import pygame
import config
from engine.camera import Camera

from engine.level import Level
from engine.lighting import Lighting
from engine.player import Player
from engine.window import WindowMetrics


class DebugOverlay:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("consolas", 16)
        self.font_step = 16

    def draw(self, screen: pygame.Surface, level: Level, player: Player,
             lighting: Lighting, fps: float, timings: dict[str, float],
             render_size: tuple[int, int], game: Any = None,
             camera: Camera | None = None,
             metrics: WindowMetrics | None = None) -> None:
        """Display performance, state and a map of walls and lights."""
        active = sum(not light.shot_out for light in lighting.lights) + len(lighting.temporary) + int(lighting.flashlight_on)
        if metrics is not None:
            step = max(12, round(16 * metrics.ui_scale))
            if step != self.font_step:
                self.font = pygame.font.SysFont("consolas", step)
                self.font_step = step
        lines = [
            f"FPS {fps:5.1f} | frame {1000/max(fps, 0.01):5.1f} ms | {render_size[0]}x{render_size[1]} | {lighting.quality}",
            f"ray {timings.get('raycast', 0):4.1f} floor {timings.get('planes', 0):4.1f} light {timings.get('lighting', 0):4.1f} upscale {timings.get('upscale', 0):4.1f} ms",
            f"lightmap {timings.get('lightmap', 0):4.1f} decal {timings.get('decals', 0):4.1f} enemy {timings.get('enemy', 0):4.1f} viewmodel {timings.get('viewmodel', 0):4.1f} HUD {timings.get('hud', 0):4.1f} ms",
            f"{active} lights ({len(lighting.temporary)}/{config.MAX_TEMP_LIGHTS} temp) pos {player.x:.2f},{player.y:.2f} angle {math.degrees(player.angle)%360:.0f} pitch {player.pitch:.0f}",
            f"z {player.z:.2f} vz {player.vz:.2f} ground {player.on_ground} crouch {player.crouch_t:.2f} speed {math.hypot(player.vx, player.vy):.2f}",
            "WASD move  Space jump  Ctrl crouch  mouse fire/zoom  R reload  1/2 switch  H damage",
            "F1 debug  F2 light  F3 fog  F4 quality  F5 look  F6 bob  F7 gun  F8 HUD",
        ]
        if game is not None:
            weapon = game.weapons.current
            eye = camera.eye_z if camera is not None else player.z + config.STAND_EYE_HEIGHT + (config.CROUCH_EYE_HEIGHT - config.STAND_EYE_HEIGHT) * player.crouch_t
            lines.append(f"eye {eye:.2f} | {weapon.name} {game.weapons.state} {weapon.magazine}/{weapon.reserve} | {len(game.decals.items)} decals")
            lines.append(f"character ASSAULT | Alpha Drone {game.enemy.health}/{config.TEST_ENEMY_HEALTH} HP | {game.enemy.animation}")
            lines += [f"event {name}: {str(data)[:95]}" for name, data in game.events.recent]
        if metrics is not None and camera is not None:
            lines.insert(1, f"window {metrics.size[0]}x{metrics.size[1]} aspect {metrics.aspect:.2f} "
                         f"HFOV {camera.fov:.1f} UI {metrics.ui_scale:.2f}")
        line_step = max(18, round(26 * (metrics.ui_scale if metrics else 1)))
        panel = pygame.Surface((min(screen.get_width(), round(900 * (metrics.ui_scale if metrics else 1))),
                                line_step * len(lines) + 6), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 185))
        screen.blit(panel, (0, 0))
        for row, line in enumerate(lines):
            screen.blit(self.font.render(line, True, (235, 240, 235)), (9, 6 + row * line_step))
        scale = max(4, round(7 * (metrics.ui_scale if metrics else 1)))
        left, top = screen.get_width() - level.width * scale - 10, 10
        for y in range(level.height):
            for x in range(level.width):
                color = (65, 73, 81) if level.solid[y, x] else (17, 21, 28)
                pygame.draw.rect(screen, color, (left + x * scale, top + y * scale, scale - 1, scale - 1))
        for light in lighting.lights + lighting.temporary:
            pygame.draw.circle(screen, (255, 174, 85), (left + int(light.x * scale), top + int(light.y * scale)), 2)
        if game is not None and game.enemy.alive:
            pygame.draw.circle(screen, (255, 68, 66),
                               (left + int(game.enemy.x * scale), top + int(game.enemy.y * scale)), 3)
        pygame.draw.circle(screen, (255, 255, 255), (left + int(player.x * scale), top + int(player.y * scale)), 3)
        pygame.draw.line(screen, (255, 255, 255),
                         (left + int(player.x * scale), top + int(player.y * scale)),
                         (left + int((player.x + math.cos(player.angle)) * scale),
                          top + int((player.y + math.sin(player.angle)) * scale)), 2)
