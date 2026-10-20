"""Resizable pygame window, aspect-safe viewport and UI scaling."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

import config


def compute_render_size(window_w: int, window_h: int) -> tuple[int, int]:
    """Keep internal height fixed while width follows a clamped window aspect."""
    # Use the actual positive aspect even below the logical minimum, so a
    # platform that permits a tiny window cannot stretch the scene.
    width = int(window_w) if window_w > 0 else config.MIN_WINDOW_SIZE[0]
    height = int(window_h) if window_h > 0 else config.MIN_WINDOW_SIZE[1]
    aspect = min(config.MAX_ASPECT, max(config.MIN_ASPECT, width / height))
    render_w = 2 * round(config.RENDER_HEIGHT * aspect / 2)
    return max(2, render_w), config.RENDER_HEIGHT


def compute_viewport(window_w: int, window_h: int) -> pygame.Rect:
    """Fill normal aspects; center bars only beyond the supported range."""
    width, height = max(1, window_w), max(1, window_h)
    aspect = width / height
    if aspect > config.MAX_ASPECT:
        view_w, view_h = min(width, round(height * config.MAX_ASPECT)), height
    elif aspect < config.MIN_ASPECT:
        view_w, view_h = width, min(height, round(width / config.MIN_ASPECT))
    else:
        view_w, view_h = width, height
    return pygame.Rect((width - view_w) // 2, (height - view_h) // 2, view_w, view_h)


def compute_ui_scale(window_h: int) -> float:
    """Scale UI from the actual window height, with usable small-screen limits."""
    return min(config.UI_SCALE_MAX,
               max(config.UI_SCALE_MIN, window_h / config.UI_REFERENCE_HEIGHT))


@dataclass(frozen=True)
class WindowMetrics:
    size: tuple[int, int]
    render_size: tuple[int, int]
    viewport: pygame.Rect
    aspect: float
    ui_scale: float


class WindowManager:
    """Own the display surface and coalesce native resize events per frame."""

    def __init__(self, start_maximized: bool = config.START_MAXIMIZED):
        self.screen = pygame.display.set_mode(config.WINDOW_DEFAULT_SIZE, pygame.RESIZABLE)
        self.windowed_size = config.WINDOW_DEFAULT_SIZE
        self.maximized = False
        self.fullscreen = False
        self.was_maximized_before_fullscreen = False
        self.minimized = False
        self.maximize_method = ""
        native = self._window_api()
        if native is not None:
            try:
                native.minimum_size = config.MIN_WINDOW_SIZE
            except (pygame.error, AttributeError, TypeError):
                pass
        if start_maximized:
            self._maximize()
        self.metrics = self._metrics()
        if config.START_FULLSCREEN:
            self.toggle_fullscreen()

    def _window_api(self):
        if hasattr(pygame, "Window") and hasattr(pygame.Window, "from_display_module"):
            return pygame.Window.from_display_module()
        return None

    def _maximize(self) -> None:
        window = self._window_api()
        if window is not None and hasattr(window, "maximize"):
            try:
                window.maximize()
                self.maximized = True
                self.maximize_method = "pygame.Window.from_display_module().maximize()"
                return
            except (pygame.error, AttributeError, TypeError):
                pass
        desktop = pygame.display.get_desktop_sizes()[0]
        fallback = (max(config.MIN_WINDOW_SIZE[0], desktop[0] - 80),
                    max(config.MIN_WINDOW_SIZE[1], desktop[1] - 80))
        self.screen = pygame.display.set_mode(fallback, pygame.RESIZABLE)
        self.maximize_method = "desktop size minus 80 pixels"

    def _metrics(self) -> WindowMetrics:
        size = tuple(map(int, pygame.display.get_window_size()))
        safe = (max(1, size[0]), max(1, size[1]))
        viewport = compute_viewport(*safe)
        return WindowMetrics(size, compute_render_size(*safe), viewport,
                             viewport.width / max(1, viewport.height),
                             compute_ui_scale(safe[1]))

    def handle_window_event(self, event: pygame.event.Event) -> None:
        """Record maximize/minimize state; size is read once after all events."""
        if event.type == getattr(pygame, "WINDOWMINIMIZED", -1):
            self.minimized = True
        elif event.type == getattr(pygame, "WINDOWMAXIMIZED", -1):
            self.minimized = False
            if not self.fullscreen:
                self.maximized = True
        elif event.type == getattr(pygame, "WINDOWRESTORED", -1):
            self.minimized = False
            if not self.fullscreen:
                self.maximized = False
        elif event.type in (getattr(pygame, "WINDOWSHOWN", -1),
                            getattr(pygame, "WINDOWSIZECHANGED", -1), pygame.VIDEORESIZE):
            self.minimized = False

    def sync(self) -> bool:
        """Return whether the final size changed since the previous frame."""
        current = self._metrics()
        if current.size == self.metrics.size:
            return False
        self.metrics = current
        surface = pygame.display.get_surface()
        if surface is None or surface.get_size() != current.size:
            if current.size[0] > 0 and current.size[1] > 0:
                flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
                self.screen = pygame.display.set_mode(current.size, flags)
        else:
            self.screen = surface
        if not self.fullscreen and not self.maximized:
            self.windowed_size = current.size
        return True

    def toggle_fullscreen(self) -> bool:
        """Switch to desktop fullscreen and restore prior window state afterward."""
        if self.fullscreen:
            self.fullscreen = False
            self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
            self.maximized = self.was_maximized_before_fullscreen
            if self.maximized:
                self._maximize()
        else:
            self.was_maximized_before_fullscreen = self.maximized
            if not self.maximized:
                self.windowed_size = self.metrics.size
            self.fullscreen = True
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.metrics = self._metrics()
        return self.fullscreen
