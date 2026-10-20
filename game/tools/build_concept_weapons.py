"""Make the M0 drawing baseline from the approved concept sheet silhouettes."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CONCEPTS = ROOT / "art_concepts" / "weapon_pack_v1"


def cropped(path: Path, box: tuple[int, int, int, int]) -> Image.Image:
    image = Image.open(path).convert("RGBA").crop(box)
    alpha = image.getchannel("A")
    bounds = alpha.point(lambda a: 255 if a > 30 else 0).getbbox()
    if not bounds:
        raise ValueError(f"No visible art in {path}")
    return image.crop(bounds)


def build(force: bool = False) -> None:
    outputs = [ASSETS / name for name in ("weapons.png", "weapons.json", "weapons_concept.png",
                                          "weapons_concept.json")]
    existing = [path for path in outputs if path.exists()]
    if existing and not force:
        raise SystemExit("Refusing to replace weapon art; use --force to back up existing files")
    if existing:
        backup_dir = ASSETS / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        for path in existing:
            shutil.copy2(path, backup_dir / f"{path.stem}-{stamp}{path.suffix}")
    manifest = json.loads((ROOT / "art_templates" / "weapons_template.json").read_text(encoding="utf-8"))
    sheet = Image.new("RGBA", tuple(manifest["template_size"]))
    view_sources = {
        "pistol": cropped(ASSETS / "weapon_views" / "pistol_fps.png", (0, 0, 1536, 1024)),
        "shotgun": cropped(ASSETS / "weapon_views" / "rifle_fps.png", (0, 0, 1536, 1536)),
    }
    reload_sources = {
        "pistol": cropped(ASSETS / "weapon_views" / "pistol_reload.png", (0, 0, 1536, 1024)),
        "shotgun": cropped(ASSETS / "weapon_views" / "rifle_reload.png", (0, 0, 1536, 1536)),
    }
    finish_sources = {
        "pistol": cropped(ASSETS / "weapon_views" / "pistol_reload_finish.png", (0, 0, 1536, 1024)),
        "shotgun": cropped(ASSETS / "weapon_views" / "rifle_reload_finish.png", (0, 0, 1536, 1536)),
    }
    ads_sources = {
        "pistol": cropped(ASSETS / "weapon_views" / "pistol_ads.png", (0, 0, 1536, 1024)),
        "shotgun": cropped(ASSETS / "weapon_views" / "rifle_ads.png", (0, 0, 1536, 1536)),
    }
    icon_sources = {
        "pistol": cropped(CONCEPTS / "sidearms.png", (0, 0, 1024, 768)),
        "shotgun": cropped(CONCEPTS / "primary_secondary_and_rocket.png", (0, 0, 768, 360)),
    }
    for name, weapon in manifest["weapons"].items():
        source = view_sources[name]
        for state, value in weapon["frames"].items():
            entries = value if isinstance(value, list) else [value]
            for index, entry in enumerate(entries):
                x, y, w, h = entry["rect"]
                use_reload = state == "reload" and (index in (2, 3) if name == "pistol" else index == 1)
                use_finish = state == "reload" and (index == 4 if name == "pistol" else index == 2)
                use_action = name == "shotgun" and state == "pump" and index in (1, 2)
                frame_source = (reload_sources[name] if use_reload else
                                finish_sources[name] if use_finish or use_action else source)
                max_w, max_h = w - 8, h - 18
                ratio = min(max_w / frame_source.width, max_h / frame_source.height)
                image = frame_source.resize((max(1, round(frame_source.width * ratio)),
                                             max(1, round(frame_source.height * ratio))), Image.Resampling.LANCZOS)
                shift_y = ((-3, -10, -5)[index] if state == "fire" else
                           (0, 2, -2, 0)[index] if state == "pump" else
                           (4, 2, 0)[index] if state == "switch" else
                           (2 if index == 1 else 0) if state == "reload" and not (use_reload or use_finish) else
                           (-2 if use_reload and index % 2 else 0))
                shift_x = (-2 if use_reload and index % 2 else
                           -2 if state == "reload" and index == 1 and not use_reload else 0)
                cell = Image.new("RGBA", (w, h))
                cell.alpha_composite(image, ((w - image.width) // 2 + shift_x,
                                             h - image.height - 6 + shift_y))
                sheet.alpha_composite(cell, (x, y))
        ads_x, ads_y, ads_w, ads_h = weapon["ads"]["rect"]
        ads_source = ads_sources[name]
        ads_ratio = min((ads_w - 8) / ads_source.width, (ads_h - 8) / ads_source.height)
        ads_image = ads_source.resize((max(1, round(ads_source.width * ads_ratio)),
                                       max(1, round(ads_source.height * ads_ratio))), Image.Resampling.LANCZOS)
        sheet.alpha_composite(ads_image, (ads_x + (ads_w - ads_image.width) // 2,
                                          ads_y + ads_h - ads_image.height - 2))
        icon = weapon["hud_icon"]["rect"]
        x, y, w, h = icon
        icon_source = icon_sources[name]
        ratio = min((w - 2) / icon_source.width, (h - 2) / icon_source.height)
        thumb = icon_source.resize((max(1, round(icon_source.width * ratio)),
                                    max(1, round(icon_source.height * ratio))), Image.Resampling.LANCZOS)
        sheet.alpha_composite(thumb, (x + (w - thumb.width) // 2, y + (h - thumb.height) // 2))
        for flash in weapon["muzzle_flash"]:
            x, y, w, h = flash["rect"]
            layer = Image.new("RGBA", (w, h))
            draw = ImageDraw.Draw(layer)
            color = (255, 190, 80, 240) if name == "pistol" else (255, 138, 43, 240)
            draw.polygon([(2, h // 2), (w // 3, h // 3), (w // 2, 2),
                          (2 * w // 3, h // 3), (w - 3, h // 2),
                          (2 * w // 3, 2 * h // 3), (w // 2, h - 3),
                          (w // 3, 2 * h // 3)], fill=color)
            sheet.alpha_composite(layer, (x, y))
    sheet.save(ASSETS / "weapons.png")
    sheet.save(ASSETS / "weapons_concept.png")
    manifest["fallback_image"] = "weapons_concept.png"
    manifest["fallback_manifest"] = "weapons_concept.json"
    manifest.pop("placeholder_image", None)
    manifest["weapons"]["pistol"]["muzzle_offset"] = [-8, -88]
    manifest["weapons"]["shotgun"]["muzzle_offset"] = [-23, -85]
    (ASSETS / "weapons.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (ASSETS / "weapons_concept.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="back up and replace existing weapon files")
    build(parser.parse_args().force)
