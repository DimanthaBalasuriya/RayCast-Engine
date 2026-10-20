"""Data-driven weapon magazine and timing state machine."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import config
from engine.events import Events


@dataclass
class WeaponState:
    name: str
    definition: dict
    magazine: int
    reserve: int


class Weapons:
    def __init__(self, manifest: Path, events: Events):
        self.manifest = manifest
        data = json.loads(manifest.read_text(encoding="utf-8"))
        fallback_path = manifest.parent / data.get("fallback_manifest", "weapons_concept.json")
        fallback = json.loads(fallback_path.read_text(encoding="utf-8"))["weapons"]
        data["weapons"] = {**fallback, **data.get("weapons", {})}
        self.image_path = manifest.parent / data["image"]
        self.items = {name: WeaponState(name, definition, int(definition["mag_size"]),
                                        int(definition["start_reserve"]))
                      for name, definition in data["weapons"].items()}
        self.slots = {int(item.definition["slot"]): name for name, item in self.items.items()}
        self.current_name = self.slots[min(self.slots)]
        self.last_name = self.current_name
        self.state = "READY"
        self.timer = 0.0
        self.cooldown = 0.0
        self.recoil = 0.0
        self.spread_stack = 0.0
        self.events = events
        self.pending_name: str | None = None
        self.flash_left = 0.0

    @property
    def current(self) -> WeaponState:
        return self.items[self.current_name]

    def switch(self, name: str) -> None:
        """Lower the current weapon before raising the selected one."""
        if name not in self.items or name == self.current_name or self.state.startswith("SWITCHING"):
            return
        self.pending_name = name
        self.state = "SWITCHING_OUT"
        self.timer = float(self.current.definition["switch_time"]) * 0.5

    def switch_slot(self, slot: int) -> None:
        if slot in self.slots:
            self.switch(self.slots[slot])

    def cycle(self, direction: int) -> None:
        ordered = [self.slots[key] for key in sorted(self.slots)]
        self.switch(ordered[(ordered.index(self.current_name) + direction) % len(ordered)])

    def reload(self) -> bool:
        """Start a full-magazine reload if ammunition is available."""
        item = self.current
        if self.state in ("RELOADING", "SWITCHING_OUT", "SWITCHING_IN"):
            return False
        if item.magazine >= item.definition["mag_size"] or item.reserve <= 0:
            return False
        self.state = "RELOADING"
        self.timer = float(item.definition["reload_time"])
        self.events.emit("weapon_reload_start", weapon=item.name)
        return True

    def refill(self) -> None:
        for item in self.items.values():
            item.magazine = int(item.definition["mag_size"])
            item.reserve = int(item.definition["start_reserve"])
        self.state, self.timer = "READY", 0.0
        self.cooldown = self.flash_left = self.recoil = self.spread_stack = 0.0
        self.pending_name = None

    def update(self, dt: float, pressed: bool = False, held: bool = False,
               position: tuple[float, float] | None = None) -> bool:
        """Advance timers and return True exactly when a shot is fired."""
        dt = min(dt, config.MAX_DT)
        self.timer = max(0.0, self.timer - dt)
        self.cooldown = max(0.0, self.cooldown - dt)
        self.flash_left = max(0.0, self.flash_left - dt)
        self.recoil *= max(0.0, 1 - config.RECOIL_RECOVERY * dt)
        self.spread_stack = max(0.0, self.spread_stack - config.SPREAD_RECOVERY * dt)
        if self.timer == 0:
            if self.state == "RELOADING":
                item = self.current
                count = min(item.reserve, item.definition["mag_size"] - item.magazine)
                item.magazine += count
                item.reserve -= count
                self.events.emit("weapon_reload_end", weapon=item.name)
                self.state = "READY"
            elif self.state == "SWITCHING_OUT":
                old = self.current_name
                self.last_name = old
                self.current_name = self.pending_name or old
                self.pending_name = None
                self.events.emit("weapon_switch", **{"from": old, "to": self.current_name})
                self.state = "SWITCHING_IN"
                self.timer = float(self.current.definition["switch_time"]) * 0.5
            elif self.state == "FIRING":
                self.state = "COOLDOWN" if self.cooldown > 0 else "READY"
                self.timer = self.cooldown
            elif self.state in ("SWITCHING_IN", "COOLDOWN"):
                self.state = "READY"
        item = self.current
        wants_fire = held if item.definition["fire_mode"] == "auto" else pressed
        if not wants_fire or self.state != "READY" or self.cooldown > 0:
            return False
        if item.magazine <= 0:
            self.events.emit("weapon_dry_fire", weapon=item.name)
            self.reload()
            return False
        item.magazine -= 1
        self.cooldown = 60.0 / float(item.definition["rpm"])
        self.state = "FIRING"
        self.timer = min(self.cooldown * config.WEAPON_FIRE_FRAME_FRACTION,
                         float(item.definition["muzzle_light"]["duration"]))
        self.flash_left = float(item.definition["muzzle_light"]["duration"])
        self.recoil += float(item.definition["recoil"]["viewmodel"])
        self.spread_stack = min(config.MAX_SPREAD_STACK, self.spread_stack + config.SPREAD_BUILDUP)
        self.events.emit("weapon_fire", weapon=item.name, position=position)
        return True
