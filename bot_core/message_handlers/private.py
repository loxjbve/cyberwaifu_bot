import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot_core.message_handlers.command_dispatcher import CommandDispatcher
from bot_core.plugin_system import resolve_plugin_manager
from bot_core.services.conversation import PrivateConv
from bot_core.services.utils.decorators import Decorators
from utils.logging_utils import setup_logging

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
        plugin_manager = resolve_plugin_manager(context)
        if plugin_manager and await plugin_manager.run_message_interceptors(
            update,
            context,
            "private",
        ):
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
