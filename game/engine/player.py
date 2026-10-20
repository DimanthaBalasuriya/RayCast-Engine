"""Player movement and circle-versus-grid sliding collision."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pygame

from config import PLAYER_RADIUS, RUN_MULTIPLIER, TURN_SPEED, WALK_SPEED
from engine.level import Level


@dataclass
class Player:
    x: float
    y: float
    angle: float
    pitch: float = 0.0

    def _clear(self, level: Level, x: float, y: float) -> bool:
        r = PLAYER_RADIUS
        return all(not level.is_solid(x + dx, y + dy) for dx in (-r, r) for dy in (-r, r))

    def move(self, level: Level, keys: pygame.key.ScancodeWrapper, dt: float) -> None:
        """Resolve short X/Y substeps separately to prevent tunneling and allow sliding."""
        forward = int(keys[pygame.K_w]) - int(keys[pygame.K_s])
        side = int(keys[pygame.K_d]) - int(keys[pygame.K_a])
        if keys[pygame.K_LEFT]:
            self.angle -= TURN_SPEED * dt
        if keys[pygame.K_RIGHT]:
            self.angle += TURN_SPEED * dt
        if not (forward or side):
            return
        length = math.hypot(forward, side)
        speed = WALK_SPEED * (RUN_MULTIPLIER if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] else 1)
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        dx = (forward * ca - side * sa) * speed * dt / length
        dy = (forward * sa + side * ca) * speed * dt / length
        steps = max(1, math.ceil(max(abs(dx), abs(dy)) / 0.12))
        for _ in range(steps):
            nx = self.x + dx / steps
            if self._clear(level, nx, self.y):
                self.x = nx
            ny = self.y + dy / steps
            if self._clear(level, self.x, ny):
                self.y = ny
