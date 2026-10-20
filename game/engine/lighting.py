"""Occluded tile-grid irradiance for floors, ceilings and four wall normals."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

import numpy as np

import config
from engine.level import Level
from engine.player import Player


@dataclass
class Light:
    """A colored point or cone light with optional time behavior and motion."""

    x: float
    y: float
    color: tuple[float, float, float]
    intensity: float
    radius: float
    z: float = 0.65
    kind: str = "point"
    flicker: str = "none"
    angle: float = 0.0
    inner: float = 0.35
    outer: float = 0.58
    motion: str = "none"
    center: tuple[float, float] = (0, 0)
    orbit_radius: float = 0.0
    orbit_speed: float = 0.0
    created: float = 0.0
    lifetime: float = 0.0
    role: str = "level"
    shootable: bool = False
    shot_out: bool = False
    identifier: str = ""
    base_x: float = field(init=False)
    base_y: float = field(init=False)

    def __post_init__(self) -> None:
        self.base_x, self.base_y = self.x, self.y

    def current(self, now: float) -> tuple[float, float]:
        """Return smoothly varying intensity and radius scale."""
        if self.flicker == "torch":
            wave = 0.5 * math.sin(now * 7.3 + self.base_x) + 0.3 * math.sin(now * 12.7 + self.base_y) + 0.2 * math.sin(now * 19.1)
            return 0.86 + 0.14 * wave, 1 + 0.035 * wave
        if self.flicker == "pulse":
            return 0.65 + 0.35 * math.sin(now * 2.8), 1.0
        if self.flicker == "strobe":
            return (1.0 if now % 1.6 < 0.19 else 0.03), 1.0
        if self.flicker == "broken":
            phase = (now * 3.4 + self.base_x * 0.37) % 5.1
            return (0.85 if phase < 0.36 or 1.1 < phase < 1.23 else 0.025), 1.0
        return 1.0, 1.0


class Lighting:
    """Cache static lightmaps; rebuild only dynamic contributions on update frames.

    Six maps encode floor, ceiling, and ±X/±Y wall normals. This costs more
    memory than a single RGB map, but keeps Lambert facing correct at runtime.
    """

    def __init__(self, level: Level, quality: str = config.LIGHTING_QUALITY):
        self.level = level
        self.lights: list[Light] = []
        for index, item in enumerate(level.meta["lights"]):
            px, py = item["pos"]
            self.lights.append(Light(
                float(px), float(py), tuple(item["color"]), float(item["intensity"]),
                float(item["radius"]), float(item.get("z", 0.65)), item["type"],
                item.get("flicker", "none"), motion=item.get("motion", "none"),
                center=tuple(item.get("center", (px, py))),
                orbit_radius=float(item.get("orbit_radius", 0)),
                orbit_speed=float(item.get("orbit_speed", 0)),
                shootable=bool(item.get("shootable", False)), identifier=str(item.get("id", index)),
            ))
        self.flashlight = Light(0, 0, (0.9, 0.96, 1.0), 2.0, 9.0, 0.55,
                                "spot", "none", inner=0.30, outer=0.56)
        self.flashlight_on = False
        self.temporary: list[Light] = []
        self.quality = quality
        self.frame = 0
        self.update_ms = 0.0
        self.set_quality(quality)

    def set_quality(self, quality: str) -> None:
        """Reallocate and rebake the map after an F4 quality change."""
        self.quality = quality
        self.subdivision, self.interval = config.QUALITY_LEVELS[quality]
        sub = self.subdivision
        shape = (6, self.level.height * sub, self.level.width * sub, 3)
        self.static_map = np.zeros(shape, dtype=np.float32)
        self.dynamic_map = np.zeros(shape, dtype=np.float32)
        for light in self.lights:
            if not light.shot_out and light.flicker == "none" and light.motion == "none":
                self._add_light(self.static_map, light, 0, 1, 1)
        self.combined_map = self.static_map.copy()
        self.frame = 0

    def spawn(self, player: Player, now: float) -> None:
        """Create a five-second fading debug light at the player."""
        self.spawn_temp_light(player.x, player.y, (1.0, 0.78, 0.42), 1.6, 5.0, 5.0, now,
                              "debug", player.z + config.STAND_EYE_HEIGHT)

    def spawn_temp_light(self, x: float, y: float, color: tuple[float, float, float],
                         intensity: float, radius: float, duration: float, now: float,
                         role: str = "impact", z: float = 0.65) -> bool:
        """Add a budgeted light; impact lights are evicted before muzzle flashes."""
        if len(self.temporary) >= config.MAX_TEMP_LIGHTS:
            victim = next((light for light in self.temporary if light.role == "impact"), None)
            if victim is None and role == "muzzle":
                victim = next((light for light in self.temporary if light.role != "muzzle"), None)
            if victim is None:
                return False
            self.temporary.remove(victim)
        self.temporary.append(Light(x, y, color, intensity, radius, z=z,
                                    created=now, lifetime=duration, role=role))
        self.frame = self.interval - 1  # ensure brief flashes appear next update
        return True

    def shoot_out(self, light: Light) -> None:
        """Permanently disable a demo light and rebake if it was static."""
        if light.shot_out:
            return
        light.shot_out = True
        if light.flicker == "none" and light.motion == "none":
            self.set_quality(self.quality)
            self.frame = self.interval - 1

    def update(self, now: float, player: Player, dt: float) -> None:
        """Refresh only moving/flickering lights, with quality-dependent cadence."""
        self.temporary = [light for light in self.temporary if now - light.created < light.lifetime]
        if self.flashlight_on:
            self.flashlight.x, self.flashlight.y = player.x, player.y
            self.flashlight.z = player.z + config.STAND_EYE_HEIGHT + (config.CROUCH_EYE_HEIGHT - config.STAND_EYE_HEIGHT) * player.crouch_t
            target = player.angle
            diff = math.atan2(math.sin(target - self.flashlight.angle), math.cos(target - self.flashlight.angle))
            lag = config.FLASHLIGHT_LAG
            self.flashlight.angle += diff * (1 - math.exp(-dt / lag)) if lag > 0 else diff
        self.frame += 1
        if self.frame % self.interval:
            return
        start = time.perf_counter()
        self.dynamic_map.fill(0)
        for light in self.lights:
            if light.shot_out or (light.flicker == "none" and light.motion == "none"):
                continue
            if light.motion == "orbit":
                light.x = light.center[0] + math.cos(now * light.orbit_speed) * light.orbit_radius
                light.y = light.center[1] + math.sin(now * light.orbit_speed) * light.orbit_radius
            strength, radius_scale = light.current(now)
            self._add_light(self.dynamic_map, light, now, strength, radius_scale)
        if self.flashlight_on:
            self._add_light(self.dynamic_map, self.flashlight, now, 1, 1)
        for light in self.temporary:
            strength = max(0, 1 - (now - light.created) / light.lifetime)
            self._add_light(self.dynamic_map, light, now, strength, 1)
        np.add(self.static_map, self.dynamic_map, out=self.combined_map)
        self.update_ms = (time.perf_counter() - start) * 1000

    def _visible(self, light: Light, target_x: np.ndarray, target_y: np.ndarray) -> np.ndarray:
        """Vectorized grid DDA from one light to many lightmap sample points."""
        count = len(target_x)
        if not count:
            return np.zeros(0, dtype=bool)
        ux = self.level.tile_world_size
        lx, ly = light.x / ux, light.y / ux
        tx, ty = target_x / ux, target_y / ux
        vx, vy = tx - lx, ty - ly
        cell_x = np.full(count, math.floor(lx), dtype=np.int32)
        cell_y = np.full(count, math.floor(ly), dtype=np.int32)
        end_x, end_y = np.floor(tx).astype(np.int32), np.floor(ty).astype(np.int32)
        sx, sy = np.where(vx < 0, -1, 1), np.where(vy < 0, -1, 1)
        inv_x = 1 / np.maximum(np.abs(vx), 1e-8)
        inv_y = 1 / np.maximum(np.abs(vy), 1e-8)
        max_x = np.where(vx < 0, lx - cell_x, cell_x + 1 - lx) * inv_x
        max_y = np.where(vy < 0, ly - cell_y, cell_y + 1 - ly) * inv_y
        clear = np.ones(count, dtype=bool)
        active = (cell_x != end_x) | (cell_y != end_y)
        for _ in range(self.level.width + self.level.height + 2):
            if not active.any():
                break
            # At an exact grid corner, either neighboring wall blocks the ray.
            corner = active & (np.abs(max_x - max_y) < 1e-7)
            if corner.any():
                probe_x = self.level.solid[
                    np.clip(cell_y, 0, self.level.height - 1),
                    np.clip(cell_x + sx, 0, self.level.width - 1)]
                probe_y = self.level.solid[
                    np.clip(cell_y + sy, 0, self.level.height - 1),
                    np.clip(cell_x, 0, self.level.width - 1)]
                blocked_corner = corner & (probe_x | probe_y)
                clear[blocked_corner] = False
                active &= ~blocked_corner
            ax = active & (max_x < max_y)
            ay = active & ~ax
            cell_x[ax] += sx[ax]
            cell_y[ay] += sy[ay]
            max_x[ax] += inv_x[ax]
            max_y[ay] += inv_y[ay]
            in_map = (cell_x >= 0) & (cell_y >= 0) & (cell_x < self.level.width) & (cell_y < self.level.height)
            blocked = ~in_map | self.level.solid[np.clip(cell_y, 0, self.level.height - 1),
                                                  np.clip(cell_x, 0, self.level.width - 1)]
            clear[active & blocked] = False
            active &= ~blocked & ((cell_x != end_x) | (cell_y != end_y))
        return clear

    def _add_light(self, dest: np.ndarray, light: Light, now: float, strength: float, radius_scale: float) -> None:
        if strength <= 0:
            return
        sub = self.subdivision
        unit = self.level.tile_world_size
        radius = light.radius * radius_scale
        x0 = max(0, math.floor((light.x - radius) / unit * sub))
        y0 = max(0, math.floor((light.y - radius) / unit * sub))
        x1 = min(dest.shape[2], math.ceil((light.x + radius) / unit * sub))
        y1 = min(dest.shape[1], math.ceil((light.y + radius) / unit * sub))
        if x0 >= x1 or y0 >= y1:
            return
        gy, gx = np.mgrid[y0:y1, x0:x1]
        wx = (gx + 0.5) * unit / sub
        wy = (gy + 0.5) * unit / sub
        vx, vy = light.x - wx, light.y - wy
        horizontal = np.hypot(vx, vy)
        in_radius = horizontal < radius
        tile_x = np.clip((wx / unit).astype(np.int32), 0, self.level.width - 1)
        tile_y = np.clip((wy / unit).astype(np.int32), 0, self.level.height - 1)
        in_radius &= ~self.level.solid[tile_y, tile_x]
        if not np.any(in_radius):
            return
        local_y, local_x = np.nonzero(in_radius)
        visible = self._visible(light, wx[in_radius], wy[in_radius])
        local_y, local_x = local_y[visible], local_x[visible]
        if not len(local_y):
            return
        vx, vy = vx[local_y, local_x], vy[local_y, local_x]
        d = horizontal[local_y, local_x]
        if config.FALLOFF_CURVE == "inverse":
            attenuation = (1 / (1 + 0.18 * d * d)) * np.maximum(1 - (d / radius) ** 2, 0) ** 2
        else:
            attenuation = np.maximum(1 - (d / radius) ** 2, 0) ** 2
        if light.kind == "spot":
            outgoing = np.arctan2(-vy, -vx)
            angle = np.arctan2(np.sin(outgoing - light.angle), np.cos(outgoing - light.angle))
            cone = np.clip((light.outer - np.abs(angle)) / (light.outer - light.inner), 0, 1)
            attenuation *= cone * cone * (3 - 2 * cone)
        power = attenuation * light.intensity * strength
        if not np.any(power):
            return
        # Lambert factors from sample toward light, with a small bounce term.
        floor_len = np.sqrt(d * d + light.z * light.z)
        ceil_z = max(0.05, 1 - light.z)
        ceil_len = np.sqrt(d * d + ceil_z * ceil_z)
        wall_len = np.sqrt(d * d + (light.z - 0.5) ** 2)
        factors = np.stack((
            0.15 + 0.85 * light.z / floor_len,
            0.15 + 0.85 * ceil_z / ceil_len,
            0.15 + 0.85 * np.maximum(vx / wall_len, 0),
            0.15 + 0.85 * np.maximum(-vx / wall_len, 0),
            0.15 + 0.85 * np.maximum(vy / wall_len, 0),
            0.15 + 0.85 * np.maximum(-vy / wall_len, 0),
        ))
        rgb = np.asarray(light.color, dtype=np.float32)
        dest[:, y0 + local_y, x0 + local_x] += (factors * power[None, :])[:, :, None] * rgb

    def sample(self, wx: np.ndarray, wy: np.ndarray, face: np.ndarray) -> np.ndarray:
        """Bilinearly interpolate both cached maps at arbitrary world positions."""
        sub = self.subdivision / self.level.tile_world_size
        x = np.clip(wx * sub - 0.5, 0, self.static_map.shape[2] - 1.001)
        y = np.clip(wy * sub - 0.5, 0, self.static_map.shape[1] - 1.001)
        x0, y0 = x.astype(np.int32), y.astype(np.int32)
        x1, y1 = x0 + 1, y0 + 1
        fx, fy = (x - x0)[..., None], (y - y0)[..., None]
        grid = self.combined_map
        a = grid[face, y0, x0] * (1 - fx) + grid[face, y0, x1] * fx
        b = grid[face, y1, x0] * (1 - fx) + grid[face, y1, x1] * fx
        return a * (1 - fy) + b * fy
