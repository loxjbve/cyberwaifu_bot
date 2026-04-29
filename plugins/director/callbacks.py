import logging
import time

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import bot_core.services.messages
from bot_core.callback_handlers.base import BaseCallback, CallbackMeta
from plugins.director.menu import DirectorMenu
from bot_core.services.conversation import PrivateConv

logger = logging.getLogger(__name__)


class DirectorCallback(BaseCallback):
    meta = CallbackMeta(
        name="director",
        callback_type="private",
        trigger="director_",
        enabled=True,
    )

    def __init__(self):
        super().__init__()
        self.menu_manager = DirectorMenu()

    async def handle_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        data: str = "",
    ) -> None:
        query = update.callback_query
        if query:
            await query.answer()
        user_id = update.effective_user.id if update.effective_user else 0

        if data is None or data == "":
            await self._send_menu(
                context,
                user_id,
                self.menu_manager.get_main_menu_id(),
                query=query,
            )
            return

        if data.startswith("nav_"):
            await self._send_menu(context, user_id, data.replace("nav_", ""), query=query)
            return

        if data.startswith("act_"):
            started_at = time.time()
            action_data = data.replace("act_", "")
            await self._handle_action(action_data, context, user_id, query, update)
            logger.debug("Director action %s took %.3fs", data, time.time() - started_at)
            return

        logger.warning("Unknown director callback data: %s, user_id: %s", data, user_id)
        await bot_core.services.messages.send_message(
            context,
            user_id,
            "未知的操作，请返回主菜单。",
        )
        await self._send_menu(
            context,
            user_id,
            self.menu_manager.get_main_menu_id(),
            query=query,
        )

    async def _send_menu(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        menu_id: str,
        query=None,
    ):
        menu_meta = self.menu_manager.get_menu_meta(menu_id)
        if not menu_meta:
            logger.warning("Unknown director menu id: %s, user_id: %s", menu_id, user_id)
            await bot_core.services.messages.send_message(
                context,
                user_id,
                "菜单未找到，返回主菜单。",
            )
            menu_id = self.menu_manager.get_main_menu_id()

        reply_markup = self.menu_manager.get_menu_keyboard(menu_id)
        description_text = self.menu_manager.get_menu_description_text(menu_id)
        try:
            if query:
                await query.edit_message_text(description_text, reply_markup=reply_markup)
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=description_text,
                    reply_markup=reply_markup,
                    parse_mode="markdown",
                )
        except BadRequest as error:
            logger.warning("Failed to edit director menu: %s, user_id: %s", error, user_id)
            await context.bot.send_message(
                chat_id=user_id,
                text=description_text,
                reply_markup=reply_markup,
                parse_mode="markdown",
            )

    async def _handle_action(
        self,
        action_data: str,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        query,
        update=None,
    ):
        conversation = PrivateConv(update, context) if update else None
        long_data = self.menu_manager.get_action_data(action_data)

        if conversation:
            if action_data == "undo":
                await conversation.undo()
            elif action_data == "regen":
                await conversation.regen()
            elif action_data.startswith("camera"):
                conversation.set_callback_data(long_data)
                await conversation.response(False)
            else:
                conversation.set_callback_data(long_data)
                await conversation.response()
        else:
            logger.warning("Unable to create conversation for director action: %s", action_data)

        try:
            await context.bot.delete_message(
                chat_id=user_id,
                message_id=query.message.message_id,
            )
        except BadRequest as error:
            logger.warning("Failed to delete director menu: %s, user_id: %s", error, user_id)
        await self._send_menu(context, user_id, self.menu_manager.get_main_menu_id())
