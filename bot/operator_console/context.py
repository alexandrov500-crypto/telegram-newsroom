from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.operator_console.console import OperatorTelegramConsole

_console: OperatorTelegramConsole | None = None


def install_operator_console(console: OperatorTelegramConsole | None) -> None:
    global _console
    _console = console


def get_operator_console() -> OperatorTelegramConsole | None:
    return _console
