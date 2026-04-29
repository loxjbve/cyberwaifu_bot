import logging
import random
from typing import Union

from telegram import Update
from telegram.ext import ContextTypes

from bot_core.message_handlers.command_dispatcher import CommandDispatcher
from bot_core.plugin_system import resolve_plugin_manager
from bot_core.services.conversation import GroupConv
from bot_core.services.utils.decorators import Decorators
from bot_core.services.utils.error import BotError
from bot_core.services.utils.tg_parse import update_info_get
from utils import db_utils as db

logger = logging.getLogger(__name__)


@Decorators.ensure_group_info_updated
@Decorators.check_message_expiration
async def group_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user:
        return

    user_id = update.message.from_user.id
    message_text = update.message.text or ""

    if message_text.startswith("/"):
        info = update_info_get(update)
        _group_dialog_add(info)
        if await CommandDispatcher.dispatch(update, context, "group"):
            return

    try:
        plugin_manager = resolve_plugin_manager(context)
        if plugin_manager and await plugin_manager.run_message_interceptors(
            update,
            context,
            "group",
        ):
            return
        await group_reply(update, context)
    except Exception as error:
        logger.error(
            "Failed to process group message for user %s in group %s: %s",
            user_id,
            update.message.chat.id,
            error,
            exc_info=True,
        )

async def group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    info = update_info_get(update)
    _group_dialog_add(info)

    if not _check_topic_permission(update):
        return

    trigger = _group_msg_need_reply(update, context)
    if not trigger:
        return

    conversation = GroupConv(update, context)
    conversation.set_trigger(trigger)
    await conversation.response()


def _group_dialog_add(info) -> bool:
    try:
        return db.group_dialog_initial_add(
            group_id=info["group_id"],
            msg_user_id=info["user_id"],
            msg_user_name=info["user_name"],
            msg_text=info["message_text"],
            msg_id=info["message_id"],
            group_name=info["group_name"],
        )
    except Exception as error:
        logger.error(
            "Failed to append group dialog for group %s message %s: %s",
            info.get("group_id"),
            info.get("message_id"),
            error,
            exc_info=True,
        )
        return False


def _group_msg_need_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> Union[str, bool]:
    if not update.message:
        return False

    message = update.message
    bot_username = context.bot.username
    info = update_info_get(update)
    if not info:
        return False

    message_text = message.text or message.caption or ""
    group_id = info["group_id"]
    group_name = info["group_name"]
    user_name = info["user_name"]
    keyword_list = db.group_keyword_get(group_id)
    rate = db.group_rate_get(group_id) or 0.05

    try:
        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == context.bot.id:
                logger.info("Triggered by reply in %s from %s", group_name, user_name)
                return "reply"

        if message_text:
            if f"@{bot_username}" in message_text:
                logger.info("Triggered by mention in %s from %s", group_name, user_name)
                return "@"

            if keyword_list and any(keyword in message_text for keyword in keyword_list):
                logger.info("Triggered by keyword in %s from %s", group_name, user_name)
                return "keyword"

            if random.random() < rate:
                logger.info("Triggered by random rate in %s from %s", group_name, user_name)
                return "random"

        return False
    except Exception as error:
        logger.error(
            "Failed to evaluate group reply trigger for group %s: %s",
            group_id,
            error,
        )
        raise BotError(f"Failed to evaluate group reply trigger: {error}")


def _check_topic_permission(update: Update) -> bool:
    if not update.message:
        return False

    try:
        message = update.message
        group_id = message.chat.id
        disabled_topics = db.group_disabled_topics_get(group_id)

        if getattr(message, "message_thread_id", None):
            return str(message.message_thread_id) not in disabled_topics
        return "main" not in disabled_topics
    except Exception as error:
        logger.error("Failed to evaluate topic permission: %s", error)
        return True
