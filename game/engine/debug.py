"""Debug text and top-down map drawn after nearest-neighbor upscale."""

from __future__ import annotations

import math

import pygame

from engine.level import Level
from engine.lighting import Lighting
from engine.player import Player


class DebugOverlay:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("consolas", 16)

    def draw(self, screen: pygame.Surface, level: Level, player: Player,
             lighting: Lighting, fps: float, timings: dict[str, float],
             render_size: tuple[int, int]) -> None:
        """Display performance, state and a map of walls and lights."""
        active = len(lighting.lights) + len(lighting.temporary) + int(lighting.flashlight_on)
        lines = [
            f"FPS {fps:5.1f} | frame {1000/max(fps, 0.01):5.1f} ms | {render_size[0]}x{render_size[1]} | {lighting.quality}",
            f"ray {timings.get('raycast', 0):4.1f}  floor/ceil {timings.get('planes', 0):4.1f}  light {timings.get('lighting', 0):4.1f}  upscale {timings.get('upscale', 0):4.1f} ms",
            f"lightmap {timings.get('lightmap', 0):4.1f} ms | {active} lights | pos {player.x:.2f},{player.y:.2f} angle {math.degrees(player.angle)%360:.0f} pitch {player.pitch:.0f}",
            "WASD move  mouse/arrows turn  Shift run  F flashlight  E drop light",
            "F1 debug  F2 lighting  F3 fog  F4 quality  F5 vertical look  C center  Esc release/quit",
        ]
        panel = pygame.Surface((min(screen.get_width(), 900), 26 * len(lines) + 6), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 185))
        screen.blit(panel, (0, 0))
        for row, line in enumerate(lines):
            screen.blit(self.font.render(line, True, (235, 240, 235)), (9, 6 + row * 26))
        scale = 7
        left, top = 10, screen.get_height() - level.height * scale - 10
        for y in range(level.height):
            for x in range(level.width):
                color = (65, 73, 81) if level.solid[y, x] else (17, 21, 28)
                pygame.draw.rect(screen, color, (left + x * scale, top + y * scale, scale - 1, scale - 1))
        for light in lighting.lights + lighting.temporary:
            pygame.draw.circle(screen, (255, 174, 85), (left + int(light.x * scale), top + int(light.y * scale)), 2)
        pygame.draw.circle(screen, (255, 255, 255), (left + int(player.x * scale), top + int(player.y * scale)), 3)
        pygame.draw.line(screen, (255, 255, 255),
                         (left + int(player.x * scale), top + int(player.y * scale)),
                         (left + int((player.x + math.cos(player.angle)) * scale),
                          top + int((player.y + math.sin(player.angle)) * scale)), 2)
