"""Plain-assert headless checks for movement, camera, hitscan and weapons."""

from __future__ import annotations

import math
import os
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from engine.camera import Camera, CameraRig, derive_hfov, derive_vfov, projection_scale
from engine.combat import Combat
from engine.decals import Decals
from engine.dialog import ConfirmDialog, DialogResult
from engine.events import Events
from engine.level import Level
from engine.lighting import Lighting
from engine.player import Player, PlayerInput
from engine.state import GameState, StateMachine
from engine.viewmodel import Viewmodel
from engine.weapons import Weapons
from engine.window import compute_render_size, compute_ui_scale, compute_viewport


def run() -> None:
    assert compute_render_size(1280, 800) == (320, 200)
    assert compute_render_size(1920, 1080) == (356, 200)
    assert compute_render_size(2560, 1440) == (356, 200)
    assert compute_render_size(10000, 1000) == (480, 200)
    assert compute_render_size(200, 1000) == (200, 200)  # extreme aspect clamp
    assert compute_render_size(400, 400) == (200, 200)  # no distortion if native minimum fails
    assert compute_render_size(0, 0) == (320, 200)
    assert compute_render_size(777, 700)[0] % 2 == 0
    assert compute_viewport(2400, 500).size == (1200, 500)
    assert compute_viewport(500, 1000).size == (500, 500)
    assert compute_viewport(1920, 1080).size == (1920, 1080)
    assert compute_ui_scale(1080) == 1.0
    assert compute_ui_scale(200) == config.UI_SCALE_MIN
    vfov = derive_vfov(config.FOV_DEG, config.REFERENCE_ASPECT)
    assert abs(derive_hfov(vfov, config.REFERENCE_ASPECT) - config.FOV_DEG) < 1e-10
    assert derive_hfov(vfov, 16 / 9) > config.FOV_DEG
    assert projection_scale(200, vfov) > 0

    state = StateMachine()
    assert state.state == GameState.PLAYING and not state.paused
    assert not state.request_quit() and state.paused
    assert not state.request_quit() and state.state == GameState.QUIT_CONFIRM
    assert state.resume() and not state.paused
    state.focus_paused = True
    assert state.paused
    state.focus_paused = False
    assert state.request_quit(False) and state.state == GameState.PLAYING
    assert not state.request_quit() and state.choose_quit()
    dialog = ConfirmDialog()
    assert dialog.focus == 0 and dialog.handle_key("enter") == DialogResult.RESUME
    assert dialog.handle_key("right") == DialogResult.NONE
    assert dialog.handle_key("space") == DialogResult.QUIT
    assert dialog.handle_key("tab", shift=True) == DialogResult.NONE
    assert dialog.handle_key("n") == DialogResult.RESUME
    assert dialog.handle_key("y") == DialogResult.QUIT
    assert dialog.handle_key("escape") == DialogResult.RESUME
    panel, buttons = dialog.layout((1280, 800), 0.75)
    assert abs(panel.centerx - 640) <= 1 and abs(panel.centery - 400) <= 1
    assert dialog.click(buttons[1].center, (1280, 800), 0.75) == DialogResult.QUIT
    assert dialog.click((0, 0), (1280, 800), 0.75) == DialogResult.NONE

    level = Level(ROOT / "levels" / "level01.txt")
    events = Events()
    start = level.player_start
    player = Player(start["x"], start["y"], 0)

    # A large dt is clamped and movement is substepped through the corner.
    player.x, player.y, player.angle = 2.55, 2.55, math.pi * 1.25
    for _ in range(25):
        player.update(level, PlayerInput(forward=1, run=True), 0.5, events)
        assert player._clear(level, player.x, player.y)
    assert player.x >= 2 + config.PLAYER_RADIUS - 1e-5
    assert player.y >= 2 + config.PLAYER_RADIUS - 1e-5
    player.x, player.y, player.angle = 2.26, 3.0, math.pi
    player.vx = player.vy = 0
    for _ in range(12):
        player.update(level, PlayerInput(forward=1, side=-1), 1 / 60, events)
    assert player.x >= 2 + config.PLAYER_RADIUS
    assert player.y > 3.0  # slides along the wall

    player.respawn(level, events)
    peak = 0.0
    player.update(level, PlayerInput(jump_pressed=True), 1 / 240, events)
    for _ in range(180):
        player.update(level, PlayerInput(), 1 / 240, events)
        peak = max(peak, player.z)
    target = config.JUMP_VELOCITY ** 2 / (2 * config.GRAVITY)
    assert abs(peak - target) < 0.025, (peak, target)
    assert player.on_ground and player.z == 0
    assert any(name == "land" for name, _ in events.recent)

    player.z, player.vz, player.on_ground, player.coyote_left = 0.02, -1.0, False, 0.0
    player.update(level, PlayerInput(jump_pressed=True), 0.01, events)
    player.update(level, PlayerInput(), 0.01, events)
    assert player.vz > 0 and not player.on_ground  # buffered jump on landing
    player.z, player.vz, player.on_ground = 0.02, 0.0, False
    player.coyote_left = config.COYOTE_TIME
    player.update(level, PlayerInput(jump_pressed=True), 0.01, events)
    assert player.vz > 0  # coyote time

    player.respawn(level, events)
    rig = CameraRig(events)
    for _ in range(3):
        player.update(level, PlayerInput(crouch=True), config.CROUCH_TRANSITION_TIME / 3, events)
    camera = rig.build(player, 0, False)
    assert abs(camera.eye_z - config.CROUCH_EYE_HEIGHT) < 1e-6
    assert player.crouching
    for _ in range(3):
        player.update(level, PlayerInput(), config.CROUCH_TRANSITION_TIME / 3, events)
    assert abs(rig.build(player, 0, False).eye_z - config.STAND_EYE_HEIGHT) < 1e-6
    rig.on_shoot(2.0, 1.0, 200, False)
    assert rig.build(player, 0, False).pitch == 0
    rig.on_shoot(2.0, 1.0, 200, True)
    assert rig.build(player, 0, True).pitch > 0
    for _ in range(20):
        zoom_camera = rig.build(player, 1 / 60, False, True)
    assert zoom_camera.fov < config.FOV_DEG

    hit = level.grid_raycast((4.5, 4.5), (1, 0), 40)
    assert hit is not None and hit.tile == (27, 4)
    assert abs(hit.point[0] - 27) < 1e-6 and abs(hit.u - 0.5) < 1e-6
    decals = Decals()
    decals.add(hit, 0.30, 0)
    assert decals.items[-1].v == 0.30
    base = np.full((100, 1, 3), 200, dtype=np.uint8)
    visible = np.ones((100, 1), dtype=bool)
    tile_x, tile_y, face, u = (np.array([27]), np.array([4]), np.array([3]), np.array([0.5]))
    height = np.array([60.0])
    first = decals.apply(base, visible, tile_x, tile_y, face, u,
                         np.array([20.0]), height, 0)
    second = decals.apply(base, visible, tile_x, tile_y, face, u,
                          np.array([30.0]), height, 0)
    assert first[62, 0, 0] < 200 and second[72, 0, 0] < 200
    assert second[62, 0, 0] == 200  # hole follows projected wall height

    lighting = Lighting(level)
    combat = Combat(level, lighting, decals, events)
    for light in lighting.lights:
        light.shootable = False
    low_camera = Camera(4.5, 4.5, 0, config.FOV_DEG, 0, 0.30)
    low_impact = combat.trace(low_camera, 0, 40, False, 200)
    assert low_impact is not None and low_impact.kind == "wall"
    assert abs(low_impact.position[2] - 0.30) < 1e-6
    high_camera = Camera(4.5, 4.5, 0, config.FOV_DEG, 0, 0.80)
    assert combat.trace(high_camera, 0, 40, False, 200).position[2] == 0.80
    up_camera = Camera(4.5, 4.5, 0, config.FOV_DEG, 40, 0.5)
    assert combat.trace(up_camera, 0, 40, True, 200).kind == "ceiling"
    near_camera = Camera(25.5, 4.5, 0, config.FOV_DEG, 10, 0.5)
    near_impact = combat.trace(near_camera, 0, 4, True, 200)
    assert near_impact.kind == "wall"
    assert abs(near_impact.position[2] - (0.5 + 10 * near_impact.hit.distance / 200)) < 1e-6
    angles = combat.sample_angles(0, 5, 100)
    assert all(abs(math.degrees(angle)) <= 5 for angle in angles)

    weapons = Weapons(ROOT / "assets" / "weapons.json", events)
    pistol = weapons.current
    assert pistol.magazine == 12
    for _ in range(12):
        for _ in range(5):
            weapons.update(0.05)
        assert weapons.update(0.05, pressed=True, position=(4.5, 4.5))
    assert pistol.magazine == 0
    for _ in range(5):
        weapons.update(0.05)
    assert not weapons.update(0.05, pressed=True)
    assert weapons.state == "RELOADING"
    assert not weapons.update(0.05, pressed=True)
    for _ in range(23):
        weapons.update(0.05)
    assert pistol.magazine == 12 and pistol.reserve == 48
    weapons.switch_slot(2)
    assert not weapons.update(0.01, pressed=True)
    for _ in range(30):
        weapons.update(0.05)
    assert weapons.current.name == "shotgun" and weapons.state == "READY"
    assert weapons.update(0.05, pressed=True)
    assert not weapons.update(0.05, pressed=True)

    tech = next(light for light in lighting.lights if light.identifier == "cyan_tech")
    tech.shootable = True
    player.x, player.y, player.angle = 13.5, 4.5, 0.0
    shot_camera = Camera(player.x, player.y, 0.0, config.FOV_DEG, 0.0, 0.5)
    impacts = combat.fire(pistol, player, shot_camera, 2.0, False, False, 0.0, 200)
    assert any(impact.kind == "light" for impact in impacts)
    assert tech.shot_out
    assert any(name == "light_shot_out" for name, _ in events.recent)

    for i in range(config.MAX_TEMP_LIGHTS + 5):
        lighting.spawn_temp_light(4.5, 4.5, (1, 1, 1), 1, 2, 1, i * 0.01, "impact")
    assert len(lighting.temporary) == config.MAX_TEMP_LIGHTS
    lighting.spawn_temp_light(4.5, 4.5, (1, 1, 1), 1, 2, 1, 2, "muzzle")
    assert len(lighting.temporary) == config.MAX_TEMP_LIGHTS
    assert any(light.role == "muzzle" for light in lighting.temporary)

    player.damage(player.max_health, events)
    assert not player.alive and player.health == 0
    player.respawn(level, events)
    assert player.alive and player.health == player.max_health
    player.events = events
    player.take_damage(5, (player.x, player.y, 0.5), "test")
    assert player.health == player.max_health - 5

    # No visible display is needed: the gun must keep the same screen position
    # for mouse or keyboard rotation while the player is standing still.
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    model = Viewmodel(weapons, player, lighting)
    screen = pygame.Surface((320, 200))
    player.vx = player.vy = 0
    centers = []
    for angle in (0, 0.5, -0.7):
        player.angle = angle
        model.draw(screen, rig.build(player, 0, False), 0)
        assert model.last_draw_rect is not None
        centers.append(model.last_draw_rect.centerx)
    assert len(set(centers)) == 1

    from main import setup
    game = setup()
    assert game.player.character_id == "assault"
    camera = game.camera_rig.build(game.player, 0, False,
                                   aspect=game.renderer.width / game.renderer.height,
                                   render_height=game.renderer.height)
    target_hit = game.combat.trace(camera, game.player.angle, 40, False,
                                   game.renderer.height)
    assert target_hit is not None and target_hit.kind == "enemy"
    assert target_hit.enemy is game.enemy
    game.enemy.x, game.enemy.y = 15.5, 2.5
    blocked_hit = game.combat.trace(camera, math.atan2(game.enemy.y - game.player.y,
                                                       game.enemy.x - game.player.x),
                                    40, False, game.renderer.height)
    assert blocked_hit is not None and blocked_hit.kind != "enemy"
    game.enemy.x, game.enemy.y = config.TEST_ENEMY_SPAWN
    game.combat.fire(game.weapons.current, game.player, camera, 0,
                     False, False, 0, game.renderer.height)
    assert game.enemy.health < config.TEST_ENEMY_HEALTH
    game.enemy.take_damage(999, (game.enemy.x, game.enemy.y, 0.5), game.player)
    assert not game.enemy.alive and game.enemy.animation == "die"
    for _ in range(int(config.TEST_ENEMY_RESPAWN_TIME / config.MAX_DT) + 1):
        game.enemy.update(game.level, game.player, config.MAX_DT)
    assert game.enemy.alive and game.enemy.health == config.TEST_ENEMY_HEALTH
    pygame.quit()
    print("selftest: all checks passed")


if __name__ == "__main__":
    run()
