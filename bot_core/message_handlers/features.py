import logging
from typing import TYPE_CHECKING

from utils import db_utils as db
from utils.logging_utils import setup_logging

# Conditional imports for type checking
if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


async def private_newchar(update: "Update", newchar_state: dict, user_id: int):
    """处理用于创建新角色的文本输入。

    此函数处理角色创建工作流程中的传入文本消息。

    Args:
        update: Telegram更新对象。
        newchar_state: 用于存储新角色创建过程状态的字典，
                     包括 'char_name' 和 'desc_chunks'。
        user_id: Telegram用户的唯一标识符。
    """
    if not update.message or not update.message.text:
        return

    # 在此状态下忽略命令
    if update.message.text.startswith('/'):
        return
        
    newchar_state.setdefault("desc_chunks", []).append(update.message.text)
    await update.message.reply_text(
        "文本已接收，可继续发送，发送 /done 完成。"
    )


async def _cleanup_keyword_messages(
    context: "ContextTypes.DEFAULT_TYPE",
    chat_id: int,
    user_message_id: int,
    bot_message_id: int,
    original_message_id: int | None,
):
    """删除用户和机器人的消息并移除内联键盘。"""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e:
        logger.warning(f"Failed to delete user reply message: {e}")

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=bot_message_id)
    except Exception as e:
        logger.warning(f"Failed to delete prompt message: {e}")

    if original_message_id:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=original_message_id, reply_markup=None
            )
        except Exception as e:
            logger.warning(f"Failed to remove inline keyboard: {e}")


async def group_keyword_add(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """处理为群组添加新关键词的过程。

    当用户回复特定的机器人消息以添加关键字时，将触发此功能。
    它会验证上下文，解析新关键字，更新数据库并清理交互消息。

    Args:
        update: Telegram更新对象。
        context: 上下文对象，用于访问user_data和机器人实例。
    """
    if (
        not context.user_data
        or not update.message
        or context.user_data.get("keyword_action") != "add"
        or not update.message.reply_to_message
        or not update.message.reply_to_message.from_user
    ):
        return

    if update.message.reply_to_message.from_user.id != context.bot.id:
        await update.message.reply_text("请回复 Bot 的消息来添加关键词。")
        return

    group_id = context.user_data.get("group_id")
    if not group_id:
        logger.warning("group_keyword_add called without group_id in user_data.")
        return

    input_text = (update.message.text or "").strip()
    new_keywords = [kw.strip() for kw in input_text.split() if kw.strip()]

    if not new_keywords:
        await update.message.reply_text("未提供有效的关键词。")
        return

    current_keywords = db.group_keyword_get(group_id)
    updated_keywords = list(set(current_keywords + new_keywords))
    db.group_keyword_set(group_id, updated_keywords)

    await _cleanup_keyword_messages(
        context,
        chat_id=update.message.chat.id,
        user_message_id=update.message.message_id,
        bot_message_id=update.message.reply_to_message.message_id,
        original_message_id=context.user_data.get("original_message_id"),
    )

    await update.message.reply_text(f"已成功添加关键词：{', '.join(new_keywords)}")
    context.user_data.clear()
