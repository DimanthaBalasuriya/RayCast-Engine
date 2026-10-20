"""Deterministic hitscan and combat effects, independent of pygame drawing."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol
import random

import config
from engine.camera import Camera
from engine.decals import Decals
from engine.enemy import Enemy
from engine.events import Events
from engine.level import Hit, Level
from engine.lighting import Lighting, Light
from engine.player import Player
from engine.weapons import WeaponState


class Damageable(Protocol):
    def take_damage(self, amount: int, hit_point: tuple[float, float, float], source: object) -> None: ...


@dataclass(frozen=True)
class Impact:
    kind: str
    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    surface: int | None
    hit: Hit | None = None
    light: Light | None = None
    enemy: Enemy | None = None


class Combat:
    def __init__(self, level: Level, lighting: Lighting, decals: Decals, events: Events):
        self.level, self.lighting, self.decals, self.events = level, lighting, decals, events
        self.random = random.Random(config.HITSCAN_SEED)
        self.enemies: list[Enemy] = []

    def sample_angles(self, base_angle: float, half_cone_deg: float, count: int) -> list[float]:
        """Return reproducible pellet directions within the configured spread cone."""
        return [base_angle + math.radians(self.random.uniform(-half_cone_deg, half_cone_deg))
                for _ in range(count)]

    def spread_degrees(self, weapon: WeaponState, player: Player, zoomed: bool,
                       stack: float) -> float:
        """Compute the half-cone spread from movement and weapon state."""
        spread = float(weapon.definition["spread_deg"]) * (1 + stack)
        speed = math.hypot(player.vx, player.vy)
        if not player.on_ground:
            spread *= config.SPREAD_AIR_MULT
        elif player.crouching and speed < config.CROUCH_SPEED * 0.5:
            spread *= config.SPREAD_CROUCH_MULT
        elif speed > config.WALK_SPEED + 0.3:
            spread *= config.SPREAD_RUNNING_MULT
        elif speed > 0.25:
            spread *= config.SPREAD_MOVING_MULT
        if zoomed:
            spread *= config.SPREAD_ZOOM_MULT
        return spread

    def trace(self, camera: Camera, angle: float, max_range: float,
              vertical_look: bool, screen_height: int) -> Impact | None:
        """Return the first wall, plane or shootable light along one bullet ray."""
        dx, dy = math.cos(angle), math.sin(angle)
        wall = self.level.grid_raycast((camera.x, camera.y), (dx, dy), max_range)
        wall_distance = wall.distance if wall else max_range
        # Use the renderer's vertical projection so shots land at the crosshair.
        projection = camera.projection if camera.projection > 0 else screen_height
        slope = camera.pitch / projection if vertical_look else 0.0
        plane_kind = None
        plane_distance = math.inf
        if slope > 0:
            plane_distance = (1 - camera.eye_z) / slope
            plane_kind = "ceiling"
        elif slope < 0:
            plane_distance = -camera.eye_z / slope
            plane_kind = "floor"
        limit = min(wall_distance, plane_distance, max_range)

        nearest: tuple[float, Light] | None = None
        for light in self.lighting.lights:
            if not light.shootable or light.shot_out:
                continue
            tx, ty = light.x - camera.x, light.y - camera.y
            along = tx * dx + ty * dy
            lateral = abs(tx * dy - ty * dx)
            bullet_z = camera.eye_z + slope * along
            if (config.MIN_LIGHT_SHOT_DISTANCE < along < limit and lateral <= config.LIGHT_HIT_RADIUS
                    and abs(bullet_z - light.z) <= config.LIGHT_HIT_Z_RADIUS
                    and (nearest is None or along < nearest[0])):
                nearest = (along, light)
        nearest_enemy: tuple[float, Enemy] | None = None
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            tx, ty = enemy.x - camera.x, enemy.y - camera.y
            along = tx * dx + ty * dy
            lateral = abs(tx * dy - ty * dx)
            bullet_z = camera.eye_z + slope * along
            if (config.MIN_LIGHT_SHOT_DISTANCE < along < limit
                    and lateral <= config.TEST_ENEMY_HIT_RADIUS
                    and 0 <= bullet_z <= config.TEST_ENEMY_WORLD_HEIGHT
                    and (nearest_enemy is None or along < nearest_enemy[0])):
                nearest_enemy = (along, enemy)
        if nearest_enemy is not None and (nearest is None or nearest_enemy[0] < nearest[0]):
            along, enemy = nearest_enemy
            return Impact("enemy", (enemy.x, enemy.y, camera.eye_z + slope * along),
                          (-dx, -dy, 0.0), None, enemy=enemy)
        if nearest is not None:
            along, light = nearest
            return Impact("light", (light.x, light.y, camera.eye_z + slope * along),
                          (0.0, 0.0, 0.0), None, light=light)
        if plane_distance < wall_distance and plane_distance <= max_range:
            px = camera.x + dx * plane_distance
            py = camera.y + dy * plane_distance
            assert plane_kind is not None
            z = 1.0 if plane_kind == "ceiling" else 0.0
            tx, ty = int(px), int(py)
            tx = max(0, min(self.level.width - 1, tx))
            ty = max(0, min(self.level.height - 1, ty))
            surface = int((self.level.ceilings if z else self.level.floors)[ty, tx])
            return Impact(plane_kind, (px, py, z), (0.0, 0.0, -1.0 if z else 1.0), surface)
        if wall is not None:
            z = camera.eye_z + slope * wall.distance
            return Impact("wall", (wall.point[0], wall.point[1], z),
                          (float(wall.normal[0]), float(wall.normal[1]), 0.0), wall.surface, wall)
        return None

    def fire(self, weapon: WeaponState, player: Player, camera: Camera, now: float,
             vertical_look: bool, zoomed: bool, spread_stack: float,
             screen_height: int) -> list[Impact]:
        """Fire all pellets, merge impact flashes, and emit hit feedback."""
        definition = weapon.definition
        muzzle = definition["muzzle_light"]
        self.lighting.spawn_temp_light(
            camera.x + math.cos(camera.angle) * config.MUZZLE_FORWARD_OFFSET,
            camera.y + math.sin(camera.angle) * config.MUZZLE_FORWARD_OFFSET,
            tuple(muzzle["color"]), float(muzzle["intensity"]),
            float(muzzle["radius"]), float(muzzle["duration"]), now, "muzzle", camera.eye_z)
        spread = self.spread_degrees(weapon, player, zoomed, spread_stack)
        impacts: list[Impact] = []
        flash_positions: set[tuple[int, int]] = set()
        for angle in self.sample_angles(camera.angle, spread, int(definition["pellets"])):
            impact = self.trace(camera, angle, float(definition["range"]), vertical_look, screen_height)
            if impact is None:
                continue
            impacts.append(impact)
            self.events.emit("bullet_impact", position=impact.position,
                             normal=impact.normal, surface=impact.surface, kind=impact.kind)
            if impact.kind == "wall" and impact.hit is not None:
                self.decals.add(impact.hit, impact.position[2], now)
            if impact.kind == "light" and impact.light is not None:
                self.lighting.shoot_out(impact.light)
                self.events.emit("light_shot_out", light_id=impact.light.identifier)
            if impact.kind == "enemy" and impact.enemy is not None:
                impact.enemy.take_damage(int(definition["damage"]), impact.position, player)
            key = (int(impact.position[0] * 2), int(impact.position[1] * 2))
            if key not in flash_positions and len(flash_positions) < config.MAX_IMPACT_LIGHTS_PER_SHOT:
                flash_positions.add(key)
                px = impact.position[0] + impact.normal[0] * config.IMPACT_LIGHT_OFFSET
                py = impact.position[1] + impact.normal[1] * config.IMPACT_LIGHT_OFFSET
                self.lighting.spawn_temp_light(px, py, config.IMPACT_LIGHT_COLOR,
                                               config.IMPACT_LIGHT_INTENSITY,
                                               config.IMPACT_LIGHT_RADIUS,
                                               config.IMPACT_LIGHT_DURATION, now, "impact",
                                               max(0.04, min(0.96, impact.position[2])))
        return impacts
