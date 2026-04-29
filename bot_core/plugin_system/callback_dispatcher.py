from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from bot_core.plugin_system.manager import PluginManager, resolve_plugin_manager
from bot_core.services.utils.error import BotError

logger = logging.getLogger(__name__)


class CallbackHandler:
    def __init__(self, plugin_manager: PluginManager | None = None) -> None:
        self.plugin_manager = plugin_manager

    async def handle_callback_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if not query:
            return

        await query.answer()
        data = query.data or ""
        user_id = query.from_user.id if query.from_user else 0
        manager = self.plugin_manager or resolve_plugin_manager(context)
        if not manager:
            logger.error("No plugin manager available for callback data: %s", data)
            return

        try:
            for registration in manager.iter_callbacks():
                prefix = registration.meta.trigger
                if data.startswith(prefix):
                    logger.debug("Matched callback handler %s for %s", prefix, data)
                    await registration.handler(update, context, data[len(prefix):])
                    return

            logger.warning("Unknown callback data %s from user %s", data, user_id)
            if query.message:
                await query.message.reply_text("未知的回调操作。")
        except Exception as error:
            logger.error(
                "Failed to handle callback, user_id=%s, data=%s: %s",
                user_id,
                data,
                error,
                exc_info=True,
            )
            raise BotError(f"处理回调 {data} 失败: {error}")


def create_callback_handler(plugin_manager: PluginManager | None = None) -> CallbackHandler:
    return CallbackHandler(plugin_manager)
