"""Validate the weapon atlas and report empty, cropped or jumping frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
COUNTS = {"pistol": {"idle": 1, "fire": 3, "reload": 6, "switch": 3},
          "shotgun": {"idle": 1, "fire": 3, "pump": 4, "reload": 4, "switch": 3}}


def check(manifest_path: Path, image_path: Path | None = None, layout_only: bool = False) -> int:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_path = image_path or manifest_path.parent / data["image"]
    image = Image.open(image_path)
    errors: list[str] = []
    warnings: list[str] = []
    if image.mode != "RGBA":
        errors.append(f"PNG must be RGBA, got {image.mode}")
    expected = tuple(data.get("template_cell_size", [96, 96]))

    def rect(label: str, entry: dict, size: tuple[int, int] | None = None) -> Image.Image | None:
        try:
            x, y, w, h = map(int, entry["rect"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{label}: invalid rectangle")
            return None
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > image.width or y + h > image.height:
            errors.append(f"{label}: rectangle outside PNG")
            return None
        if size and (w, h) != size:
            errors.append(f"{label}: size {w}x{h}, expected {size[0]}x{size[1]}")
        crop = image.crop((x, y, x + w, y + h)).convert("RGBA")
        if not layout_only:
            alpha = crop.getchannel("A")
            if not alpha.getbbox():
                errors.append(f"{label}: empty frame")
            elif (alpha.crop((0, 0, w, 1)).getbbox() or alpha.crop((0, h - 1, w, h)).getbbox()
                  or alpha.crop((0, 0, 1, h)).getbbox() or alpha.crop((w - 1, 0, w, h)).getbbox()):
                warnings.append(f"{label}: opaque pixels touch cell edge")
        return crop

    print("weapon    state     frames   result")
    print("--------- --------- -------- ------")
    for name, states in COUNTS.items():
        weapon = data.get("weapons", {}).get(name)
        if weapon is None:
            errors.append(f"{name}: missing weapon")
            continue
        boxes: list[tuple[float, float]] = []
        for state, count in states.items():
            value = weapon.get("frames", {}).get(state, [])
            entries = value if isinstance(value, list) else [value]
            start_errors = len(errors)
            if len(entries) != count:
                errors.append(f"{name}/{state}: {len(entries)} frames, expected {count}")
            for index, entry in enumerate(entries):
                crop = rect(f"{name}/{state}/{index + 1}", entry, expected)
                if crop is not None and crop.getchannel("A").getbbox():
                    box = crop.getchannel("A").getbbox()
                    assert box is not None
                    boxes.append(((box[0] + box[2]) / 2, box[3]))
            print(f"{name:9} {state:9} {len(entries):>3}/{count:<4} {'PASS' if len(errors) == start_errors else 'FAIL'}")
        if boxes and not layout_only:
            midpoint_x = sorted(point[0] for point in boxes)[len(boxes) // 2]
            bottom_y = sorted(point[1] for point in boxes)[len(boxes) // 2]
            for index, point in enumerate(boxes):
                if abs(point[0] - midpoint_x) > expected[0] * 0.2 or abs(point[1] - bottom_y) > expected[1] * 0.2:
                    warnings.append(f"{name}: frame {index + 1} bounding box jumps from anchor")
        rect(f"{name}/hud_icon", weapon.get("hud_icon", {}), (32, 16))
        flashes = weapon.get("muzzle_flash", [])
        if len(flashes) < 2 or len(flashes) > 3:
            errors.append(f"{name}: need 2 or 3 muzzle flashes")
        for index, entry in enumerate(flashes):
            rect(f"{name}/muzzle_flash/{index + 1}", entry, (32, 32))
        if weapon.get("ads"):
            rect(f"{name}/ads", weapon["ads"], expected)
        if weapon.get("pickup_sprite"):
            rect(f"{name}/pickup_sprite", weapon["pickup_sprite"], (32, 32))
    for message in errors:
        print("ERROR:", message)
    for message in sorted(set(warnings)):
        print("WARN: ", message)
    print(f"RESULT: {'FAIL' if errors else 'PASS'} ({len(errors)} errors, {len(set(warnings))} warnings)")
    return int(bool(errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "assets" / "weapons.json")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--layout-only", action="store_true", help="check blank template layout before painting")
    args = parser.parse_args()
    raise SystemExit(check(args.manifest, args.image, args.layout_only))
