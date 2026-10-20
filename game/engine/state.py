"""Small app state machine for gameplay, quit confirmation and focus pause."""

from __future__ import annotations

from enum import Enum, auto


class GameState(Enum):
    PLAYING = auto()
    QUIT_CONFIRM = auto()


class StateMachine:
    def __init__(self) -> None:
        self.state = GameState.PLAYING
        self.focus_paused = False

    @property
    def paused(self) -> bool:
        return self.focus_paused or self.state == GameState.QUIT_CONFIRM

    def request_quit(self, confirm: bool = True) -> bool:
        """Open confirmation; return True only when immediate exit is configured."""
        if self.state == GameState.QUIT_CONFIRM:
            return False
        if not confirm:
            return True
        self.state = GameState.QUIT_CONFIRM
        return False

    def resume(self) -> bool:
        """Close an open dialog; return whether a transition happened."""
        if self.state != GameState.QUIT_CONFIRM:
            return False
        self.state = GameState.PLAYING
        return True

    def choose_quit(self) -> bool:
        """Only the dialog's Quit action can confirm termination."""
        return self.state == GameState.QUIT_CONFIRM
