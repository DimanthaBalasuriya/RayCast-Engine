"""Window-resolution HUD and modal dialog with scaled, anchored layout."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

import config
from engine.character_art import CharacterArt
from engine.dialog import ConfirmDialog
from engine.events import Events
from engine.player import Player
from engine.weapons import Weapons
from engine.weapon_art import WeaponArt


@dataclass(frozen=True)
class HUDLayout:
    center: tuple[int, int]
    health_pos: tuple[int, int]
    health_bar: pygame.Rect
    ammo_right: int
    ammo_y: int
    crosshair_gap: int
    crosshair_length: int
    avatar_rect: pygame.Rect


def layout_for_window(size: tuple[int, int], ui_scale: float,
                      spread: float, viewport: pygame.Rect | None = None) -> HUDLayout:
    """Compute edge and centre anchors from current window metrics."""
    width, height = size
    margin = round(24 * ui_scale)
    view = viewport or pygame.Rect(0, 0, width, height)
    bar_w, bar_h = round(180 * ui_scale), max(2, round(7 * ui_scale))
    avatar = pygame.Rect(margin, height - margin - round(112 * ui_scale),
                         round(96 * ui_scale), round(112 * ui_scale))
    health_x = avatar.right + round(12 * ui_scale)
    return HUDLayout(view.center, (health_x, height - round(47 * ui_scale)),
                     pygame.Rect(health_x, height - round(17 * ui_scale), bar_w, bar_h),
                     width - margin, height - round(45 * ui_scale),
                     round((5 + min(25, spread * 2)) * ui_scale),
                     max(2, round(9 * ui_scale)), avatar)


class HUD:
    def __init__(self, events: Events, avatar_art: CharacterArt | None = None,
                 weapon_art: WeaponArt | None = None):
        self.font: pygame.font.Font | None = None
        self.large: pygame.font.Font | None = None
        self._font_step = -1
        self.damage_alpha = 0.0
        self.muzzle_alpha = 0.0
        self._dim: pygame.Surface | None = None
        self.avatar_art = avatar_art
        self.weapon_art = weapon_art
        self.avatar_state = "idle"
        self.avatar_time = 0.0
        events.subscribe("hurt", self.on_hurt)
        events.subscribe("weapon_fire", self.on_fire)

    def _fonts(self, ui_scale: float) -> None:
        step = round(ui_scale * 20)
        if step == self._font_step:
            return
        self._font_step = step
        scale = step / 20
        self.font = pygame.font.SysFont("consolas", max(12, round(24 * scale)), bold=True)
        self.large = pygame.font.SysFont("consolas", max(20, round(38 * scale)), bold=True)

    def on_hurt(self, amount: int, health: int, source: object = None) -> None:
        self.damage_alpha = min(145, self.damage_alpha + amount * 5)

    def on_fire(self, weapon: str, position: tuple[float, float] | None = None) -> None:
        self.muzzle_alpha = 20

    def draw(self, screen: pygame.Surface, player: Player, weapons: Weapons,
             spread: float, dt: float, ui_scale: float = 1.0,
             viewport: pygame.Rect | None = None) -> None:
        """Draw the normal HUD after the internal scene has been upscaled."""
        self.damage_alpha = max(0, self.damage_alpha - config.HUD_DAMAGE_FADE * 60 * dt)
        self.muzzle_alpha = max(0, self.muzzle_alpha - config.HUD_MUZZLE_FADE * 60 * dt)
        if not config.SHOW_HUD:
            return
        self._fonts(ui_scale)
        assert self.font is not None and self.large is not None
        width, height = screen.get_size()
        layout = layout_for_window((width, height), ui_scale, spread, viewport)
        if self.avatar_art is not None:
            speed = (player.vx * player.vx + player.vy * player.vy) ** 0.5
            if weapons.state == "FIRING" or weapons.flash_left > 0:
                avatar_state = "fight"
            elif player.crouching:
                avatar_state = "cover"
            elif speed > config.WALK_SPEED + 0.3:
                avatar_state = "run"
            elif speed > 0.25:
                avatar_state = "walk"
            else:
                avatar_state = "idle"
            if avatar_state != self.avatar_state:
                self.avatar_state = avatar_state
                self.avatar_time = 0.0
            else:
                self.avatar_time += dt
            avatar = self.avatar_art.frame(self.avatar_state, self.avatar_time)
            scale = min(layout.avatar_rect.width / avatar.get_width(),
                        layout.avatar_rect.height / avatar.get_height())
            image = pygame.transform.scale(avatar,
                                           (max(1, round(avatar.get_width() * scale)),
                                            max(1, round(avatar.get_height() * scale))))
            screen.blit(image, (layout.avatar_rect.centerx - image.get_width() // 2,
                                layout.avatar_rect.bottom - image.get_height()))
            label = self.font.render(player.character_id.upper() if player.alive else "DOWN", True,
                                     (143, 218, 244) if player.alive else (240, 120, 105))
            screen.blit(label, (layout.avatar_rect.centerx - label.get_width() // 2,
                                layout.avatar_rect.top - label.get_height()))
        if self.muzzle_alpha:
            wash = pygame.Surface((width, height), pygame.SRCALPHA)
            wash.fill((255, 187, 83, int(self.muzzle_alpha)))
            screen.blit(wash, (0, 0))
        if self.damage_alpha:
            edge = pygame.Surface((width, height), pygame.SRCALPHA)
            alpha = int(self.damage_alpha)
            thick = max(20, round(min(width, height) * ui_scale / 12))
            pygame.draw.rect(edge, (180, 5, 8, alpha), (0, 0, width, thick))
            pygame.draw.rect(edge, (180, 5, 8, alpha), (0, height - thick, width, thick))
            pygame.draw.rect(edge, (180, 5, 8, alpha), (0, 0, thick, height))
            pygame.draw.rect(edge, (180, 5, 8, alpha), (width - thick, 0, thick, height))
            screen.blit(edge, (0, 0))
        if config.SHOW_CROSSHAIR and player.alive:
            cx, cy = layout.center
            gap, arm = layout.crosshair_gap, layout.crosshair_length
            color = (235, 237, 230)
            for start, end in (((cx - gap - arm, cy), (cx - gap, cy)),
                               ((cx + gap, cy), (cx + gap + arm, cy)),
                               ((cx, cy - gap - arm), (cx, cy - gap)),
                               ((cx, cy + gap), (cx, cy + gap + arm))):
                pygame.draw.line(screen, color, start, end, max(1, round(2 * ui_scale)))
        item = weapons.current
        ammo_color = (235, 76, 71) if item.magazine <= max(2, item.definition["mag_size"] // 4) else (237, 235, 222)
        ammo = f"{item.name.upper()}  {item.magazine} / {item.reserve}"
        if item.magazine == 0:
            ammo += "  RELOAD"
        ammo_image = self.font.render(ammo, True, ammo_color)
        screen.blit(ammo_image, (layout.ammo_right - ammo_image.get_width(), layout.ammo_y))
        if self.weapon_art is not None:
            icon = self.weapon_art.icon(item.name)
            icon_size = (round(32 * ui_scale), round(16 * ui_scale))
            icon = pygame.transform.scale(icon, icon_size)
            screen.blit(icon, (layout.ammo_right - ammo_image.get_width() - icon_size[0] - round(8 * ui_scale),
                               layout.ammo_y + (ammo_image.get_height() - icon_size[1]) // 2))
        health_image = self.font.render(f"HEALTH {player.health}", True, (237, 235, 222))
        screen.blit(health_image, layout.health_pos)
        pygame.draw.rect(screen, (50, 43, 45), layout.health_bar)
        filled = layout.health_bar.copy()
        filled.width = int(filled.width * player.health / player.max_health)
        pygame.draw.rect(screen, (196, 60, 55), filled)
        if not player.alive:
            message = self.large.render("YOU DIED — press Enter to respawn", True, (240, 120, 105))
            screen.blit(message, ((width - message.get_width()) // 2,
                                  height // 2 - round(70 * ui_scale)))

    def draw_dialog(self, screen: pygame.Surface, dialog: ConfirmDialog,
                    ui_scale: float) -> None:
        """Dim the frozen frame and draw a centered, accessible modal panel."""
        self._fonts(ui_scale)
        assert self.font is not None and self.large is not None
        size = screen.get_size()
        if self._dim is None or self._dim.get_size() != size:
            self._dim = pygame.Surface(size, pygame.SRCALPHA)
            self._dim.fill((0, 0, 0, 155))
        screen.blit(self._dim, (0, 0))
        panel, buttons = dialog.layout(size, ui_scale)
        pygame.draw.rect(screen, (21, 25, 30), panel, border_radius=max(2, round(8 * ui_scale)))
        pygame.draw.rect(screen, (147, 158, 166), panel,
                         max(1, round(2 * ui_scale)), border_radius=max(2, round(8 * ui_scale)))
        title = self.large.render(dialog.title, True, (241, 239, 229))
        screen.blit(title, (panel.centerx - title.get_width() // 2,
                            panel.top + round(25 * ui_scale)))
        if dialog.text:
            subtitle = self.font.render(dialog.text, True, (186, 192, 198))
            screen.blit(subtitle, (panel.centerx - subtitle.get_width() // 2,
                                   panel.top + round(75 * ui_scale)))
        for index, (button, rect) in enumerate(zip(dialog.buttons, buttons)):
            hovered = index == dialog.hover
            focused = index == dialog.focus
            fill = (75, 91, 100) if hovered else (48, 57, 64)
            pygame.draw.rect(screen, fill, rect, border_radius=max(2, round(5 * ui_scale)))
            border = (249, 207, 118) if focused else (126, 147, 156)
            pygame.draw.rect(screen, border, rect,
                             max(1, round((3 if focused else 1) * ui_scale)),
                             border_radius=max(2, round(5 * ui_scale)))
            label = self.font.render(button.label, True, (245, 245, 236))
            screen.blit(label, (rect.centerx - label.get_width() // 2,
                                rect.centery - label.get_height() // 2))
            if focused:
                pygame.draw.circle(screen, (249, 207, 118),
                                   (rect.left + round(9 * ui_scale), rect.centery),
                                   max(2, round(3 * ui_scale)))
