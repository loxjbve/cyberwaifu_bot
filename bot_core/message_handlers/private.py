import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot_core.message_handlers.command_dispatcher import CommandDispatcher
from bot_core.services.conversation import PrivateConv
from bot_core.services.utils.decorators import Decorators
from utils.logging_utils import setup_logging

from . import features

setup_logging()
logger = logging.getLogger(__name__)


@Decorators.ensure_user_info_updated
async def private_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user:
        return

    user_id = update.message.from_user.id
    message_text = update.message.text or ""

    if message_text.startswith("/") and await CommandDispatcher.dispatch(
        update,
        context,
        "private",
    ):
        return

    try:
        newchar_state = context.bot_data.get("newchar_state", {}).get(user_id)
        if newchar_state:
            logger.info("Processing new character flow for user %s", user_id)
            await features.private_newchar(update, newchar_state, user_id)
            return

        if update.message.photo or update.message.sticker or update.message.animation:
            logger.info("Processing media message for user %s", user_id)
            await features.f_or_not(update, context)
            return

        userconv = PrivateConv(update, context)
        await userconv.response()
    except Exception as error:
        logger.error(
            "Failed to process private message for user %s: %s",
            user_id,
            error,
            exc_info=True,
        )
