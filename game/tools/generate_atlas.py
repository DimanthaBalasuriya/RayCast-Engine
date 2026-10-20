"""Generate deterministic, edge-tiling placeholder textures and an atlas viewer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SIZE = 64
COLUMNS = 8
SEED = 29841
TILES = [
    (1, "brick_red", "wall"), (2, "stone_gray", "wall"),
    (3, "metal_panel", "wall"), (4, "wood_planks", "wall"),
    (5, "mossy_stone", "wall"), (6, "tech_wall", "wall"),
    (7, "door_frame", "wall"), (8, "window_slit", "wall"),
    (20, "floor_stone", "floor"), (21, "floor_metal", "floor"),
    (22, "floor_wood", "floor"), (23, "floor_dirt", "floor"),
    (40, "ceiling_concrete", "ceiling"), (41, "ceiling_metal", "ceiling"),
    (42, "ceiling_wood", "ceiling"),
]


def make_tile(tile_id: int, rng: np.random.Generator) -> np.ndarray:
    """Use periodic motifs and wrapped noise so opposite edges meet cleanly."""
    y, x = np.mgrid[:SIZE, :SIZE]
    bases = {
        1: (124, 76, 67), 2: (119, 122, 121), 3: (105, 117, 125),
        4: (119, 91, 72), 5: (104, 117, 103), 6: (84, 107, 115),
        7: (112, 119, 124), 8: (106, 114, 119), 20: (126, 126, 120),
        21: (113, 121, 126), 22: (129, 105, 82), 23: (111, 100, 87),
        40: (118, 120, 119), 41: (112, 118, 122), 42: (115, 95, 79),
    }
    coarse = rng.integers(-12, 13, (8, 8)).repeat(8, 0).repeat(8, 1)
    fine = rng.integers(-8, 9, (SIZE, SIZE))
    noise = coarse + fine
    color = np.asarray(bases[tile_id])[None, None, :] + noise[:, :, None]
    color = np.broadcast_to(color, (SIZE, SIZE, 3)).copy().astype(np.int16)
    seam = np.zeros((SIZE, SIZE), dtype=bool)
    if tile_id in (1, 2, 5, 20, 40):
        step = 16 if tile_id == 1 else 32
        seam = (y % step == 0) | ((x + ((y // step) % 2) * (step // 2)) % step == 0)
        color[seam] -= 28
        if tile_id == 5:
            moss = (coarse > 5) & (fine > -1) & ~seam
            color[moss] += np.array([-23, 12, -17])
    elif tile_id in (4, 22, 42):
        vertical = tile_id == 4
        coord, other = (x, y) if vertical else (y, x)
        seam = coord % 16 == 0
        grain = np.sin(other * 0.65 + coord * 0.15) * 5
        color += grain[:, :, None].astype(np.int16)
        color[seam] -= 34
    elif tile_id in (3, 7, 8, 21, 41):
        seam = (x % 32 == 0) | (y % 32 == 0)
        color[seam] -= 24
        rivet = ((x % 32 - 4) ** 2 + (y % 32 - 4) ** 2) <= 3
        color[rivet] += 30
        if tile_id == 8:
            slit = (y >= 27) & (y <= 36) & (x >= 10) & (x <= 54)
            color[slit] = (25, 35, 40)
        if tile_id == 7:
            color[(x >= 27) & (x <= 36)] -= 23
        if tile_id == 21:
            color[(x + y) % 8 < 2] -= 18
    elif tile_id == 6:
        color[(x % 32 == 0) | (y % 32 == 0)] -= 30
        color[(x % 32 >= 12) & (x % 32 <= 15) & (y % 32 >= 8) & (y % 32 <= 25)] = (60, 169, 169)
        color[(x % 32 >= 22) & (x % 32 <= 24) & (y % 32 >= 8) & (y % 32 <= 25)] = (172, 112, 60)
    elif tile_id == 23:
        pebbles = (fine > 6) & (coarse > 2)
        color[pebbles] += 25
    # Give boundary pixels matching colors without sacrificing interior detail.
    color[-1] = color[0]
    color[:, -1] = color[:, 0]
    return np.clip(color, 0, 255).astype(np.uint8)


def generate() -> None:
    """Write the atlas and manifest beside the game source."""
    out = Path(__file__).resolve().parents[1] / "assets"
    out.mkdir(parents=True, exist_ok=True)
    rows = (len(TILES) + COLUMNS - 1) // COLUMNS
    image = np.zeros((rows * SIZE, COLUMNS * SIZE, 4), dtype=np.uint8)
    manifest: dict[str, object] = {
        "tile_size": SIZE, "columns": COLUMNS, "image": "atlas.png",
        "tiles": {}, "default_floor": 20, "default_ceiling": 40,
    }
    rng = np.random.default_rng(SEED)
    for index, (tile_id, name, category) in enumerate(TILES):
        col, row = index % COLUMNS, index // COLUMNS
        image[row * SIZE:(row + 1) * SIZE, col * SIZE:(col + 1) * SIZE, :3] = make_tile(tile_id, rng)
        image[row * SIZE:(row + 1) * SIZE, col * SIZE:(col + 1) * SIZE, 3] = 255
        manifest["tiles"][str(tile_id)] = {"name": name, "category": category, "col": col, "row": row}
    Image.fromarray(image, "RGBA").save(out / "atlas.png")
    (out / "atlas.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def viewer() -> None:
    """Write a labeled contact sheet for reviewing tile IDs."""
    out = Path(__file__).resolve().parents[1] / "assets"
    source = Image.open(out / "atlas.png").convert("RGB")
    canvas = Image.new("RGB", (COLUMNS * 120, 2 * 105), (23, 25, 30))
    draw = ImageDraw.Draw(canvas)
    for index, (tile_id, name, _) in enumerate(TILES):
        col, row = index % COLUMNS, index // COLUMNS
        tile = source.crop((col * SIZE, row * SIZE, (col + 1) * SIZE, (row + 1) * SIZE))
        canvas.paste(tile, (col * 120, row * 105))
        draw.text((col * 120 + 2, row * 105 + 66), f"{tile_id}: {name}", fill=(225, 225, 225), font=ImageFont.load_default())
    canvas.save(out / "atlas_viewer.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--viewer", action="store_true", help="also write a labeled contact sheet")
    args = parser.parse_args()
    generate()
    if args.viewer:
        viewer()
