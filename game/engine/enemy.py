"""One damageable Alpha Drone for the combat and sprite-rendering demo."""

from __future__ import annotations

from dataclasses import dataclass
import math

import config
from engine.events import Events
from engine.level import Level
from engine.player import Player


@dataclass
class Enemy:
    x: float
    y: float
    events: Events
    spawn_x: float
    spawn_y: float
    health: int = config.TEST_ENEMY_HEALTH
    alive: bool = True
    animation: str = "idle"
    animation_time: float = 0.0
    attack_cooldown: float = 0.0
    attack_time: float = 0.0
    death_time: float = 0.0
    hit_flash: float = 0.0

    def __post_init__(self) -> None:
        self.health = config.TEST_ENEMY_HEALTH

    def set_animation(self, name: str) -> None:
        if self.animation != name:
            self.animation = name
            self.animation_time = 0.0

    def _clear(self, level: Level, x: float, y: float) -> bool:
        radius = config.TEST_ENEMY_RADIUS
        return all(not level.is_solid(x + dx, y + dy)
                   for dx in (-radius, radius) for dy in (-radius, radius))

    def _sees_player(self, level: Level, player: Player, distance: float) -> bool:
        if distance < 1e-6:
            return True
        direction = ((player.x - self.x) / distance, (player.y - self.y) / distance)
        wall = level.grid_raycast((self.x, self.y), direction, distance)
        return wall is None or wall.distance >= distance - 0.05

    def take_damage(self, amount: int, hit_point: tuple[float, float, float], source: object) -> None:
        if not self.alive:
            return
        self.health = max(0, self.health - amount)
        self.hit_flash = 0.18
        self.events.emit("enemy_hurt", enemy="alpha_drone", health=self.health,
                         amount=amount, position=hit_point)
        if self.health == 0:
            self.alive = False
            self.death_time = 0.0
            self.set_animation("die")
            self.events.emit("enemy_died", enemy="alpha_drone", position=(self.x, self.y))

    def update(self, level: Level, player: Player, dt: float) -> None:
        dt = max(0.0, min(dt, config.MAX_DT))
        if not self.alive:
            self.death_time += dt
            self.animation_time += dt
            if self.death_time >= config.TEST_ENEMY_RESPAWN_TIME:
                self.x, self.y = self.spawn_x, self.spawn_y
                self.health = config.TEST_ENEMY_HEALTH
                self.alive = True
                self.attack_cooldown = 0.0
                self.set_animation("idle")
                self.events.emit("enemy_respawn", enemy="alpha_drone", position=(self.x, self.y))
            return
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        self.attack_time = max(0.0, self.attack_time - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)
        dx, dy = player.x - self.x, player.y - self.y
        distance = math.hypot(dx, dy)
        active = player.alive and distance < config.TEST_ENEMY_ALERT_RANGE and self._sees_player(level, player, distance)
        if active and distance <= config.TEST_ENEMY_ATTACK_RANGE:
            if self.attack_cooldown == 0:
                player.damage(config.TEST_ENEMY_DAMAGE, self.events, "alpha_drone")
                self.attack_cooldown = config.TEST_ENEMY_ATTACK_COOLDOWN
                self.attack_time = 0.36
                self.set_animation("pounce")
                self.events.emit("enemy_attack", enemy="alpha_drone", position=(self.x, self.y))
        elif active and distance > config.TEST_ENEMY_STOP_DISTANCE:
            step = min(config.TEST_ENEMY_SPEED * dt, distance - config.TEST_ENEMY_STOP_DISTANCE)
            mx, my = dx / distance * step, dy / distance * step
            if self._clear(level, self.x + mx, self.y):
                self.x += mx
            if self._clear(level, self.x, self.y + my):
                self.y += my
            if self.attack_time == 0:
                self.set_animation("walk")
        elif self.attack_time == 0:
            self.set_animation("idle")
        if self.attack_time > 0:
            self.set_animation("pounce")
        self.animation_time += dt
