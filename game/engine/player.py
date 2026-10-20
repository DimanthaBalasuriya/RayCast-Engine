"""Frame-rate independent player movement, jump, crouch and health."""

from __future__ import annotations

from dataclasses import dataclass
import math

import config
from engine.events import Events
from engine.level import Level


@dataclass
class PlayerInput:
    forward: float = 0.0
    side: float = 0.0
    turn: float = 0.0
    run: bool = False
    crouch: bool = False
    jump_pressed: bool = False
    jump_held: bool = False


@dataclass
class Player:
    x: float
    y: float
    angle: float
    pitch: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    z: float = 0.0
    vz: float = 0.0
    on_ground: bool = True
    crouching: bool = False
    crouch_t: float = 0.0
    health: int = config.MAX_HEALTH
    max_health: int = config.MAX_HEALTH
    alive: bool = True
    coyote_left: float = 0.0
    jump_buffer_left: float = 0.0
    footstep_travel: float = 0.0
    death_time: float = 0.0
    damage_impulse: float = 0.0
    events: Events | None = None
    character_id: str = config.PLAYER_CHARACTER

    def _clear(self, level: Level, x: float, y: float) -> bool:
        r = config.PLAYER_RADIUS
        return all(not level.is_solid(x + dx, y + dy) for dx in (-r, r) for dy in (-r, r))

    def damage(self, amount: int, events: Events, source: object = None) -> None:
        """Take damage and emit hurt/death exactly once."""
        if not self.alive:
            return
        self.health = max(0, self.health - amount)
        self.damage_impulse = min(1.0, amount / self.max_health)
        events.emit("hurt", amount=amount, health=self.health, source=source)
        if self.health == 0:
            self.alive = False
            self.death_time = 0.0
            self.vx = self.vy = self.vz = 0.0
            events.emit("died", amount=amount, health=0)

    def take_damage(self, amount: int, hit_point: tuple[float, float, float],
                    source: object) -> None:
        """Damageable interface for later hitscan targets."""
        if self.events is not None:
            self.damage(amount, self.events, source)

    def respawn(self, level: Level, events: Events) -> None:
        """Reset all movement and health state at the level start."""
        start = level.player_start
        self.x, self.y = float(start["x"]), float(start["y"])
        self.angle = math.radians(start["angle_deg"])
        self.pitch = self.vx = self.vy = self.z = self.vz = 0.0
        self.crouch_t = self.coyote_left = self.jump_buffer_left = 0.0
        self.footstep_travel = self.death_time = self.damage_impulse = 0.0
        self.crouching = False
        self.on_ground = self.alive = True
        self.health = self.max_health
        events.emit("respawn", amount=0, health=self.health)

    def update(self, level: Level, controls: PlayerInput, dt: float, events: Events) -> None:
        """Accelerate, slide against walls and integrate vertical motion."""
        dt = max(0.0, min(dt, config.MAX_DT))
        if not self.alive:
            self.death_time += dt
            return
        self.angle += controls.turn * config.TURN_SPEED * dt
        requested_crouch = controls.crouch
        if requested_crouch != self.crouching and (requested_crouch or level.can_stand(self.x, self.y)):
            self.crouching = requested_crouch
            events.emit("crouch_start" if requested_crouch else "crouch_end", position=(self.x, self.y))
        target = float(self.crouching)
        delta = dt / max(config.CROUCH_TRANSITION_TIME, 1e-6)
        self.crouch_t += max(-delta, min(delta, target - self.crouch_t))

        self.coyote_left = config.COYOTE_TIME if self.on_ground else max(0.0, self.coyote_left - dt)
        if controls.jump_pressed or (config.AUTO_JUMP and controls.jump_held):
            self.jump_buffer_left = config.JUMP_BUFFER
        else:
            self.jump_buffer_left = max(0.0, self.jump_buffer_left - dt)
        if self.jump_buffer_left > 0 and (self.on_ground or self.coyote_left > 0):
            self.vz = config.JUMP_VELOCITY
            self.on_ground = False
            self.coyote_left = self.jump_buffer_left = 0.0
            events.emit("jump", position=(self.x, self.y))

        forward, side = controls.forward, controls.side
        magnitude = math.hypot(forward, side)
        if magnitude:
            forward, side = forward / magnitude, side / magnitude
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        wx, wy = forward * ca - side * sa, forward * sa + side * ca
        speed = config.CROUCH_SPEED if self.crouching else config.RUN_SPEED if controls.run else config.WALK_SPEED
        acceleration = config.GROUND_ACCEL if self.on_ground else config.AIR_ACCEL * config.AIR_CONTROL
        if magnitude:
            target_x, target_y = wx * speed, wy * speed
            diff_x, diff_y = target_x - self.vx, target_y - self.vy
            change = min(1.0, acceleration * dt / max(math.hypot(diff_x, diff_y), 1e-9))
            self.vx += diff_x * change
            self.vy += diff_y * change
        elif self.on_ground:
            factor = math.exp(-config.GROUND_FRICTION * dt)
            self.vx *= factor
            self.vy *= factor
        length = math.hypot(self.vx, self.vy)
        if length > config.RUN_SPEED:
            self.vx *= config.RUN_SPEED / length
            self.vy *= config.RUN_SPEED / length

        dx, dy = self.vx * dt, self.vy * dt
        steps = max(1, math.ceil(max(abs(dx), abs(dy)) /
                                 (config.PLAYER_RADIUS * config.COLLISION_STEP_FRACTION)))
        old_x, old_y = self.x, self.y
        for _ in range(steps):
            nx = self.x + dx / steps
            if self._clear(level, nx, self.y):
                self.x = nx
            else:
                self.vx = 0.0
            ny = self.y + dy / steps
            if self._clear(level, self.x, ny):
                self.y = ny
            else:
                self.vy = 0.0
        travelled = math.hypot(self.x - old_x, self.y - old_y)
        if self.on_ground:
            self.footstep_travel += travelled
            if self.footstep_travel >= config.FOOTSTEP_DISTANCE:
                self.footstep_travel %= config.FOOTSTEP_DISTANCE
                events.emit("footstep", position=(self.x, self.y), speed=length,
                            crouching=self.crouching, quiet=self.crouching)

        if not self.on_ground:
            self.vz -= config.GRAVITY * dt
            self.z += self.vz * dt
            ground = level.ground_height(self.x, self.y)
            if self.z <= ground:
                impact = max(0.0, -self.vz)
                self.z = ground
                self.vz = 0.0
                self.on_ground = True
                events.emit("land", position=(self.x, self.y), impact_speed=impact)
                if self.jump_buffer_left > 0:
                    self.vz = config.JUMP_VELOCITY
                    self.on_ground = False
                    self.jump_buffer_left = 0.0
                    events.emit("jump", position=(self.x, self.y))
