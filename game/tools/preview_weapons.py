"""Interactive weapon sheet preview with animation timing and frame stepping."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import pygame

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.weapon_art import WeaponArt


def viewer(manifest: Path, check_only: bool = False) -> None:
    if check_only:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1, 1) if check_only else (800, 600))
    art = WeaponArt(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    names = list(data["weapons"])
    if check_only:
        for name in names:
            for state in data["weapons"][name]["frames"]:
                for index in range(art.count(name, state)):
                    art.frame(name, state, index)
            if data["weapons"][name].get("ads"):
                art.ads(name)
        print("viewer: all weapon frames loaded")
        pygame.quit()
        return
    screen = pygame.display.get_surface()
    assert screen is not None
    pygame.display.set_caption("Weapon preview")
    font = pygame.font.SysFont("consolas", 20)
    clock = pygame.time.Clock()
    weapon_i = state_i = frame_i = 0
    zoom = 4
    brightness_i = 2
    anchor_guide = True
    paused = False
    elapsed = 0.0
    running = True
    while running:
        dt = clock.tick(60) / 1000
        name = names[weapon_i]
        states = list(data["weapons"][name]["frames"])
        if data["weapons"][name].get("ads"):
            states.append("ads")
        state_i %= len(states)
        state = states[state_i]
        count = 1 if state == "ads" else art.count(name, state)
        frame_time = float(data["weapons"][name].get("frame_time", {}).get(state, 0.12))
        for event in pygame.event.get():
            if event.type == pygame.QUIT or event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    weapon_i = (weapon_i + (1 if event.key == pygame.K_RIGHT else -1)) % len(names)
                    state_i = frame_i = 0
                    elapsed = 0
                elif event.key in (pygame.K_UP, pygame.K_DOWN):
                    state_i += 1 if event.key == pygame.K_DOWN else -1
                    frame_i = 0
                    elapsed = 0
                elif event.key in (pygame.K_COMMA, pygame.K_PERIOD):
                    paused = True
                    frame_i = (frame_i + (1 if event.key == pygame.K_PERIOD else -1)) % count
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_a:
                    anchor_guide = not anchor_guide
                elif event.key == pygame.K_b:
                    brightness_i = (brightness_i + 1) % 3
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                    zoom = min(8, zoom + 1)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    zoom = max(1, zoom - 1)
        if not paused:
            elapsed += dt
            frame_i = int(elapsed / max(0.001, frame_time)) % count
        brightness = (32, 84, 160)[brightness_i]
        screen.fill((brightness, brightness, brightness))
        image, offset = ((art.ads(name), (0, 0)) if state == "ads"
                         else art.frame(name, state, frame_i))
        anchor = data["weapons"][name].get("ads_sight" if state == "ads" else "anchor",
                                            [image.get_width() // 2, image.get_height()])
        scaled = pygame.transform.scale(image, (image.get_width() * zoom, image.get_height() * zoom))
        target = (screen.get_width() // 2 - anchor[0] * zoom + offset[0] * zoom,
                  screen.get_height() // 2 - anchor[1] * zoom + offset[1] * zoom)
        screen.blit(scaled, target)
        if anchor_guide:
            pygame.draw.circle(screen, (255, 205, 65), (screen.get_width() // 2, screen.get_height() // 2), 6, 2)
        lines = [f"{name.upper()} / {state.upper()}  {frame_i + 1}/{count}   {frame_time:.3f}s/frame",
                 "Left/Right weapon  Up/Down animation  ,/. step  Space pause",
                 f"A anchor  B brightness ({brightness_i + 1}/3)  +/- zoom ({zoom}x)  Esc exit"]
        for index, line in enumerate(lines):
            label = font.render(line, True, (255, 244, 218))
            screen.blit(label, (16, 14 + 26 * index))
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "assets" / "weapons.json")
    parser.add_argument("--viewer", action="store_true", help="open the interactive window")
    parser.add_argument("--check", action="store_true", help="load all frames headlessly")
    args = parser.parse_args()
    if not args.viewer and not args.check:
        parser.error("choose --viewer or --check")
    viewer(args.manifest, args.check)
