"""Build a labeled, non-destructive drawing template for weapon art."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
ASSETS = ROOT / "assets"
ORDER = {
    "pistol": (("idle", 1), ("fire", 3), ("reload", 6), ("switch", 3)),
    "shotgun": (("idle", 1), ("fire", 3), ("pump", 4), ("reload", 4), ("switch", 3)),
}
COLS = 8


def entries(value: dict | list[dict]) -> list[dict]:
    return value if isinstance(value, list) else [value]


def frame_size(weapon: dict) -> tuple[int, int]:
    sizes = Counter(tuple(entry["rect"][2:])
                    for value in weapon["frames"].values() for entry in entries(value))
    if not sizes:
        raise ValueError("Weapon has no frame rectangles")
    if len(sizes) != 1:
        raise ValueError(f"Mixed frame sizes in one weapon: {dict(sizes)}")
    return sizes.most_common(1)[0][0]


def build(out_dir: Path, source_manifest: Path, force: bool = False) -> dict:
    """Write template, blank export, overlay and companion JSON."""
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    for name in ORDER:
        if name not in source["weapons"]:
            raise ValueError(f"Missing required weapon: {name}")
    sizes = {name: frame_size(source["weapons"][name]) for name in ORDER}
    for name, size in sizes.items():
        print(f"{name}: existing frame rectangles {size[0]}x{size[1]} px")
    if len(set(sizes.values())) != 1:
        raise ValueError("Current pistol and shotgun sizes differ; use separate templates")
    cell_w, cell_h = sizes["pistol"]
    if cell_w < 48 or cell_h < 48:
        raise ValueError("Existing cells are too small for readable drawing guides")
    width, height = COLS * cell_w, 5 * cell_h
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = [out_dir / name for name in ("weapons_template.png", "weapons_template.json",
                                          "weapons_reference_overlay.png", "weapons_blank.png")]
    existing = [path for path in outputs if path.exists()]
    if existing and not force:
        raise FileExistsError("Template files already exist; use --force to back them up and rebuild")
    if existing:
        backup_dir = out_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        for path in existing:
            shutil.copy2(path, backup_dir / f"{path.stem}-{stamp}{path.suffix}")

    blank = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    template = Image.new("RGBA", (width, height), (14, 20, 27, 245))
    overlay = blank.copy()
    draw = ImageDraw.Draw(template)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 11)
    except OSError:
        font = ImageFont.load_default()
    reference_path = source_manifest.parent / source.get("fallback_manifest", "weapons_concept.json")
    legacy = json.loads(reference_path.read_text(encoding="utf-8"))
    legacy_sheet = Image.open(source_manifest.parent / legacy.get("fallback_image", "weapons_concept.png")).convert("RGBA")
    result = json.loads(json.dumps(source))
    result["image"] = "weapons.png"
    result["fallback_image"] = "weapons_concept.png"
    result["fallback_manifest"] = "weapons_concept.json"
    result["template_size"] = [width, height]
    result["template_cell_size"] = [cell_w, cell_h]

    for name, sequence in ORDER.items():
        weapon = result["weapons"][name]
        old_frames = legacy["weapons"][name]["frames"]
        base_row = 0 if name == "pistol" else 2
        slot = 0
        new_frames: dict[str, dict | list[dict]] = {}
        for state, count in sequence:
            state_entries = []
            old_entries = entries(old_frames.get(state, old_frames["idle"]))
            for index in range(count):
                col, row = slot % COLS, base_row + slot // COLS
                x, y = col * cell_w, row * cell_h
                rect = [x, y, cell_w, cell_h]
                state_entries.append({"rect": rect, "offset": [0, 0]})
                label = f"{name}/{state}/{index + 1}"
                draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), outline=(75, 119, 143, 255), width=1)
                draw.rectangle((x + 6, y + 14, x + cell_w - 7, y + cell_h - 7),
                               outline=(58, 83, 95, 255), width=1)
                draw.text((x + 3, y + 2), label, fill=(233, 235, 226, 255), font=font)
                draw.line((x + cell_w // 2, y + cell_h - 11,
                           x + cell_w // 2, y + cell_h - 2), fill=(255, 191, 72, 255), width=1)
                draw.line((x + cell_w // 2 - 4, y + cell_h - 6,
                           x + cell_w // 2 + 4, y + cell_h - 6), fill=(255, 191, 72, 255), width=1)
                old_rect = old_entries[min(index, len(old_entries) - 1)]["rect"]
                reference = legacy_sheet.crop((old_rect[0], old_rect[1], old_rect[0] + old_rect[2],
                                               old_rect[1] + old_rect[3]))
                reference = reference.resize((cell_w, cell_h), Image.Resampling.NEAREST)
                reference.putalpha(reference.getchannel("A").point(lambda alpha: alpha // 2))
                overlay.alpha_composite(reference, (x, y))
                slot += 1
            new_frames[state] = state_entries[0] if state == "idle" else state_entries
        weapon["frames"] = new_frames
        weapon["anchor"] = [cell_w // 2, cell_h]
        weapon["hip_sight"] = [17, 17] if name == "pistol" else [28, 13]
        weapon["hip_sight_drop"] = 12
        weapon["ads_sight"] = [cell_w // 2, 33 if name == "pistol" else 30]
        weapon["ads_scale"] = 1.1 if name == "pistol" else 1.5
        ads_x = (6 if name == "pistol" else 7) * cell_w
        weapon["ads"] = {"rect": [ads_x, cell_h * 4, cell_w, cell_h]}
        draw.rectangle((ads_x, cell_h * 4, ads_x + cell_w - 1, cell_h * 5 - 1),
                       outline=(75, 119, 143, 255), width=1)
        draw.rectangle((ads_x + 6, cell_h * 4 + 14, ads_x + cell_w - 7, cell_h * 5 - 7),
                       outline=(58, 83, 95, 255), width=1)
        draw.text((ads_x + 3, cell_h * 4 + 2), f"{name}/ads", fill=(233, 235, 226, 255), font=font)
        old_ads = legacy["weapons"][name].get("ads")
        if old_ads:
            ox, oy, ow, oh = old_ads["rect"]
            reference = legacy_sheet.crop((ox, oy, ox + ow, oy + oh))
            reference = reference.resize((cell_w, cell_h), Image.Resampling.NEAREST)
            reference.putalpha(reference.getchannel("A").point(lambda alpha: alpha // 2))
            overlay.alpha_composite(reference, (ads_x, cell_h * 4))
        weapon["muzzle_offset"] = [0, -(74 if name == "pistol" else 85)]
        weapon["frame_time"] = {
            "fire": round(float(weapon["muzzle_light"]["duration"]) / 3, 4),
            "reload": round(float(weapon["reload_time"]) / dict(sequence)["reload"], 4),
            "switch": round(float(weapon["switch_time"]) / 2 / 3, 4),
        }
        if name == "shotgun":
            shot_interval = 60 / float(weapon["rpm"])
            fire_window = min(shot_interval * config.WEAPON_FIRE_FRAME_FRACTION,
                              float(weapon["muzzle_light"]["duration"]))
            weapon["frame_time"]["pump"] = round((shot_interval - fire_window) / 4, 4)
        extra_y = cell_h * 4
        extra_start = 0 if name == "pistol" else 3
        icon_x = extra_start * cell_w + (cell_w - 32) // 2
        weapon["hud_icon"] = {"rect": [icon_x, extra_y + 48, 32, 16]}
        weapon["muzzle_flash"] = [
            {"rect": [(extra_start + 1) * cell_w + (cell_w - 32) // 2, extra_y + 36, 32, 32]},
            {"rect": [(extra_start + 2) * cell_w + (cell_w - 32) // 2, extra_y + 36, 32, 32]},
        ]
        for label, rect in ((f"{name}/icon", weapon["hud_icon"]["rect"]),
                            *((f"{name}/flash/{i + 1}", entry["rect"])
                              for i, entry in enumerate(weapon["muzzle_flash"]))):
            x, y, w, h = rect
            cell_x = (x // cell_w) * cell_w
            draw.rectangle((cell_x, extra_y, cell_x + cell_w - 1, extra_y + cell_h - 1),
                           outline=(75, 119, 143, 255), width=1)
            draw.rectangle((x, y, x + w - 1, y + h - 1), outline=(77, 182, 179, 255), width=1)
            draw.text((cell_x + 3, extra_y + 2), label, fill=(178, 224, 221, 255), font=font)
    blank.save(out_dir / "weapons_blank.png")
    template.save(out_dir / "weapons_template.png")
    overlay.save(out_dir / "weapons_reference_overlay.png")
    (out_dir / "weapons_template.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_dir} ({width}x{height}, {cell_w}x{cell_h} weapon cells)")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "art_templates")
    parser.add_argument("--source-manifest", type=Path, default=ASSETS / "weapons.json")
    parser.add_argument("--force", action="store_true", help="back up and rebuild existing template files")
    args = parser.parse_args()
    build(args.out_dir, args.source_manifest, args.force)
