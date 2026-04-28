from __future__ import annotations

import asyncio
from types import SimpleNamespace

from bot_core.message_handlers.command_dispatcher import CommandDispatcher


def _build_update(text: str):
    return SimpleNamespace(message=SimpleNamespace(text=text))


def _build_context(username: str = "testbot"):
    return SimpleNamespace(bot=SimpleNamespace(username=username), args=[])


def test_dispatcher_handles_multi_command_and_bot_mentions(monkeypatch):
    calls: list[tuple[str, list[str], str]] = []

    async def ping_handler(update, context):
        calls.append(("ping", list(context.args), update.message.text))

    async def echo_handler(update, context):
        calls.append(("echo", list(context.args), update.message.text))

    handlers = {
        ("ping", "private"): ping_handler,
        ("echo", "private"): echo_handler,
    }

    monkeypatch.setattr(
        "bot_core.message_handlers.command_dispatcher.CommandHandlers.get_command_handler",
        lambda command, chat_type: handlers.get((command, chat_type)),
    )

    handled = asyncio.run(
        CommandDispatcher.dispatch(
            _build_update("/ping one two && /echo@testbot hello && /echo@otherbot skip"),
            _build_context(),
            "private",
        )
    )

    assert handled is True
    assert calls == [
        ("ping", ["one", "two"], "/ping one two && /echo@testbot hello && /echo@otherbot skip"),
        ("echo", ["hello"], "/ping one two && /echo@testbot hello && /echo@otherbot skip"),
    ]


def test_dispatcher_returns_false_when_no_matching_handler(monkeypatch):
    monkeypatch.setattr(
        "bot_core.message_handlers.command_dispatcher.CommandHandlers.get_command_handler",
        lambda command, chat_type: None,
    )

    handled = asyncio.run(
        CommandDispatcher.dispatch(
            _build_update("/unknown value"),
            _build_context(),
            "group",
        )
    )

    assert handled is False
