from __future__ import annotations

import logging
from typing import Any

from bot_core.plugin_system import resolve_plugin_manager
from bot_core.services.utils.tg_parse import parse_commands_with_and

logger = logging.getLogger(__name__)


class CommandDispatcher:
    @staticmethod
    async def dispatch(update: Any, context: Any, chat_type: str) -> bool:
        message = getattr(update, "message", None)
        if not message:
            return False

        message_text = message.text or ""
        if not message_text.startswith("/"):
            return False

        commands = parse_commands_with_and(message_text)
        if not commands:
            return False

        handled = False
        for command_token, args in commands:
            command_name, target_username = CommandDispatcher._split_command_target(
                command_token
            )
            if target_username and not CommandDispatcher._matches_bot(
                context,
                target_username,
            ):
                logger.debug("Skipping command for other bot: %s", command_token)
                continue

            plugin_manager = resolve_plugin_manager(context)
            if not plugin_manager:
                logger.error("No plugin manager available for command: %s", command_name)
                return handled

            handler = plugin_manager.get_command_handler(command_name, chat_type)
            if not handler:
                continue

            context.args = args
            await handler(update, context)
            handled = True

        return handled

    @staticmethod
    def _split_command_target(command_token: str) -> tuple[str, str | None]:
        command_full = command_token.lstrip("/")
        command_name, separator, target_username = command_full.partition("@")
        if not separator:
            return command_name, None
        return command_name, target_username

    @staticmethod
    def _matches_bot(context: Any, target_username: str) -> bool:
        bot_username = getattr(getattr(context, "bot", None), "username", None)
        return bool(bot_username and bot_username == target_username)
