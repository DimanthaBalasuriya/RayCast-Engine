"""Run the textured raycaster demo or a headless performance benchmark."""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import time

import pygame

import config
from engine.atlas import Atlas
from engine.debug import DebugOverlay
from engine.level import Level
from engine.lighting import Lighting
from engine.player import Player
from engine.renderer import Renderer

ROOT = Path(__file__).resolve().parent


def setup() -> tuple[Level, Player, Lighting, Renderer]:
    """Load all game data and create the render pipeline."""
    level = Level(ROOT / "levels" / "level01.txt")
    atlas = Atlas(ROOT / "assets" / "atlas.json")
    atlas.validate_ids(level.walls[level.solid])
    atlas.validate_ids(level.floors)
    atlas.validate_ids(level.ceilings)
    start = level.player_start
    player = Player(float(start["x"]), float(start["y"]), math.radians(start["angle_deg"]))
    lighting = Lighting(level)
    renderer = Renderer(level, atlas, lighting, config.RENDER_SIZE)
    return level, player, lighting, renderer


def benchmark(frames: int, size: tuple[int, int] | None = None) -> None:
    """Measure wall-only, baked, dynamic, and shifted-horizon frame rates."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1, 1))
    level, player, lighting, renderer = setup()
    if size is not None:
        renderer = Renderer(level, renderer.atlas, lighting, size)
    all_lights = lighting.lights[:]
    for name, dynamic, lit, pitch in (
        ("M3 walls (floor pass included)", False, False, 0),
        ("M5 baked static", False, True, 0),
        ("M6 full, vertical off", True, True, 0),
        ("M7 full, vertical on", True, True, renderer.height * 0.17),
    ):
        lighting.lights = all_lights if dynamic or not lit else [
            light for light in all_lights if light.flicker == "none" and light.motion == "none"]
        lighting.set_quality(lighting.quality)
        lighting.flashlight_on = dynamic
        player.pitch = pitch
        now = time.perf_counter()
        for i in range(5):
            if lit:
                lighting.update(now + i / 60, player, 1 / 60)
            renderer.render(player, lighting_on=lit)
        start = time.perf_counter()
        for i in range(frames):
            if lit:
                lighting.update(now + (i + 5) / 60, player, 1 / 60)
            renderer.render(player, lighting_on=lit)
        elapsed = time.perf_counter() - start
        print(f"{name}: {frames / elapsed:.1f} FPS ({elapsed * 1000 / frames:.2f} ms/frame)")
    pygame.quit()


def run() -> None:
    """Main event loop with frame-rate independent movement."""
    pygame.init()
    screen = pygame.display.set_mode(config.WINDOW_SIZE, pygame.RESIZABLE)
    pygame.display.set_caption("Ray — Dynamic Light Raycaster")
    level, player, lighting, renderer = setup()
    overlay = DebugOverlay()
    clock = pygame.time.Clock()
    pygame.event.set_grab(True)
    pygame.mouse.set_visible(False)
    show_debug = True
    lighting_on = True
    fog_on = True
    vertical_look = config.ENABLE_VERTICAL_LOOK
    running = True
    start_time = time.perf_counter()
    while running:
        dt = min(clock.tick(config.TARGET_FPS) / 1000, 0.05)
        now = time.perf_counter() - start_time
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
            elif event.type == pygame.MOUSEBUTTONDOWN and not pygame.event.get_grab():
                pygame.event.set_grab(True)
                pygame.mouse.set_visible(False)
            elif event.type == pygame.MOUSEMOTION and pygame.event.get_grab():
                player.angle += event.rel[0] * config.MOUSE_SENSITIVITY_X
                if vertical_look:
                    direction = -1 if config.INVERT_MOUSE_Y else 1
                    player.pitch -= event.rel[1] * config.MOUSE_SENSITIVITY_Y * direction
                    limit = renderer.height * config.MAX_PITCH
                    player.pitch = max(-limit, min(limit, player.pitch))
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if pygame.event.get_grab():
                        pygame.event.set_grab(False)
                        pygame.mouse.set_visible(True)
                    else:
                        running = False
                elif event.key == pygame.K_F1:
                    show_debug = not show_debug
                elif event.key == pygame.K_F2:
                    lighting_on = not lighting_on
                elif event.key == pygame.K_F3:
                    fog_on = not fog_on
                elif event.key == pygame.K_F4:
                    names = list(config.QUALITY_LEVELS)
                    lighting.set_quality(names[(names.index(lighting.quality) + 1) % len(names)])
                elif event.key == pygame.K_F5:
                    vertical_look = not vertical_look
                    if not vertical_look:
                        player.pitch = 0
                elif event.key == pygame.K_c and vertical_look:
                    player.pitch = 0
                elif event.key == pygame.K_f:
                    lighting.flashlight_on = not lighting.flashlight_on
                elif event.key == pygame.K_e:
                    lighting.spawn(player, now)
        player.move(level, pygame.key.get_pressed(), dt)
        lighting.update(now, player, dt)
        surface = renderer.render(player, lighting_on, fog_on)
        upscale_start = time.perf_counter()
        screen.blit(pygame.transform.scale(surface, screen.get_size()), (0, 0))
        renderer.timings["upscale"] = (time.perf_counter() - upscale_start) * 1000
        if show_debug:
            overlay.draw(screen, level, player, lighting, clock.get_fps(), renderer.timings, config.RENDER_SIZE)
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", action="store_true", help="measure pipeline stages without a window")
    parser.add_argument("--frames", type=int, default=50)
    parser.add_argument("--size", type=str, help="benchmark internal resolution, e.g. 640x360")
    arguments = parser.parse_args()
    if arguments.benchmark:
        size = tuple(map(int, arguments.size.lower().split("x"))) if arguments.size else None
        benchmark(arguments.frames, size)
    else:
        run()
