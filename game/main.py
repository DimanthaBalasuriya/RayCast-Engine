"""Run the raycaster, adaptive window and modal quit confirmation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
import os
from pathlib import Path
import time

import pygame

import config
from engine.atlas import Atlas
from engine.camera import CameraRig
from engine.character_art import CharacterArt
from engine.combat import Combat
from engine.debug import DebugOverlay
from engine.decals import Decals
from engine.dialog import ConfirmDialog, DialogResult
from engine.events import Events
from engine.enemy import Enemy
from engine.hud import HUD
from engine.level import Level
from engine.lighting import Lighting
from engine.player import Player, PlayerInput
from engine.renderer import Renderer
from engine.state import GameState, StateMachine
from engine.viewmodel import Viewmodel
from engine.weapons import Weapons
from engine.window import WindowManager, compute_render_size, compute_ui_scale, compute_viewport

ROOT = Path(__file__).resolve().parent
CONTROL_KEYS = (pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d,
                pygame.K_LEFT, pygame.K_RIGHT, pygame.K_SPACE,
                pygame.K_LCTRL, pygame.K_LSHIFT, pygame.K_RSHIFT)


@dataclass
class Game:
    level: Level
    player: Player
    lighting: Lighting
    renderer: Renderer
    events: Events
    camera_rig: CameraRig
    weapons: Weapons
    combat: Combat
    decals: Decals
    hud: HUD
    overlay: DebugOverlay
    enemy: Enemy


def setup(size: tuple[int, int] | None = None) -> Game:
    """Load data and connect gameplay, lighting and drawing systems."""
    level = Level(ROOT / "levels" / "level01.txt")
    atlas = Atlas(ROOT / "assets" / "atlas.json")
    atlas.validate_ids(level.walls[level.solid])
    atlas.validate_ids(level.floors)
    atlas.validate_ids(level.ceilings)
    start = level.player_start
    player = Player(float(start["x"]), float(start["y"]), math.radians(start["angle_deg"]))
    events = Events()
    player.events = events
    lighting = Lighting(level)
    renderer = Renderer(level, atlas, lighting, size or config.RENDER_SIZE)
    camera_rig = CameraRig(events)
    weapons = Weapons(ROOT / "assets" / "weapons.json", events)
    decals = Decals()
    combat = Combat(level, lighting, decals, events)
    spawn_x, spawn_y = config.TEST_ENEMY_SPAWN
    if level.is_solid(spawn_x, spawn_y):
        raise ValueError("Test enemy spawn is inside a wall")
    enemy = Enemy(spawn_x, spawn_y, events, spawn_x, spawn_y)
    combat.enemies.append(enemy)
    renderer.decals = decals
    renderer.viewmodel = Viewmodel(weapons, player, lighting)
    character_manifest = ROOT / "assets" / "characters" / "animations" / "manifest.json"
    renderer.enemy = enemy
    renderer.enemy_art = CharacterArt(character_manifest, "enemies", "alpha_drone")
    avatar_art = CharacterArt(character_manifest, "players", player.character_id)
    return Game(level, player, lighting, renderer, events, camera_rig,
                weapons, combat, decals, HUD(events, avatar_art), DebugOverlay(), enemy)


def benchmark(frames: int, size: tuple[int, int] | None = None) -> None:
    """Measure the prior phase milestones with the adaptive camera."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    screen = pygame.display.set_mode(config.WINDOW_DEFAULT_SIZE)
    game = setup(size)
    game.player.angle = 0.04
    for stage in ("P2", "P5", "P7"):
        game.decals.items.clear()
        for vertical in (False, True):
            game.weapons.refill()
            game.player.pitch = game.renderer.height * 0.12 if vertical else 0
            game.renderer.viewmodel = None if stage == "P2" else Viewmodel(game.weapons, game.player, game.lighting)
            game.renderer.decals = None if stage == "P2" else game.decals
            game.lighting.flashlight_on = stage != "P2"
            now = time.perf_counter()

            def frame(index: int) -> None:
                current = now + index / 60
                if stage != "P2":
                    fired = game.weapons.update(1 / 60, index % 12 == 0, False,
                                                (game.player.x, game.player.y))
                    if fired:
                        aim = game.camera_rig.build(game.player, 0, vertical,
                                                    aspect=game.renderer.width / game.renderer.height,
                                                    render_height=game.renderer.height)
                        game.combat.fire(game.weapons.current, game.player, aim, current,
                                         vertical, False, game.weapons.spread_stack,
                                         game.renderer.height)
                game.lighting.update(current, game.player, 1 / 60)
                camera = game.camera_rig.build(game.player, 1 / 60, vertical,
                                               aspect=game.renderer.width / game.renderer.height,
                                               render_height=game.renderer.height)
                surface = game.renderer.render(camera, now=current, dt=1 / 60)
                if stage == "P7":
                    screen.blit(pygame.transform.scale(surface, screen.get_size()), (0, 0))
                    game.hud.draw(screen, game.player, game.weapons, 0.6, 1 / 60)

            for i in range(5):
                frame(i)
            started = time.perf_counter()
            for i in range(frames):
                frame(i + 5)
            elapsed = time.perf_counter() - started
            print(f"{stage} vertical {'on' if vertical else 'off'}: "
                  f"{frames / elapsed:.1f} FPS ({elapsed * 1000 / frames:.2f} ms/frame)")
    pygame.quit()


