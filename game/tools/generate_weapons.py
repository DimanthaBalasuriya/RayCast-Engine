"""Generate deterministic placeholder viewmodel frames and weapon definitions."""

from __future__ import annotations

import json
from pathlib import Path
import random

from PIL import Image, ImageDraw

SEED = 81991
FRAME = 96
OUT = Path(__file__).resolve().parents[1] / "assets"


def draw_frame(draw: ImageDraw.ImageDraw, ox: int, oy: int, shotgun: bool,
               pose: str, rng: random.Random) -> None:
    """Draw chunky first-person hands, grip and barrel into one frame."""
    shift = {"idle": 0, "fire1": -7, "fire2": -3, "reload1": 17,
             "reload2": 10, "switch": 30, "pump": 8}[pose]
    metal = (58, 67, 75, 255)
    edge = (111, 126, 132, 255)
    dark = (30, 34, 39, 255)
    wood = (112, 76, 55, 255)
    skin = (164, 120, 91, 255)
    outline = (27, 24, 25, 255)
    left, right = (25, 72) if shotgun else (34, 64)
    barrel_top = 11 if shotgun else 22
    draw.rectangle((ox + left, oy + barrel_top + shift, ox + right, oy + 68 + shift), fill=outline)
    draw.rectangle((ox + left + 3, oy + barrel_top + 3 + shift, ox + right - 3, oy + 65 + shift), fill=metal)
    draw.rectangle((ox + left + 5, oy + barrel_top + 4 + shift, ox + left + 8, oy + 54 + shift), fill=edge)
    draw.rectangle((ox + left + 7, oy + 53 + shift, ox + right - 7, oy + 68 + shift), fill=wood)
    draw.rectangle((ox + left + 12, oy + 15 + shift, ox + right - 12, oy + 23 + shift), fill=dark)
    draw.rectangle((ox + 39, oy + 62 + shift, ox + 56, oy + 94), fill=skin)
    draw.rectangle((ox + 31, oy + 74, ox + 44, oy + 94), fill=skin)
    draw.rectangle((ox + 57, oy + 77, ox + 69, oy + 94), fill=skin)
    draw.rectangle((ox + 30, oy + 89, ox + 70, oy + 95), fill=outline)
    if pose.startswith("fire"):
        draw.polygon([(ox + 48, oy + barrel_top + shift - 14),
                      (ox + 42, oy + barrel_top + shift + 2),
                      (ox + 48, oy + barrel_top + shift - 3),
                      (ox + 56, oy + barrel_top + shift + 1)], fill=(255, 198, 85, 230))
    for _ in range(6):
        px = rng.randrange(left + 5, right - 4)
        py = rng.randrange(barrel_top + 25, 53)
        draw.point((ox + px, oy + py + shift), fill=(85, 91, 94, 255))


def generate() -> None:
    """Write the sprite sheet and manifest with fixed frame ordering."""
    OUT.mkdir(exist_ok=True)
    poses = ("idle", "fire1", "fire2", "reload1", "reload2", "switch", "pump")
    image = Image.new("RGBA", (FRAME * len(poses), FRAME * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rng = random.Random(SEED)
    for row, shotgun in enumerate((False, True)):
        for col, pose in enumerate(poses):
            draw_frame(draw, col * FRAME, row * FRAME, shotgun, pose, rng)
    image.save(OUT / "weapons.png")

    def frames(row: int) -> dict:
        def rect(col: int) -> dict:
            return {"rect": [col * FRAME, row * FRAME, FRAME, FRAME]}
        return {"idle": rect(0), "fire": [rect(1), rect(2)],
                "reload": [rect(3), rect(4)], "switch": [rect(5)], "pump": [rect(6)]}

    data = {
        "image": "weapons.png",
        "weapons": {
            "pistol": {"slot": 1, "fire_mode": "semi", "rpm": 300, "damage": 20,
                       "pellets": 1, "spread_deg": 0.6, "range": 40.0,
                       "mag_size": 12, "start_reserve": 60, "reload_time": 1.1,
                       "switch_time": 0.35, "recoil": {"viewmodel": 0.8, "pitch_deg": 0.8, "fov": 1.0},
                       "muzzle_light": {"color": [1.0, 0.8, 0.5], "intensity": 2.0,
                                        "radius": 5.0, "duration": 0.06}, "frames": frames(0)},
            "shotgun": {"slot": 2, "fire_mode": "pump", "rpm": 70, "damage": 10,
                        "pellets": 8, "spread_deg": 5.0, "range": 25.0,
                        "mag_size": 6, "start_reserve": 30, "reload_time": 1.9,
                        "switch_time": 0.5, "recoil": {"viewmodel": 1.5, "pitch_deg": 2.0, "fov": 2.0},
                        "muzzle_light": {"color": [1.0, 0.72, 0.39], "intensity": 3.4,
                                         "radius": 6.5, "duration": 0.08}, "frames": frames(1)}
        }
    }
    (OUT / "weapons.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    generate()
