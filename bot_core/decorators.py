import functools
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot_core import tg, user,public
# from bot_run import BotRunError  # Assuming BotRunError is defined in bot_run.py
from bot_core.exceptions import BotRunError # Import from new exceptions file

logger = logging.getLogger(__name__)


def handle_command_errors(func):
    """Decorator to handle common errors in command handlers."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        command_name = func.__name__
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.error(f"处理 /{command_name} 命令时出错: {str(e)}", exc_info=True)
            # Optionally, send a generic error message to the user here
            # await update.message.reply_text("处理命令时发生错误，请稍后重试。")
            # Re-raising BotRunError might be handled by a global error handler
            raise BotRunError(f"处理 /{command_name} 命令失败: {str(e)}")
    return wrapper


def check_message_and_user(func):
    """Decorator to check if the message is expired and update user info."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        command_name = func.__name__
        if tg.is_message_expired(update):
            logger.warning(f"忽略过期的 /{command_name} 命令，消息ID: {update.message.message_id}")
            return None  # Stop processing if message is expired

        info = public.update_parser(update)
        if not user.info_update(info['user_id'], info['username'], info['first_name'], info['last_name']):
            # Log if user update/creation failed, though the current logic proceeds anyway
            logger.warning(f"用户 {info['user_id']} 信息更新/创建失败，但仍继续处理 /{command_name} 命令")
            # Decide if you want to stop processing if user update fails
            # return None

        # Log command processing start after checks pass
        logger.info(f"处理 /{command_name} 命令，用户名称: {info['first_name']}{info['last_name']}")

        # Proceed to the actual command logic
        return await func(update, context, *args, **kwargs)
    return wrapper