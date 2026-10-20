"""Reusable keyboard and mouse confirmation dialog geometry and focus."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import pygame


class DialogResult(Enum):
    NONE = auto()
    RESUME = auto()
    QUIT = auto()


@dataclass(frozen=True)
class DialogButton:
    label: str
    result: DialogResult


class ConfirmDialog:
    def __init__(self, title: str = "Quit game?", text: str = "",
                 buttons: tuple[DialogButton, ...] | None = None):
        self.title = title
        self.text = text
        self.buttons = buttons or (DialogButton("Resume", DialogResult.RESUME),
                                   DialogButton("Quit", DialogResult.QUIT))
        self.focus = 0  # Resume is deliberately safe by default.
        self.hover = -1

    def reset(self) -> None:
        self.focus = 0
        self.hover = -1

    def navigate(self, direction: int) -> None:
        self.focus = (self.focus + direction) % len(self.buttons)

    def handle_key(self, key: str, shift: bool = False) -> DialogResult:
        """Use named keys so navigation can be tested without a display."""
        if key in ("left", "right", "tab"):
            self.navigate(-1 if key == "left" or (key == "tab" and shift) else 1)
            return DialogResult.NONE
        if key in ("enter", "space"):
            return self.buttons[self.focus].result
        if key in ("escape", "n"):
            return DialogResult.RESUME
        if key == "y":
            return DialogResult.QUIT
        return DialogResult.NONE

    def layout(self, size: tuple[int, int], ui_scale: float) -> tuple[pygame.Rect, list[pygame.Rect]]:
        """Return a centered panel and equally spaced button rectangles."""
        width, height = size
        panel_w = min(width - 24, max(round(width * 0.30), round(390 * ui_scale)))
        panel_h = min(height - 24, round((210 if self.text else 180) * ui_scale))
        panel = pygame.Rect((width - panel_w) // 2, (height - panel_h) // 2, panel_w, panel_h)
        gap = max(8, round(14 * ui_scale))
        margin = max(14, round(28 * ui_scale))
        button_w = max(1, (panel_w - margin * 2 - gap * (len(self.buttons) - 1)) // len(self.buttons))
        button_h = max(1, round(48 * ui_scale))
        button_y = panel.bottom - margin - button_h
        rects = [pygame.Rect(panel.left + margin + index * (button_w + gap),
                             button_y, button_w, button_h)
                 for index in range(len(self.buttons))]
        return panel, rects

    def mouse_move(self, pos: tuple[int, int], size: tuple[int, int], ui_scale: float) -> None:
        _, buttons = self.layout(size, ui_scale)
        self.hover = next((index for index, rect in enumerate(buttons) if rect.collidepoint(pos)), -1)

    def click(self, pos: tuple[int, int], size: tuple[int, int], ui_scale: float) -> DialogResult:
        _, buttons = self.layout(size, ui_scale)
        for index, rect in enumerate(buttons):
            if rect.collidepoint(pos):
                self.focus = index
                return self.buttons[index].result
        return DialogResult.NONE
