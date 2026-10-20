"""Camera state derived from the player, with smooth gameplay feedback."""

from __future__ import annotations

from dataclasses import dataclass
import math

import config
from engine.events import Events
from engine.player import Player


@dataclass(frozen=True)
class Camera:
    x: float
    y: float
    angle: float
    fov: float
    pitch: float
    eye_z: float
    vfov: float = 0.0
    projection: float = 0.0


def derive_vfov(reference_hfov_deg: float, reference_aspect: float) -> float:
    """Convert the reference horizontal FOV to a fixed vertical FOV."""
    return math.degrees(2 * math.atan(math.tan(math.radians(reference_hfov_deg) / 2)
                                      / reference_aspect))


def derive_hfov(vfov_deg: float, aspect: float) -> float:
    """Hor+: wider windows expose more world at the same vertical scale."""
    value = math.degrees(2 * math.atan(aspect * math.tan(math.radians(vfov_deg) / 2)))
    return min(config.MAX_HFOV_DEG, value)


def projection_scale(render_height: int, vfov_deg: float) -> float:
    """Perspective scale shared by wall, floor, ceiling, decals and hitscan."""
    return (render_height * 0.5) / math.tan(math.radians(vfov_deg) * 0.5)


class CameraRig:
    def __init__(self, events: Events):
        self.head_bob = config.HEAD_BOB
        self.bob_phase = 0.0
        self.bob_weight = 0.0
        self.landing_dip = 0.0
        self.pitch_kick = 0.0
        self.fov_kick = 0.0
        self.damage_kick = 0.0
        self.zoom_blend = 0.0
        events.subscribe("land", self.on_land)
        events.subscribe("hurt", self.on_hurt)

    def on_land(self, position: tuple[float, float], impact_speed: float) -> None:
        self.landing_dip = min(config.LANDING_DIP_MAX, impact_speed * config.LANDING_DIP_SCALE)

    def on_hurt(self, amount: int, health: int, source: object = None) -> None:
        self.damage_kick += config.DAMAGE_KICK * amount / max(health + amount, 1)

    def on_shoot(self, pitch_deg: float, fov: float, screen_height: int,
                 vertical_look: bool) -> None:
        """Queue a transient recoil pitch and FOV punch."""
        if vertical_look:
            self.pitch_kick += math.tan(math.radians(pitch_deg)) * screen_height
        self.fov_kick += fov

    def build(self, player: Player, dt: float, vertical_look: bool,
              zoomed: bool = False, aspect: float = config.REFERENCE_ASPECT,
              render_height: int = config.RENDER_HEIGHT) -> Camera:
        """Advance camera springs and return a renderer-only value object."""
        dt = min(dt, config.MAX_DT)
        speed = math.hypot(player.vx, player.vy)
        target_bob = min(speed / config.RUN_SPEED, 1) if player.on_ground and player.alive else 0
        self.bob_weight += (target_bob - self.bob_weight) * (1 - math.exp(-dt * config.LANDING_SPRING))
        self.bob_phase += speed * config.HEAD_BOB_FREQUENCY * dt
        bob = (math.sin(self.bob_phase) * self.bob_weight * config.HEAD_BOB_AMPLITUDE
               * (0.5 if player.crouching else 1)) if self.head_bob else 0
        decay = math.exp(-dt * config.LANDING_SPRING)
        self.landing_dip *= decay
        recoil_decay = math.exp(-dt * config.RECOIL_RECOVERY)
        self.pitch_kick *= recoil_decay
        self.fov_kick *= recoil_decay
        self.damage_kick *= recoil_decay
        target_zoom = float(zoomed and config.ENABLE_ZOOM)
        self.zoom_blend += (target_zoom - self.zoom_blend) * (1 - math.exp(-dt * config.ZOOM_SPEED))
        eye = (player.z + config.STAND_EYE_HEIGHT
               + (config.CROUCH_EYE_HEIGHT - config.STAND_EYE_HEIGHT) * player.crouch_t
               + bob - self.landing_dip)
        if not player.alive:
            eye *= max(0.08, 1 - player.death_time / config.DEATH_CAMERA_TIME)
        reference_hfov = config.FOV_DEG + self.fov_kick + config.RUN_FOV_BONUS * speed / config.RUN_SPEED
        vfov = derive_vfov(reference_hfov, config.REFERENCE_ASPECT)
        zoom_vfov = derive_vfov(config.ZOOM_FOV, config.REFERENCE_ASPECT)
        vfov += (zoom_vfov - vfov) * self.zoom_blend
        hfov = derive_hfov(vfov, aspect)
        pitch = player.pitch + self.pitch_kick + self.damage_kick if vertical_look else 0.0
        return Camera(player.x, player.y, player.angle, hfov, pitch,
                      max(0.03, eye), vfov, projection_scale(render_height, vfov))