def benchmark_windows(frames: int) -> None:
    """Headless viewport benchmark at windowed and simulated desktop sizes."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1, 1))
    game = setup()
    for window_size in ((1280, 800), (1920, 1080), (2560, 1440)):
        render_size = compute_render_size(*window_size)
        game.renderer.resize(*render_size)
        viewport = compute_viewport(*window_size)
        screen = pygame.Surface(window_size)
        game.lighting.flashlight_on = True
        now = time.perf_counter()

        def frame(index: int) -> None:
            current = now + index / 60
            game.lighting.update(current, game.player, 1 / 60)
            camera = game.camera_rig.build(game.player, 1 / 60, False,
                                           aspect=render_size[0] / render_size[1],
                                           render_height=render_size[1])
            scene = game.renderer.render(camera, now=current, dt=1 / 60)
            if viewport.size == window_size:
                pygame.transform.scale(scene, window_size, screen)
            else:
                screen.fill((0, 0, 0))
                screen.blit(pygame.transform.scale(scene, viewport.size), viewport.topleft)
            game.hud.draw(screen, game.player, game.weapons, 0.6, 1 / 60,
                          compute_ui_scale(window_size[1]), viewport)

        for i in range(5):
            frame(i)
        started = time.perf_counter()
        for i in range(frames):
            frame(i + 5)
        elapsed = time.perf_counter() - started
        print(f"window {window_size[0]}x{window_size[1]} -> {render_size[0]}x{render_size[1]}: "
              f"{frames / elapsed:.1f} FPS ({elapsed * 1000 / frames:.2f} ms/frame)")
    pygame.quit()


def run(confirm_quit: bool = config.CONFIRM_QUIT) -> None:
    """Route input by app state, then draw world, HUD, debug and modal dialog."""
    pygame.init()
    window = WindowManager()
    pygame.display.set_caption("Ray — First-Person Core")
    game = setup(window.metrics.render_size)
    state = StateMachine()
    dialog = ConfirmDialog()
    clock = pygame.time.Clock()
    pygame.event.set_grab(True)
    pygame.mouse.set_visible(False)
    show_debug = True
    lighting_on = True
    fog_on = True
    vertical_look = config.ENABLE_VERTICAL_LOOK
    crouch_toggle = False
    discard_motion = True
    swallow_click = False
    blocked_keys: set[int] = set()
    blocked_mouse: set[int] = set()
    running = True
    simulation_time = 0.0
    just_resumed = False

    def grab(enabled: bool) -> None:
        nonlocal discard_motion
        pygame.event.set_grab(enabled)
        pygame.mouse.set_visible(not enabled)
        if enabled:
            pygame.mouse.get_rel()
            discard_motion = True

    def clear_held() -> None:
        keys_now = pygame.key.get_pressed()
        blocked_keys.update(key for key in CONTROL_KEYS if keys_now[key])
        blocked_mouse.update(index for index, down in enumerate(pygame.mouse.get_pressed(3)) if down)

    def open_quit() -> None:
        nonlocal running
        if state.state == GameState.QUIT_CONFIRM:
            return
        if state.request_quit(confirm_quit):
            running = False
            return
        clear_held()
        dialog.reset()
        grab(False)
        game.events.emit("quit_confirm_open", result="none")

    def close_dialog(result: DialogResult) -> None:
        nonlocal running, swallow_click, just_resumed
        if result == DialogResult.RESUME and state.resume():
            game.events.emit("quit_confirm_closed", result="resume")
            clear_held()
            swallow_click = True
            just_resumed = True
            if not state.focus_paused:
                grab(True)
            clock.tick(0)
        elif result == DialogResult.QUIT and state.choose_quit():
            game.events.emit("quit_confirm_closed", result="quit")
            running = False

    while running:
        dt = min(clock.tick(config.TARGET_FPS) / 1000, config.MAX_DT)
        just_resumed = False
        previous_window_size = window.metrics.size
        fire_pressed = False
        jump_pressed = False
        resize_event = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                open_quit()
                continue
            if event.type in (pygame.VIDEORESIZE,
                              getattr(pygame, "WINDOWSIZECHANGED", -1),
                              getattr(pygame, "WINDOWMAXIMIZED", -1),
                              getattr(pygame, "WINDOWRESTORED", -1),
                              getattr(pygame, "WINDOWMINIMIZED", -1)):
                window.handle_window_event(event)
                resize_event = True
                discard_motion = True
                continue
            if event.type == getattr(pygame, "WINDOWFOCUSLOST", -1) and config.PAUSE_ON_FOCUS_LOSS:
                state.focus_paused = True
                clear_held()
                grab(False)
                game.events.emit("focus_lost")
                continue
            if event.type == getattr(pygame, "WINDOWFOCUSGAINED", -1) and config.PAUSE_ON_FOCUS_LOSS:
                state.focus_paused = False
                just_resumed = True
                if state.state == GameState.PLAYING:
                    grab(True)
                clear_held()
                clock.tick(0)
                game.events.emit("focus_gained")
                continue
            if state.state == GameState.QUIT_CONFIRM:
                result = DialogResult.NONE
                if event.type == pygame.KEYDOWN:
                    names = {pygame.K_LEFT: "left", pygame.K_RIGHT: "right",
                             pygame.K_TAB: "tab", pygame.K_RETURN: "enter",
                             pygame.K_KP_ENTER: "enter", pygame.K_SPACE: "space",
                             pygame.K_ESCAPE: "escape", pygame.K_n: "n", pygame.K_y: "y"}
                    result = dialog.handle_key(names.get(event.key, ""),
                                               bool(event.mod & pygame.KMOD_SHIFT))
                elif event.type == pygame.MOUSEMOTION:
                    dialog.mouse_move(event.pos, window.metrics.size, window.metrics.ui_scale)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    result = dialog.click(event.pos, window.metrics.size, window.metrics.ui_scale)
                close_dialog(result)
                continue
            if state.focus_paused or just_resumed:
                continue
            if event.type == pygame.KEYDOWN and (event.key == pygame.K_F11 or
                    (event.key == pygame.K_RETURN and event.mod & pygame.KMOD_ALT)):
                enabled = window.toggle_fullscreen()
                game.events.emit("fullscreen_changed", enabled=enabled)
                resize_event = True
                grab(True)
                continue
            if event.type == pygame.MOUSEBUTTONDOWN:
                if not pygame.event.get_grab():
                    grab(True)
                    swallow_click = True
                elif event.button == 1:
                    if not swallow_click and 0 not in blocked_mouse:
                        fire_pressed = True
                elif event.button == 4:
                    game.weapons.cycle(-1)
                elif event.button == 5:
                    game.weapons.cycle(1)
            elif event.type == pygame.MOUSEWHEEL:
                game.weapons.cycle(-event.y)
            elif event.type == pygame.MOUSEMOTION and pygame.event.get_grab() and game.player.alive:
                if discard_motion:
                    discard_motion = False
                    continue
                sensitivity = config.MOUSE_SENSITIVITY_X * (
                    config.ZOOM_TURN_MULT if config.ENABLE_ZOOM and pygame.mouse.get_pressed()[2] else 1)
                game.player.angle += event.rel[0] * sensitivity
                if vertical_look:
                    direction = -1 if config.INVERT_MOUSE_Y else 1
                    game.player.pitch -= event.rel[1] * config.MOUSE_SENSITIVITY_Y * direction
                    limit = game.renderer.height * config.MAX_PITCH
                    game.player.pitch = max(-limit, min(limit, game.player.pitch))
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    open_quit()
                elif event.key == pygame.K_SPACE:
                    jump_pressed = True
                elif event.key == pygame.K_LCTRL and config.CROUCH_TOGGLE:
                    crouch_toggle = not crouch_toggle
                elif event.key == pygame.K_r:
                    game.weapons.reload()
                elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    game.weapons.switch_slot(event.key - pygame.K_0)
                elif event.key == pygame.K_q:
                    game.weapons.switch(game.weapons.last_name)
                elif event.key == pygame.K_h:
                    game.player.damage(config.DEBUG_DAMAGE, game.events, "debug")
                elif event.key == pygame.K_t:
                    game.weapons.refill()
                elif event.key == pygame.K_RETURN and not game.player.alive:
                    game.player.respawn(game.level, game.events)
                    game.weapons.refill()
                    crouch_toggle = False
                elif event.key == pygame.K_F1:
                    show_debug = not show_debug
                elif event.key == pygame.K_F2:
                    lighting_on = not lighting_on
                elif event.key == pygame.K_F3:
                    fog_on = not fog_on
                elif event.key == pygame.K_F4:
                    names = list(config.QUALITY_LEVELS)
                    game.lighting.set_quality(names[(names.index(game.lighting.quality) + 1) % len(names)])
                elif event.key == pygame.K_F5:
                    vertical_look = not vertical_look
                    if not vertical_look:
                        game.player.pitch = 0
                elif event.key == pygame.K_F6:
                    game.camera_rig.head_bob = not game.camera_rig.head_bob
                elif event.key == pygame.K_F7:
                    config.SHOW_VIEWMODEL = not config.SHOW_VIEWMODEL
                elif event.key == pygame.K_F8:
                    config.SHOW_HUD = not config.SHOW_HUD
                elif event.key == pygame.K_c and vertical_look:
                    game.player.pitch = 0
                elif event.key == pygame.K_f:
                    game.lighting.flashlight_on = not game.lighting.flashlight_on
                elif event.key == pygame.K_e:
                    game.lighting.spawn(game.player, simulation_time)

        if not running:
            break
        if window.sync() or window.metrics.size != previous_window_size:
            resize_event = True
            game.renderer.resize(*window.metrics.render_size)
            game.events.emit("window_resized", window_size=window.metrics.size,
                             render_size=window.metrics.render_size,
                             aspect=window.metrics.aspect)
        if resize_event:
            discard_motion = True
        if window.minimized or min(window.metrics.size) <= 0:
            clock.tick(10)
            continue

        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed(3)
        blocked_keys.intersection_update(key for key in CONTROL_KEYS if keys[key])
        blocked_mouse.intersection_update(index for index, down in enumerate(mouse) if down)
        if swallow_click and not mouse[0]:
            swallow_click = False

        def down(key: int) -> bool:
            return bool(keys[key]) and key not in blocked_keys

        if not state.paused and not just_resumed:
            simulation_time += dt
            controls = PlayerInput(
                forward=float(down(pygame.K_w)) - float(down(pygame.K_s)),
                side=float(down(pygame.K_d)) - float(down(pygame.K_a)),
                turn=float(down(pygame.K_RIGHT)) - float(down(pygame.K_LEFT)),
                run=down(pygame.K_LSHIFT) or down(pygame.K_RSHIFT),
                crouch=crouch_toggle if config.CROUCH_TOGGLE else down(pygame.K_LCTRL),
                jump_pressed=jump_pressed, jump_held=down(pygame.K_SPACE),
            )
            game.player.update(game.level, controls, dt, game.events)
            game.enemy.update(game.level, game.player, dt)
        zoomed = bool(config.ENABLE_ZOOM and mouse[2] and 2 not in blocked_mouse and not state.paused)
        metrics = window.metrics
        camera = game.camera_rig.build(game.player, 0 if state.paused or just_resumed else dt, vertical_look,
                                       zoomed, game.renderer.width / game.renderer.height,
                                       game.renderer.height)
        if not state.paused and not just_resumed:
            if game.player.alive:
                fired = game.weapons.update(dt, fire_pressed,
                                            mouse[0] and 0 not in blocked_mouse and not swallow_click,
                                            (game.player.x, game.player.y))
                if fired:
                    recoil = game.weapons.current.definition["recoil"]
                    game.combat.fire(game.weapons.current, game.player, camera,
                                     simulation_time, vertical_look, zoomed,
                                     game.weapons.spread_stack, game.renderer.height)
                    game.camera_rig.on_shoot(float(recoil["pitch_deg"]), float(recoil["fov"]),
                                             camera.projection, vertical_look)
            else:
                game.weapons.update(dt)
            game.lighting.update(simulation_time, game.player, dt)
        scene = game.renderer.render(camera, lighting_on, fog_on, simulation_time,
                                     0 if state.paused or just_resumed else dt)
        upscale_start = time.perf_counter()
        screen = window.screen
        if metrics.viewport.size == metrics.size:
            pygame.transform.scale(scene, metrics.size, screen)
        else:
            screen.fill((0, 0, 0))
            screen.blit(pygame.transform.scale(scene, metrics.viewport.size), metrics.viewport.topleft)
        game.renderer.timings["upscale"] = (time.perf_counter() - upscale_start) * 1000
        spread = game.combat.spread_degrees(game.weapons.current, game.player, zoomed,
                                            game.weapons.spread_stack)
        hud_start = time.perf_counter()
        game.hud.draw(screen, game.player, game.weapons, spread,
                      0 if state.paused or just_resumed else dt, metrics.ui_scale, metrics.viewport)
        game.renderer.timings["hud"] = (time.perf_counter() - hud_start) * 1000
        if show_debug:
            game.overlay.draw(screen, game.level, game.player, game.lighting,
                              clock.get_fps(), game.renderer.timings,
                              metrics.render_size, game, camera, metrics)
        if state.state == GameState.QUIT_CONFIRM:
            game.hud.draw_dialog(screen, dialog, metrics.ui_scale)
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--window-benchmark", action="store_true")
    parser.add_argument("--frames", type=int, default=50)
    parser.add_argument("--size", type=str, help="benchmark internal size, e.g. 640x360")
    parser.add_argument("--no-confirm-quit", action="store_true")
    arguments = parser.parse_args()
    size = tuple(map(int, arguments.size.lower().split("x"))) if arguments.size else None
    if arguments.window_benchmark:
        benchmark_windows(arguments.frames)
    elif arguments.benchmark:
        benchmark(arguments.frames, size)
    else:
        run(confirm_quit=config.CONFIRM_QUIT and not arguments.no_confirm_quit)
